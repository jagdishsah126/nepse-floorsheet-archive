#!/usr/bin/env python3
"""
recover_floorsheet.py — Recovers missing historical daily floorsheet data
via Chukul's historical archive API and enriches it with official NEPSE metadata.

Output:
    Floorsheet/<date>.csv
    Then invokes DailySummary.py to produce:
    Summary/<date>_brokers.csv
    Summary/<date>_broker_totals.csv
"""

import argparse
import os
import sys
import time
import requests
import pandas as pd

from nepse_client import NepseClient


def get_nepse_metadata(client: NepseClient):
    """Fetches official broker and security mappings from NEPSE API."""
    print("📋 Fetching official broker and security metadata from NEPSE...")
    client.authenticate()

    # 1. Fetch brokers
    broker_map = {}
    try:
        m_resp = client.session.get(
            f"{client.BASE_URL}/api/nots/member?nonDelisted=true&size=500",
            timeout=15,
        )
        if m_resp.status_code == 200:
            for m in m_resp.json().get("content", []):
                code = str(m.get("memberCode"))
                name = m.get("memberName")
                if code and name:
                    broker_map[code] = name
            print(f"   ✓ Loaded {len(broker_map)} official broker mappings.")
    except Exception as e:
        print(f"   ⚠️ Warning: Failed to fetch brokers from NEPSE: {e}")

    # 2. Fetch securities
    sec_map = {}
    try:
        s_resp = client.session.get(
            f"{client.BASE_URL}/api/nots/security?nonDelisted=true",
            timeout=15,
        )
        if s_resp.status_code == 200:
            for s in s_resp.json():
                sym = s.get("symbol")
                if sym:
                    sec_map[sym] = (s.get("id"), s.get("securityName"))
            print(f"   ✓ Loaded {len(sec_map)} official securities.")
    except Exception as e:
        print(f"   ⚠️ Warning: Failed to fetch securities from NEPSE: {e}")

    return broker_map, sec_map


def fetch_chukul_floorsheet(date_str: str):
    """Paginates Chukul's historical floorsheet API to extract all transactions."""
    base_url = "https://chukul.com/api/data/v2/floorsheet/bydate/"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }

    current_page = 1
    total_pages = 1
    all_rows = []

    print(f"📡 Querying historical floorsheet archive for date: {date_str}...")

    session = requests.Session()

    while current_page <= total_pages:
        params = {
            "date": date_str,
            "page": current_page,
            "size": 500,
        }

        retries = 3
        while retries > 0:
            try:
                resp = session.get(base_url, params=params, headers=headers, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    page_items = data.get("data", [])
                    total_pages = data.get("last_page", 1)
                    all_rows.extend(page_items)
                    pct = (current_page / total_pages * 100) if total_pages else 0
                    print(
                        f"   📥 Page {current_page}/{total_pages} ({pct:.1f}%) | "
                        f"Fetched {len(page_items)} rows | Total: {len(all_rows):,}",
                        end="\r",
                    )
                    break
                else:
                    print(f"\n   ⚠️ Page {current_page} returned HTTP {resp.status_code}. Retrying...")
                    time.sleep(2)
                    retries -= 1
            except Exception as e:
                print(f"\n   ⚠️ Page {current_page} failed: {e}. Retrying...")
                time.sleep(2)
                retries -= 1

        if retries == 0:
            print(f"\n❌ Aborted fetching page {current_page} after 3 retries.")
            return None

        current_page += 1
        time.sleep(0.3)

    print(f"\n✅ Successfully extracted {len(all_rows):,} total transactions for {date_str}.")
    return all_rows


def build_and_save_floorsheet(date_str: str, raw_records: list, broker_map: dict, sec_map: dict):
    """Transforms raw records into the official floorsheet CSV format."""
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Floorsheet")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{date_str}.csv")

    rows = []
    for r in raw_records:
        sym = r.get("symbol", "").strip()
        sec_info = sec_map.get(sym, (None, ""))
        stock_id = sec_info[0] if sec_info else None
        sec_name = sec_info[1] if sec_info else ""

        buyer_id = str(r.get("buyer", "")).strip()
        seller_id = str(r.get("seller", "")).strip()

        buyer_name = broker_map.get(buyer_id, f"Broker {buyer_id}")
        seller_name = broker_map.get(seller_id, f"Broker {seller_id}")

        qty = int(r.get("quantity", 0)) if r.get("quantity") is not None else 0
        rate = float(r.get("rate", 0.0)) if r.get("rate") is not None else 0.0
        amount = float(r.get("amount", 0.0)) if r.get("amount") is not None else 0.0

        rows.append({
            "contractId": str(r.get("transaction", "")),
            "stockSymbol": sym,
            "buyerMemberId": buyer_id,
            "sellerMemberId": seller_id,
            "contractQuantity": qty,
            "contractRate": rate,
            "contractAmount": amount,
            "businessDate": date_str,
            "tradeBookId": "",
            "stockId": stock_id if stock_id is not None else "",
            "buyerBrokerName": buyer_name,
            "sellerBrokerName": seller_name,
            "tradeTime": "",
            "securityName": sec_name,
        })

    df = pd.DataFrame(rows)
    # Sort descending by contractId to match NEPSE default ordering
    df["contractId_numeric"] = pd.to_numeric(df["contractId"], errors="coerce")
    df = df.sort_values("contractId_numeric", ascending=False).drop(columns=["contractId_numeric"])

    df.to_csv(output_file, index=False)
    size_mb = os.path.getsize(output_file) / (1024 * 1024)
    print(f"🎉 Saved Floorsheet/{date_str}.csv: {len(df):,} rows ({size_mb:.2f} MB)")
    return output_file


def main():
    parser = argparse.ArgumentParser(description="Recover missing NEPSE floorsheet data by date.")
    parser.add_argument("--date", default="2026-11-02", help="Date to recover (YYYY-MM-DD)")
    args = parser.parse_args()

    date_str = args.date
    print(f"==================================================")
    print(f"🛠️ NEPSE Floorsheet Historical Recovery Tool")
    print(f"📅 Target Date: {date_str}")
    print(f"==================================================")

    # 1. Fetch metadata mappings from NEPSE
    client = NepseClient()
    broker_map, sec_map = get_nepse_metadata(client)

    # 2. Extract historical rows
    raw_records = fetch_chukul_floorsheet(date_str)
    if not raw_records:
        print("❌ Recovery aborted: no records retrieved.", file=sys.stderr)
        sys.exit(1)

    # 3. Transform and save Floorsheet CSV
    output_file = build_and_save_floorsheet(date_str, raw_records, broker_map, sec_map)

    # 4. Generate Broker Summary
    summary_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DailySummary.py")
    if os.path.exists(summary_script):
        print(f"\n📊 Generating broker summary for {date_str}...")
        res = os.system(f"python3 {summary_script} --date {date_str}")
        if res == 0:
            print("✅ Broker summary generated successfully.")
        else:
            print(f"⚠️ Warning: DailySummary.py exited with code {res}")

    print("\n🏁 Recovery process completed successfully!")


if __name__ == "__main__":
    main()
