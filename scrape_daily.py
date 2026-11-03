#!/usr/bin/env python3
"""
Automated Daily Floorsheet Scraper for NEPSE.
Saves all trades into Floorsheet/<YYYY-MM-DD>.csv based on the actual
businessDate returned by the NEPSE API.

Guards:
  1. Empty payload guard — skips if totalElements == 0 (off-market / holiday).
  2. Duplicate / Holiday guard — if the businessDate returned by the API is
     already archived in Floorsheet/<date>.csv, skips gracefully to avoid
     overwriting existing data or duplicating past data on public holidays.
  3. Desynchronization guard — if a scheduled run is delayed overnight past
     midnight NPT, correctly archives under the API's businessDate instead of
     discarding valid data.
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
    NEPSE shifted from Sun–Thu to Mon–Fri.
    weekday(): 0=Monday … 4=Friday, 5=Saturday, 6=Sunday
    """
    return get_nepal_now().weekday() < 5   # 0–4 → Mon–Fri


def set_github_output(name: str, value: str):
    """Sets a step output variable for GitHub Actions if running in CI."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path and os.path.exists(output_path):
        try:
            with open(output_path, "a") as f:
                f.write(f"{name}={value}\n")
        except Exception as e:
            print(f"⚠️ Warning: Could not write to GITHUB_OUTPUT: {e}", file=sys.stderr)


def main():
    now_npt = get_nepal_now()
    today_str = now_npt.strftime("%Y-%m-%d")
    print("==================================================")
    print("🚀 NEPSE Daily Floorsheet Automated Scraper")
    print(f"📅 Current NPT Timestamp : {now_npt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"📅 Local Calendar Date   : {today_str} ({now_npt.strftime('%A')})")
    print("==================================================")

    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Floorsheet")
    os.makedirs(output_dir, exist_ok=True)

    client = NepseClient()

    # 1. Authenticate
    try:
        token = client.authenticate()
        payload_id = client.get_floorsheet_payload_id()
        print(f"✅ Authentication successful! Dynamic Payload ID: {payload_id}")
    except Exception as e:
        print(f"❌ Failed to authenticate with NEPSE API: {e}", file=sys.stderr)
        set_github_output("scraped_date", "")
        sys.exit(1)

    # 2. Probe first page to inspect total elements and actual businessDate
    print("📊 Probing market data...")
    try:
        first_page = client.get_floorsheet_page(page=0, size=500, sort_by="contractId", sort_order="desc")
    except Exception as e:
        print(f"❌ Error fetching initial floorsheet probe: {e}", file=sys.stderr)
        set_github_output("scraped_date", "")
        sys.exit(1)

    floorsheets_info = first_page.get("floorsheets", {})
    total_elements = floorsheets_info.get("totalElements", 0)
    total_pages = floorsheets_info.get("totalPages", 0)

    print(f"📈 Total transactions reported by NEPSE: {total_elements:,} across {total_pages:,} pages.")

    if total_elements == 0:
        print("⚠️ No trading transactions found (Public Holiday, Weekend, or Off-Market).")
        print("Exiting gracefully without creating empty file.")
        set_github_output("scraped_date", "")
        return

    # ── Guard: Extract and validate actual businessDate from API ─────────────
    sample_records = floorsheets_info.get("content", [])
    if not sample_records:
        print("⚠️ Content list is empty despite totalElements > 0. Exiting.")
        set_github_output("scraped_date", "")
        return

    api_business_date = sample_records[0].get("businessDate", "")
    target_date = api_business_date[:10] if api_business_date else ""

    if not target_date:
        print("⚠️ Could not extract valid businessDate from records. Exiting.")
        set_github_output("scraped_date", "")
        return

    print(f"🎯 Target Business Date from API: {target_date}")
    output_file = os.path.join(output_dir, f"{target_date}.csv")

    # ── Guard: Duplicate / Holiday Stale Data Check ──────────────────────────
    # If this date's CSV already exists:
    # 1. Either today was already scraped earlier, OR
    # 2. Today is a public holiday/weekend/pre-market and NEPSE is returning the
    #    previous trading day's data (which is already saved in Floorsheet/).
    if os.path.exists(output_file):
        file_size_kb = os.path.getsize(output_file) / 1024
        print(f"ℹ️ Floorsheet for {target_date} is already archived: {output_file} ({file_size_kb:.1f} KB)")
        if target_date != today_str:
            print(f"   (Local date is {today_str}; API returned already-archived {target_date} → Public Holiday / Off-Hours).")
        print("Skipping extraction to prevent duplicate archiving.")
        set_github_output("scraped_date", "")
        return

    # If target_date != today_str, but the file does NOT exist:
    # This happens when a scheduled run is delayed overnight past midnight,
    # or a previous trading day's run was missed.
    if target_date != today_str:
        print(f"🔔 Note: API returned unarchived data for {target_date} while local date is {today_str}.")
        print(f"   Proceeding to archive missing data for {target_date}...")

    # 3. Scrape all pages
    def progress_callback(current, total, count, total_records):
        pct = (count / total_records * 100) if total_records else 0
        print(f"📥 Page {current}/{total} | Scraped: {count:,}/{total_records:,} records ({pct:.1f}%)")

    print(f"📥 Commencing full extraction of {total_elements:,} transactions for {target_date}...")
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
        set_github_output("scraped_date", "")
        sys.exit(1)

    # 4. Convert and Save
    df = pd.DataFrame(all_records)
    df.to_csv(output_file, index=False)

    file_size_mb = os.path.getsize(output_file) / (1024 * 1024)

    print("\n==================================================")
    print("🎉 Successfully completed floorsheet extraction!")
    print(f"📁 Destination: {output_file}")
    print(f"📝 Total Rows Saved: {len(df):,}")
    print(f"💾 File Size: {file_size_mb:.2f} MB")
    if "contractAmount" in df.columns:
        total_turnover = df["contractAmount"].sum()
        print(f"💰 Total Turnover Recorded: NPR {total_turnover:,.2f}")
    print("==================================================")

    # Inform downstream workflow steps of the exact date that was scraped
    set_github_output("scraped_date", target_date)


if __name__ == "__main__":
    main()
