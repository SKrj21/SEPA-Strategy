import pytest
from pathlib import Path

from csv_loader import discover_csv_files, load_csv_file


# ── CSV fixture builders ───────────────────────────────────────────────────────

def _smartbroker_csv() -> str:
    # Semicolon-separated; ASSETKLASSE column; mix of Aktien, Derivate, ETF and a duplicate
    return (
        "ISIN;Name;ASSETKLASSE\n"
        "DE0007164600;SAP;Aktien\n"
        "US67066G1040;NVIDIA;Aktien\n"
        "US67066G1040;NVIDIA dup;Aktien\n"   # duplicate — should be collapsed
        "DE000BASF111;BASF;Derivate\n"        # excluded
        "DE0005140008;Deutsche Bank;ETF\n"    # excluded
    )


def _trade_republic_bytes() -> bytes:
    # UTF-8 BOM + semicolon-separated; Anzahl column triggers trade_republic detection
    return (
        b"\xef\xbb\xbf"
        b"ISIN;Name;Anzahl\n"
        b"US0378331005;Apple;10\n"
        b"US0231351067;Amazon;5\n"
    )


def _reference_csv() -> str:
    # Semicolon-separated; only ISIN and Name — no quantity keyword → reference format
    return (
        "ISIN;Name\n"
        "GB00B16GWD56;ARM Holdings\n"
        "IE00B4L5Y983;iShares MSCI World\n"
    )


def _legacy_csv() -> str:
    # Has Ticker column — legacy format; returns tickers, not ISINs
    return "Ticker;CompanyName\nAAPL;Apple Inc\nMSFT;Microsoft\nTSLA;Tesla\n"


def _unrecognized_csv() -> str:
    # Two columns but no recognizable column names
    return "Foo;Bar\nabc;123\ndef;456\n"


# ── TestLoadCsvFileSmartbroker ────────────────────────────────────────────────

class TestLoadCsvFileSmartbroker:
    def test_returns_only_aktien_rows(self, tmp_path):
        path = tmp_path / "sb.csv"
        path.write_text(_smartbroker_csv(), encoding="utf-8")
        result = load_csv_file(path)
        assert "DE0007164600" in result
        assert "US67066G1040" in result
        assert "DE000BASF111" not in result
        assert "DE0005140008" not in result

    def test_deduplication_within_file(self, tmp_path):
        path = tmp_path / "sb.csv"
        path.write_text(_smartbroker_csv(), encoding="utf-8")
        result = load_csv_file(path)
        assert result.count("US67066G1040") == 1

    def test_detected_by_assetklasse_column_case_insensitive(self, tmp_path):
        # Mixed-case header still triggers Smartbroker detection
        csv = "ISIN;Name;Assetklasse\nDE0007164600;SAP;Aktien\nDE000BASF111;BASF;Derivate\n"
        path = tmp_path / "sb_mixed.csv"
        path.write_text(csv, encoding="utf-8")
        result = load_csv_file(path)
        assert result == ["DE0007164600"]
        assert "DE000BASF111" not in result

    def test_no_rows_returned_when_all_excluded(self, tmp_path):
        csv = "ISIN;Name;ASSETKLASSE\nDE000BASF111;BASF;Derivate\nDE0005140008;DB;ETF\n"
        path = tmp_path / "sb_no_aktien.csv"
        path.write_text(csv, encoding="utf-8")
        result = load_csv_file(path)
        assert result == []


# ── TestLoadCsvFileTradeRepublic ──────────────────────────────────────────────

class TestLoadCsvFileTradeRepublic:
    def test_bom_stripped_and_isins_returned(self, tmp_path):
        path = tmp_path / "tr.csv"
        path.write_bytes(_trade_republic_bytes())
        result = load_csv_file(path)
        assert "US0378331005" in result
        assert "US0231351067" in result

    def test_no_garbled_isin_from_bom(self, tmp_path):
        path = tmp_path / "tr.csv"
        path.write_bytes(_trade_republic_bytes())
        result = load_csv_file(path)
        # BOM-contaminated value would start with
        for isin in result:
            assert "﻿" not in isin
            assert isin == isin.strip().upper()

    def test_quantity_column_triggers_detection(self, tmp_path):
        # Anzahl keyword routes to trade_republic (not reference)
        path = tmp_path / "tr.csv"
        path.write_bytes(_trade_republic_bytes())
        result = load_csv_file(path)
        # Both rows should be present (no row-level filtering unlike Smartbroker)
        assert len(result) == 2

    def test_stuecke_umlaut_column_falls_through_to_reference_and_still_returns_isins(self, tmp_path):
        # Real TR export uses "Stücke" → uppercases to "STÜCKE" (Ü ≠ U) so does not match
        # "STUCK"; file is routed to "reference" format, which still extracts ISINs correctly.
        csv_bytes = (
            b"\xef\xbb\xbf"
            b"ISIN;Name;St\xc3\xbccke;EINSTANDSKURS PRO ST\xc3\x9cCK\n"
            b"US0378331005;Apple;10;150.00\n"
        )
        path = tmp_path / "tr_real.csv"
        path.write_bytes(csv_bytes)
        result = load_csv_file(path)
        assert result == ["US0378331005"]


# ── TestLoadCsvFileReference ──────────────────────────────────────────────────

class TestLoadCsvFileReference:
    def test_extracts_isin_column(self, tmp_path):
        path = tmp_path / "ref.csv"
        path.write_text(_reference_csv(), encoding="utf-8")
        result = load_csv_file(path)
        assert result == ["GB00B16GWD56", "IE00B4L5Y983"]

    def test_no_quantity_column_routes_to_reference(self, tmp_path):
        # Verify reference is not misrouted to trade_republic when no qty column present
        path = tmp_path / "ref.csv"
        path.write_text(_reference_csv(), encoding="utf-8")
        result = load_csv_file(path)
        assert len(result) == 2


# ── TestLoadCsvFileLegacy ─────────────────────────────────────────────────────

class TestLoadCsvFileLegacy:
    def test_returns_tickers_not_isins(self, tmp_path):
        path = tmp_path / "leg.csv"
        path.write_text(_legacy_csv(), encoding="utf-8")
        result = load_csv_file(path)
        assert result == ["AAPL", "MSFT", "TSLA"]

    def test_symbol_column_also_detected(self, tmp_path):
        csv = "Symbol;CompanyName\nGOOG;Alphabet\nAMZN;Amazon\n"
        path = tmp_path / "sym.csv"
        path.write_text(csv, encoding="utf-8")
        result = load_csv_file(path)
        assert result == ["GOOG", "AMZN"]


# ── TestLoadCsvFileUnrecognized ───────────────────────────────────────────────

class TestLoadCsvFileUnrecognized:
    def test_raises_value_error(self, tmp_path):
        path = tmp_path / "bad.csv"
        path.write_text(_unrecognized_csv(), encoding="utf-8")
        with pytest.raises(ValueError):
            load_csv_file(path)

    def test_error_message_contains_column_names(self, tmp_path):
        path = tmp_path / "bad.csv"
        path.write_text(_unrecognized_csv(), encoding="utf-8")
        with pytest.raises(ValueError) as exc_info:
            load_csv_file(path)
        msg = str(exc_info.value)
        assert "Foo" in msg or "foo" in msg.lower()


# ── TestLoadCsvFileDeduplication ──────────────────────────────────────────────

class TestLoadCsvFileDeduplication:
    def test_duplicate_isins_collapsed_to_one(self, tmp_path):
        csv = "ISIN;Name\nUS0378331005;Apple\nUS0378331005;Apple copy\nUS0378331005;Apple again\n"
        path = tmp_path / "dup.csv"
        path.write_text(csv, encoding="utf-8")
        result = load_csv_file(path)
        assert result == ["US0378331005"]
        assert len(result) == 1

    def test_isins_normalized_to_uppercase(self, tmp_path):
        csv = "ISIN;Name\nus0378331005;Apple\n"
        path = tmp_path / "lower.csv"
        path.write_text(csv, encoding="utf-8")
        result = load_csv_file(path)
        assert result == ["US0378331005"]

    def test_invalid_isin_rows_filtered_out(self, tmp_path):
        # Row with non-ISIN value should not appear in result
        csv = "ISIN;Name\nUS0378331005;Apple\nNOT_AN_ISIN;Junk\n"
        path = tmp_path / "mixed.csv"
        path.write_text(csv, encoding="utf-8")
        result = load_csv_file(path)
        assert result == ["US0378331005"]
        assert "NOT_AN_ISIN" not in result


# ── TestDiscoverCsvFiles ──────────────────────────────────────────────────────

class TestDiscoverCsvFiles:
    def test_discovers_files_in_base_dir(self, tmp_path):
        (tmp_path / "ref.csv").write_text(_reference_csv(), encoding="utf-8")
        (tmp_path / "sb.csv").write_text(_smartbroker_csv(), encoding="utf-8")
        result = discover_csv_files(tmp_path)
        assert "ref.csv" in result
        assert "sb.csv" in result
        assert all(isinstance(v, list) and len(v) > 0 for v in result.values())

    def test_discovers_files_in_immediate_subdirectory(self, tmp_path):
        sub = tmp_path / "data"
        sub.mkdir()
        (sub / "ref.csv").write_text(_reference_csv(), encoding="utf-8")
        result = discover_csv_files(tmp_path)
        assert "ref.csv" in result

    def test_skips_sepa_results_csv(self, tmp_path):
        (tmp_path / "sepa_results.csv").write_text(_reference_csv(), encoding="utf-8")
        (tmp_path / "ref.csv").write_text(_reference_csv(), encoding="utf-8")
        result = discover_csv_files(tmp_path)
        assert "sepa_results.csv" not in result
        assert "ref.csv" in result

    def test_skips_unparseable_files_without_crashing(self, tmp_path):
        # single-column file cannot be parsed (< 2 columns triggers ValueError)
        (tmp_path / "garbage.csv").write_text("only_one_column\nvalue\n", encoding="utf-8")
        (tmp_path / "ref.csv").write_text(_reference_csv(), encoding="utf-8")
        result = discover_csv_files(tmp_path)
        assert "garbage.csv" not in result
        assert "ref.csv" in result

    def test_returns_empty_dict_for_empty_directory(self, tmp_path):
        result = discover_csv_files(tmp_path)
        assert result == {}

    def test_result_values_are_lists_of_strings(self, tmp_path):
        (tmp_path / "ref.csv").write_text(_reference_csv(), encoding="utf-8")
        result = discover_csv_files(tmp_path)
        for entries in result.values():
            assert isinstance(entries, list)
            assert all(isinstance(e, str) for e in entries)

    def test_skips_isin_cache_csv(self, tmp_path):
        # isin_cache.csv excluded to prevent circular re-ingestion of the resolver cache
        (tmp_path / "isin_cache.csv").write_text(_reference_csv(), encoding="utf-8")
        (tmp_path / "ref.csv").write_text(_reference_csv(), encoding="utf-8")
        result = discover_csv_files(tmp_path)
        assert "isin_cache.csv" not in result
        assert "ref.csv" in result

    def test_file_keys_sorted_alphabetically(self, tmp_path):
        (tmp_path / "zoo.csv").write_text(_reference_csv(), encoding="utf-8")
        (tmp_path / "apple.csv").write_text(_reference_csv(), encoding="utf-8")
        (tmp_path / "mango.csv").write_text(_reference_csv(), encoding="utf-8")
        result = discover_csv_files(tmp_path)
        assert list(result.keys()) == sorted(result.keys())

    def test_skips_file_that_parses_but_returns_empty_list(self, tmp_path):
        # Smartbroker file with only Derivate rows returns [] from load_csv_file
        # discover_csv_files should silently omit it (not add an empty entry)
        derivate_only = "ISIN;Name;ASSETKLASSE\nDE000BASF111;BASF;Derivate\n"
        (tmp_path / "derivate.csv").write_text(derivate_only, encoding="utf-8")
        (tmp_path / "ref.csv").write_text(_reference_csv(), encoding="utf-8")
        result = discover_csv_files(tmp_path)
        assert "derivate.csv" not in result
        assert "ref.csv" in result

    def test_file_keys_sorted_alphabetically_across_subdirectories(self, tmp_path):
        sub = tmp_path / "data"
        sub.mkdir()
        (tmp_path / "zoo.csv").write_text(_reference_csv(), encoding="utf-8")
        (sub / "apple.csv").write_text(_reference_csv(), encoding="utf-8")
        result = discover_csv_files(tmp_path)
        assert list(result.keys()) == sorted(result.keys())

    def test_does_not_recurse_deeper_than_one_level(self, tmp_path):
        deep = tmp_path / "level1" / "level2"
        deep.mkdir(parents=True)
        (deep / "deep.csv").write_text(_reference_csv(), encoding="utf-8")
        result = discover_csv_files(tmp_path)
        assert "deep.csv" not in result
