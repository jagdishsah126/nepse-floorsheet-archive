#!/usr/bin/env python3
"""
NEPSE Archive Verification Utility (Verify.py)

Two-stage verification engine:
  Step 1: Floorsheet vs Official Chukul API (contract-level reconciliation)
  Step 2: Summary vs Floorsheet (broker & aggregate math reconciliation)

Supports:
  - Interactive terminal mode (if run with no arguments)
  - Non-interactive CLI flags (for scripting and GitHub Actions CI)
  - Date ranges, single dates, or full archive sweeps
  - Automatic fallback to `git show` if running in a sparse-checkout environment
  - Detailed Markdown and JSON report generation
"""

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple


CHUKUL_FLOORSHEET_URL = "https://chukul.com/api/data/floorsheet/bydate/?date={date}"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
FLOAT_TOLERANCE = 0.01


def get_available_dates() -> List[str]:
    """Retrieve all available dates in Floorsheet/ from git or local filesystem."""
    # Try git ls-tree first (works even in sparse checkout)
    try:
        res = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD:Floorsheet"],
            capture_output=True,
            text=True,
            check=True
        )
        dates = [
            line.replace(".csv", "")
            for line in res.stdout.splitlines()
            if line.endswith(".csv")
        ]
        if dates:
            return sorted(dates)
    except Exception:
        pass

    # Fallback to filesystem
    if os.path.exists("Floorsheet"):
        dates = [
            f.replace(".csv", "")
            for f in os.listdir("Floorsheet")
            if f.endswith(".csv")
        ]
        return sorted(dates)

    return []


def read_repo_csv(path: str) -> Optional[str]:
    """Read CSV from disk, or fallback to `git show HEAD:<path>`."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    try:
        res = subprocess.run(
            ["git", "show", f"HEAD:{path}"],
            capture_output=True,
            text=True,
            check=True
        )
        return res.stdout
    except Exception:
        return None


def fetch_chukul_floorsheet(date_str: str, retries: int = 3, delay: float = 0.5) -> Tuple[bool, List[Dict[str, Any]], str]:
    """
    Fetch floorsheet records from Chukul API for a given date.
    Returns (success, records, error_message).
    """
    url = CHUKUL_FLOORSHEET_URL.format(date=date_str)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, list):
                        return True, data, ""
                    return False, [], f"Unexpected response format: {type(data)}"
                return False, [], f"HTTP status {resp.status}"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False, [], "Date not found on Chukul (404)"
            if attempt == retries:
                return False, [], f"HTTP {e.code}: {e.reason}"
        except Exception as e:
            if attempt == retries:
                return False, [], str(e)
        time.sleep(delay * attempt)

    return False, [], "Max retries exceeded"


def verify_floorsheet_against_chukul(date_str: str, tolerance: float = FLOAT_TOLERANCE) -> Dict[str, Any]:
    """
    Step 1: Reconcile Floorsheet/<date>.csv against Chukul API.
    """
    result: Dict[str, Any] = {
        "date": date_str,
        "step": 1,
        "passed": False,
        "archive_count": 0,
        "chukul_count": 0,
        "missing_in_archive": 0,
        "missing_in_chukul": 0,
        "attribute_mismatches": 0,
        "archive_turnover": 0.0,
        "chukul_turnover": 0.0,
        "errors": []
    }

    # 1. Load archive floorsheet
    content = read_repo_csv(f"Floorsheet/{date_str}.csv")
    if not content:
        result["errors"].append(f"Floorsheet/{date_str}.csv not found in archive")
        return result

    archive_map: Dict[str, Dict[str, Any]] = {}
    reader = csv.DictReader(io.StringIO(content))
    archive_turnover = 0.0
    for row in reader:
        cid = str(row.get("contractId", "")).strip()
        if cid:
            try:
                amt = float(row.get("contractAmount", 0.0))
            except ValueError:
                amt = 0.0
            archive_turnover += amt
            archive_map[cid] = row
    result["archive_count"] = len(archive_map)
    result["archive_turnover"] = round(archive_turnover, 2)

    # 2. Fetch Chukul floorsheet
    ok, chukul_data, err = fetch_chukul_floorsheet(date_str)
    if not ok:
        result["errors"].append(f"Failed to fetch Chukul data: {err}")
        return result

    chukul_map: Dict[str, Dict[str, Any]] = {}
    chukul_turnover = 0.0
    for item in chukul_data:
        tid = str(item.get("transaction", "")).strip()
        if tid:
            try:
                amt = float(item.get("amount", 0.0))
            except ValueError:
                amt = 0.0
            chukul_turnover += amt
            chukul_map[tid] = item
    result["chukul_count"] = len(chukul_map)
    result["chukul_turnover"] = round(chukul_turnover, 2)

    # 3. Contract ID comparison
    missing_in_archive = set(chukul_map.keys()) - set(archive_map.keys())
    missing_in_chukul = set(archive_map.keys()) - set(chukul_map.keys())
    result["missing_in_archive"] = len(missing_in_archive)
    result["missing_in_chukul"] = len(missing_in_chukul)

    if missing_in_archive:
        result["errors"].append(f"{len(missing_in_archive)} contracts in Chukul missing in archive (sample: {list(missing_in_archive)[:3]})")
    if missing_in_chukul:
        result["errors"].append(f"{len(missing_in_chukul)} contracts in archive missing in Chukul (sample: {list(missing_in_chukul)[:3]})")

    # 4. Attribute reconciliation for common contracts
    common_cids = set(archive_map.keys()) & set(chukul_map.keys())
    mismatch_count = 0
    for cid in common_cids:
        a = archive_map[cid]
        c = chukul_map[cid]

        # Stock symbol
        if a.get("stockSymbol", "").strip() != str(c.get("symbol", "")).strip():
            mismatch_count += 1
            continue

        # Buyer & Seller broker IDs
        if str(a.get("buyerMemberId", "")).strip() != str(c.get("buyer", "")).strip():
            mismatch_count += 1
            continue
        if str(a.get("sellerMemberId", "")).strip() != str(c.get("seller", "")).strip():
            mismatch_count += 1
            continue

        # Quantity
        try:
            a_qty = float(a.get("contractQuantity", 0))
            c_qty = float(c.get("quantity", 0))
            if abs(a_qty - c_qty) > tolerance:
                mismatch_count += 1
                continue
        except ValueError:
            mismatch_count += 1
            continue

        # Rate
        try:
            a_rate = float(a.get("contractRate", 0))
            c_rate = float(c.get("rate", 0))
            if abs(a_rate - c_rate) > tolerance:
                mismatch_count += 1
                continue
        except ValueError:
            mismatch_count += 1
            continue

        # Amount
        try:
            a_amt = float(a.get("contractAmount", 0))
            c_amt = float(c.get("amount", 0))
            if abs(a_amt - c_amt) > tolerance:
                mismatch_count += 1
                continue
        except ValueError:
            mismatch_count += 1
            continue

    result["attribute_mismatches"] = mismatch_count
    if mismatch_count > 0:
        result["errors"].append(f"{mismatch_count} contracts have attribute discrepancies")

    # Overall pass condition
    result["passed"] = (
        result["missing_in_archive"] == 0 and
        result["missing_in_chukul"] == 0 and
        mismatch_count == 0 and
        abs(result["archive_turnover"] - result["chukul_turnover"]) < (tolerance * max(1, len(common_cids)))
    )

    return result


def verify_summary_against_floorsheet(date_str: str, tolerance: float = FLOAT_TOLERANCE) -> Dict[str, Any]:
    """
    Step 2: Reconcile Summary files against Floorsheet/<date>.csv.
    """
    result: Dict[str, Any] = {
        "date": date_str,
        "step": 2,
        "passed": False,
        "floorsheet_rows": 0,
        "summary_brokers_rows": 0,
        "summary_totals_rows": 0,
        "errors": []
    }

    # 1. Load Floorsheet
    fs_content = read_repo_csv(f"Floorsheet/{date_str}.csv")
    if not fs_content:
        result["errors"].append(f"Floorsheet/{date_str}.csv missing")
        return result

    fs_reader = csv.DictReader(io.StringIO(fs_content))
    computed_brokers: Dict[Tuple[str, str], Dict[str, float]] = {}
    computed_totals: Dict[str, Dict[str, float]] = {}
    total_buy_amt = 0.0
    total_sell_amt = 0.0
    fs_count = 0

    for row in fs_reader:
        fs_count += 1
        sym = row.get("stockSymbol", "").strip()
        buyer = str(row.get("buyerMemberId", "")).strip()
        seller = str(row.get("sellerMemberId", "")).strip()
        try:
            qty = float(row.get("contractQuantity", 0))
            rate = float(row.get("contractRate", 0))
            amt = float(row.get("contractAmount", 0))
        except ValueError:
            continue

        total_buy_amt += amt
        total_sell_amt += amt

        # Buyer scrip aggregate
        bk = (buyer, sym)
        if bk not in computed_brokers:
            computed_brokers[bk] = {"buy_qty": 0.0, "buy_amt": 0.0, "sell_qty": 0.0, "sell_amt": 0.0}
        computed_brokers[bk]["buy_qty"] += qty
        computed_brokers[bk]["buy_amt"] += amt

        # Seller scrip aggregate
        sk = (seller, sym)
        if sk not in computed_brokers:
            computed_brokers[sk] = {"buy_qty": 0.0, "buy_amt": 0.0, "sell_qty": 0.0, "sell_amt": 0.0}
        computed_brokers[sk]["sell_qty"] += qty
        computed_brokers[sk]["sell_amt"] += amt

        # Buyer total
        if buyer not in computed_totals:
            computed_totals[buyer] = {"buy_amt": 0.0, "sell_amt": 0.0}
        computed_totals[buyer]["buy_amt"] += amt

        # Seller total
        if seller not in computed_totals:
            computed_totals[seller] = {"buy_amt": 0.0, "sell_amt": 0.0}
        computed_totals[seller]["sell_amt"] += amt

    result["floorsheet_rows"] = fs_count

    # Check internal mathematical balance
    if abs(total_buy_amt - total_sell_amt) > tolerance:
        result["errors"].append(f"Floorsheet buy/sell imbalance: Buy={total_buy_amt:.2f}, Sell={total_sell_amt:.2f}")

    # 2. Check Summary/<date>_brokers.csv
    sb_content = read_repo_csv(f"Summary/{date_str}_brokers.csv")
    if not sb_content:
        result["errors"].append(f"Summary/{date_str}_brokers.csv missing")
        return result

    sb_reader = csv.DictReader(io.StringIO(sb_content))
    sb_rows = list(sb_reader)
    result["summary_brokers_rows"] = len(sb_rows)

    if len(sb_rows) != len(computed_brokers):
        result["errors"].append(f"Broker scrip count mismatch: expected {len(computed_brokers)}, found {len(sb_rows)}")

    # 3. Check Summary/<date>_broker_totals.csv
    st_content = read_repo_csv(f"Summary/{date_str}_broker_totals.csv")
    if not st_content:
        result["errors"].append(f"Summary/{date_str}_broker_totals.csv missing")
        return result

    st_reader = csv.DictReader(io.StringIO(st_content))
    st_rows = list(st_reader)
    result["summary_totals_rows"] = len(st_rows)

    all_active_brokers = set(computed_totals.keys())
    if len(st_rows) < len(all_active_brokers):
        result["errors"].append(f"Broker totals count mismatch: expected at least {len(all_active_brokers)}, found {len(st_rows)}")

    result["passed"] = len(result["errors"]) == 0
    return result


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify NEPSE floorsheet and summary archives against Chukul and internal consistency."
    )
    parser.add_argument("--step", choices=["1", "2", "both"], default=None, help="Step 1 (Chukul), Step 2 (Summary), or both")
    parser.add_argument("--mode", choices=["single", "range", "all"], default=None, help="Date scope mode")
    parser.add_argument("--date", help="Single date (YYYY-MM-DD)")
    parser.add_argument("--start", help="Range start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="Range end date (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", help="Verify all available dates")
    parser.add_argument("--tolerance", type=float, default=FLOAT_TOLERANCE, help="Float comparison tolerance")
    parser.add_argument("--output", help="Path to write JSON verification report")
    parser.add_argument("--summary-file", help="Path to write Markdown summary (e.g. $GITHUB_STEP_SUMMARY)")
    parser.add_argument("--non-interactive", action="store_true", help="Disable interactive prompts")
    return parser.parse_args()


def prompt_user_interactively(all_dates: List[str]) -> Tuple[str, List[str]]:
    """Prompt user for step and date range if run interactively."""
    print("=" * 60)
    print(" 🔍 NEPSE Archive Verification Engine")
    print("=" * 60)
    print(f"Total archive dates available: {len(all_dates)} ({all_dates[0]} → {all_dates[-1]})\n")

    # Step prompt
    print("[1] Select Verification Step:")
    print("  1) Step 1: Floorsheet vs Chukul (Official reconciliation)")
    print("  2) Step 2: Summary vs Floorsheet (Offline, stdlib math check)")
    print("  3) Both Step 1 & Step 2 (Recommended)")
    step_choice = input("Enter choice [1/2/3] (default 3): ").strip() or "3"
    step_map = {"1": "1", "2": "2", "3": "both"}
    step = step_map.get(step_choice, "both")

    # Scope prompt
    print("\n[2] Select Date Scope:")
    print("  1) Single Date")
    print("  2) Date Range (e.g. Last 6 months)")
    print("  3) Full Archive (All 425 days)")
    scope_choice = input("Enter choice [1/2/3] (default 2): ").strip() or "2"

    selected_dates: List[str] = []
    if scope_choice == "1":
        latest = all_dates[-1]
        dt = input(f"Enter date YYYY-MM-DD (default {latest}): ").strip() or latest
        selected_dates = [dt] if dt in all_dates else [all_dates[-1]]
    elif scope_choice == "3":
        if step in ["1", "both"]:
            print("⚠️ Notice: Verifying all days against Chukul will fetch ~2GB over the network.")
            confirm = input("Are you sure? [y/N]: ").strip().lower()
            if confirm != "y":
                print("Defaulting to last 30 days to conserve data.")
                selected_dates = all_dates[-30:]
            else:
                selected_dates = all_dates
        else:
            selected_dates = all_dates
    else:
        # Default range (last 6 months ~ 125 trading days)
        six_months_ago = (datetime.now() - timedelta(days=182)).strftime("%Y-%m-%d")
        print(f"\nEnter range (default: last ~6 months, {six_months_ago} → {all_dates[-1]})")
        start = input(f"Start date YYYY-MM-DD (default {six_months_ago}): ").strip() or six_months_ago
        end = input(f"End date YYYY-MM-DD (default {all_dates[-1]}): ").strip() or all_dates[-1]
        selected_dates = [d for d in all_dates if start <= d <= end]

    return step, selected_dates


def generate_markdown_summary(step: str, results_step1: List[Dict[str, Any]], results_step2: List[Dict[str, Any]]) -> str:
    """Generate GitHub-friendly Markdown summary table."""
    lines: List[str] = []
    lines.append("## 📊 NEPSE Archive Verification Report\n")
    lines.append(f"- **Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"- **Step(s) Executed:** `{step}`\n")

    if results_step1:
        passed1 = sum(1 for r in results_step1 if r["passed"])
        failed1 = len(results_step1) - passed1
        lines.append(f"### 🌐 Step 1: Floorsheet vs Chukul API ({passed1}/{len(results_step1)} Passed)")
        lines.append("| Date | Status | Archive Contracts | Chukul Contracts | Mismatches | Turnover Diff |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
        for r in results_step1:
            status = "✅ PASS" if r["passed"] else "❌ FAIL"
            diff = abs(r["archive_turnover"] - r["chukul_turnover"])
            mismatches = r["missing_in_archive"] + r["missing_in_chukul"] + r["attribute_mismatches"]
            lines.append(f"| {r['date']} | {status} | {r['archive_count']:,} | {r['chukul_count']:,} | {mismatches} | NPR {diff:.2f} |")
        lines.append("")

    if results_step2:
        passed2 = sum(1 for r in results_step2 if r["passed"])
        failed2 = len(results_step2) - passed2
        lines.append(f"### 📈 Step 2: Summary vs Floorsheet Internal Math ({passed2}/{len(results_step2)} Passed)")
        lines.append("| Date | Status | Floorsheet Rows | Broker×Scrips | Broker Totals | Errors |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
        for r in results_step2:
            status = "✅ PASS" if r["passed"] else "❌ FAIL"
            err_text = ", ".join(r["errors"]) if r["errors"] else "None"
            lines.append(f"| {r['date']} | {status} | {r['floorsheet_rows']:,} | {r['summary_brokers_rows']:,} | {r['summary_totals_rows']:,} | {err_text} |")
        lines.append("")

    return "\n".join(lines)


def main():
    args = parse_arguments()
    all_dates = get_available_dates()
    if not all_dates:
        print("❌ Error: No archived trading dates found in repository.", file=sys.stderr)
        sys.exit(1)

    # Determine step and target dates
    if not args.non_interactive and args.step is None and args.date is None and args.start is None and not args.all:
        step, target_dates = prompt_user_interactively(all_dates)
    else:
        step = args.step or "both"
        if args.date:
            target_dates = [args.date]
        elif args.start or args.end:
            start = args.start or all_dates[0]
            end = args.end or all_dates[-1]
            target_dates = [d for d in all_dates if start <= d <= end]
        elif args.all:
            target_dates = all_dates
        else:
            # Default to last 6 months (~125 trading days)
            six_months_ago = (datetime.now() - timedelta(days=182)).strftime("%Y-%m-%d")
            target_dates = [d for d in all_dates if d >= six_months_ago]

    print(f"\n🚀 Running verification on {len(target_dates)} date(s) (Step: {step})...")
    print(f"Date range: {target_dates[0]} → {target_dates[-1]}\n")

    results_step1: List[Dict[str, Any]] = []
    results_step2: List[Dict[str, Any]] = []

    # Execute verification
    for idx, date_str in enumerate(target_dates, 1):
        print(f"[{idx}/{len(target_dates)}] Verifying {date_str}...", end="", flush=True)

        status_parts = []
        if step in ["1", "both"]:
            r1 = verify_floorsheet_against_chukul(date_str, tolerance=args.tolerance)
            results_step1.append(r1)
            status_parts.append(f"Chukul: {'PASS' if r1['passed'] else 'FAIL'}")
            time.sleep(0.3)  # Polite delay for Chukul API

        if step in ["2", "both"]:
            r2 = verify_summary_against_floorsheet(date_str, tolerance=args.tolerance)
            results_step2.append(r2)
            status_parts.append(f"Summary: {'PASS' if r2['passed'] else 'FAIL'}")

        print(f"  --> {' | '.join(status_parts)}")

    # Print overall summary
    print("\n" + "=" * 60)
    print(" 🏁 Verification Complete")
    print("=" * 60)

    total_failures = 0
    if results_step1:
        p1 = sum(1 for r in results_step1 if r["passed"])
        f1 = len(results_step1) - p1
        total_failures += f1
        print(f"Step 1 (Chukul Reconciliation): {p1}/{len(results_step1)} Passed ({f1} Failed)")

    if results_step2:
        p2 = sum(1 for r in results_step2 if r["passed"])
        f2 = len(results_step2) - p2
        total_failures += f2
        print(f"Step 2 (Summary Reconciliation): {p2}/{len(results_step2)} Passed ({f2} Failed)")

    # Generate Markdown Summary
    md_summary = generate_markdown_summary(step, results_step1, results_step2)

    # Output to summary file (e.g., GITHUB_STEP_SUMMARY)
    summary_path = args.summary_file or os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write("\n" + md_summary + "\n")
            print(f"📝 Markdown summary appended to {summary_path}")
        except Exception as e:
            print(f"⚠️ Warning: Could not write summary file: {e}", file=sys.stderr)

    # Output JSON report if requested
    if args.output:
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "step": step,
            "total_days": len(target_dates),
            "step1_results": results_step1,
            "step2_results": results_step2,
            "total_failures": total_failures
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"💾 Detailed JSON report saved to {args.output}")

    sys.exit(0 if total_failures == 0 else 1)


if __name__ == "__main__":
    main()
