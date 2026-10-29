# NOTICE — Data Source, Ownership & Contact

> Please read alongside the [README](README.md). This notice explains where the data in
> this repository comes from, who owns it, what it is published for, and how to reach us.

---

## 1. Data Source

All market data published in this repository (`Floorsheet/`, `Summary/` and derived files)
is obtained from the **complete daily transaction floorsheet that the Nepal Stock Exchange
Limited (NEPSE) publishes publicly on its own website**:

- NEPSE official website: <https://www.nepalstock.com.np/>
- Source document: the publicly downloadable daily "Floorsheet" report
- Retrieval method: automated, polite, once-per-trading-day retrieval (see
  [`ReverseEngineering.md`](ReverseEngineering.md) for the technical context)

No data here is fabricated, estimated or combined from third-party vendors.

## 2. Ownership & Attribution

- **The underlying market data remains the property of Nepal Stock Exchange Limited (NEPSE).**
  This repository claims no ownership of the data and acknowledges NEPSE as its sole source.
- The archive, formatting and pipeline code in this repository is the work of the
  repository author.
- "NEPSE" and related names and marks are used **nominatively** — solely to identify the
  data source — and remain the property of their owner.

## 3. Purpose of Publication

The archive exists to preserve and widely publish **factual, transaction-level public market
data** so that:

- small retail investors, students and independent researchers in Nepal can access the same
  data set for free that institutional players buy commercially;
- trading-behavior studies (broker concentration, odd-lot activity, etc.) can be replicated
  and audited against immutable records.

Factual price, volume and counterparty information in official public reports constitutes
functional data rather than creative expression; republishing it with clear attribution is
intended as a public-interest service, not competition with any commercial data vendor.

## 4. No Affiliation / Not Endorsed

This is an independent, non-commercial, open-source project. It is **not** affiliated with,
sponsored by, endorsed by, or authorized by NEPSE, the Securities Board of Nepal (SEBON) or
any stockbroker. Accuracy of the data mirrors the official source; anything wrong is fixed
against that source.

## 5. Removal / Correction Requests

If you are a rightsholder, an exchange regulator, or NEPSE itself, and you believe any part
of this repository should be changed or removed:

1. Open a GitHub issue at
   <https://github.com/jagdishsah126/nepse-floorsheet-archive/issues>
   (preferred — creates a public, immutable record of the request), **or**
2. reach the maintainer via their GitHub profile
   <https://github.com/jagdishsah126>.

Requests will be reviewed promptly; the repository maintainer commits to good-faith
cooperation and timely resolution.

## 6. Warranty Disclaimer

Data and code are provided **as-is, without warranty of any kind**. Publication of a file
here is not financial advice and creates no liability for trading decisions made using it.
