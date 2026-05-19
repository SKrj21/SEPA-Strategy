import pandas as pd
import pytest

from screener import check_rs_rating, check_trend_template, detect_breakout, run_full_screen

# Base passing indicators dict: all conditions True
PASSING = {
    "current_price": 100.0,
    "sma50": 95.0,
    "sma150": 90.0,
    "sma200": 85.0,
    "high_52w": 110.0,   # 100 >= 110*0.75=82.5 → True
    "low_52w": 70.0,     # 100 >= 70*1.30=91 → True
    "sma200_slope": 0.5,
}


def _with(**overrides):
    return {**PASSING, **overrides}


class TestAboveSma50:
    def test_true_when_price_above(self):
        result = check_trend_template(_with(current_price=110.0, sma50=100.0))
        assert result["above_sma50"] is True

    def test_false_when_price_below(self):
        result = check_trend_template(_with(current_price=90.0, sma50=100.0))
        assert result["above_sma50"] is False

    def test_true_at_boundary(self):
        result = check_trend_template(_with(current_price=100.0, sma50=100.0))
        assert result["above_sma50"] is True

    def test_none_when_price_none(self):
        result = check_trend_template(_with(current_price=None))
        assert result["above_sma50"] is None

    def test_none_when_sma50_none(self):
        result = check_trend_template(_with(sma50=None))
        assert result["above_sma50"] is None


class TestAboveSma150:
    def test_true_when_price_above(self):
        result = check_trend_template(_with(current_price=110.0, sma150=100.0))
        assert result["above_sma150"] is True

    def test_false_when_price_below(self):
        result = check_trend_template(_with(current_price=90.0, sma150=100.0))
        assert result["above_sma150"] is False

    def test_none_when_sma150_none(self):
        result = check_trend_template(_with(sma150=None))
        assert result["above_sma150"] is None


class TestAboveSma200:
    def test_true_when_price_above(self):
        result = check_trend_template(_with(current_price=110.0, sma200=100.0))
        assert result["above_sma200"] is True

    def test_false_when_price_below(self):
        result = check_trend_template(_with(current_price=90.0, sma200=100.0))
        assert result["above_sma200"] is False

    def test_none_when_sma200_none(self):
        result = check_trend_template(_with(sma200=None))
        assert result["above_sma200"] is None


class TestSma50AboveSma150:
    def test_true_when_sma50_above(self):
        result = check_trend_template(_with(sma50=110.0, sma150=100.0))
        assert result["sma50_above_sma150"] is True

    def test_false_when_sma50_below(self):
        result = check_trend_template(_with(sma50=90.0, sma150=100.0))
        assert result["sma50_above_sma150"] is False

    def test_none_when_either_none(self):
        assert check_trend_template(_with(sma50=None))["sma50_above_sma150"] is None
        assert check_trend_template(_with(sma150=None))["sma50_above_sma150"] is None


class TestSma50AboveSma200:
    def test_true_when_sma50_above(self):
        result = check_trend_template(_with(sma50=110.0, sma200=100.0))
        assert result["sma50_above_sma200"] is True

    def test_false_when_sma50_below(self):
        result = check_trend_template(_with(sma50=90.0, sma200=100.0))
        assert result["sma50_above_sma200"] is False


class TestSma200Uptrend:
    def test_true_when_slope_positive(self):
        result = check_trend_template(_with(sma200_slope=0.5))
        assert result["sma200_uptrend"] is True

    def test_false_when_slope_negative(self):
        result = check_trend_template(_with(sma200_slope=-0.5))
        assert result["sma200_uptrend"] is False

    def test_false_when_slope_zero(self):
        result = check_trend_template(_with(sma200_slope=0.0))
        assert result["sma200_uptrend"] is False

    def test_none_when_slope_none(self):
        result = check_trend_template(_with(sma200_slope=None))
        assert result["sma200_uptrend"] is None


class TestWithin25PctOfHigh:
    def test_true_when_price_within_25pct(self):
        # 80 >= 100 * 0.75 = 75 → True (20% below high)
        result = check_trend_template(_with(current_price=80.0, high_52w=100.0))
        assert result["within_25pct_of_high"] is True

    def test_false_when_price_more_than_25pct_below(self):
        # 70 >= 100 * 0.75 = 75 → False (30% below high)
        result = check_trend_template(_with(current_price=70.0, high_52w=100.0))
        assert result["within_25pct_of_high"] is False

    def test_true_at_exact_75pct(self):
        result = check_trend_template(_with(current_price=75.0, high_52w=100.0))
        assert result["within_25pct_of_high"] is True

    def test_none_when_high_none(self):
        result = check_trend_template(_with(high_52w=None))
        assert result["within_25pct_of_high"] is None


class TestAbove30PctOfLow:
    def test_true_when_price_30pct_above_low(self):
        # 130 >= 100 * 1.30 = 130 → True
        result = check_trend_template(_with(current_price=130.0, low_52w=100.0))
        assert result["above_30pct_of_low"] is True

    def test_false_when_price_less_than_30pct_above(self):
        # 120 >= 100 * 1.30 = 130 → False
        result = check_trend_template(_with(current_price=120.0, low_52w=100.0))
        assert result["above_30pct_of_low"] is False

    def test_none_when_low_none(self):
        result = check_trend_template(_with(low_52w=None))
        assert result["above_30pct_of_low"] is None


class TestCheckRsRating:
    def test_true_when_rs_above_threshold(self):
        assert check_rs_rating(85.0) is True

    def test_true_at_exact_threshold(self):
        assert check_rs_rating(70.0) is True

    def test_false_when_rs_below_threshold(self):
        assert check_rs_rating(65.0) is False

    def test_none_when_rs_none(self):
        assert check_rs_rating(None) is None


class TestAllPass:
    def test_true_when_all_conditions_pass(self):
        result = check_trend_template(PASSING)
        assert result["all_pass"] is True

    def test_false_when_one_condition_fails(self):
        result = check_trend_template(_with(current_price=50.0, sma50=100.0))
        assert result["all_pass"] is False

    def test_false_when_any_condition_is_none(self):
        result = check_trend_template(_with(sma200_slope=None))
        assert result["all_pass"] is False

    def test_no_short_circuit_all_conditions_computed(self):
        # Even when first condition fails, all 9 keys must be present
        result = check_trend_template(_with(current_price=50.0, sma50=100.0))
        expected_keys = {
            "above_sma50", "above_sma150", "above_sma200",
            "sma50_above_sma150", "sma50_above_sma200",
            "sma200_uptrend", "within_25pct_of_high", "above_30pct_of_low", "all_pass",
        }
        assert set(result.keys()) == expected_keys


def _breakout_df(closes):
    n = len(closes)
    return pd.DataFrame({
        "Close": closes, "High": closes, "Low": closes,
        "Open": closes, "Volume": [1_000_000] * n,
    })


SURGE = {"vol_surge": True, "avg_vol_50d": 1_000_000.0, "latest_vol": 2_000_000.0, "vol_ratio": 2.0}
NO_SURGE = {"vol_surge": False, "avg_vol_50d": 1_000_000.0, "latest_vol": 800_000.0, "vol_ratio": 0.8}


class TestDetectBreakout:
    def test_returns_all_keys(self):
        df = _breakout_df([100.0] * 21)
        result = detect_breakout(df, SURGE)
        assert set(result.keys()) == {"breakout_detected", "base_high", "pct_from_base", "in_buy_range"}

    def test_base_high_is_max_of_prior_20_days(self):
        # prior 20 days = 90..109 (max=109), today = 80
        closes = list(range(90, 110)) + [80.0]
        result = detect_breakout(_breakout_df(closes), NO_SURGE)
        assert result["base_high"] == pytest.approx(109.0)

    def test_breakout_detected_true_with_vol_surge(self):
        # prior 20 days max = 100, today = 101, vol_surge=True
        closes = [100.0] * 20 + [101.0]
        assert detect_breakout(_breakout_df(closes), SURGE)["breakout_detected"] is True

    def test_breakout_detected_false_without_vol_surge(self):
        closes = [100.0] * 20 + [101.0]
        assert detect_breakout(_breakout_df(closes), NO_SURGE)["breakout_detected"] is False

    def test_breakout_detected_false_when_vol_surge_none(self):
        closes = [100.0] * 21
        assert detect_breakout(_breakout_df(closes), {"vol_surge": None})["breakout_detected"] is False

    def test_in_buy_range_true_within_5pct(self):
        closes = [100.0] * 20 + [103.0]
        assert detect_breakout(_breakout_df(closes), SURGE)["in_buy_range"] is True

    def test_in_buy_range_true_at_exactly_5pct(self):
        closes = [100.0] * 20 + [105.0]
        result = detect_breakout(_breakout_df(closes), SURGE)
        assert result["in_buy_range"] is True
        assert result["pct_from_base"] == pytest.approx(5.0)

    def test_in_buy_range_false_when_extended(self):
        closes = [100.0] * 20 + [110.0]
        assert detect_breakout(_breakout_df(closes), SURGE)["in_buy_range"] is False

    def test_in_buy_range_false_when_below_base(self):
        closes = [100.0] * 20 + [95.0]
        assert detect_breakout(_breakout_df(closes), NO_SURGE)["in_buy_range"] is False

    def test_pct_from_base_correct_and_rounded(self):
        closes = [100.0] * 20 + [103.0]
        result = detect_breakout(_breakout_df(closes), SURGE)
        assert result["pct_from_base"] == pytest.approx(3.0)
        assert result["pct_from_base"] == round(result["pct_from_base"], 2)

    def test_pct_from_base_negative_when_below(self):
        closes = [100.0] * 20 + [95.0]
        assert detect_breakout(_breakout_df(closes), NO_SURGE)["pct_from_base"] < 0

    def test_at_boundary_price_equals_base_high(self):
        closes = [100.0] * 21
        result = detect_breakout(_breakout_df(closes), SURGE)
        assert result["pct_from_base"] == pytest.approx(0.0)
        assert result["in_buy_range"] is True
        assert result["breakout_detected"] is True

    def test_handles_fewer_than_20_rows(self):
        closes = [100.0] * 5
        result = detect_breakout(_breakout_df(closes), SURGE)
        assert result["base_high"] is not None
        assert "breakout_detected" in result

    def test_returns_none_dict_when_single_row(self):
        result = detect_breakout(_breakout_df([100.0]), SURGE)
        assert result["breakout_detected"] is None
        assert result["base_high"] is None


def _screen_df(n=300, start=100.0, step=0.5):
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    prices = [start + i * step for i in range(n)]
    return pd.DataFrame(
        {"Close": prices, "Open": prices, "High": prices, "Low": prices, "Volume": [1_000_000] * n},
        index=dates,
    )


_EXPECTED_ROW_KEYS = {
    "Ticker", "Price", "RS Rating",
    "Above SMA50", "Above SMA150", "Above SMA200",
    "SMA50>SMA150", "SMA50>SMA200", "SMA200 Uptrend",
    "Near 52W High", "Above 52W Low",
    "Volume Surge", "Breakout", "SEPA Pass",
}


class TestRunFullScreen:
    def test_returns_expected_keys_per_ticker(self):
        spy = _screen_df(300)
        ticker_data = {"A": _screen_df(300, start=100.0, step=0.5), "B": _screen_df(300, start=50.0, step=0.1)}
        results, excluded = run_full_screen(ticker_data, spy)
        assert len(results) == 2
        for row in results:
            assert set(row.keys()) == _EXPECTED_ROW_KEYS

    def test_ticker_names_preserved(self):
        spy = _screen_df(300)
        results, _ = run_full_screen({"AAPL": _screen_df(300)}, spy)
        assert results[0]["Ticker"] == "AAPL"

    def test_insufficient_data_excluded(self):
        spy = _screen_df(300)
        ticker_data = {"GOOD": _screen_df(300), "BAD": _screen_df(10)}
        results, excluded = run_full_screen(ticker_data, spy)
        assert "BAD" in excluded
        assert len(results) == 1
        assert results[0]["Ticker"] == "GOOD"

    def test_empty_input_returns_empty(self):
        spy = _screen_df(300)
        results, excluded = run_full_screen({}, spy)
        assert results == []
        assert excluded == []

    def test_sepa_pass_is_bool(self):
        spy = _screen_df(300)
        results, _ = run_full_screen({"X": _screen_df(300)}, spy)
        assert type(results[0]["SEPA Pass"]) is bool

    def test_strongly_trending_stock_sepa_pass(self):
        # Steadily rising stock; single ticker gets RS=99 → RS pass=True; trend template should pass
        stock = _screen_df(300, start=50.0, step=1.0)
        spy = _screen_df(300, start=100.0, step=0.1)
        results, _ = run_full_screen({"BULL": stock}, spy)
        assert results[0]["SEPA Pass"] is True
