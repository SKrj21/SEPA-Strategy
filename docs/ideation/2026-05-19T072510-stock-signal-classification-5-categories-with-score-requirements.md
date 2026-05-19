# Stock Signal Classification — 5 Categories with Score

*Date: 2026-05-19 07:25*
*Session: 2026-05-19T072510-stock-signal-classification-5-categories-with-score*

## Problem
The current screener output uses a binary SEPA Pass / Fail column. A stock meeting 7 of 8 conditions looks identical to one meeting 0 of 8 — both return `False`. This makes it impossible to triage at a glance: which stocks are close to a buy signal, which are strengthening, and which need to be exited.

## Goal
Users can triage the full screener output in seconds — identifying actionable Buy candidates and stocks requiring exit without scanning every row — by seeing each stock's Signal tier (Buy / Bullish / Neutral / Bearish / Sell-Panic) and its RS Rating score side-by-side.

## Success Metrics

- **leading indicators** (observable while the work is in flight, predict the outcome):
  - Category labels match the user's own manual assessment on ≥90% of spot-checked stocks within the first week after deploy
  - Buy-signal stocks appear in the top rows of the results table without any manual re-sorting, within the first screening session after deploy

- **lagging indicators** (the outcome itself, observable only after it has occurred):
  - User stops needing to manually scan the boolean SEPA Pass column to find actionable stocks within two weeks of deploy
  - ≥70% of stocks the user acts on (buys or sells) originate from the Buy or Sell-Panic category within one month of deploy

## Assumptions
*Ordered highest to lowest risk; the riskiest entry is marked `(R)`.*

- Absolute thresholds (Buy = all 8 conditions + RS ≥ 70; Sell-Panic = ≤ 1 condition or RS < 10 override) will produce at least some non-empty categories in typical market conditions — in a sustained bear market the Buy category may be persistently empty; in a sustained bull market the Sell-Panic category may be sparse `(R)`
- The RS Rating percentile (1–99) is a trusted, already-understood signal; users know what RS = 82 means and will not need a separate explanation of the score
- The 8 SEPA conditions carry equal weight in the conditions count — no single condition is more decisive than the others as a gating criterion
- Users will use the category as a triage aid alongside their own judgment, not as an autonomous trade signal
- Replacing the boolean "SEPA Pass" column with the category label does not remove the rule-following discipline users relied on — the Buy category effectively encodes the same gate with more nuance above it

## Constraints
- Existing test suite (160 tests) must remain green; any new classification logic must be covered by its own unit tests
- The classification is a display layer only — `screener.py` and `indicators.py` must not be modified

## Non-goals
- Changing the 8 SEPA trend-template conditions themselves
- Adding new data sources (earnings, fundamentals, sentiment) — score is derived from existing SEPA conditions and RS Rating only
- Historical signal tracking or category-change alerts — point-in-time classification only
- Dynamic / percentile-based thresholds that adjust to market regime — thresholds are hardcoded defaults (adjustable only in code)
- Per-depot different thresholds — one threshold set applies uniformly across all depots

## Outcome
After this ships, the results table shows a **Signal** column (Buy / Bullish / Neutral / Bearish / Sell-Panic) and a **Score** column (RS Rating, 1–99) instead of the boolean "SEPA Pass" column. Stocks are sorted by Score descending by default, so the strongest buy candidates surface at the top without manual effort. Users can identify which stocks to investigate, which to hold, and which to exit at a glance — without scanning every condition column individually.

## Sketch

**Category classification logic (evaluated in order):**

1. If RS Rating is `None` (fewer than 64 days of data) → **excluded from results** (same as the existing data-exclusion path)
2. If RS < 10 → **Sell-Panic** (hard override — extreme RS weakness overrides conditions count)
3. Otherwise, conditions gate the tier (count of True values across the 8 individual trend-template fields — *not* the `all_pass` boolean):
   - 8 conditions met + RS ≥ 70 → **Buy**
   - 6–7 conditions met + RS ≥ 50 → **Bullish**
   - 4–5 conditions met → **Neutral**
   - 2–3 conditions met → **Bearish**
   - ≤ 1 condition met → **Sell-Panic**

**Score:** RS Rating (1–99) — no new calculation required; reuse the value already present in each result row.

**Display:**
- "Signal" and "Score" columns replace the "SEPA Pass" boolean column
- Colour coding: Buy = green, Bullish = light green, Neutral = grey/yellow, Bearish = light red, Sell-Panic = red
- Results sorted by Score descending by default within each depot tab
- Overview tab shows a category-count summary row (e.g., "3 Buy / 7 Bullish / 12 Neutral / …") so empty-category market regimes are visible at a glance

## Open Questions
- Should the Sell-Panic RS override threshold (currently RS < 10) be adjustable via a sidebar input, or is code-only editability sufficient for now?
- Should the old "SEPA Pass" boolean be retained as a hidden/toggleable column for users who prefer the strict binary gate for position entry discipline?
