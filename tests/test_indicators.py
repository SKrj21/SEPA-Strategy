import pandas as pd
import pytest

from indicators import compute_indicators, compute_raw_rs_score, compute_volume_indicators, normalise_rs_scores


def _make_df(n, close_val=100.0, high_val=110.0, low_val=90.0):
    return pd.DataFrame({
        "Close":  [close_val] * n,
        "High":   [high_val]  * n,
        "Low":    [low_val]   * n,
        "Open":   [close_val] * n,
        "Volume": [1_000_000] * n,
    })


class TestComputeIndicatorsKeys:
    def test_returns_all_keys(self):
        result = compute_indicators(_make_df(504))
        assert set(result.keys()) == {
            "sma50", "sma150", "sma200",
            "high_52w", "low_52w", "sma200_slope", "current_price",
            "avg_vol_50d", "latest_vol", "vol_ratio", "vol_surge",
        }


class TestSma50:
    def test_correct_value(self):
        result = compute_indicators(_make_df(504, close_val=100.0))
        assert result["sma50"] == pytest.approx(100.0, rel=1e-4)

    def test_none_when_insufficient(self):
        result = compute_indicators(_make_df(49))
        assert result["sma50"] is None


class TestSma150:
    def test_correct_value(self):
        result = compute_indicators(_make_df(504, close_val=150.0))
        assert result["sma150"] == pytest.approx(150.0, rel=1e-4)

    def test_none_when_insufficient(self):
        result = compute_indicators(_make_df(149))
        assert result["sma150"] is None


class TestSma200:
    def test_correct_value(self):
        result = compute_indicators(_make_df(504, close_val=200.0))
        assert result["sma200"] == pytest.approx(200.0, rel=1e-4)

    def test_none_when_insufficient(self):
        result = compute_indicators(_make_df(199))
        assert result["sma200"] is None


class TestHigh52w:
    def test_correct_value(self):
        result = compute_indicators(_make_df(504, high_val=110.0))
        assert result["high_52w"] == pytest.approx(110.0, rel=1e-4)

    def test_none_when_insufficient(self):
        result = compute_indicators(_make_df(251))
        assert result["high_52w"] is None


class TestLow52w:
    def test_correct_value(self):
        result = compute_indicators(_make_df(504, low_val=90.0))
        assert result["low_52w"] == pytest.approx(90.0, rel=1e-4)

    def test_none_when_insufficient(self):
        result = compute_indicators(_make_df(251))
        assert result["low_52w"] is None


class TestSma200Slope:
    def test_positive_when_trending_up(self):
        closes = list(range(50, 50 + 250))  # steadily rising
        df = pd.DataFrame({
            "Close": closes, "High": closes, "Low": closes,
            "Open": closes, "Volume": [1_000_000] * 250,
        })
        result = compute_indicators(df)
        assert result["sma200_slope"] is not None
        assert result["sma200_slope"] > 0

    def test_negative_when_trending_down(self):
        closes = list(range(300, 300 - 250, -1))  # steadily falling
        df = pd.DataFrame({
            "Close": closes, "High": closes, "Low": closes,
            "Open": closes, "Volume": [1_000_000] * 250,
        })
        result = compute_indicators(df)
        assert result["sma200_slope"] is not None
        assert result["sma200_slope"] < 0

    def test_none_when_only_one_sma200_point(self):
        # Exactly 200 rows → rolling(200) produces exactly 1 non-NaN value → len < 2
        result = compute_indicators(_make_df(200))
        assert result["sma200_slope"] is None


class TestNanHandling:
    def test_nan_close_returns_none_for_current_price(self):
        df = _make_df(504)
        df.loc[df.index[-1], "Close"] = float("nan")
        result = compute_indicators(df)
        assert result["current_price"] is None


def _make_price_df(n, start=100.0, step=0.0):
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    prices = [start + i * step for i in range(n)]
    return pd.DataFrame(
        {"Close": prices, "Open": prices, "High": prices, "Low": prices, "Volume": [1_000_000] * n},
        index=dates,
    )


class TestComputeRawRsScore:
    def test_returns_none_when_fewer_than_64_aligned_rows(self):
        stock = _make_price_df(63)
        spy = _make_price_df(63)
        assert compute_raw_rs_score(stock, spy) is None

    def test_returns_float_with_sufficient_data(self):
        stock = _make_price_df(300, start=100.0, step=0.5)
        spy = _make_price_df(300, start=100.0, step=0.2)
        result = compute_raw_rs_score(stock, spy)
        assert isinstance(result, float)

    def test_outperforming_stock_has_positive_score(self):
        # Stock rises faster than SPY → positive excess return
        stock = _make_price_df(300, start=100.0, step=1.0)
        spy = _make_price_df(300, start=100.0, step=0.1)
        assert compute_raw_rs_score(stock, spy) > 0

    def test_underperforming_stock_has_negative_score(self):
        # Stock rises slower (or falls) vs SPY → negative excess return
        stock = _make_price_df(300, start=100.0, step=0.1)
        spy = _make_price_df(300, start=100.0, step=1.0)
        assert compute_raw_rs_score(stock, spy) < 0

    def test_matching_stock_has_near_zero_score(self):
        df = _make_price_df(300, start=100.0, step=0.5)
        result = compute_raw_rs_score(df, df.copy())
        assert abs(result) < 1e-9

    def test_aligns_on_index_when_spy_has_extra_dates(self):
        # SPY has 70 extra rows extending beyond stock; inner join yields 200 aligned rows
        stock = _make_price_df(200, start=100.0, step=0.5)
        spy_dates = pd.date_range("2023-01-01", periods=270, freq="B")
        spy = pd.DataFrame(
            {"Close": [100.0] * 270, "Open": [100.0] * 270,
             "High": [100.0] * 270, "Low": [100.0] * 270, "Volume": [1_000_000] * 270},
            index=spy_dates,
        )
        result = compute_raw_rs_score(stock, spy)
        assert isinstance(result, float)


class TestComputeVolumeIndicators:
    def _surge_df(self, base_vol, spike_vol, n=51):
        # spike at position -2 (penultimate = last fully closed bar)
        vols = [base_vol] * (n - 2) + [spike_vol] + [base_vol]
        return pd.DataFrame({
            "Close": [100.0] * n, "High": [110.0] * n, "Low": [90.0] * n,
            "Open": [100.0] * n, "Volume": vols,
        })

    def test_returns_all_keys(self):
        result = compute_volume_indicators(_make_df(60))
        assert set(result.keys()) == {"avg_vol_50d", "latest_vol", "vol_ratio", "vol_surge"}

    def test_avg_vol_50d_matches_rolling_50_mean(self):
        result = compute_volume_indicators(_make_df(60))
        assert result["avg_vol_50d"] == pytest.approx(1_000_000.0, rel=1e-4)

    def test_latest_vol_is_penultimate_row(self):
        # latest_vol uses iloc[-2] — the last fully closed bar
        result = compute_volume_indicators(_make_df(60))
        assert result["latest_vol"] == pytest.approx(1_000_000.0)

    def test_vol_surge_true_when_spike(self):
        # spike at iloc[-2]; avg ~= (49*100 + 10_000 + 100) / 51 ≈ 298; 10_000 >> 1.5*298
        df = self._surge_df(base_vol=100, spike_vol=10_000)
        assert compute_volume_indicators(df)["vol_surge"] is True

    def test_vol_surge_false_when_uniform(self):
        # all same volume → ratio = 1.0, not >= 1.5
        assert compute_volume_indicators(_make_df(60))["vol_surge"] is False

    def test_vol_ratio_is_1_for_uniform_volume(self):
        result = compute_volume_indicators(_make_df(60))
        assert result["vol_ratio"] == pytest.approx(1.0)

    def test_vol_ratio_rounded_to_2dp(self):
        result = compute_volume_indicators(_make_df(60))
        assert result["vol_ratio"] == round(result["vol_ratio"], 2)

    def test_handles_fewer_than_50_rows(self):
        result = compute_volume_indicators(_make_df(30))
        assert result["avg_vol_50d"] is not None
        assert isinstance(result["vol_surge"], bool)

    def test_vol_surge_is_python_bool(self):
        result = compute_volume_indicators(_make_df(60))
        assert type(result["vol_surge"]) is bool


class TestNormaliseRsScores:
    def test_returns_dict_with_same_keys(self):
        raw = {"A": 0.5, "B": -0.3, "C": 0.1}
        result = normalise_rs_scores(raw)
        assert set(result.keys()) == {"A", "B", "C"}

    def test_all_scores_in_1_to_99(self):
        raw = {"A": 1.0, "B": -1.0, "C": 0.0, "D": 0.5}
        result = normalise_rs_scores(raw)
        for v in result.values():
            assert 1.0 <= v <= 99.0

    def test_highest_raw_gets_highest_normalised(self):
        raw = {"best": 2.0, "mid": 0.0, "worst": -2.0}
        result = normalise_rs_scores(raw)
        assert result["best"] > result["mid"] > result["worst"]

    def test_empty_input_returns_empty(self):
        assert normalise_rs_scores({}) == {}

    def test_single_ticker_returns_99(self):
        result = normalise_rs_scores({"AAPL": 0.5})
        assert result["AAPL"] == 99.0
