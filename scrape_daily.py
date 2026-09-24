#!/usr/bin/env python3
"""
Automated Daily Floorsheet Scraper for NEPSE.
Saves all trades of the current date into Floorsheet/<YYYY-MM-DD>.csv.

Guards:
  1. businessDate validation — API returns previous day data on holidays;
     we compare the date embedded in returned records against today (NPT).
  2. Duplicate file guard — if today's CSV already exists, skip entirely.
  3. Weekend skip — NEPSE trades Monday–Friday; Saturday & Sunday are off.
"""

import glob
import os
import sys
import time
from datetime import datetime
import pytz
import pandas as pd

from nepse_client import NepseClient


def get_nepal_now() -> datetime:
    """Returns the current datetime in Nepal Standard Time (UTC+5:45)."""
    tz = pytz.timezone("Asia/Kathmandu")
    return datetime.now(tz)


def get_nepal_date_str() -> str:
    """Returns today's date formatted as YYYY-MM-DD in Nepal Standard Time."""
    return get_nepal_now().strftime("%Y-%m-%d")


def is_trading_day() -> bool:
    """
    Returns True if today is a NEPSE trading day (Monday–Friday, NPT).
    NEPSE recently shifted from Sun–Thu to Mon–Fri.
    weekday(): 0=Monday … 4=Friday, 5=Saturday, 6=Sunday
    """
    return get_nepal_now().weekday() < 5   # 0–4 → Mon–Fri


def main():
    date_str = get_nepal_date_str()
    print(f"==================================================")
    print(f"🚀 NEPSE Daily Floorsheet Automated Scraper")
    print(f"📅 Target Trading Date (NPT): {date_str}")
    print(f"==================================================")

    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Floorsheet")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{date_str}.csv")

    # ── Guard 1: Weekend check (NEPSE: Monday–Friday) ───────────────────────
    if not is_trading_day():
        day_name = get_nepal_now().strftime("%A")
        print(f"📅 Today is {day_name} — NEPSE is closed on weekends (Sat & Sun).")
        print("Exiting gracefully. No data to fetch.")
        return

    # ── Guard 2: Duplicate file guard ────────────────────────────────────────
    if os.path.exists(output_file):
        file_size_kb = os.path.getsize(output_file) / 1024
        print(f"⚠️  Today's floorsheet already exists: {output_file} ({file_size_kb:.1f} KB)")
        print("Skipping to avoid overwriting existing data.")
        return

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
        print("⚠️ No trading transactions found for today (Public Holiday or Off-Market).")
        print("Exiting gracefully without creating empty file.")
        return

    # ── Guard 3: businessDate validation ─────────────────────────────────────
    # NEPSE returns previous day data when market is closed (public holiday).
    # We verify the date inside the actual records matches today (NPT).
    sample_records = floorsheets_info.get("content", [])
    if sample_records:
        api_date = sample_records[0].get("businessDate", "")
        # Normalise: API may return full datetime string "2026-09-24T..." or plain date
        api_date_short = api_date[:10] if api_date else ""
        if api_date_short and api_date_short != date_str:
            print(f"🚨 businessDate mismatch detected!")
            print(f"   Today (NPT)  : {date_str}")
            print(f"   API returned : {api_date_short}  ← previous trading day's data")
            print("Market was closed today (Public Holiday). Skipping save to prevent stale data.")
            return

    # ── Also cross-check: has this date's CSV already been saved? ─────────────
    # Catches edge-case where api_date_short == date_str but we ran twice.
    existing_files = sorted(glob.glob(os.path.join(output_dir, "*.csv")))
    if existing_files:
        last_saved_date = os.path.basename(existing_files[-1]).replace(".csv", "")
        if api_date_short and api_date_short == last_saved_date:
            print(f"⚠️  Data for {api_date_short} is already saved as the most recent CSV.")
            print("Skipping to prevent duplicate archiving.")
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
