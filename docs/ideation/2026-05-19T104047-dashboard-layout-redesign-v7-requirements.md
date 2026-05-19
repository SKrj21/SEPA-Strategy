# Dashboard Layout Redesign — Overview Depot Summary Table

*Date: 2026-05-19 11:05*
*Session: 2026-05-19T104047-dashboard-layout-redesign-v7*

## Problem

The current Overview tab buries depot health information behind individual depot tabs. To assess how all depots are performing, a user must navigate to each tab separately — multiple clicks with no side-by-side comparison. There is no single view that answers "which depot needs attention right now?" at a glance, and no persistent indicator showing whether the displayed data is fresh.

## Goal

Depot operators can assess the health of all depots at a glance from a single Overview screen — seeing stock counts, average Score, and signal-tier distribution per depot — and can see at a glance whether the data is current and trigger a re-scan without leaving the page.

## Success Metrics

- **Leading indicators** (observable while the work is in flight, predict the outcome):
  - 4 out of 5 first-time readers can correctly identify which depot has the most urgent signals by reading the Overview table alone, within 30 seconds, without guidance
  - All five signal tiers (Buy, Bullish, Neutral, Bearish, Sell-Panic) appear as separate labelled columns in the depot summary table after a real scan completes

- **Lagging indicators** (the outcome itself, observable only after it has occurred):
  - The primary user opens the Overview tab first in at least 8 of 10 consecutive morning sessions within one week of deploy, without navigating to an individual depot tab first
  - At least 80% of daily review sessions begin on the Overview tab within two weeks of deploy

## Assumptions

*Ordered highest to lowest risk; the riskiest entry is marked `(R)`.*

- The existing `depot_results` pipeline in `app.py` may not carry pre-aggregated per-depot signal counts, forcing a structural change that touches `screener.py` or `classifier.py` and violates the constraints (R)
- Streamlit's `st.dataframe` may render the depot summary table poorly on narrow screens (column overflow, truncation), requiring CSS overrides that add scope
- The `depot_config.json` structure or auto-discovery fallback may produce inconsistent depot metadata across runs, making it hard to build a stable summary row
- Users may find the depot table informative but still click into individual tabs for every session, because the table shows counts but not which stocks

## Constraints

- All 193 existing tests must remain green; `screener.py`, `indicators.py`, and `classifier.py` must not be modified
- No new pip dependencies — layout changes use Streamlit's built-in components only
- The layout must work with both `depot_config.json` and the single-depot auto-discovery fallback

## Non-goals

- VCP Breakout detection — separate feature initiative
- Three-stage exit monitor — separate feature initiative
- FX / currency conversion — separate feature initiative
- Renaming the five signal tiers (Buy/Bullish/Neutral/Bearish/Sell-Panic remain unchanged)
- Clickable rows in the depot summary table linking to individual depot tabs

## Outcome

After this ships, the Overview tab shows:

1. **Status bar**: a scan-completed indicator with timestamp ("Scan completed • HH:MM:SS"), last scan date/time, and a configurable auto-scan countdown (default 60 minutes) with a visible Re-scan button — all on one line at the top of the page
2. **Depot-Übersicht table**: one row per depot with columns Depot | Stocks | Score Ø | Buy | Bullish | Neutral | Bearish | Sell-Panic | Errors, plus a GESAMT (total) row at the bottom; signal count cells are colour-coded to match the per-depot tab styling
3. **Per-depot tabs**: unchanged — each depot tab continues to show Buy Signals, All Results, and Detail Chart sub-tabs

Users can assess all depots in under 10 seconds and trigger a re-scan or navigate to a specific depot's detail tab from the same starting point.

## Sketch

**Status bar (top of page, always visible):**
```
✅ Scan completed • 12:34:32   |   Last scan: 19.05.2026 12:34:32   |   Next auto-scan in 58:43   [🔄 Re-scan]
```

**Depot summary table (Depot-Übersicht):**

| Depot          | Stocks | Score Ø | 🟢 Buy | 🟡 Bullish | ⚪ Neutral | 🔴 Bearish | 🔴 Sell-Panic | ❌ Errors |
|----------------|--------|---------|--------|-----------|----------|-----------|-------------|---------|
| Trade Republic | 104    | 82.3    | 3      | 18        | 45       | 30        | 8           | 6       |
| SmartBroker+   | 36     | 71.4    | 1      | 5         | 15       | 12        | 3           | 1       |
| **Total**      | **140**| **79.8**| **4**  | **23**    | **60**   | **42**    | **11**      | **7**   |

Score Ø = mean RS Rating across all screened stocks in the depot (excluding stocks with no RS Rating).
Errors = count of ISINs that failed to resolve to a ticker symbol.

The existing per-depot tabs (Trade Republic, SmartBroker+, etc.) are untouched.

## Open Questions

- Should the countdown timer in the status bar update live (requires JS/autorefresh polling), or show the configured interval at scan time and remain static until the next scan?
- Should the status bar be visible on per-depot tabs as well, or only on the Overview tab?
