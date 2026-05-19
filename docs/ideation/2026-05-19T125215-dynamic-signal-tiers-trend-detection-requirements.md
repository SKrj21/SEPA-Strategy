# Dynamic Signal Tiers — 7-Tier Direction-Aware Classification

*Date: 2026-05-19 12:52*
*Session: 2026-05-19T125215-dynamic-signal-tiers-trend-detection*

## Problem

The current 5-tier system (Buy / Bullish / Neutral / Bearish / Sell-Panic) classifies stocks based on a point-in-time snapshot of SEPA conditions and RS Rating. It cannot distinguish a stock that has just started deteriorating from one that has been stuck weak for weeks, and it offers no signal for stocks recovering from weakness. Users act too late — the stock is already deep in Sell-Panic before the deterioration is visible in the tier label.

## Goal

Users can identify deteriorating stocks 1–2 scans earlier and recovering stocks before they re-qualify for Buy, by replacing the 5-tier snapshot system with a 7-tier classification — Buy / Bullish / Recovered / Neutral / Warning / Chronic / Sell-Panic — derived purely from the current scan's SEPA conditions count and RS Rating, with no historical scan storage required. The Buy signal is simultaneously tightened from RS ≥ 70 to RS ≥ 85, reducing false Buy signals in stocks with weak momentum.

## Success Metrics

- **Leading indicators** (observable while the work is in flight, predict the outcome):
  - After deploying on a live dataset, at least one stock is visible in the Warning tier that would have shown Neutral or Bearish under the old 5-tier system on the same scan data (spot-checkable by running both classifiers on the same row)
  - At least one stock currently in Buy under the old system (RS 70–84, 8 conditions) drops to Bullish under the new system, confirming the RS ≥ 85 tightening is active

- **Lagging indicators** (the outcome itself, observable only after it has occurred):
  - Within 3 weeks of deploy, the user exits at least one position earlier than under the old system, explicitly triggered by a Warning tier label
  - The Recovered tier surfaces at least one re-entry candidate per month that the old Neutral label would have obscured

## Assumptions

*Ordered highest to lowest risk; the riskiest entry is marked `(R)`.*

- The 2–3 condition Warning boundary produces a useful signal-to-noise ratio in normal market conditions — during a broad market correction, many stocks simultaneously drop to 2–3 conditions, making Warning fire for the entire portfolio simultaneously and losing actionability (R)
- The RS ≥ 85 Buy threshold reclassifies some currently-Buy stocks to Bullish; the user accepts this tightening and will not treat the Bullish tier as a substitute Buy trigger
- The existing `classify_signal()` function signature is unchanged; however, the tier label strings it returns change from `{"Bearish", "Neutral"}` to `{"Warning", "Chronic", "Recovered", "Neutral"}` — all call sites in `app.py` that string-match tier labels (colour mapping, Buy-signal filters, sound alerts) must be updated atomically with the classifier change or they will silently misclassify
- Stocks with 8 conditions met but RS 50–84 are correctly classified as Bullish; users accept that perfect SEPA alignment without strong RS momentum is not a Buy signal

## Constraints

- All existing tests must remain green after the classifier update; test files must be updated to reflect the new tier names and thresholds, but `screener.py` and `indicators.py` must not be modified
- No new pip dependencies
- No external data sources beyond yfinance (already used per scan)
- No scan-history storage — all 7 tiers are derived from a single scan's current data

## Non-goals

- Historical scan log / persistence (JSON, SQLite, CSV append) — not needed for this tier system
- Per-user adjustable thresholds via the sidebar — thresholds are hardcoded defaults, adjustable in code only
- VCP Breakout detection, three-stage exit monitor, FX conversion — separate initiatives
- Keeping the old 5-tier system as a runtime toggle alongside the new 7-tier system

## Outcome

After this ships, a user scanning their depot sees:
- **Warning** labels on stocks that are beginning to fail SEPA criteria (2–3 conditions met), before they reach Sell-Panic — giving 1–2 scans of earlier visibility into deterioration
- **Recovered** labels on stocks rebuilding from weakness (4–5 conditions, RS ≥ 50), surfacing potential re-entry candidates that the old Neutral label lumped together with stuck stocks
- **Chronic** labels on stocks that have fully failed SEPA conditions (0–1 conditions met, RS ≥ 10) but have not hit the RS < 10 panic threshold — making it clear these are held positions needing a decision
- **Fewer Buy signals** overall, because the Buy RS floor rises from 70 to 85 — stocks with all 8 conditions but RS 70–84 now appear as Bullish, reducing false Buy signals in low-momentum setups

The per-depot tab and Overview depot table both show all 7 tiers. The user no longer needs to cross-reference RS Rating manually to distinguish "watch" from "act" situations.

## Sketch

**Classification logic — evaluation order (after RS = None → ValueError):**

```
1. RS < 10              → Sell-Panic   (RS override, always fires first)
2. cond == 8, RS ≥ 85   → Buy
3. cond ≥ 6, RS ≥ 50    → Bullish      (includes 8 cond + RS 50–84)
4. cond ≥ 4, RS ≥ 50    → Recovered
5. cond ≥ 4             → Neutral      (4–5 cond, RS < 50)
                                        Note: 6–7 cond + RS < 50 also falls here —
                                        high condition count with weak RS is Neutral,
                                        not Bullish or Warning (RS gates the upper tiers)
6. cond ≥ 2             → Warning      (2–3 cond, RS ≥ 10)
7. else                 → Chronic      (0–1 cond, RS ≥ 10)
```

**Worked edge case — cond = 6, RS = 40:**
Step 3 fails (RS < 50). Step 4 fails (RS < 50). Step 5 fires: cond ≥ 4 → **Neutral**.
A stock with 6 conditions but RS = 40 shows Neutral, not Bullish — RS strength gates the upper tiers.

**RS Buy threshold change from current code:**
Current: `_RS_BUY_MIN = 70.0` → New: `_RS_BUY_MIN = 85.0`
Effect: stocks with 8 conditions + RS 70–84 move from Buy → Bullish.

**Colour mapping:**

| Tier       | Background       | Text     |
|------------|-----------------|----------|
| Buy        | Dark green       | White    |
| Bullish    | Light green      | Dark     |
| Recovered  | Teal / cyan      | Dark     |
| Neutral    | Grey / yellow    | Dark     |
| Warning    | Orange           | Dark     |
| Chronic    | Dark grey        | White    |
| Sell-Panic | Red              | White    |

**SIGNAL_ORDER (for sort and display):**
`["Buy", "Bullish", "Recovered", "Neutral", "Warning", "Chronic", "Sell-Panic"]`

## Open Questions

- Should a 2–3 condition stock with RS 10–29 be Warning or Sell-Panic? Currently Warning (only RS < 10 triggers the override). Worth monitoring after first week of use.
- Should the depot summary table show all 7 tier columns, or group Warning + Chronic into one "Caution" column to keep the table width manageable?
