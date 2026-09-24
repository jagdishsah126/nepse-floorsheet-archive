# 📁 Project File Map — NEPSE Floorsheet Archive

## Directory Tree

```
nepse-floorsheet-archive/
├── .github/
│   └── workflows/
│       └── daily_scrape.yml        # GitHub Actions: runs daily at 3:36 PM NPT (Sun–Thu)
├── Floorsheet/
│   ├── .gitkeep                    # Keeps empty dir in Git
│   ├── 2026-09-17.csv              # Daily trade archive (auto-generated)
│   ├── 2026-09-18.csv
│   ├── 2026-09-22.csv
│   ├── 2026-09-23.csv
│   └── 2026-09-24.csv
├── nepse_auth.py                   # Auth & payload math engine
├── nepse_client.py                 # HTTP client with retry & auto-refresh
├── scrape_daily.py                 # Entry point — orchestrates daily scrape
├── requirements.txt                # Python dependencies
├── .gitignore                      # Standard Python ignores
├── explain.md                      # Additional explanations
├── ReverseEngineering.md           # Full reverse-engineering writeup
├── README.md                       # Project documentation
├── Files.md                        # (this file) Codebase map
└── Work_Step.md                    # Task tracker
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
- **`is_trading_day()`** — Returns `True` if today is Mon–Fri in NPT (NEPSE's updated trading schedule)
- **`main()`** — Orchestrates with three stale-data guards:
  1. **Weekend skip** — exits early on Saturday/Sunday
  2. **Duplicate file guard** — skips if today's CSV already saved on disk
  3. **`businessDate` validation** — aborts if API returns previous day's records (holiday detection)
  → authenticate → probe → paginate → save `Floorsheet/<date>.csv`

### `.github/workflows/daily_scrape.yml`
> GitHub Actions workflow.
- Triggered daily at `09:51 UTC` (3:36 PM NPT), Sunday–Thursday
- Also supports manual `workflow_dispatch` trigger

### `Floorsheet/<YYYY-MM-DD>.csv`
> Daily archived trade data with columns:
`contractId`, `stockSymbol`, `securityName`, `buyerMemberId`, `sellerMemberId`,
`buyerBrokerName`, `sellerBrokerName`, `contractQuantity`, `contractRate`,
`contractAmount`, `businessDate`, `tradeTime`
