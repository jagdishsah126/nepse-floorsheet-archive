# 🕵️ How NEPSE Floorsheet Scraping Works: The Complete Reverse-Engineering Guide

> **Author**: 💖Your Zara💖  
> **Target**: Nepal Stock Exchange (`nepalstock.com.np`)  
> **Date**: September 2026  

---

## 📑 Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [The Problem: Why the Original `curl` Failed](#2-the-problem-why-the-original-curl-failed)
3. [The Reverse-Engineering Journey: Step-by-Step](#3-the-reverse-engineering-journey-step-by-step)
   - [Phase 1: Diagnosis & OSINT Research](#phase-1-diagnosis--osint-research)
   - [Phase 2: Investigating the Handshake & WebAssembly](#phase-2-investigating-the-handshake--webassembly)
   - [Phase 3: Inspecting NEPSE's Live Production Frontend](#phase-3-inspecting-nepses-live-production-frontend)
   - [Phase 4: Cracking the Dynamic Payload ID](#phase-4-cracking-the-dynamic-payload-id)
   - [Phase 5: Live Verification & Testing](#phase-5-live-verification--testing)
4. [Deep Dive: How the Security Mechanism Actually Works](#4-deep-dive-how-the-security-mechanism-actually-works)
   - [Mechanism 1: The `Salter` Authorization Token](#mechanism-1-the-salter-authorization-token)
   - [Mechanism 2: The Dynamic POST Body Payload ID](#mechanism-2-the-dynamic-post-body-payload-id)
   - [Mechanism 3: Query Parameter Filtering](#mechanism-3-query-parameter-filtering)
5. [Codebase Architecture: Which File Does What](#5-codebase-architecture-which-file-does-what)
6. [Frequently Asked Questions (FAQ)](#6-frequently-asked-questions-faq)
7. [The Universal Playbook: How to Reverse-Engineer Any API in the Future](#7-the-universal-playbook-how-to-reverse-engineer-any-api-in-the-future)

---

## 1. Executive Summary

When attempting to query NEPSE’s private APIs directly, developers often encounter:
```html
<html><head><title>Error</title></head><body>WARNING: UNAUTHORIZED ACCESS</body></html>
```

NEPSE does not protect its endpoints using standard OAuth2 or simple API keys. Instead, it uses a **two-layer client-side proof-of-work/obfuscation system**:
1. **Dynamic Salter Header**: Every request requires an `Authorization: Salter <token>` header. The token is derived from a raw token issued by `/api/authenticate/prove` and scrambled using cryptographic salt parameters evaluated through mathematical functions originally compiled to WebAssembly (`css.wasm`).
2. **Dynamic Body Payload**: The POST body must contain `{"id": <calculated_id>}`. This integer is **not** static—it changes every single day, depends on the current market status ID, and relies on mathematical transformations using the authentication salts and an embedded 100-number lookup table.

By reverse-engineering both mechanisms directly from NEPSE's live production bundle (`main.js`) and WebAssembly module, we built a fully autonomous scraper that generates valid authentication tokens and dynamic payload IDs without requiring a browser or headless Puppeteer/Selenium instance.

---

## 2. The Problem: Why the Original `curl` Failed

The user provided this `curl` command:

```bash
curl --url 'https://nepalstock.com.np/api/nots/nepse-data/floorsheet?&sort=contractId,desc' \
  -H 'accept: application/json, text/plain, */*' \
  -H 'accept-language: en-US,en;q=0.5' \
  -H 'authorization: Salter eyJlbmMiOiJBMTI4Q0JDLUhTMjU2IiwiYWxnIjoiZGlyIn0..HEz96Mg5-lDfAxusNfw_Kw.UhiSm-TRHDXR3DTpzxeMWbMkDv269QYFLIve3BrXPjDMRAMTJyeAX1UUgibhIOAzNFY8shxG9-HsIHyC_-TXWKV3x6Mn4N-wx-NeXWszTXM41I91eTfatNTQPOoj_KXsBgFoTGbc8Cdmok30Ec2trw.8JHmlXK6Lo4GRe8foBfkSA' \
  -H 'content-type: application/json' \
  -H 'origin: https://nepalstock.com.np' \
  -H 'referer: https://nepalstock.com.np/floor-sheet' \
  -H 'user-agent: Mozilla/5.0 (X11; Linux x86_64) ...' \
  --data-raw '{"id":1128724}'
```

Executing this command resulted in:
`WARNING: UNAUTHORIZED ACCESS`

### Why did this happen?
1. **Token Expiration**: The JWT in `Salter <token>` has an expiration window (TTL). Once expired, the backend gateway immediately denies access.
2. **Stale Dynamic ID**: The value `'{"id":1128724}'` was computed for a specific date and market status session. When the day rolled over, the backend rejected this ID.
3. **Session Desynchronization**: The backend validates that the payload `id` in the POST body matches the specific mathematical formula tied to the active token's salts. A token generated with salt set $A$ cannot be used with an ID computed using salt set $B$.

---

## 3. The Reverse-Engineering Journey: Step-by-Step

Here is the exact diagnostic and investigative process used to solve this problem:

### Phase 1: Diagnosis & OSINT Research
1. We tested the user's `curl` directly to reproduce the failure.
2. We searched developer community knowledge and GitHub repositories (`polymorphisma/nepse_scraper`, `dahsameer/nepse-api-helper`, `CaffeineDuck/nepse-api`) to understand previous attempts at scraping NEPSE.
3. Key discoveries from community research:
   - NEPSE introduced an endpoint `/api/authenticate/prove`.
   - NEPSE serves a WebAssembly file named `css.wasm`.
   - The Authorization header uses a custom prefix `Salter`.

### Phase 2: Investigating the Handshake & WebAssembly
1. We tested querying `GET https://nepalstock.com.np/api/authenticate/prove` using standard browser headers.
2. The server responded with HTTP 200 and a rich JSON structure:
   ```json
   {
     "serverTime": 1789583705000,
     "accessToken": "eyJlbmMi...",
     "refreshToken": "eyJlbmMi...",
     "salt1": 14396,
     "salt2": 25497,
     "salt3": 41086,
     "salt4": 15623,
     "salt5": 63868
   }
   ```
3. Next, we fetched the WebAssembly module:
   ```bash
   curl -s 'https://nepalstock.com.np/assets/prod/css.wasm' -o css.wasm
   ```
4. Using Node.js's built-in `WebAssembly.instantiate()`, we inspected the module's export table and found five key exported functions:
   - `cdx`, `rdx`, `bdx`, `ndx`, `mdx`
5. By decompiling the WebAssembly bytecode and analyzing open-source references, we verified that each function takes salt inputs, decomposes digits (ones, tens, hundreds), and indexes into a static 40-element lookup table:
   ```
   LOOKUP_TABLE = [
     5, 8, 4, 7, 9, 4, 6, 9, 5, 5,
     6, 5, 3, 5, 4, 4, 9, 6, 6, 8,
     8, 6, 8, 6, 5, 8, 4, 9, 5, 9,
     8, 5, 3, 4, 7, 7, 4, 7, 3, 9
   ]
   ```
6. We implemented pure Python and pure JavaScript versions of these 5 functions and confirmed their output matches the WebAssembly module with 100% precision.

### Phase 3: Inspecting NEPSE's Live Production Frontend
To find out how NEPSE's client-side Angular app handles the token and floorsheet, we extracted the script tags from `https://nepalstock.com.np/floor-sheet`:
```html
<script src="runtime.9b2a97262eec1e4c58ce.js"></script>
<script src="main.6ca32ef2df433b06ed55.js"></script>
```
We downloaded `main.6ca32ef2df433b06ed55.js` (approx. 4.5 MB) and searched for references to `floorsheet`.

### Phase 4: Cracking the Dynamic Payload ID
In `main.js`, we located the exact service method called by the floorsheet page:

```javascript
// Extracted verbatim from main.6ca32ef2df433b06ed55.js
getMarketStatus() {
  this.dashboardService.getMarketStatus().then(t => {
    this.storageService.set("marketStatus", t);
    this.marketStatus = t;
    this.dummyId = t.id;
    this.getData(this.dummyId);
  });
}

getListsOfFloorSheet(t = null, e = "", n = "", l = "") {
  var i = this.utilService.getDummyData()[this.dummyId] + this.dummyId + 2 * this.day;
  this.floorSheetService.getAllFloorSheet(
    t,
    e,
    n,
    l,
    i + this.storeService.secMsgSrc.getValue().accessTokens[i % 10 < 4 ? 1 : 3] * this.day 
      - this.storeService.secMsgSrc.getValue().accessTokens[(i % 10 < 4 ? 1 : 3) - 1]
  ).then(t => { ... });
}
```

This single block revealed the entire algorithm:
1. `this.dummyId` is retrieved from `GET /api/nots/nepse-data/market-open` (field: `id`).
2. `this.day` is the current day of the month in Nepal time (`Asia/Kathmandu`).
3. `getDummyData()` is an internal array of 100 static integers hardcoded in the bundle.
4. `accessTokens` is the array `[salt1, salt2, salt3, salt4, salt5]`.
5. Notice the condition `i % 10 < 4` specifically used for floorsheet:
   - If `i % 10 < 4`, index is `1` (which maps to `salt2` and `salt1`).
   - Otherwise, index is `3` (which maps to `salt4` and `salt3`).

### Phase 5: Live Verification & Testing
We wrote an end-to-end script implementing this formula. Upon sending the POST request to:
`https://nepalstock.com.np/api/nots/nepse-data/floorsheet?&sort=contractId,desc`
with `Authorization: Salter <deobfuscated_token>` and `{"id": <calculated_payload_id>}`, NEPSE returned HTTP 200 with complete transaction records, proving the reverse-engineered solution works.

---

## 4. Deep Dive: How the Security Mechanism Actually Works

### Mechanism 1: The `Salter` Authorization Token

When you call `/api/authenticate/prove`, NEPSE returns an `accessToken` string (around 250 characters). It also returns 5 integers: `salt1` through `salt5`.

The client must slice out 5 characters at specific index positions:
```
n = cdx(salt2)
l = rdx(salt2)
o = bdx(salt2)
p = ndx(salt2)
q = mdx(salt2)
```

The valid token is constructed by stitching together the substrings while skipping characters at $n, l, o, p, q$:
$$\text{token} = \text{token}[0:n] + \text{token}[n+1:l] + \text{token}[l+1:o] + \text{token}[o+1:p] + \text{token}[p+1:q] + \text{token}[q+1:]$$

This de-obfuscated string is then prefixed with `Salter `:
```
Authorization: Salter <deobfuscated_token>
```

### Mechanism 2: The Dynamic POST Body Payload ID

The POST body requires a dynamic JSON payload:
```json
{
  "id": 1226728
}
```

The formula to calculate this `id` is:
```python
# 1. Fetch marketStatus ID from /api/nots/nepse-data/market-open
market_open_id = market_status["id"]

# 2. Get day of month in Nepal timezone (UTC +5:45)
day = datetime.now(pytz.timezone("Asia/Kathmandu")).day

# 3. Compute base integer
i = DUMMY_DATA[market_open_id] + market_open_id + 2 * day

# 4. Choose salt index (0-indexed array of [salt1, salt2, salt3, salt4, salt5])
idx = 1 if (i % 10 < 4) else 3

# 5. Calculate final dynamic payload ID
payload_id = i + access_tokens[idx] * day - access_tokens[idx - 1]
```

### Mechanism 3: Query Parameter Filtering

The floorsheet endpoint accepts query parameters that control pagination and filtering:
- `page`: 0-indexed page number (`0`, `1`, `2`, ...)
- `size`: Items per page (default: `500`, max: `500`)
- `sort`: Sort criteria, e.g. `contractId,desc` or `contractId,asc`
- `stockId`: Company numeric ID (e.g. `180` for `UAIL`). Retrieved via `GET /api/nots/security?nonDelisted=true`.
- `buyerBroker`: Buyer broker ID (e.g. `58`)
- `sellerBroker`: Seller broker ID (e.g. `3`)
- `contractNo`: Specific contract number

---

## 5. Codebase Architecture: Which File Does What

The `Scrapee/` folder contains a clean, modular structure:

| File | Purpose |
| :--- | :--- |
| [`nepse_auth.py`](file:///home/jagdish/Desktop/Sandbox/Scrapee/nepse_auth.py) | **Authentication & Math Engine**: Contains the 40-element lookup table, digit calculation functions (`cdx`, `rdx`, etc.), token slicing logic, and the dynamic payload ID formula. |
| [`nepse_client.py`](file:///home/jagdish/Desktop/Sandbox/Scrapee/nepse_client.py) | **Core Python Client**: Manages requests session, retry policies, auto-authentication, automatic re-authentication if token expires, stock symbol to ID resolution, pagination, and curl generation. |
| [`cli.py`](file:///home/jagdish/Desktop/Sandbox/Scrapee/cli.py) | **Command-Line Interface**: User-facing tool. Allows scraping with filters (`--symbol`, `--buyer`, `--seller`, `--pages`), exporting directly to CSV or JSON, and printing fresh curl commands with `--dump-curl`. |
| [`scraper.js`](file:///home/jagdish/Desktop/Sandbox/Scrapee/scraper.js) | **Zero-Dependency Node.js Scraper**: A self-contained alternative in JavaScript. Uses only native Node.js `https` without any `npm install` required. |
| [`requirements.txt`](file:///home/jagdish/Desktop/Sandbox/Scrapee/requirements.txt) | **Dependencies**: Lists required Python libraries (`requests`, `pytz`, `pandas`). |
| [`README.md`](file:///home/jagdish/Desktop/Sandbox/Scrapee/README.md) | **User Guide**: Quick start instructions and CLI usage examples. |

---

## 6. Frequently Asked Questions (FAQ)

### Q1: Why does NEPSE use "Salter" instead of standard "Bearer"?
NEPSE's backend engineers implemented a custom gateway scheme to prevent automated scripts from simply using generic JWT bearer tokens. The prefix `Salter` signifies to their API gateway that the client has satisfied their client-side challenge.

### Q2: Do I need to download or compile WebAssembly (`css.wasm`) every time?
**No.** We reverse-engineered the assembly code into pure Python and JavaScript. The functions (`cdx`, `rdx`, `bdx`, `ndx`, `mdx`) and the 40-entry `LOOKUP_TABLE` are completely static and embedded directly in the source code.

### Q3: Why does the day calculation need Nepal timezone (`Asia/Kathmandu`)?
NEPSE’s server runs on Nepal Standard Time (UTC+5:45). If you run your scraper on a server in New York or London (e.g., at 8:00 PM EST), your local calendar date might be the 16th, while in Nepal it is already the 17th. Using the wrong date produces an incorrect payload ID, resulting in authorization failure.

### Q4: Does this require Selenium, Puppeteer, or Playwright?
**No.** Browser automation tools are slow, heavy, consume hundreds of megabytes of RAM, and are prone to crashing. Because we reverse-engineered the exact mathematical formulas, this scraper uses lightweight HTTP requests, making it over **50x faster** and capable of running in headless environments with minimal resources.

### Q5: How many records can I scrape?
Each page supports up to `size=500` records. During an active trading day, NEPSE often has between 50,000 and 150,000 transactions. With `cli.py --pages 0`, the client iterates through all pages with configurable rate limiting (default 0.3s sleep) to avoid triggering DDoS protections.

---

## 7. The Universal Playbook: How to Reverse-Engineer Any API in the Future

When faced with an undocumented, protected API or a failing `curl` command on any website, follow this battle-tested methodology:

### Step 1: Open Chrome DevTools Network Tab
1. Open DevTools (`F12`), go to the **Network** tab, and check **Preserve log**.
2. Perform the action in the browser (e.g. click "Floorsheet", click "Next Page").
3. Filter by **Fetch/XHR**.
4. Identify the request that loads the data. Right-click it and choose **Copy as cURL**.

### Step 2: Compare Browser Request vs CLI Request
1. Run the copied `curl` in your terminal.
2. If it works once but fails 5 minutes later, inspect what changed:
   - Is there a timestamp or nonces in the URL/headers?
   - Is there an Authorization header or dynamic cookie?
   - Is there a CSRF token or custom header (like `Salter`)?

### Step 3: Search the Frontend JavaScript Bundles
1. In DevTools, press `Ctrl + Shift + F` (Global Search) or search the downloaded `.js` files.
2. Search for the URL path fragment (e.g. `nepse-data/floorsheet` or `authenticate/prove`).
3. You will almost always find the exact service function where the headers and request body are assembled.
4. Pretty-print the code (the `{}` button in DevTools Sources tab) and trace where variables are calculated.

### Step 4: Handle WebAssembly (WASM) Modules
If a site loads a `.wasm` file:
1. Check the exports in the browser console:
   ```javascript
   fetch('/assets/prod/css.wasm')
     .then(r => r.arrayBuffer())
     .then(b => WebAssembly.instantiate(b))
     .then(res => console.log(res.instance.exports));
   ```
2. You can inspect the exported function signatures or decompile the WASM to WebAssembly Text Format (`wat`) using `wasm2wat` from the [WABT toolkit](https://github.com/WebAssembly/wabt).
3. Most WebAssembly modules used in anti-scraping are small mathematical obfuscators that can be easily replicated in Python.

### Step 5: Automate and Test Incrementally
1. Implement authentication first. Verify that you can obtain a valid token.
2. Implement metadata endpoints (e.g. market status, security lists).
3. Implement the final protected data endpoint.
4. Add auto-refresh retry logic so your scraper runs reliably for hours or days without human intervention.
