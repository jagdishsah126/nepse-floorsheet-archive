# 📈 Automated NEPSE Daily Floorsheet Scraper

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Schedule](https://img.shields.io/badge/Schedule-Daily%203%3A36%20PM%20NPT-brightgreen.svg)
![Market](https://img.shields.io/badge/Exchange-NEPSE-orange.svg)
![Automation](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-blueviolet.svg)

An autonomous data pipeline that scrapes the complete daily transaction floorsheet directly from the **Nepal Stock Exchange (NEPSE)** and archives it into version-controlled CSV files.

---

## ⚡ Key Highlights

- **Automated Execution**: Runs automatically every trading day (Sunday to Thursday) at **3:36 PM NPT** (09:51 UTC) via GitHub Actions.
- **Dynamic Reverse-Engineered Handshake**: Solves NEPSE's dynamic `Salter` token and calculated daily payload ID automatically without requiring external browser automation.
- **Dedicated Daily Archiving**: Saves the full day's transactions in `Floorsheet/<YYYY-MM-DD>.csv`.
- **In-Depth Technical Documentation**: Full reverse-engineering writeup available in [`ReverseEngineering.md`](ReverseEngineering.md).
- **Manual Trigger**: Supports the `workflow_dispatch` trigger, allowing you to trigger a scrape anytime from the GitHub Actions web interface.

---

## 📊 How to Access Daily Floorsheet Data Directly

You do not need to clone the repository or manually download files to use this data. Every daily CSV is publicly available and can be loaded directly into any data analysis environment (Python Pandas, Jupyter Notebook, Google Colab, R, Excel, or Bash).

### 1. Direct Raw URL Format
Every trading day's CSV file is hosted at a permanent URL:
```text
https://raw.githubusercontent.com/jagdishsah126/nepse-floorsheet-archive/main/Floorsheet/<YYYY-MM-DD>.csv
```
*(Example: `https://raw.githubusercontent.com/jagdishsah126/nepse-floorsheet-archive/main/Floorsheet/2026-09-17.csv`)*

### 2. One-Line Python (Pandas / Jupyter / Colab)
Load any trading day directly into memory:
```python
import pandas as pd

# Specify any target trading date (YYYY-MM-DD)
date = "2026-09-17"
url = f"https://raw.githubusercontent.com/jagdishsah126/nepse-floorsheet-archive/main/Floorsheet/{date}.csv"

df = pd.read_csv(url)
print(f"Loaded {len(df):,} transactions for {date}:")
print(df.head())
```

### 3. Direct Download via Terminal (`curl` / `wget`)
```bash
# Download a specific date's floorsheet
curl -O https://raw.githubusercontent.com/jagdishsah126/nepse-floorsheet-archive/main/Floorsheet/2026-09-17.csv

# Or using wget
wget https://raw.githubusercontent.com/jagdishsah126/nepse-floorsheet-archive/main/Floorsheet/2026-09-17.csv
```

### 4. Load All Historical Dates Combined
Merge every archived day into a single time-series DataFrame:
```python
import glob
import pandas as pd

# If you have the repo locally, combine all archived dates:
all_files = glob.glob("Floorsheet/*.csv")
master_df = pd.concat([pd.read_csv(f) for f in all_files], ignore_index=True)
print(f"Total Historical Records: {len(master_df):,} across {len(all_files)} days")
```


## 🕵️ Reverse-Engineering Deep Dive

Curious about how we bypassed the `WARNING: UNAUTHORIZED ACCESS` error, reverse-engineered the `css.wasm` WebAssembly module, and cracked the Angular payload calculation?

👉 **Read the full step-by-step breakdown in [`ReverseEngineering.md`](ReverseEngineering.md).**

---

## 📂 Repository Structure

```
├── .github/
│   └── workflows/
│       └── daily_scrape.yml     # GitHub Actions workflow scheduled at 3:36 PM NPT
├── Floorsheet/
│   └── .gitkeep                 # Data directory where daily CSVs are archived
├── nepse_auth.py                # De-obfuscation and dynamic payload math engine
├── nepse_client.py              # HTTP client with retry policies & auto-refresh
├── scrape_daily.py              # Automated execution entry point for GitHub Actions
├── requirements.txt             # Python dependencies
├── .gitignore                   # Standard Python ignores
├── ReverseEngineering.md        # Complete reverse-engineering writeup and investigation
└── README.md                    # Project documentation
```

---

## 🚀 Step-by-Step: How to Upload to GitHub

### 1. Initialize Git Repository
Inside this folder:

```bash
git init
git add .
git commit -m "🎉 Initial commit: Automated NEPSE Floorsheet pipeline"
```

### 2. Create a New Repository on GitHub
1. Go to [GitHub New Repository](https://github.com/new).
2. Name it (e.g., `nepse-daily-floorsheet`).
3. Leave it empty (do **not** check "Add a README" or ".gitignore").

### 3. Link Remote & Push
```bash
git branch -M main
git remote add origin https://github.com/<YOUR_USERNAME>/nepse-daily-floorsheet.git
git push -u origin main
```

---

## ⚙️ REQUIRED GitHub Configuration (One-Time Setup)

To allow GitHub Actions to commit and push the scraped CSV files back into your repository:

1. In your GitHub repository, click on **Settings** (top right tab).
2. On the left sidebar, click **Actions** $\rightarrow$ **General**.
3. Scroll down to **Workflow permissions**.
4. Select **Read and write permissions**.
5. Check **Allow GitHub Actions to create and approve pull requests** (optional, recommended).
6. Click **Save**.

*(If this setting is not enabled, the workflow will fail at the `git push` step with a `403 Permission Denied` error).*

---

## 🕒 Schedule & Timing

- **NEPSE Market Close**: 3:00 PM NPT
- **Action Trigger Time**: **3:36 PM NPT** (15:36 NPT)
- **UTC Schedule**: `51 9 * * 0-4` (09:51 UTC, Sunday through Thursday)

---

## 📊 Extracted CSV Columns

| Column | Type | Description |
| :--- | :--- | :--- |
| `contractId` | Integer | Unique trade transaction ID |
| `stockSymbol` | String | Company ticker symbol (e.g. `UAIL`, `NABIL`) |
| `securityName` | String | Full company name |
| `buyerMemberId` | String | Buyer broker number |
| `sellerMemberId` | String | Seller broker number |
| `buyerBrokerName` | String | Buyer broker company name |
| `sellerBrokerName` | String | Seller broker company name |
| `contractQuantity` | Integer | Volume of shares transacted |
| `contractRate` | Float | Price per share in NPR |
| `contractAmount` | Float | Total trade amount in NPR |
| `businessDate` | String | Trading date (`YYYY-MM-DD`) |
| `tradeTime` | String | Precise timestamp of transaction |

---

## 🛠️ Running Locally

If you want to run the scraper manually on your local computer:

```bash
pip install -r requirements.txt
python scrape_daily.py
```

The CSV will be generated inside the `Floorsheet/` directory with today's date.
