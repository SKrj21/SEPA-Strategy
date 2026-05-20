import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_EXCLUDE_FILES = {"sepa_results.csv", "isin_cache.csv"}  # isin_cache.csv excluded to prevent circular ISIN re-ingestion


# ── Format detection ──────────────────────────────────────────────────────────

def _try_read(path: Path) -> pd.DataFrame:
    # Pick the separator that yields the most columns (handles Smartbroker which may use
    # either comma or semicolon). Break ties by taking the first successful encoding.
    best: pd.DataFrame | None = None
    for sep in [";", ","]:
        for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
            try:
                df = pd.read_csv(path, sep=sep, encoding=enc, dtype=str)
                if len(df.columns) >= 2:
                    if best is None or len(df.columns) > len(best.columns):
                        best = df
                    break  # best encoding found for this sep; move to next sep
            except Exception:
                continue
    if best is not None:
        return best
    raise ValueError(
        f"Cannot parse '{path.name}': tried common separators and encodings"
    )


def _detect_format(cols: list[str]) -> str:
    upper = [c.strip().upper() for c in cols]
    upper_set = set(upper)

    if any("ASSETKLASSE" in c for c in upper):
        return "smartbroker"
    if any(c in upper_set for c in ("TICKER", "SYMBOL")):
        return "legacy"
    if "ISIN" in upper_set:
        # Note: "Stücke" (real TR column) uppercases to "STÜCKE" (Ü ≠ U), so it does NOT
        # match "STUCK". TR files with only "Stücke" fall through to "reference" format,
        # which is harmless — both paths extract the ISIN column identically.
        if any(
            any(kw in c for kw in ("STUCK", "QTY", "QUANTITY", "AMOUNT", "ANZAHL"))
            for c in upper
        ):
            return "trade_republic"
        return "reference"
    raise ValueError(f"Unrecognized CSV format. Columns found: {cols}")


def _find_col(df: pd.DataFrame, *candidates: str) -> str | None:
    mapping = {c.strip().upper(): c for c in df.columns}
    for cand in candidates:
        hit = mapping.get(cand.upper())
        if hit is not None:
            return hit
    return None


# ── ISIN validation ───────────────────────────────────────────────────────────

def _is_valid_isin(value: str) -> bool:
    v = value.strip().upper()
    return len(v) == 12 and v[:2].isalpha() and v[2:].replace(" ", "").isalnum()


def _dedupe_isins(raw: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in raw:
        v = v.strip().upper()
        if v and _is_valid_isin(v) and v not in seen:
            seen.add(v)
            out.append(v)
    return out


# ── Public API ────────────────────────────────────────────────────────────────

def load_csv_file(path: Path) -> list[str]:
    """Parse a broker CSV and return a deduplicated list of ISIN codes (or ticker symbols for legacy format)."""
    df = _try_read(path)
    df.columns = [c.strip() for c in df.columns]
    fmt = _detect_format(list(df.columns))

    if fmt == "smartbroker":
        isin_col = _find_col(df, "ISIN")
        asset_col = _find_col(df, "ASSETKLASSE", "Assetklasse", "assetklasse")
        if isin_col is None:
            raise ValueError(f"'{path.name}': Smartbroker format but no ISIN column")
        if asset_col is not None:
            df = df[df[asset_col].str.strip().str.lower() == "aktien"]
        return _dedupe_isins(df[isin_col].dropna().tolist())

    if fmt == "trade_republic":
        isin_col = _find_col(df, "ISIN")
        if isin_col is None:
            raise ValueError(f"'{path.name}': Trade Republic format but no ISIN column")
        return _dedupe_isins(df[isin_col].dropna().tolist())

    if fmt == "reference":
        isin_col = _find_col(df, "ISIN")
        if isin_col is None:
            raise ValueError(f"'{path.name}': Reference format but no ISIN column")
        return _dedupe_isins(df[isin_col].dropna().tolist())

    if fmt == "legacy":
        ticker_col = _find_col(df, "Ticker", "TICKER", "ticker", "Symbol", "SYMBOL")
        if ticker_col is None:
            raise ValueError(f"'{path.name}': Legacy format but no Ticker column")
        tickers = df[ticker_col].dropna().str.strip().tolist()
        return [t for t in dict.fromkeys(tickers) if t]

    raise ValueError(f"'{path.name}': Unknown format '{fmt}'")  # unreachable


def load_csv_isin_wkn_map(path: Path) -> dict[str, str]:
    """Return {ISIN: WKN} for broker CSVs that carry a WKN column (e.g. Smartbroker).

    WKN codes are short German securities identifiers that Yahoo Finance's search
    API resolves more reliably than ISINs — use as a priority lookup hint.
    Returns an empty dict for formats without a WKN column.
    """
    try:
        df = _try_read(path)
        df.columns = [c.strip() for c in df.columns]
        fmt = _detect_format(list(df.columns))
        if fmt != "smartbroker":
            return {}
        isin_col = _find_col(df, "ISIN")
        wkn_col = _find_col(df, "WKN", "Wkn", "wkn")
        if not isin_col or not wkn_col:
            return {}
        result: dict[str, str] = {}
        for _, row in df.iterrows():
            isin = str(row[isin_col]).strip().upper()
            wkn = str(row[wkn_col]).strip()
            if _is_valid_isin(isin) and wkn and wkn.lower() != "nan":
                result[isin] = wkn
        return result
    except Exception:
        return {}


def load_csv_name_map(path: Path) -> dict[str, str]:
    """Return {isin_or_ticker: display_name} from a broker CSV.

    Best-effort — returns an empty dict on any parse failure.
    """
    try:
        df = _try_read(path)
        df.columns = [c.strip() for c in df.columns]
        fmt = _detect_format(list(df.columns))
        result: dict[str, str] = {}

        if fmt in ("smartbroker", "trade_republic", "reference"):
            isin_col = _find_col(df, "ISIN")
            name_col = _find_col(df, "Bezeichnung", "Name", "Wertpapier", "Unternehmen", "Firma", "Titel")
            if isin_col and name_col:
                for _, row in df.iterrows():
                    isin = str(row[isin_col]).strip().upper()
                    name = str(row[name_col]).strip()
                    if _is_valid_isin(isin) and name and name.lower() != "nan":
                        result[isin] = name

        elif fmt == "legacy":
            ticker_col = _find_col(df, "Ticker", "TICKER", "Symbol", "SYMBOL")
            name_col = _find_col(df, "Name", "Company", "Bezeichnung", "Unternehmen", "Firma", "Titel")
            if ticker_col and name_col:
                for _, row in df.iterrows():
                    ticker = str(row[ticker_col]).strip().upper()
                    name = str(row[name_col]).strip()
                    if ticker and name and name.lower() != "nan":
                        result[ticker] = name

        return result
    except Exception:
        return {}


def discover_csv_files(base_dir: Path) -> dict[str, list[str]]:
    """Scan base_dir and its immediate subdirectories for broker CSV files.

    Returns {filename: [isin_or_ticker, ...]} for each successfully parsed file.
    Files that fail to parse are logged and skipped.
    """
    paths: list[Path] = list(base_dir.glob("*.csv"))
    for sub in sorted(p for p in base_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
        paths.extend(sub.glob("*.csv"))
    paths = sorted(paths, key=lambda p: p.name.lower())

    results: dict[str, list[str]] = {}
    for path in paths:
        if path.name.lower() in _EXCLUDE_FILES:
            continue
        try:
            entries = load_csv_file(path)
            if entries:
                results[path.name] = entries
                logger.info("Discovered %d entries in %s", len(entries), path.name)
        except Exception as exc:
            logger.warning("Skipping %s: %s", path.name, exc)

    return results
