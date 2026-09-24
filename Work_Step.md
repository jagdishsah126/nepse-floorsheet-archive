# 📋 Work Steps — NEPSE Floorsheet Archive

## Import from GitHub
- [x] Clone repository from `https://github.com/jagdishsah126/nepse-floorsheet-archive`
- [x] Set Git author identity (`Your Zara` / `foreverzaraa@gmail.com`)
- [x] Explore project structure
- [x] Generate `Files.md` codebase map
- [x] Generate `Work_Step.md`

## Fix: Stale Data on Market Closed Days
- [x] Guard 1 — Weekend skip: `is_trading_day()` checks Mon–Fri (NPT) before any API call
- [x] Guard 2 — Duplicate file guard: abort if today's CSV already exists on disk
- [x] Guard 3 — `businessDate` validation: compare `content[0].businessDate` against today's date (NPT); mismatch means API returned previous day's stale data → skip save
- [x] Update `scrape_daily.py` with all three guards
- [x] Update `Files.md` with new helper functions
