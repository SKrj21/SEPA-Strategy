SIGNAL_ORDER: list[str] = ["Buy", "Bullish", "Recovered", "Neutral", "Warning", "Chronic", "Sell-Panic"]

_CONDITION_KEYS: tuple[str, ...] = (
    "Above SMA50",
    "Above SMA150",
    "Above SMA200",
    "SMA50>SMA150",
    "SMA50>SMA200",
    "SMA200 Uptrend",
    "Near 52W High",
    "Above 52W Low",
)

_RS_PANIC_OVERRIDE = 10.0
_RS_BUY_MIN = 85.0
_RS_BULLISH_MIN = 50.0


def classify_signal(row: dict) -> str:
    """Classify a screener result row into one of seven signal tiers.

    Evaluation order (must not be changed):
      1. RS Rating is None  → raises ValueError
      2. RS < 10            → "Sell-Panic" (override, ignores conditions)
      3. cond == 8, RS ≥ 85 → "Buy"
      4. cond ≥ 6, RS ≥ 50  → "Bullish"   (incl. 8 cond + RS 50–84)
      5. cond ≥ 4, RS ≥ 50  → "Recovered"
      6. cond ≥ 4           → "Neutral"   (incl. 6–7 cond + RS < 50)
      7. cond ≥ 2           → "Warning"
      8. else               → "Chronic"   (0–1 cond, RS ≥ 10)

    Args:
        row: A screener result dict containing the 8 trend-template condition
             keys and an "RS Rating" key.

    Returns:
        One of: "Buy", "Bullish", "Recovered", "Neutral", "Warning",
        "Chronic", "Sell-Panic".

    Raises:
        ValueError: If "RS Rating" is None (caller should exclude such rows
                    from results before calling classify_signal).
    """
    rs = row.get("RS Rating")
    if rs is None:
        raise ValueError(
            "classify_signal received a row with RS Rating = None. "
            "Rows with no RS Rating should be excluded before classification."
        )

    if rs < _RS_PANIC_OVERRIDE:
        return "Sell-Panic"

    conditions_met = sum(1 for k in _CONDITION_KEYS if row.get(k) is True)

    if conditions_met == 8 and rs >= _RS_BUY_MIN:
        return "Buy"
    if conditions_met >= 6 and rs >= _RS_BULLISH_MIN:
        return "Bullish"
    if conditions_met >= 4 and rs >= _RS_BULLISH_MIN:
        return "Recovered"
    if conditions_met >= 4:
        return "Neutral"
    if conditions_met >= 2:
        return "Warning"
    return "Chronic"
