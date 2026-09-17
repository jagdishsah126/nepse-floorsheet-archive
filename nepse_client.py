"""
NEPSE Client for scraping Floorsheet and market data.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Union
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd

try:
    from .nepse_auth import parse_access_token, calculate_floorsheet_payload_id
except (ImportError, ValueError):
    from nepse_auth import parse_access_token, calculate_floorsheet_payload_id

logger = logging.getLogger(__name__)


class NepseClient:
    BASE_URL = "https://nepalstock.com.np"

    def __init__(self, timeout: int = 15, max_retries: int = 3):
        self.timeout = timeout
        self.session = requests.Session()

        # Configure connection retries
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": f"{self.BASE_URL}/floor-sheet",
            "Origin": self.BASE_URL,
        })

        self.prove_data: Optional[Dict[str, Any]] = None
        self.access_token: Optional[str] = None
        self.market_open_id: Optional[int] = None
        self._company_map: Optional[Dict[str, int]] = None

    def authenticate(self, force_refresh: bool = False) -> str:
        """
        Authenticate with NEPSE by calling /api/authenticate/prove and /api/nots/nepse-data/market-open.
        """
        if self.access_token and not force_refresh:
            return self.access_token

        logger.info("Authenticating with NEPSE...")
        prove_url = f"{self.BASE_URL}/api/authenticate/prove"
        resp = self.session.get(prove_url, timeout=self.timeout)
        resp.raise_for_status()
        self.prove_data = resp.json()

        self.access_token = parse_access_token(self.prove_data)
        self.session.headers["Authorization"] = f"Salter {self.access_token}"

        # Fetch market open info to retrieve dummyId
        market_open_url = f"{self.BASE_URL}/api/nots/nepse-data/market-open"
        m_resp = self.session.get(market_open_url, timeout=self.timeout)
        m_resp.raise_for_status()
        m_data = m_resp.json()
        self.market_open_id = int(m_data["id"])

        logger.info(f"Authenticated successfully. Market Open ID: {self.market_open_id}")
        return self.access_token

    def get_floorsheet_payload_id(self) -> int:
        """Compute the dynamic payload ID for the POST body."""
        self.authenticate()
        return calculate_floorsheet_payload_id(self.market_open_id, self.prove_data)

    def get_company_map(self, force_refresh: bool = False) -> Dict[str, int]:
        """
        Fetches all securities and maps Symbol -> Stock ID (e.g. 'UAIL' -> 180).
        """
        if self._company_map and not force_refresh:
            return self._company_map

        self.authenticate()
        url = f"{self.BASE_URL}/api/nots/security?nonDelisted=true"
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        companies = resp.json()

        self._company_map = {item["symbol"].upper(): item["id"] for item in companies if "symbol" in item and "id" in item}
        return self._company_map

    def resolve_symbol_to_id(self, symbol: str) -> Optional[int]:
        """Resolve a ticker symbol to its numeric stock ID."""
        comp_map = self.get_company_map()
        return comp_map.get(symbol.upper())

    def get_floorsheet_page(
        self,
        page: Optional[int] = None,
        size: int = 500,
        sort_by: str = "contractId",
        sort_order: str = "desc",
        symbol: Optional[str] = None,
        stock_id: Optional[int] = None,
        buyer_broker: Optional[Union[str, int]] = None,
        seller_broker: Optional[Union[str, int]] = None,
        contract_no: Optional[Union[str, int]] = None,
    ) -> Dict[str, Any]:
        """
        Fetch a single page of floorsheet data.
        page: 0-indexed page number (0 is the first page)
        """
        self.authenticate()

        # Resolve symbol to stock_id if symbol is specified
        if symbol and not stock_id:
            resolved = self.resolve_symbol_to_id(symbol)
            if not resolved:
                raise ValueError(f"Symbol '{symbol}' not found in active NEPSE securities.")
            stock_id = resolved

        # Construct query parameters matching NEPSE frontend
        query_params = []
        if page is not None:
            query_params.append(f"page={page}")
        query_params.append(f"size={size}")
        if stock_id:
            query_params.append(f"stockId={stock_id}")
        if contract_no:
            query_params.append(f"contractNo={contract_no}")
        if buyer_broker:
            query_params.append(f"buyerBroker={buyer_broker}")
        if seller_broker:
            query_params.append(f"sellerBroker={seller_broker}")
        query_params.append(f"sort={sort_by},{sort_order}")

        query_string = "&".join(query_params)
        url = f"{self.BASE_URL}/api/nots/nepse-data/floorsheet?{query_string}"

        payload_id = self.get_floorsheet_payload_id()
        payload = {"id": payload_id}

        headers = {"Content-Type": "application/json"}
        resp = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)

        # Check for expired token or unauthorized access
        if "UNAUTHORIZED" in resp.text or resp.status_code == 401:
            logger.warning("Token expired or unauthorized. Re-authenticating...")
            self.authenticate(force_refresh=True)
            payload_id = self.get_floorsheet_payload_id()
            resp = self.session.post(url, json={"id": payload_id}, headers=headers, timeout=self.timeout)

        resp.raise_for_status()
        return resp.json()

    def scrape_all_floorsheet(
        self,
        size: int = 500,
        max_pages: Optional[int] = None,
        sort_by: str = "contractId",
        sort_order: str = "desc",
        symbol: Optional[str] = None,
        buyer_broker: Optional[Union[str, int]] = None,
        seller_broker: Optional[Union[str, int]] = None,
        delay: float = 0.3,
        progress_callback: Optional[callable] = None,
    ) -> List[Dict[str, Any]]:
        """
        Scrape all pages of floorsheet data.
        """
        first_page = self.get_floorsheet_page(
            page=0,
            size=size,
            sort_by=sort_by,
            sort_order=sort_order,
            symbol=symbol,
            buyer_broker=buyer_broker,
            seller_broker=seller_broker,
        )

        floorsheets_info = first_page.get("floorsheets", {})
        total_pages = floorsheets_info.get("totalPages", 1)
        total_elements = floorsheets_info.get("totalElements", 0)

        all_records = list(floorsheets_info.get("content", []))

        if progress_callback:
            progress_callback(1, total_pages, len(all_records), total_elements)

        pages_to_fetch = min(total_pages, max_pages) if max_pages else total_pages

        for page in range(1, pages_to_fetch):
            time.sleep(delay)
            page_data = self.get_floorsheet_page(
                page=page,
                size=size,
                sort_by=sort_by,
                sort_order=sort_order,
                symbol=symbol,
                buyer_broker=buyer_broker,
                seller_broker=seller_broker,
            )
            records = page_data.get("floorsheets", {}).get("content", [])
            if not records:
                break
            all_records.extend(records)

            if progress_callback:
                progress_callback(page + 1, pages_to_fetch, len(all_records), total_elements)

        return all_records

    def generate_curl_command(
        self,
        page: Optional[int] = None,
        size: int = 500,
        sort_by: str = "contractId",
        sort_order: str = "desc",
        symbol: Optional[str] = None,
        buyer_broker: Optional[Union[str, int]] = None,
        seller_broker: Optional[Union[str, int]] = None,
    ) -> str:
        """
        Generates the exact curl command with fresh Salter token and payload ID.
        """
        self.authenticate()
        stock_id = self.resolve_symbol_to_id(symbol) if symbol else None

        query_params = []
        if page is not None:
            query_params.append(f"page={page}")
        query_params.append(f"size={size}")
        if stock_id:
            query_params.append(f"stockId={stock_id}")
        if buyer_broker:
            query_params.append(f"buyerBroker={buyer_broker}")
        if seller_broker:
            query_params.append(f"sellerBroker={seller_broker}")
        query_params.append(f"sort={sort_by},{sort_order}")

        query_string = "&".join(query_params)
        url = f"{self.BASE_URL}/api/nots/nepse-data/floorsheet?{query_string}"
        payload_id = self.get_floorsheet_payload_id()

        curl_cmd = f"""curl --url '{url}' \\
  -H 'accept: application/json, text/plain, */*' \\
  -H 'accept-language: en-US,en;q=0.5' \\
  -H 'authorization: Salter {self.access_token}' \\
  -H 'content-type: application/json' \\
  -H 'origin: https://nepalstock.com.np' \\
  -H 'referer: https://nepalstock.com.np/floor-sheet' \\
  -H 'user-agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36' \\
  --data-raw '{{"id":{payload_id}}}'"""
        return curl_cmd

    @staticmethod
    def to_dataframe(records: List[Dict[str, Any]]) -> pd.DataFrame:
        """Convert scraped records to pandas DataFrame."""
        return pd.DataFrame(records)
