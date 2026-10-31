#!/usr/bin/env python3
"""summaryBackfill.py — generate `Summary/` files for Floorsheet days missing one.

Every Floorsheet day that lacks a Summary file gets both, using the exact
same logic as the daily job:

    Floorsheet/YYYY-MM-DD.csv  ->  Summary/YYYY-MM-DD_brokers.csv
                                   Summary/YYYY-MM-DD_broker_totals.csv

Reuses DailySummary.py, so output is identical to the daily workflow.
Stdlib only: no pandas, no installs, no network access.

Examples:
    python3 summaryBackfill.py --dry-run
    python3 summaryBackfill.py
    python3 summaryBackfill.py --limit 50
    python3 summaryBackfill.py --start 2025-01-01 --end 2025-06-30
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import DailySummary as D

BASE_DIR = Path(__file__).resolve().parent
FLOORSHEET_DIR = BASE_DIR / "Floorsheet"
SUMMARY_DIR = BASE_DIR / "Summary"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill Summary/ files for Floorsheet days missing one."
    )
    parser.add_argument(
        "--start",
        help="Only process dates >= this (YYYY-MM-DD). Default: first Floorsheet.",
    )
    parser.add_argument(
        "--end",
        help="Only process dates <= this (YYYY-MM-DD). Default: last Floorsheet.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N days per run (0 = all missing).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List missing dates and exit without writing anything.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with a non-zero status if any day failed to process.",
    )
    return parser.parse_args(argv)


def parse_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise SystemExit(f"error: invalid date {value!r}, expected YYYY-MM-DD")


def missing_dates(start: str | None, end: str | None) -> list[str]:
    """Floorsheet dates that are missing at least one Summary file."""
    missing: list[str] = []
    paths = sorted(FLOORSHEET_DIR.glob("????-??-??.csv"))
    if not paths:
        raise SystemExit(f"error: no Floorsheet files found in {FLOORSHEET_DIR}")
    for path in paths:
        date = path.stem
        if start and date < start:
            continue
        if end and date > end:
            continue
        if (
            (SUMMARY_DIR / f"{date}_brokers.csv").is_file()
            and (SUMMARY_DIR / f"{date}_broker_totals.csv").is_file()
        ):
            continue
        missing.append(date)
    return missing


def process_date(date: str) -> tuple[str, list[tuple[str, int]], dict]:
    """Generate both Summary files for one date, skipping files that exist."""
    buy, sell, raw_names, stats, _symbols = D.read_floorsheet(
        FLOORSHEET_DIR / f"{date}.csv", date
    )
    names = D.broker_names(raw_names)
    data_date = stats["date"]
    detail_rows = D.build_detail_rows(buy, sell, names, data_date)
    total_rows = D.build_total_rows(buy, sell, names, data_date)

    written: list[tuple[str, int]] = []
    for target, fields, rows in (
        (SUMMARY_DIR / f"{data_date}_brokers.csv", D.DETAIL_FIELDS, detail_rows),
        (
            SUMMARY_DIR / f"{data_date}_broker_totals.csv",
            D.TOTAL_FIELDS,
            total_rows,
        ),
    ):
        if target.is_file():
            continue
        D.write_csv(target, fields, rows)
        written.append((target.name, len(rows)))
    return data_date, written, stats


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    start = parse_date(args.start) if args.start else None
    end = parse_date(args.end) if args.end else None

    missing = missing_dates(start, end)
    print(f"Floorsheet days missing Summary files: {len(missing):,}")
    if not missing:
        return 0
    if len(missing) <= 5 or args.dry_run:
        print("missing:", ", ".join(missing))
    else:
        print(f"missing: {missing[0]} .. {missing[-1]}")

    if args.dry_run:
        return 0
    if args.limit > 0:
        missing = missing[: args.limit]
        print(f"limiting this run to {len(missing):,} day(s)")

    processed = 0
    failures: list[str] = []
    for i, date in enumerate(missing, 1):
        try:
            data_date, written, stats = process_date(date)
            processed += 1
            print(
                f"[{i}/{len(missing)}] {data_date}: "
                f"{stats['accepted']:,} contracts | {stats['turnover']:,.2f} NPR | "
                f"+{len(written)} file(s)",
                flush=True,
            )
            if written and stats["duplicate_ids"]:
                print(
                    f"    warning: skipped {stats['duplicate_ids']:,} duplicate contractId row(s)",
                    flush=True,
                )
        except (D.DataError, OSError) as exc:
            failures.append(date)
            print(f"[{i}/{len(missing)}] {date}: ERROR {exc}", file=sys.stderr, flush=True)

    print(f"done: {processed:,} day(s) processed, {len(failures)} failure(s)")
    if failures:
        print("failed dates (rerun to retry): " + ", ".join(failures), file=sys.stderr)
    if args.strict and failures:
        print("strict mode: exiting non-zero due to failed day(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
