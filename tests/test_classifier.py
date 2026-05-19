"""Unit tests for classifier.classify_signal and SIGNAL_ORDER."""
import pytest
from classifier import classify_signal, SIGNAL_ORDER

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_TRUE = {
    "Above SMA50": True,
    "Above SMA150": True,
    "Above SMA200": True,
    "SMA50>SMA150": True,
    "SMA50>SMA200": True,
    "SMA200 Uptrend": True,
    "Near 52W High": True,
    "Above 52W Low": True,
}

_CONDITION_KEYS = list(_ALL_TRUE.keys())


def _row(n_true: int, rs: float) -> dict:
    """Build a row with exactly n_true conditions set to True, rest False."""
    row = {k: (True if i < n_true else False) for i, k in enumerate(_CONDITION_KEYS)}
    row["RS Rating"] = rs
    return row


# ---------------------------------------------------------------------------
# SIGNAL_ORDER
# ---------------------------------------------------------------------------


class TestSignalOrder:
    def test_exact_content_and_order(self):
        assert SIGNAL_ORDER == [
            "Buy", "Bullish", "Recovered", "Neutral", "Warning", "Chronic", "Sell-Panic"
        ]

    def test_length(self):
        assert len(SIGNAL_ORDER) == 7


# ---------------------------------------------------------------------------
# Buy tier — requires cond == 8 AND RS >= 85
# ---------------------------------------------------------------------------


class TestBuyTier:
    def test_all_8_conditions_rs_85(self):
        assert classify_signal(_row(8, 85.0)) == "Buy"

    def test_all_8_conditions_rs_99(self):
        assert classify_signal(_row(8, 99.0)) == "Buy"

    def test_all_8_conditions_rs_exactly_85(self):
        assert classify_signal(_row(8, 85.0)) == "Buy"

    def test_all_8_conditions_rs_84_falls_to_bullish(self):
        # RS threshold raised to 85; cond=8 + RS=84 → Bullish (cond>=6, RS>=50)
        assert classify_signal(_row(8, 84.0)) == "Bullish"

    def test_all_8_conditions_rs_70_falls_to_bullish(self):
        # Old threshold was 70; now RS=70 no longer qualifies for Buy
        assert classify_signal(_row(8, 70.0)) == "Bullish"

    def test_7_conditions_rs_99_not_buy(self):
        # conditions gate requires exactly 8 for Buy
        assert classify_signal(_row(7, 99.0)) == "Bullish"


# ---------------------------------------------------------------------------
# Bullish tier — cond >= 6 AND RS >= 50 (includes 8 cond + RS 50–84)
# ---------------------------------------------------------------------------


class TestBullishTier:
    def test_7_conditions_rs_50(self):
        assert classify_signal(_row(7, 50.0)) == "Bullish"

    def test_7_conditions_rs_80(self):
        assert classify_signal(_row(7, 80.0)) == "Bullish"

    def test_6_conditions_rs_50(self):
        assert classify_signal(_row(6, 50.0)) == "Bullish"

    def test_8_conditions_rs_84_is_bullish(self):
        # 8 conditions but RS 50–84 falls to Bullish, not Buy
        assert classify_signal(_row(8, 84.0)) == "Bullish"

    def test_8_conditions_rs_50_is_bullish(self):
        assert classify_signal(_row(8, 50.0)) == "Bullish"

    def test_6_conditions_rs_49_falls_to_neutral(self):
        # 6 conditions but RS gate fails for Bullish; RS < 50 also fails Recovered → Neutral
        assert classify_signal(_row(6, 49.0)) == "Neutral"

    def test_6_conditions_rs_exactly_50(self):
        assert classify_signal(_row(6, 50.0)) == "Bullish"


# ---------------------------------------------------------------------------
# Recovered tier — cond >= 4 AND RS >= 50 (but cond < 6, so not Bullish)
# ---------------------------------------------------------------------------


class TestRecoveredTier:
    def test_5_conditions_rs_50(self):
        assert classify_signal(_row(5, 50.0)) == "Recovered"

    def test_4_conditions_rs_50(self):
        assert classify_signal(_row(4, 50.0)) == "Recovered"

    def test_5_conditions_rs_80(self):
        assert classify_signal(_row(5, 80.0)) == "Recovered"

    def test_4_conditions_rs_exactly_50(self):
        assert classify_signal(_row(4, 50.0)) == "Recovered"

    def test_4_conditions_rs_49_falls_to_neutral(self):
        # RS gate fails for Recovered → Neutral
        assert classify_signal(_row(4, 49.0)) == "Neutral"

    def test_5_conditions_rs_49_falls_to_neutral(self):
        assert classify_signal(_row(5, 49.0)) == "Neutral"


# ---------------------------------------------------------------------------
# Neutral tier — cond >= 4 AND RS < 50 (incl. high cond 6-7 with weak RS)
# ---------------------------------------------------------------------------


class TestNeutralTier:
    def test_5_conditions_low_rs(self):
        # RS < 50 fails Recovered gate → Neutral
        assert classify_signal(_row(5, 11.0)) == "Neutral"

    def test_4_conditions_low_rs(self):
        assert classify_signal(_row(4, 11.0)) == "Neutral"

    def test_6_conditions_rs_40_is_neutral(self):
        # Worked edge case: cond=6, RS=40 → Bullish gate fails (RS<50),
        # Recovered gate fails (RS<50), Neutral fires (cond>=4)
        assert classify_signal(_row(6, 40.0)) == "Neutral"

    def test_7_conditions_rs_49_is_neutral(self):
        # High cond count with weak RS → Neutral (RS gates the upper tiers)
        assert classify_signal(_row(7, 49.0)) == "Neutral"

    def test_4_conditions_rs_49(self):
        assert classify_signal(_row(4, 49.0)) == "Neutral"


# ---------------------------------------------------------------------------
# Warning tier — cond >= 2 AND RS >= 10 (but cond < 4)
# ---------------------------------------------------------------------------


class TestWarningTier:
    def test_3_conditions(self):
        assert classify_signal(_row(3, 50.0)) == "Warning"

    def test_2_conditions(self):
        assert classify_signal(_row(2, 50.0)) == "Warning"

    def test_3_conditions_low_rs(self):
        assert classify_signal(_row(3, 11.0)) == "Warning"

    def test_2_conditions_low_rs(self):
        assert classify_signal(_row(2, 11.0)) == "Warning"

    def test_3_conditions_rs_exactly_10(self):
        # RS = 10 does not trigger the RS override (requires RS < 10)
        assert classify_signal(_row(3, 10.0)) == "Warning"

    def test_2_conditions_rs_9_triggers_sell_panic(self):
        # RS < 10 fires the override before Warning check
        assert classify_signal(_row(2, 9.0)) == "Sell-Panic"


# ---------------------------------------------------------------------------
# Chronic tier — cond <= 1 AND RS >= 10
# ---------------------------------------------------------------------------


class TestChronicTier:
    def test_1_condition(self):
        assert classify_signal(_row(1, 50.0)) == "Chronic"

    def test_0_conditions(self):
        assert classify_signal(_row(0, 50.0)) == "Chronic"

    def test_1_condition_high_rs(self):
        assert classify_signal(_row(1, 99.0)) == "Chronic"

    def test_0_conditions_rs_exactly_10(self):
        # RS = 10 does not trigger Sell-Panic override; falls through to Chronic
        assert classify_signal(_row(0, 10.0)) == "Chronic"


# ---------------------------------------------------------------------------
# Sell-Panic via RS override (RS < 10, ignores conditions)
# ---------------------------------------------------------------------------


class TestSellPanicRSOverride:
    def test_rs_below_10_all_conditions_true(self):
        row = dict(_ALL_TRUE)
        row["RS Rating"] = 5.0
        assert classify_signal(row) == "Sell-Panic"

    def test_rs_9_9_boundary(self):
        row = dict(_ALL_TRUE)
        row["RS Rating"] = 9.9
        assert classify_signal(row) == "Sell-Panic"

    def test_rs_0_boundary(self):
        row = dict(_ALL_TRUE)
        row["RS Rating"] = 0.0
        assert classify_signal(row) == "Sell-Panic"

    def test_rs_exactly_10_not_override(self):
        # RS = 10.0 does NOT trigger the override (< 10 required)
        # 8 conditions + RS 10: Bullish gate fails (RS<50), Recovered fails (RS<50),
        # Neutral fires (cond>=4, RS<50)
        row = dict(_ALL_TRUE)
        row["RS Rating"] = 10.0
        result = classify_signal(row)
        assert result != "Sell-Panic", "RS = 10.0 must not trigger the RS override"
        assert result == "Neutral"  # 8 cond but RS 10 < 50 → Neutral gate (>=4)


# ---------------------------------------------------------------------------
# RS Rating = None
# ---------------------------------------------------------------------------


class TestRSNone:
    def test_rs_none_raises_value_error(self):
        row = dict(_ALL_TRUE)
        row["RS Rating"] = None
        with pytest.raises(ValueError):
            classify_signal(row)

    def test_rs_missing_key_raises_value_error(self):
        row = dict(_ALL_TRUE)
        # RS Rating key absent → row.get("RS Rating") returns None
        with pytest.raises(ValueError):
            classify_signal(row)


# ---------------------------------------------------------------------------
# Condition value edge cases
# ---------------------------------------------------------------------------


class TestConditionValues:
    def test_none_condition_not_counted(self):
        # 7 True + 1 None → only 7 counted → Bullish (with RS >= 50)
        row = {k: True for k in _CONDITION_KEYS}
        row[_CONDITION_KEYS[-1]] = None
        row["RS Rating"] = 80.0
        assert classify_signal(row) == "Bullish"

    def test_false_condition_not_counted(self):
        # 7 True + 1 False → only 7 counted → Bullish
        row = {k: True for k in _CONDITION_KEYS}
        row[_CONDITION_KEYS[-1]] = False
        row["RS Rating"] = 80.0
        assert classify_signal(row) == "Bullish"

    def test_mixed_none_and_false(self):
        # 6 True + 1 None + 1 False → 6 counted; RS 60 → Bullish
        row = {k: True for k in _CONDITION_KEYS[:6]}
        row[_CONDITION_KEYS[6]] = None
        row[_CONDITION_KEYS[7]] = False
        row["RS Rating"] = 60.0
        assert classify_signal(row) == "Bullish"

    def test_only_8_named_keys_counted(self):
        # Extra keys in row dict should not affect count
        # 4 conditions + RS 50 → Recovered (not Neutral)
        row = _row(4, 50.0)
        row["Extra Key"] = True
        row["Another Column"] = True
        assert classify_signal(row) == "Recovered"
