import pandas as pd
import plotly.graph_objects as go
import pytest

from charts import build_detail_chart


def _make_ohlcv(n=300, start=100.0, step=0.5):
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    prices = [start + i * step for i in range(n)]
    return pd.DataFrame(
        {"Close": prices, "Open": prices, "High": prices, "Low": prices, "Volume": [1_000_000] * n},
        index=dates,
    )


INDICATORS = {
    "sma50": 150.0, "sma150": 130.0, "sma200": 110.0,
    "high_52w": 200.0, "low_52w": 80.0, "sma200_slope": 0.5, "current_price": 200.0,
    "avg_vol_50d": 1_000_000.0, "latest_vol": 1_100_000.0, "vol_ratio": 1.1, "vol_surge": False,
}


class TestBuildDetailChart:
    def test_returns_plotly_figure(self):
        fig = build_detail_chart(_make_ohlcv(300), INDICATORS, pd.DataFrame())
        assert isinstance(fig, go.Figure)

    def test_sma50_trace_present(self):
        fig = build_detail_chart(_make_ohlcv(300), INDICATORS, pd.DataFrame())
        assert "SMA50" in [t.name for t in fig.data]

    def test_sma150_trace_present(self):
        fig = build_detail_chart(_make_ohlcv(300), INDICATORS, pd.DataFrame())
        assert "SMA150" in [t.name for t in fig.data]

    def test_sma200_trace_present(self):
        fig = build_detail_chart(_make_ohlcv(300), INDICATORS, pd.DataFrame())
        assert "SMA200" in [t.name for t in fig.data]

    def test_skips_sma50_when_fewer_than_50_rows(self):
        fig = build_detail_chart(_make_ohlcv(45), INDICATORS, pd.DataFrame())
        assert "SMA50" not in [t.name for t in fig.data]

    def test_skips_sma200_but_keeps_sma150_when_between_150_and_200_rows(self):
        fig = build_detail_chart(_make_ohlcv(170), INDICATORS, pd.DataFrame())
        trace_names = [t.name for t in fig.data]
        assert "SMA200" not in trace_names
        assert "SMA150" in trace_names

    def test_three_y_axes(self):
        fig = build_detail_chart(_make_ohlcv(300), INDICATORS, pd.DataFrame())
        assert fig.layout.yaxis is not None
        assert fig.layout.yaxis2 is not None
        assert fig.layout.yaxis3 is not None

    def test_volume_bar_trace_present(self):
        fig = build_detail_chart(_make_ohlcv(300), INDICATORS, pd.DataFrame())
        bar_traces = [t for t in fig.data if isinstance(t, go.Bar)]
        assert len(bar_traces) == 1

    def test_rs_line_present_with_benchmark(self):
        spy = _make_ohlcv(300, start=100.0, step=0.2)
        fig = build_detail_chart(_make_ohlcv(300), INDICATORS, spy)
        assert "RS vs SPY" in [t.name for t in fig.data]

    def test_rs_line_absent_without_benchmark(self):
        fig = build_detail_chart(_make_ohlcv(300), INDICATORS, pd.DataFrame())
        assert "RS vs SPY" not in [t.name for t in fig.data]

    def test_52w_reference_lines_present(self):
        fig = build_detail_chart(_make_ohlcv(300), INDICATORS, pd.DataFrame())
        assert len(fig.layout.shapes) == 2

    def test_no_exception_with_short_df(self):
        build_detail_chart(_make_ohlcv(60), INDICATORS, pd.DataFrame())

    def test_annotation_when_sma_unavailable(self):
        fig = build_detail_chart(_make_ohlcv(60), INDICATORS, pd.DataFrame())
        texts = [a.text for a in fig.layout.annotations]
        assert any("SMA200" in t for t in texts)
