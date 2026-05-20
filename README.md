# SEPA Strategy Screener

A Streamlit application that screens stock portfolios against Mark Minervini's **SEPA Trend Template** (Specific Entry Point Analysis), classifies each stock into one of seven signal tiers, and presents the results in an interactive multi-depot dashboard.

## Features

- **8-condition SEPA trend template** — all Minervini criteria evaluated per stock
- **7-tier signal classifier** — Buy → Bullish → Recovered → Neutral → Warning → Chronic → Sell-Panic
- **Relative Strength (RS) Rating** — percentile rank vs. SPY benchmark (1–99)
- **Multi-depot support** — one tab per broker file; or use `depot_config.json` for named depots
- **Company names** — resolved from your broker CSV, with yfinance as fallback
- **ISIN resolution** — Smartbroker, Trade Republic, and ISIN reference lists supported
- **Detail chart** — price + SMA overlay + volume for any selected ticker
- **Auto-refresh** — configurable interval via sidebar

## Signal Tiers

| Signal | Conditions | RS Rating |
|---|---|---|
| 🟢 **Buy** | All 8 met | ≥ 85 |
| 📈 **Bullish** | ≥ 6 met | ≥ 50 |
| 🔵 **Recovered** | ≥ 4 met | ≥ 50 |
| 🟡 **Neutral** | ≥ 4 met | < 50 |
| 🟠 **Warning** | ≥ 2 met | any |
| ⚫ **Chronic** | 0–1 met | ≥ 10 |
| 🔴 **Sell-Panic** | any | < 10 (override) |

## SEPA Conditions

1. Price above 50-day SMA
2. Price above 150-day SMA
3. Price above 200-day SMA
4. 50-day SMA above 150-day SMA
5. 50-day SMA above 200-day SMA
6. 200-day SMA in uptrend (positive slope)
7. Price within 25% of 52-week high
8. Price at least 30% above 52-week low

## Installation

```bash
git clone https://github.com/SKrj21/SEPA-Strategy.git
cd SEPA-Strategy
pip install -r requirements.txt
streamlit run app.py
```

## Depot Setup

### Option A — Auto-discovery (no config needed)

Place one or more broker CSV files in the project root or a `depot/` subfolder. Each file becomes its own tab. Supported formats:

| Broker | Format | Key columns |
|---|---|---|
| Smartbroker | `;`-separated | `ISIN`, `WKN`, `ASSETKLASSE`, `Bezeichnung` |
| Trade Republic | `;`-separated | `ISIN`, `Name`, `Stücke` |
| ISIN reference | `;`-separated | `ISIN`, `Name` |
| Ticker list | `,`-separated | `Ticker`, `Name` (or `Unternehmen`) |

> **WKN support:** Smartbroker exports include a `WKN` column. The screener uses WKN codes as a priority lookup hint (before ISIN) because Yahoo Finance resolves German stocks more reliably via WKN.

Sample files are included in `depot/`:
- `DAX40.csv` — DAX 40 constituents with direct tickers (`Ticker`, `Unternehmen`, `ISIN`, `WKN`)
- `USstocks.csv` — US large-cap selection (ISIN format)

### Option B — Named depots (`depot_config.json`)

Create a `depot_config.json` in the project root:

```json
{
  "depots": [
    { "name": "My Portfolio", "files": ["depot/MyBroker.csv"] },
    { "name": "Watchlist",    "files": ["depot/watchlist.csv"] }
  ]
}
```

> **Note:** Personal broker exports (`Smartbroker.csv`, `tr_depot.csv`) are excluded from version control via `.gitignore`. Add your own files locally.

## Project Structure

```
├── app.py              # Streamlit UI
├── classifier.py       # 7-tier signal classifier
├── screener.py         # SEPA condition evaluation
├── indicators.py       # SMA, RS Rating, breakout detection
├── data_fetcher.py     # yfinance OHLCV + company names
├── csv_loader.py       # Broker CSV parsing & ISIN extraction
├── isin_resolver.py    # ISIN → ticker resolution
├── charts.py           # Plotly detail chart
├── depot/              # Sample depot CSV files
├── tests/              # 206 unit tests (pytest)
└── requirements.txt
```

## Running Tests

```bash
pytest tests/ -v
```

206 tests covering the classifier, screener, indicators, CSV loader, and ISIN resolver.

## Requirements

- Python 3.11+
- See `requirements.txt` for dependencies (streamlit, pandas, yfinance, plotly, scipy)
