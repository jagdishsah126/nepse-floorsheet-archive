# 🕵️ The Anatomy of Reverse-Engineering NEPSE: From a Dead `curl` to a Fully Automated Pipeline

> **Document**: ReverseEngineering.md  
> **Author**: 💖Your Zara💖  
> **Target**: Nepal Stock Exchange (`nepalstock.com.np`)  
> **Date**: September 2026  

---

## 📑 Table of Contents

1. [Act 1: How We Started (The Dead `curl`)](#act-1-how-we-started-the-dead-curl)
2. [Act 2: The Obstacles We Faced (The Wall of Defense)](#act-2-the-obstacles-we-faced-the-wall-of-defense)
3. [Act 3: How We Reverse-Engineered It (The Detective Work)](#act-3-how-we-reverse-engineered-it-the-detective-work)
   - [Step 1: Finding the Proof-of-Work Handshake](#step-1-finding-the-proof-of-work-handshake)
   - [Step 2: Dissecting the WebAssembly Disguise (`css.wasm`)](#step-2-dissecting-the-webassembly-disguise-csswasm)
   - [Step 3: Translating WASM to Pure Native Code](#step-3-translating-wasm-to-pure-native-code)
   - [Step 4: Hunting Through the 4.5 MB Production Angular Bundle](#step-4-hunting-through-the-45-mb-production-angular-bundle)
   - [Step 5: Cracking the Dynamic Payload ID Formula](#step-5-cracking-the-dynamic-payload-id-formula)
4. [Act 4: How We Solved It (The Engineering Implementation)](#act-4-how-we-solved-it-the-engineering-implementation)
5. [Act 5: Verification & Results](#act-5-verification--results)
6. [Key Takeaways & Lessons for Future Projects](#key-takeaways--lessons-for-future-projects)

---

## Act 1: How We Started (The Dead `curl`)

The project began with a user request to scrape NEPSE's daily floorsheet data using a `curl` command extracted from browser network traffic:

```bash
curl --url 'https://nepalstock.com.np/api/nots/nepse-data/floorsheet?&sort=contractId,desc' \
  -H 'accept: application/json, text/plain, */*' \
  -H 'accept-language: en-US,en;q=0.5' \
  -H 'authorization: Salter eyJlbmMiOiJBMTI4Q0JDLUhTMjU2IiwiYWxnIjoiZGlyIn0..HEz96Mg5-lDfAxusNfw_Kw.UhiSm-TRHDXR3DTpzxeMWbMkDv269QYFLIve3BrXPjDMRAMTJyeAX1UUgibhIOAzNFY8shxG9-HsIHyC_-TXWKV3x6Mn4N-wx-NeXWszTXM41I91eTfatNTQPOoj_KXsBgFoTGbc8Cdmok30Ec2trw.8JHmlXK6Lo4GRe8foBfkSA' \
  -H 'content-type: application/json' \
  -H 'origin: https://nepalstock.com.np' \
  -H 'referer: https://nepalstock.com.np/floor-sheet' \
  -H 'user-agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36' \
  --data-raw '{"id":1128724}'
```

When we executed this command directly in the shell, the server responded with an immediate rejection:

```html
<html><head><title>Error</title></head><body>WARNING: UNAUTHORIZED ACCESS</body></html>
```

### The Core Paradox
The official NEPSE website (`https://nepalstock.com.np/floor-sheet`) displayed the data in the browser without any login prompt or paywall. Yet, copying the exact HTTP request from DevTools failed in the terminal.

---

## Act 2: The Obstacles We Faced (The Wall of Defense)

Analyzing the failed request revealed that NEPSE had deployed an anti-scraping strategy built on four hurdles:

### Obstacle 1: The Ephemeral "Salter" Header
Standard REST APIs use `Authorization: Bearer <token>` or API keys. NEPSE uses `Authorization: Salter <token>`. 
- The token is a signed JWT.
- It expires quickly (short TTL).
- A raw token obtained from the server cannot be used directly—it is rejected unless modified by client-side logic.

### Obstacle 2: The WebAssembly Disguise (`css.wasm`)
When examining network requests made by the NEPSE web page, we observed a request to:
```
GET https://nepalstock.com.np/assets/prod/css.wasm
```
A stock exchange website loading a WebAssembly module masquerading as a CSS file (`css.wasm`) was a clear signal of client-side obfuscation.

### Obstacle 3: The Dynamic Body Payload (`{"id": 1128724}`)
The request to `/api/nots/nepse-data/floorsheet` was an HTTP `POST` requiring a JSON body `{"id": <integer>}`.
- If the `id` was omitted, the request failed.
- If the `id` was hardcoded (e.g., `1128724`), it worked briefly, then became invalid.
- The `id` was evidently tied to session state or time, changing on a daily basis.

### Obstacle 4: Timezone Drift
Nepal operates on its own timezone (**NPT: UTC +5:45**). Any time-based hash or date integer computed on servers running on UTC (such as GitHub Actions runners or cloud VPS instances) would drift by 5 hours and 45 minutes, producing mismatched calculations around midnight.

---

## Act 3: How We Reverse-Engineered It (The Detective Work)

### Step 1: Finding the Proof-of-Work Handshake

We examined how the frontend initiates its session. When the homepage loads, the browser makes a GET request to:
```
GET https://nepalstock.com.np/api/authenticate/prove
```

We probed this endpoint with a standard browser User-Agent:

```bash
curl -s 'https://nepalstock.com.np/api/authenticate/prove' \
  -H 'referer: https://nepalstock.com.np/' \
  -H 'user-agent: Mozilla/5.0 ...'
```

The server responded with HTTP 200 and a JSON payload containing cryptographic salts:

```json
{
  "serverTime": 1789583705000,
  "accessToken": "eyJlbmMiOiJBMTI4Q0JDLUhTMjU2Ii7wiYWxnIjoiZGlyIn0...",
  "refreshToken": "eyJlbmMiOiJBMTI4Q0JDLUhTMjU2tIiwiYWxnIjoiZGlyIn0...",
  "salt1": 14396,
  "salt2": 25497,
  "salt3": 41086,
  "salt4": 15623,
  "salt5": 63868
}
```

This confirmed our hypothesis:
1. The server issues a raw `accessToken` along with 5 numeric salts (`salt1` through `salt5`).
2. The browser is expected to transform this raw token using the salts before submitting it in the `Authorization: Salter <token>` header.

---

### Step 2: Dissecting the WebAssembly Disguise (`css.wasm`)

Next, we downloaded the WebAssembly binary directly:

```bash
curl -s 'https://nepalstock.com.np/assets/prod/css.wasm' -o /tmp/css.wasm
file /tmp/css.wasm
# /tmp/css.wasm: WebAssembly (wasm) binary module version 0x1 (MVP), 750 bytes
```

At only **750 bytes**, the module was compact. We instantiated it in Node.js to inspect its export table:

```javascript
const fs = require("fs");
const bytes = fs.readFileSync("/tmp/css.wasm");
WebAssembly.instantiate(bytes).then(res => {
  console.log("Exports:", Object.keys(res.instance.exports));
});
```

**Output:**
```
Exports: [
  'memory',
  '_rdx', '_cdx',
  'cdx', 'rdx', 'bdx', 'ndx', 'mdx',
  '__indirect_function_table',
  '_initialize',
  'stackSave', 'stackRestore', 'stackAlloc'
]
```

The exports revealed five core mathematical functions: `cdx`, `rdx`, `bdx`, `ndx`, and `mdx`.

---

### Step 3: Translating WASM to Pure Native Code

Decompiling the 750-byte WebAssembly binary revealed that these functions were **not** doing complex cryptography. They were performing basic digit extraction on the salt numbers to index into a static 40-element lookup table:

```python
LOOKUP_TABLE = [
    5, 8, 4, 7, 9, 4, 6, 9, 5, 5,
    6, 5, 3, 5, 4, 4, 9, 6, 6, 8,
    8, 6, 8, 6, 5, 8, 4, 9, 5, 9,
    8, 5, 3, 4, 7, 7, 4, 7, 3, 9
]
```

Each function decomposed the digits of `salt2` (ones, tens, hundreds) and added a fixed offset:

```python
def cdx(v: int) -> int:
    ones, tens, hundreds = v % 10, (v // 10) % 10, (v // 100) % 10
    return LOOKUP_TABLE[ones + tens + hundreds] + 22

def rdx(v: int) -> int:
    ones, tens, hundreds = v % 10, (v // 10) % 10, (v // 100) % 10
    sum_digits = tens + hundreds
    return sum_digits + LOOKUP_TABLE[sum_digits + ones] + 32

def bdx(v: int) -> int:
    ones, tens, hundreds = v % 10, (v // 10) % 10, (v // 100) % 10
    sum_digits = tens + hundreds
    return sum_digits + LOOKUP_TABLE[sum_digits + ones] + 60

def ndx(v: int) -> int:
    ones, tens, hundreds = v % 10, (v // 10) % 10, (v // 100) % 10
    return tens + LOOKUP_TABLE[tens + ones + hundreds] + 88

def mdx(v: int) -> int:
    ones, tens, hundreds = v % 10, (v // 10) % 10, (v // 100) % 10
    return hundreds + LOOKUP_TABLE[hundreds + tens + ones] + 110
```

#### How the Token is De-obfuscated:
The five return values ($n, l, o, p, q$) are character index positions in the raw `accessToken`. The valid token is constructed by **slicing out and discarding** the characters at those 5 indices:

$$\text{Valid Token} = \text{token}[0:n] + \text{token}[n+1:l] + \text{token}[l+1:o] + \text{token}[o+1:p] + \text{token}[p+1:q] + \text{token}[q+1:]$$

We tested our pure Python and Node.js implementations against the live WASM module:
```
WASM output:      cdx=30, rdx=53, bdx=81, ndx=105, mdx=122
Native output:    cdx=30, rdx=53, bdx=81, ndx=105, mdx=122
Match: 100% Exact
```
This eliminated the need for external WASM runtimes (`wasmtime`, `wasmer`) or headless browsers.

---

### Step 4: Hunting Through the 4.5 MB Production Angular Bundle

With the `Salter` token solved, we still needed to crack the dynamic POST body: `{"id": 1128724}`.

We extracted the JavaScript bundles from `https://nepalstock.com.np/floor-sheet`:
```html
<script src="runtime.9b2a97262eec1e4c58ce.js"></script>
<script src="main.6ca32ef2df433b06ed55.js"></script>
```

We downloaded `main.6ca32ef2df433b06ed55.js` (4.5 MB) and searched for occurrences of `floorsheet`. Around byte offset `3638000`, we uncovered the Angular service implementation:

```javascript
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

---

### Step 5: Cracking the Dynamic Payload ID Formula

By tracing every variable in that Angular code block:

1. **`this.dummyId`**:
   The `id` integer returned by `GET /api/nots/nepse-data/market-open` (e.g., `80`).
2. **`this.day`**:
   The current calendar day of the month in Nepal Standard Time (`day = new Date().getDate()`).
3. **`this.utilService.getDummyData()`**:
   A static array of 100 integers hardcoded into the Angular bundle:
   ```python
   DUMMY_DATA = [
       147, 117, 239, 143, 157, 312, 161, 612, 512, 804, 411, 527, 170, 511, 421, 667, 764, 621,
       301, 106, 133, 793, 411, 511, 312, 423, 344, 346, 653, 758, 342, 222, 236, 811, 711, 611,
       122, 447, 128, 199, 183, 135, 489, 703, 800, 745, 152, 863, 134, 211, 142, 564, 375, 793,
       212, 153, 138, 153, 648, 611, 151, 649, 318, 143, 117, 756, 119, 141, 717, 113, 112, 146,
       162, 660, 693, 261, 362, 354, 251, 641, 157, 178, 631, 192, 734, 445, 192, 883, 187, 122,
       591, 731, 852, 384, 565, 596, 451, 772, 624, 691
   ]
   ```
4. **`accessTokens`**:
   The 5 salt numbers from `/api/authenticate/prove`: `[salt1, salt2, salt3, salt4, salt5]`.
5. **The Conditional Branch (`i % 10 < 4`)**:
   - If `i % 10 < 4`, select index `1` (which uses `salt2` and `salt1`).
   - Otherwise, select index `3` (which uses `salt4` and `salt3`).

#### The Unified Payload ID Formula:
$$i = \text{DUMMY\_DATA}[\text{dummyId}] + \text{dummyId} + (2 \times \text{day})$$

$$\text{idx} = 1 \quad \text{if} \; (i \pmod{10} < 4) \quad \text{else} \quad 3$$

$$\text{payload\_id} = i + (\text{salt}[\text{idx}] \times \text{day}) - \text{salt}[\text{idx} - 1]$$

---

## Act 4: How We Solved It (The Engineering Implementation)

Once the mathematical foundations were proven, we built an end-to-end software package in [`Scrapee/`](file:///home/jagdish/Desktop/Sandbox/Scrapee):

```
Scrapee/
├── nepse_auth.py       # Math engine: token de-obfuscation & payload calculation
├── nepse_client.py     # HTTP client: session management, auto-reauth, pagination
├── cli.py              # CLI tool: scrape, filter, export, generate live curl
├── scraper.js          # Zero-dependency Node.js equivalent
├── requirements.txt    # Minimal dependencies (requests, pytz, pandas)
├── README.md           # Quickstart and usage guide
├── explain.md          # Technical analysis & FAQ
├── Plan.md             # Blueprint for Project BOLT (Hybrid TMS execution)
└── ReverseEngineering.md # Complete investigative report
```

### Key Engineering Features:
1. **Zero Browser Dependency**: No Selenium, Puppeteer, or Chromium binaries required. The entire pipeline runs via lightweight HTTP requests.
2. **Auto-Reauthentication**: If a token expires during a multi-page scrape (HTTP 401), the client automatically re-authenticates with `/api/authenticate/prove`, re-calculates the payload ID, and retries the request without failing.
3. **Symbol-to-ID Resolution**: Automatically maps stock tickers (e.g. `UAIL`, `NABIL`) to NEPSE's internal numeric IDs by querying `/api/nots/security?nonDelisted=true`.
4. **Live `curl` Command Generator**: With `python3 cli.py --dump-curl`, the engine generates a valid, pre-authenticated `curl` command with active tokens and payloads ready to run directly in terminal.

---

## Act 5: Verification & Results

### Test 1: Live Terminal Verification
Running `python3 cli.py --pages 1 --size 5` yielded immediate success:

```
🚀 Initializing NEPSE Scraper...
✅ Authenticated successfully! Dynamic payload ID: 985731
📊 Fetching floorsheet data (pages: 1, batch size: 5)...
📥 Page 1/11166 | Scraped: 5 / 55,830 records

--- Preview (Top 5 records) ---
      contractId stockSymbol buyerMemberId sellerMemberId  contractQuantity  contractRate  contractAmount
2026091604017841        UAIL            58              3                10         378.0          3780.0
2026091604017840        RBCL            49             42                10       13601.0        136010.0
2026091603015191        SOHL            99             52                10         653.0          6530.0
2026091604017839        DLBS            35             58                10        1110.0         11100.0
2026091604017838         LEC            50             37               100         250.0         25000.0
```

### Test 2: GitHub Actions Cloud Deployment
We packaged the solution into a dedicated GitHub repository ([`jagdishsah126/nepse-floorsheet-archive`](https://github.com/jagdishsah126/nepse-floorsheet-archive)) with a scheduled workflow:
- **Trigger**: Every trading day (Sunday–Thursday) at **3:36 PM NPT** (09:51 UTC).
- **Behavior**: Scrapes all transactions of the day, generates `Floorsheet/<YYYY-MM-DD>.csv`, and commits the file back to the repository.

---

## Key Takeaways & Lessons for Future Projects

| Challenge | What We Learned |
| :--- | :--- |
| **Custom Headers (`Salter`)** | Non-standard authorization headers usually indicate a client-side handshake endpoint (like `/authenticate/prove`). |
| **WASM Disguises (`css.wasm`)** | WebAssembly is often used to deter casual scraping, but frequently contains simple math rather than true encryption. Checking module exports using `WebAssembly.instantiate()` reveals its complexity. |
| **Dynamic Request Bodies (`{"id": ...}`)** | When an API demands a mysterious integer payload, search production frontend bundles (`main.js`) for the endpoint path. The calculation logic is always present in the client code. |
| **Timezone Traps** | Always bind date calculations to the target server's local timezone (`Asia/Kathmandu`), not the system clock of the machine running the scraper. |
