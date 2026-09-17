#!/usr/bin/env python3
"""
Automated Daily Floorsheet Scraper for NEPSE.
Saves all trades of the current date into Floorsheet/<YYYY-MM-DD>.csv.
"""

import os
import sys
import time
from datetime import datetime
import pytz
import pandas as pd

from nepse_client import NepseClient


def get_nepal_date_str() -> str:
    """Returns today's date formatted as YYYY-MM-DD in Nepal Standard Time."""
    tz = pytz.timezone("Asia/Kathmandu")
    return datetime.now(tz).strftime("%Y-%m-%d")


def main():
    date_str = get_nepal_date_str()
    print(f"==================================================")
    print(f"🚀 NEPSE Daily Floorsheet Automated Scraper")
    print(f"📅 Target Trading Date (NPT): {date_str}")
    print(f"==================================================")

    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Floorsheet")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{date_str}.csv")

    client = NepseClient()

    # 1. Authenticate
    try:
        token = client.authenticate()
        payload_id = client.get_floorsheet_payload_id()
        print(f"✅ Authentication successful! Dynamic Payload ID: {payload_id}")
    except Exception as e:
        print(f"❌ Failed to authenticate with NEPSE API: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Fetch first page to inspect total elements
    print("📊 Probing market data...")
    try:
        first_page = client.get_floorsheet_page(page=0, size=500, sort_by="contractId", sort_order="desc")
    except Exception as e:
        print(f"❌ Error fetching initial floorsheet probe: {e}", file=sys.stderr)
        sys.exit(1)

    floorsheets_info = first_page.get("floorsheets", {})
    total_elements = floorsheets_info.get("totalElements", 0)
    total_pages = floorsheets_info.get("totalPages", 0)

    print(f"📈 Total transactions reported by NEPSE: {total_elements:,} across {total_pages:,} pages.")

    if total_elements == 0:
        print("⚠️ No trading transactions found for today (Public Holiday, Weekend, or Off-Market).")
        print("Exiting gracefully without creating empty file.")
        return

    # 3. Scrape all pages
    def progress_callback(current, total, count, total_records):
        pct = (count / total_records * 100) if total_records else 0
        print(f"📥 Page {current}/{total} | Scraped: {count:,}/{total_records:,} records ({pct:.1f}%)")

    print(f"📥 Commencing full extraction of {total_elements:,} transactions...")
    all_records = client.scrape_all_floorsheet(
        size=500,
        max_pages=None,
        sort_by="contractId",
        sort_order="desc",
        delay=0.3,
        progress_callback=progress_callback
    )

    if not all_records:
        print("❌ No records could be extracted.", file=sys.stderr)
        sys.exit(1)

    # 4. Convert and Save
    df = pd.DataFrame(all_records)
    df.to_csv(output_file, index=False)

    file_size_mb = os.path.getsize(output_file) / (1024 * 1024)

    print(f"\n==================================================")
    print(f"🎉 Successfully completed floorsheet extraction!")
    print(f"📁 Destination: {output_file}")
    print(f"📝 Total Rows Saved: {len(df):,}")
    print(f"💾 File Size: {file_size_mb:.2f} MB")
    if "contractAmount" in df.columns:
        total_turnover = df["contractAmount"].sum()
        print(f"💰 Total Turnover Recorded: NPR {total_turnover:,.2f}")
    print(f"==================================================")


if __name__ == "__main__":
    main()
