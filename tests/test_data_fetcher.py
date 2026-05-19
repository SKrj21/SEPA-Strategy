import io
import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Patch streamlit before importing data_fetcher so @st.cache_data is a no-op.
mock_st = MagicMock()
mock_st.cache_data = lambda **kwargs: (lambda fn: fn)
sys.modules["streamlit"] = mock_st

import data_fetcher  # noqa: E402


def _csv(content: str):
    return io.StringIO(content)


class TestLoadTickersFromCsv:
    def test_returns_list_of_strings(self):
        result = data_fetcher.load_tickers_from_csv(_csv("Ticker\nAAPL\nMSFT\n"))
        assert result == ["AAPL", "MSFT"]

    def test_raises_when_ticker_column_missing(self):
        with pytest.raises(ValueError, match="Ticker"):
            data_fetcher.load_tickers_from_csv(_csv("Symbol\nAAPL\n"))

    def test_strips_whitespace(self):
        result = data_fetcher.load_tickers_from_csv(_csv("Ticker\n AAPL \n MSFT\n"))
        assert result == ["AAPL", "MSFT"]

    def test_deduplicates_preserving_order(self):
        result = data_fetcher.load_tickers_from_csv(_csv("Ticker\nAAPL\nMSFT\nAAPL\n"))
        assert result == ["AAPL", "MSFT"]

    def test_drops_empty_rows(self):
        result = data_fetcher.load_tickers_from_csv(_csv("Ticker\nAAPL\n\nMSFT\n"))
        assert result == ["AAPL", "MSFT"]


class TestFetchOhlcv:
    def test_skips_empty_dataframe(self):
        with patch("yfinance.download", return_value=pd.DataFrame()):
            result = data_fetcher.fetch_ohlcv(("FAKE",))
        assert "FAKE" not in result

    def test_skips_on_exception(self):
        with patch("yfinance.download", side_effect=Exception("network error")):
            result = data_fetcher.fetch_ohlcv(("FAKE",))
        assert result == {}

    def test_returns_dataframe_for_valid_ticker(self):
        fake_df = pd.DataFrame(
            {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5], "Volume": [1000]}
        )
        with patch("yfinance.download", return_value=fake_df):
            result = data_fetcher.fetch_ohlcv(("AAPL",))
        assert "AAPL" in result
        assert {"Open", "High", "Low", "Close", "Volume"}.issubset(result["AAPL"].columns)

    def test_multiple_tickers_partial_failure(self):
        good_df = pd.DataFrame(
            {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5], "Volume": [1000]}
        )

        def side_effect(ticker, **kwargs):
            if ticker == "AAPL":
                return good_df
            return pd.DataFrame()

        with patch("yfinance.download", side_effect=side_effect):
            result = data_fetcher.fetch_ohlcv(("AAPL", "FAKE"))
        assert "AAPL" in result
        assert "FAKE" not in result


class TestFetchSpyBenchmark:
    def test_returns_dataframe_for_spy(self):
        fake_df = pd.DataFrame(
            {"Open": [400.0], "High": [410.0], "Low": [395.0], "Close": [405.0], "Volume": [50_000_000]}
        )
        with patch("yfinance.download", return_value=fake_df) as mock_dl:
            result = data_fetcher.fetch_spy_benchmark()
        mock_dl.assert_called_once_with("SPY", period="2y", interval="1d", auto_adjust=True, progress=False)
        assert not result.empty

    def test_returns_empty_dataframe_on_exception(self):
        with patch("yfinance.download", side_effect=Exception("network")):
            result = data_fetcher.fetch_spy_benchmark()
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_returns_empty_dataframe_when_yfinance_returns_empty(self):
        with patch("yfinance.download", return_value=pd.DataFrame()):
            result = data_fetcher.fetch_spy_benchmark()
        assert result.empty
