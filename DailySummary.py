#!/usr/bin/env python3
"""DailySummary.py — per-broker NEPSE summaries from a daily floorsheet.

Reads  Floorsheet/YYYY-MM-DD.csv  and writes:
    Summary/YYYY-MM-DD_brokers.csv        one row per broker per scrip
    Summary/YYYY-MM-DD_broker_totals.csv  one row per broker

Stdlib only: no pandas, no installs, no network access.

Examples:
    python3 DailySummary.py
    python3 DailySummary.py --date 2026-10-27
    python3 DailySummary.py --file 2026-10-27.csv
    python3 DailySummary.py --broker 58
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
FLOORSHEET_DIR = BASE_DIR / "Floorsheet"
SUMMARY_DIR = BASE_DIR / "Summary"
NEPAL_TZ = ZoneInfo("Asia/Kathmandu")

REQUIRED_COLUMNS = {
    "contractId",
    "stockSymbol",
    "buyerMemberId",
    "sellerMemberId",
    "contractQuantity",
    "contractRate",
    "contractAmount",
    "businessDate",
    "buyerBrokerName",
    "sellerBrokerName",
}

DETAIL_FIELDS = [
    "business_date",
    "broker_id",
    "broker_name",
    "stock_symbol",
    "buy_qty",
    "buy_amount",
    "buy_vwap",
    "sell_qty",
    "sell_amount",
    "sell_vwap",
    "net_qty",
    "net_cash",
    "gross_turnover",
    "contracts",
]

TOTAL_FIELDS = [
    "business_date",
    "broker_id",
    "broker_name",
    "buy_qty",
    "buy_amount",
    "sell_qty",
    "sell_amount",
    "net_cash",
    "gross_turnover",
    "scrips_traded",
    "contracts",
]


class DataError(Exception):
    """Raised when the input file is missing, malformed, or inconsistent."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build per-broker summaries from a NEPSE floorsheet CSV."
    )
    parser.add_argument(
        "--date",
        help="Business date as YYYY-MM-DD (default: today, Asia/Kathmandu).",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Input CSV (default: Floorsheet/<date>.csv).",
    )
    parser.add_argument(
        "--broker",
        help="Print one broker's summary and exit without writing files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite summary files that already exist.",
    )
    return parser.parse_args(argv)


def normalise_broker_id(value: str) -> str:
    """Return a canonical broker id: '58', '058' -> '58'."""
    value = value.strip()
    try:
        return str(int(float(value)))
    except ValueError:
        return value


def to_int(value: str, row_number: int, field: str) -> int:
    try:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError
        return int(number)
    except ValueError as exc:
        raise DataError(f"row {row_number}: invalid {field}={value!r}") from exc


def to_float(value: str, row_number: int, field: str) -> float:
    try:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError
        return number
    except ValueError as exc:
        raise DataError(f"row {row_number}: invalid {field}={value!r}") from exc


def resolve_input(args: argparse.Namespace) -> tuple[Path, str | None]:
    """Return the input path and the requested date, if one was given."""
    if args.file is not None:
        path = args.file.expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.is_file():
            raise DataError(f"input file not found: {path}")
        expected_date = None
        if args.date:
            expected_date = parse_date(args.date)
        return path, expected_date

    date = parse_date(args.date) if args.date else datetime.now(NEPAL_TZ).date().isoformat()
    path = FLOORSHEET_DIR / f"{date}.csv"
    if not path.is_file():
        raise DataError(
            f"input file not found: {path}\n"
            f"Download the floorsheet first or pass --date/--file. "
            f"This script never uses the network."
        )
    return path, date


def parse_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise DataError(f"invalid --date {value!r}, expected YYYY-MM-DD") from exc


def read_floorsheet(
    path: Path, expected_date: str | None
) -> tuple[dict, dict, dict, dict, dict]:
    """Aggregate both sides of every contract.

    Returns (buy, sell, names, stats, symbols) where buy/sell map
    (broker_id, symbol) -> [qty, amount, contracts].
    """
    buy: dict[tuple[str, str], list] = {}
    sell: dict[tuple[str, str], list] = {}
    names: dict[str, Counter] = defaultdict(Counter)
    dates: Counter = Counter()
    symbols: set[str] = set()
    seen_ids: set[str] = set()

    stats = {
        "rows": 0,
        "accepted": 0,
        "duplicate_ids": 0,
        "amount_mismatches": 0,
        "turnover": 0.0,
    }

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise DataError(f"missing column(s): {', '.join(sorted(missing))}")

        for row_number, row in enumerate(reader, start=2):
            stats["rows"] += 1

            contract_id = (row["contractId"] or "").strip()
            if not contract_id:
                raise DataError(f"row {row_number}: empty contractId")
            if contract_id in seen_ids:
                stats["duplicate_ids"] += 1
                continue
            seen_ids.add(contract_id)

            date = (row["businessDate"] or "").strip()
            if not date:
                raise DataError(f"row {row_number}: empty businessDate")
            dates[date] += 1

            symbol = (row["stockSymbol"] or "").strip().upper()
            if not symbol:
                raise DataError(f"row {row_number}: empty stockSymbol")

            buyer_id = normalise_broker_id(row["buyerMemberId"])
            seller_id = normalise_broker_id(row["sellerMemberId"])
            qty = to_int(row["contractQuantity"], row_number, "contractQuantity")
            rate = to_float(row["contractRate"], row_number, "contractRate")
            amount = to_float(row["contractAmount"], row_number, "contractAmount")

            if qty <= 0:
                raise DataError(f"row {row_number}: non-positive quantity {qty}")
            if rate <= 0:
                raise DataError(f"row {row_number}: non-positive rate {rate}")
            if abs(qty * rate - amount) > 1.0:
                stats["amount_mismatches"] += 1

            add_trade(buy, (buyer_id, symbol), qty, amount)
            add_trade(sell, (seller_id, symbol), qty, amount)

            buyer_name = (row["buyerBrokerName"] or "").strip()
            seller_name = (row["sellerBrokerName"] or "").strip()
            if buyer_name:
                names[buyer_id][buyer_name] += 1
            if seller_name:
                names[seller_id][seller_name] += 1

            symbols.add(symbol)
            stats["accepted"] += 1
            stats["turnover"] += amount

    if not buy:
        raise DataError(f"no trades found in {path}")

    if len(dates) != 1:
        raise DataError(
            f"expected one businessDate, found {len(dates)}: "
            f"{', '.join(sorted(dates))}"
        )
    data_date = next(iter(dates))
    if expected_date and data_date != expected_date:
        raise DataError(
            f"file contains businessDate {data_date}, expected {expected_date}"
        )

    buy_total = sum(entry[1] for entry in buy.values())
    sell_total = sum(entry[1] for entry in sell.values())
    if abs(buy_total - sell_total) > 1.0:
        raise DataError(
            f"buy/sell totals do not reconcile: {buy_total:,.2f} vs {sell_total:,.2f}"
        )

    stats["date"] = data_date
    stats["brokers"] = len(
        {broker for broker, _ in buy} | {broker for broker, _ in sell}
    )
    stats["symbols"] = len(symbols)
    return buy, sell, names, stats, symbols


def add_trade(store: dict[tuple[str, str], list], key: tuple[str, str], qty: int, amount: float) -> None:
    entry = store.get(key)
    if entry is None:
        store[key] = [qty, amount, 1]
    else:
        entry[0] += qty
        entry[1] += amount
        entry[2] += 1


def broker_names(names: dict[str, Counter]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for broker_id, counter in names.items():
        resolved[broker_id] = counter.most_common(1)[0][0]
        if len(counter) > 1:
            variants = ", ".join(repr(name) for name, _ in counter.most_common())
            print(
                f"warning: broker {broker_id} has multiple names, using most common: {variants}",
                file=sys.stderr,
            )
    return resolved


def sort_key(key: tuple[str, str]) -> tuple[int, str]:
    broker_id, symbol = key
    try:
        numeric = int(broker_id)
    except ValueError:
        numeric = 10**9
    return numeric, symbol


def build_detail_rows(buy: dict, sell: dict, names: dict[str, str], date: str) -> list[dict]:
    rows = []
    for broker_id, symbol in sorted(set(buy) | set(sell), key=sort_key):
        buy_qty, buy_amount, buy_contracts = buy.get((broker_id, symbol), (0, 0.0, 0))
        sell_qty, sell_amount, sell_contracts = sell.get((broker_id, symbol), (0, 0.0, 0))

        rows.append(
            {
                "business_date": date,
                "broker_id": broker_id,
                "broker_name": names.get(broker_id, ""),
                "stock_symbol": symbol,
                "buy_qty": buy_qty,
                "buy_amount": f"{buy_amount:.2f}",
                "buy_vwap": f"{buy_amount / buy_qty:.2f}" if buy_qty else "",
                "sell_qty": sell_qty,
                "sell_amount": f"{sell_amount:.2f}",
                "sell_vwap": f"{sell_amount / sell_qty:.2f}" if sell_qty else "",
                "net_qty": buy_qty - sell_qty,
                "net_cash": f"{sell_amount - buy_amount:.2f}",
                "gross_turnover": f"{buy_amount + sell_amount:.2f}",
                "contracts": buy_contracts + sell_contracts,
            }
        )
    return rows


def build_total_rows(buy: dict, sell: dict, names: dict[str, str], date: str) -> list[dict]:
    buy_qty: dict[str, int] = defaultdict(int)
    buy_amount: dict[str, float] = defaultdict(float)
    buy_contracts: dict[str, int] = defaultdict(int)
    sell_qty: dict[str, int] = defaultdict(int)
    sell_amount: dict[str, float] = defaultdict(float)
    sell_contracts: dict[str, int] = defaultdict(int)
    scrips: dict[str, set[str]] = defaultdict(set)

    for (broker_id, symbol), (qty, amount, count) in buy.items():
        buy_qty[broker_id] += qty
        buy_amount[broker_id] += amount
        buy_contracts[broker_id] += count
        scrips[broker_id].add(symbol)
    for (broker_id, symbol), (qty, amount, count) in sell.items():
        sell_qty[broker_id] += qty
        sell_amount[broker_id] += amount
        sell_contracts[broker_id] += count
        scrips[broker_id].add(symbol)

    rows = []
    for broker_id in sorted(set(buy_qty) | set(sell_qty), key=lambda value: sort_key((value, ""))[0]):
        rows.append(
            {
                "business_date": date,
                "broker_id": broker_id,
                "broker_name": names.get(broker_id, ""),
                "buy_qty": buy_qty[broker_id],
                "buy_amount": f"{buy_amount[broker_id]:.2f}",
                "sell_qty": sell_qty[broker_id],
                "sell_amount": f"{sell_amount[broker_id]:.2f}",
                "net_cash": f"{sell_amount[broker_id] - buy_amount[broker_id]:.2f}",
                "gross_turnover": f"{buy_amount[broker_id] + sell_amount[broker_id]:.2f}",
                "scrips_traded": len(scrips[broker_id]),
                "contracts": buy_contracts[broker_id] + sell_contracts[broker_id],
            }
        )

    rows.sort(key=lambda row: float(row["gross_turnover"]), reverse=True)
    return rows


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def print_broker_view(
    broker_id: str,
    rows: list[dict],
    total: dict | None,
    date: str,
    name: str,
) -> None:
    print(f"Broker {broker_id} — {name or 'unknown'} — {date}")
    print(
        f"{'SYMBOL':<14}{'BUY QTY':>10}{'BUY VWAP':>10}"
        f"{'SELL QTY':>10}{'SELL VWAP':>11}{'NET QTY':>10}{'NET CASH':>16}"
    )
    for row in rows:
        print(
            f"{row['stock_symbol']:<14}{row['buy_qty']:>10,}"
            f"{(row['buy_vwap'] or '-'):>10}{row['sell_qty']:>10,}"
            f"{(row['sell_vwap'] or '-'):>11}{row['net_qty']:>10,}"
            f"{float(row['net_cash']):>16,.2f}"
        )
    if total:
        print(
            f"{'TOTAL':<14}{total['buy_qty']:>10,}"
            f"{'':>10}{total['sell_qty']:>10,}{'':>11}"
            f"{total['buy_qty'] - total['sell_qty']:>10,}"
            f"{float(total['net_cash']):>16,.2f}"
        )
        print(f"gross turnover: {float(total['gross_turnover']):,.2f}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        input_path, expected_date = resolve_input(args)
        buy, sell, raw_names, stats, _symbols = read_floorsheet(input_path, expected_date)
        names = broker_names(raw_names)
        date = stats["date"]

        broker_filter = normalise_broker_id(args.broker) if args.broker else None
        detail_rows = build_detail_rows(buy, sell, names, date)
        total_rows = build_total_rows(buy, sell, names, date)

        if broker_filter:
            broker_rows = [row for row in detail_rows if row["broker_id"] == broker_filter]
            if not broker_rows:
                print(f"error: no trades for broker {broker_filter} on {date}", file=sys.stderr)
                return 1
            broker_total = next(
                (row for row in total_rows if row["broker_id"] == broker_filter), None
            )
            print_broker_view(
                broker_filter,
                broker_rows,
                broker_total,
                date,
                names.get(broker_filter, ""),
            )
            return 0

        detail_path = SUMMARY_DIR / f"{date}_brokers.csv"
        totals_path = SUMMARY_DIR / f"{date}_broker_totals.csv"

        written = []
        for path, fields, rows in (
            (detail_path, DETAIL_FIELDS, detail_rows),
            (totals_path, TOTAL_FIELDS, total_rows),
        ):
            if path.exists() and not args.force:
                print(f"skip (exists): {path}")
                continue
            write_csv(path, fields, rows)
            written.append((path, len(rows)))

        print(
            f"{date}: {stats['accepted']:,} contracts | "
            f"{stats['turnover']:,.2f} turnover | "
            f"{stats['brokers']} brokers | {stats['symbols']} scrips"
        )
        for path, count in written:
            print(f"wrote {path} ({count:,} rows)")

        if stats["duplicate_ids"]:
            print(
                f"warning: skipped {stats['duplicate_ids']:,} duplicate contractId row(s)",
                file=sys.stderr,
            )
        if stats["amount_mismatches"]:
            print(
                f"warning: {stats['amount_mismatches']:,} row(s) where qty*rate != amount",
                file=sys.stderr,
            )
        return 0

    except BrokenPipeError:
        # Allow `--broker 58 | head` without a traceback.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 0
    except DataError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
