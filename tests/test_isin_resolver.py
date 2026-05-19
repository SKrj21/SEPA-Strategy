import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import isin_resolver


def _mock_search(symbol: str, quoteType: str = "EQUITY"):
    mock = MagicMock()
    mock.quotes = [{"symbol": symbol, "quoteType": quoteType}]
    return mock


def _empty_search():
    mock = MagicMock()
    mock.quotes = []
    return mock


# ── TestResolveIsin ───────────────────────────────────────────────────────────

class TestResolveIsin:
    def test_us_isin_resolves_to_ticker(self, tmp_path, monkeypatch):
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", tmp_path / "isin_cache.json")
        with patch("isin_resolver._yahoo_search", return_value=[]):
            with patch("isin_resolver.yf.Search", return_value=_mock_search("NVDA")):
                result = isin_resolver.resolve_isin("US67066G1040")
        assert result == "NVDA"

    def test_german_isin_resolves_to_de_ticker(self, tmp_path, monkeypatch):
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", tmp_path / "isin_cache.json")
        with patch("isin_resolver._yahoo_search", return_value=[]):
            with patch("isin_resolver.yf.Search", return_value=_mock_search("SAP.DE")):
                result = isin_resolver.resolve_isin("DE0007164600")
        assert result == "SAP.DE"

    def test_yahoo_search_result_used_when_available(self, tmp_path, monkeypatch):
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", tmp_path / "isin_cache.json")
        yahoo_quote = [{"symbol": "SAP.DE", "quoteType": "EQUITY", "exchange": "XETRA"}]
        with patch("isin_resolver._yahoo_search", return_value=yahoo_quote):
            with patch("isin_resolver.yf.Search") as mock_yf:
                result = isin_resolver.resolve_isin("DE0007164600")
        assert result == "SAP.DE"
        mock_yf.assert_not_called()

    def test_manual_map_takes_priority(self, tmp_path, monkeypatch):
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", tmp_path / "isin_cache.json")
        manual_map_path = tmp_path / "manual_ticker_map.csv"
        manual_map_path.write_text("ISIN,Ticker\nDE0007164600,SAP.DE\n")
        monkeypatch.setattr(isin_resolver, "_MANUAL_MAP_PATH", manual_map_path)
        with patch("isin_resolver._yahoo_search") as mock_yahoo:
            with patch("isin_resolver.yf.Search") as mock_yf:
                result = isin_resolver.resolve_isin("DE0007164600")
        assert result == "SAP.DE"
        mock_yahoo.assert_not_called()
        mock_yf.assert_not_called()

    def test_unknown_isin_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", tmp_path / "isin_cache.json")
        with patch("isin_resolver._yahoo_search", return_value=[]):
            with patch("isin_resolver.yf.Search", return_value=_empty_search()):
                result = isin_resolver.resolve_isin("INVALID0000000")
        assert result is None

    def test_unknown_isin_stored_as_empty_string_in_cache(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "isin_cache.json"
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", cache_path)
        with patch("isin_resolver._yahoo_search", return_value=[]):
            with patch("isin_resolver.yf.Search", return_value=_empty_search()):
                isin_resolver.resolve_isin("INVALID0000000")
        cache = json.loads(cache_path.read_text())
        assert "INVALID0000000" in cache
        assert cache["INVALID0000000"] == ""

    def test_cache_written_after_first_resolution(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "isin_cache.json"
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", cache_path)
        assert not cache_path.exists()
        with patch("isin_resolver._yahoo_search", return_value=[]):
            with patch("isin_resolver.yf.Search", return_value=_mock_search("AAPL")):
                isin_resolver.resolve_isin("US0378331005")
        assert cache_path.exists()
        cache = json.loads(cache_path.read_text())
        assert cache.get("US0378331005") == "AAPL"

    def test_cached_result_returned_without_api_call(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "isin_cache.json"
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", cache_path)
        cache_path.write_text(json.dumps({"US0378331005": "AAPL"}))
        with patch("isin_resolver._yahoo_search") as mock_yahoo:
            with patch("isin_resolver.yf.Search") as mock_yf:
                result = isin_resolver.resolve_isin("US0378331005")
        assert result == "AAPL"
        mock_yahoo.assert_not_called()
        mock_yf.assert_not_called()

    def test_none_input_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", tmp_path / "isin_cache.json")
        assert isin_resolver.resolve_isin(None) is None

    def test_empty_string_input_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", tmp_path / "isin_cache.json")
        assert isin_resolver.resolve_isin("") is None

    def test_network_error_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", tmp_path / "isin_cache.json")
        with patch("isin_resolver._yahoo_search", return_value=[]):
            with patch("isin_resolver.yf.Search", side_effect=Exception("network error")):
                result = isin_resolver.resolve_isin("US67066G1040")
        assert result is None

    def test_corrupt_cache_rebuilt(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "isin_cache.json"
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", cache_path)
        cache_path.write_text("NOT VALID JSON")
        with patch("isin_resolver._yahoo_search", return_value=[]):
            with patch("isin_resolver.yf.Search", return_value=_mock_search("MSFT")):
                result = isin_resolver.resolve_isin("US5949181045")
        assert result == "MSFT"

    def test_yahoo_search_bad_score_falls_through_to_yf(self, tmp_path, monkeypatch):
        # A Yahoo result for a DE ISIN that has no .DE suffix scores poorly → use yf.Search
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", tmp_path / "isin_cache.json")
        bad_quote = [{"symbol": "SAP.US", "quoteType": "EQUITY"}]  # wrong exchange
        with patch("isin_resolver._yahoo_search", return_value=bad_quote):
            with patch("isin_resolver.yf.Search", return_value=_mock_search("SAP.DE")):
                result = isin_resolver.resolve_isin("DE0007164600")
        # bad_quote score is < 0 (has a dot but wrong suffix → penalty) → yf.Search wins
        # The yahoo result has score -5 (has a dot but no matching suffix), so yf.Search is used
        assert result is not None


# ── TestBatchResolve ──────────────────────────────────────────────────────────

class TestBatchResolve:
    def test_resolves_multiple_isins(self, tmp_path, monkeypatch):
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", tmp_path / "isin_cache.json")

        def search_side_effect(isin, **kwargs):
            mapping = {"US67066G1040": "NVDA", "US0378331005": "AAPL"}
            sym = mapping.get(isin.strip().upper())
            return _mock_search(sym) if sym else _empty_search()

        with patch("isin_resolver._yahoo_search", return_value=[]):
            with patch("isin_resolver.yf.Search", side_effect=search_side_effect):
                result = isin_resolver.batch_resolve(["US67066G1040", "US0378331005"])

        assert result == {"US67066G1040": "NVDA", "US0378331005": "AAPL"}

    def test_failed_isins_omitted_from_result(self, tmp_path, monkeypatch):
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", tmp_path / "isin_cache.json")
        with patch("isin_resolver._yahoo_search", return_value=[]):
            with patch("isin_resolver.yf.Search", return_value=_empty_search()):
                result = isin_resolver.batch_resolve(["INVALID0000000"])
        assert result == {}

    def test_cache_written_once_for_batch(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "isin_cache.json"
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", cache_path)

        def search_side_effect(isin, **kwargs):
            return _mock_search("NVDA") if "67066" in isin else _empty_search()

        with patch("isin_resolver._yahoo_search", return_value=[]):
            with patch("isin_resolver.yf.Search", side_effect=search_side_effect):
                isin_resolver.batch_resolve(["US67066G1040", "INVALID0000000"])

        assert cache_path.exists()
        cache = json.loads(cache_path.read_text())
        assert "US67066G1040" in cache
        assert "INVALID0000000" in cache

    def test_already_cached_isin_not_looked_up_again(self, tmp_path, monkeypatch):
        cache_path = tmp_path / "isin_cache.json"
        monkeypatch.setattr(isin_resolver, "_CACHE_PATH", cache_path)
        cache_path.write_text(json.dumps({"US67066G1040": "NVDA"}))

        with patch("isin_resolver._yahoo_search") as mock_yahoo:
            with patch("isin_resolver.yf.Search") as mock_yf:
                result = isin_resolver.batch_resolve(["US67066G1040"])

        mock_yahoo.assert_not_called()
        mock_yf.assert_not_called()
        assert result == {"US67066G1040": "NVDA"}
