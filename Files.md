# 📁 Project File Map — NEPSE Floorsheet Archive

## Directory Tree

```
nepse-floorsheet-archive/
├── .github/
│   └── workflows/
│       ├── daily_scrape.yml        # Mon–Fri 15:36 NPT: scrape + commit floorsheet & summaries
│       └── summary_backfill.yml    # manual dispatch: fill missing Summary/ days
├── Floorsheet/                     # YYYY-MM-DD.csv — one file per trading day (2025-01-01 →)
├── Summary/                        # <date>_brokers.csv + <date>_broker_totals.csv per day
│   └── README.md                   # Summary schema & sign conventions
├── nepse_auth.py                   # Auth & payload math engine
├── nepse_client.py                 # HTTP client with retry & auto-refresh
├── scrape_daily.py                 # Entry point — orchestrates the daily scrape
├── DailySummary.py                 # Floorsheet → per-broker Summary files (stdlib only)
├── summaryBackfill.py              # Bulk regeneration of Summary/ for missing days
├── requirements.txt                # Python dependencies (scraper only)
├── .gitignore                      # Standard Python ignores + *.tmp
├── README.md                       # Project documentation
├── Files.md                        # (this file) Codebase map
├── ReverseEngineering.md           # Full reverse-engineering writeup
├── credit.md                       # Data provenance (SocrateAI backfill, MeroLagani checks)
├── NOTICE.md                       # Ownership, attribution & removal/correction requests
└── LICENSE                         # MIT — code only
```

---

## File Details

### `nepse_auth.py`
> De-obfuscation and dynamic payload math engine.
- Solves the dynamic `Salter` token required by NEPSE's API
- Reverse-engineers `css.wasm` WebAssembly module logic
- Generates the calculated daily payload ID

### `nepse_client.py`
> HTTP client with retry policies & auto-refresh.
- **`NepseClient`** — Main client class
  - `authenticate(force_refresh)` — Authenticate and obtain Salter token
  - `get_floorsheet_payload_id()` — Compute dynamic payload ID
  - `resolve_symbol_to_id(symbol)` — Map stock ticker to internal ID
  - `get_floorsheet_page(page, size, sort_by, sort_order, ...)` — Fetch a single page of floorsheet data
  - `scrape_all_floorsheet(size, max_pages, sort_by, sort_order, symbol, buyer_broker, seller_broker, delay, progress_callback)` — Paginate and aggregate all floorsheet records
  - `generate_curl_command(...)` — Generate a ready-to-use curl command with fresh tokens
  - `to_dataframe(records)` — Convert record list to pandas DataFrame

### `scrape_daily.py`
> Automated execution entry point for GitHub Actions.
- **`get_nepal_now()`** — Returns current `datetime` in Nepal Standard Time (UTC+5:45)
- **`get_nepal_date_str()`** — Returns today's date as `YYYY-MM-DD` string (NPT)
- **`is_trading_day()`** — Returns `True` if today is Mon–Fri in NPT (NEPSE's trading schedule since April 2026; Sun–Thu before)
- **`main()`** — Orchestrates with three stale-data guards:
  1. **Weekend skip** — exits early on Saturday/Sunday
  2. **Duplicate file guard** — skips if today's CSV already saved on disk
  3. **`businessDate` validation** — aborts if API returns previous day's records (holiday detection)
  → authenticate → probe → paginate → save `Floorsheet/<date>.csv`

### `DailySummary.py`
> Per-broker summaries derived from a daily floorsheet. Stdlib-only: no pandas, no network.
- Reads `Floorsheet/<date>.csv`, writes:
  - `Summary/<date>_brokers.csv` — one row per broker × scrip (buy/sell qty, amounts, VWAP, net positions)
  - `Summary/<date>_broker_totals.csv` — one row per broker (aggregates, `scrips_traded`)
- Validates the input (reconciles buy/sell totals, flags duplicate contract IDs), writes atomically (`.tmp` → rename)
- Flags: `--date`, `--file`, `--broker`, `--force`
- Schema details: [`Summary/README.md`](Summary/README.md)

### `summaryBackfill.py`
> Bulk generation: walks every Floorsheet date that lacks a Summary pair and produces both files using `DailySummary.py` (byte-identical to the daily job).
- Flags: `--start`, `--end`, `--limit N`, `--dry-run`, `--strict` (non-zero exit on failures)
- Runs manually and inside the `Summary Backfill` workflow

### `.github/workflows/daily_scrape.yml`
> Scheduled automation.
- Triggered at `09:51 UTC` (15:36 NPT) Monday–Friday — the schedule matches NEPSE's Mon–Fri trading week (switched from Sun–Thu in April 2026)
- `scrape_daily.py` → `DailySummary.py` → single atomic commit/push of `Floorsheet/` + `Summary/`
- Also supports manual `workflow_dispatch` trigger

### `.github/workflows/summary_backfill.yml`
> Manual, one-off regeneration of missing Summary files (optional `start_date` / `end_date` / `limit` inputs).

### `Floorsheet/<YYYY-MM-DD>.csv`
> Daily archived trade data, 14 fixed columns:
`contractId`, `stockSymbol`, `buyerMemberId`, `sellerMemberId`, `contractQuantity`,
`contractRate`, `contractAmount`, `businessDate`, `tradeBookId`, `stockId`,
`buyerBrokerName`, `sellerBrokerName`, `tradeTime`, `securityName`
- Backfilled days (via SocrateAI; up to 2026-10-12) leave `tradeBookId`, `stockId`, `tradeTime` empty — see `credit.md`

### `Summary/<YYYY-MM-DD>_brokers.csv` & `Summary/<YYYY-MM-DD>_broker_totals.csv`
> Per-broker daily aggregates — column meanings in [`Summary/README.md`](Summary/README.md)

### `credit.md` / `NOTICE.md` / `LICENSE`
> Data provenance, attribution & ownership terms. The market data is © NEPSE; the pipeline code is MIT.
