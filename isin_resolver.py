import concurrent.futures
import json
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path

import yfinance as yf

_CACHE_PATH = Path(__file__).parent / "isin_cache.json"
_MANUAL_MAP_PATH = Path(__file__).parent / "manual_ticker_map.csv"
_LOOKUP_TIMEOUT = 8  # seconds per ISIN

logger = logging.getLogger(__name__)

# Primary exchange suffix per country (ordered by preference)
_COUNTRY_SUFFIXES: dict[str, list[str]] = {
    "DE": [".DE", ".F", ".HM", ".BE", ".MU", ".SG", ".DU"],
    "AT": [".VI"],
    "CH": [".SW"],
    "GB": [".L"],
    "FR": [".PA"],
    "NL": [".AS"],
    "IT": [".MI"],
    "ES": [".MC"],
    "SE": [".ST"],
    "DK": [".CO"],
    "NO": [".OL"],
    "FI": [".HE"],
    "BE": [".BR"],
    "PT": [".LS"],
    "IE": [".IR"],
    "CA": [".TO", ".V"],
    "AU": [".AX"],
    "JP": [".T"],
    "HK": [".HK"],
    "SG": [".SI"],
}


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    if _CACHE_PATH.exists():
        try:
            with _CACHE_PATH.open(encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not write ISIN cache: %s", exc)


# ── Manual map ─────────────────────────────────────────────────────────────────

def _load_manual_map() -> dict[str, str]:
    if not _MANUAL_MAP_PATH.exists():
        return {}
    try:
        import csv
        with _MANUAL_MAP_PATH.open(encoding="utf-8") as f:
            return {
                row["ISIN"].strip().upper(): row["Ticker"].strip()
                for row in csv.DictReader(f)
                if row.get("ISIN") and row.get("Ticker")
            }
    except Exception as exc:
        logger.warning("Could not load manual ticker map: %s", exc)
        return {}


# ── Yahoo Finance search API ───────────────────────────────────────────────────

def _yahoo_search(query: str) -> list[dict]:
    try:
        import requests
        resp = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": query, "quotesCount": 10, "newsCount": 0, "enableFuzzyQuery": False},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        if resp.status_code == 200:
            return resp.json().get("quotes", [])
    except Exception as exc:
        logger.debug("Yahoo search failed for %r: %s", query, exc)
    return []


# ── Name normalisation + scoring ───────────────────────────────────────────────

_CORP_SUFFIXES_RE = re.compile(
    r"\b(AG|SE|GMBH|PLC|LTD|INC|CORP|SA|NV|BV|SPA|ASA|AB|OYJ|SAS|KGaA)\b\.?",
    re.IGNORECASE,
)


def _normalize_name(name: str) -> str:
    name = _CORP_SUFFIXES_RE.sub("", name)
    return re.sub(r"\s+", " ", name).strip().upper()


def _score_quote(quote: dict, country_code: str) -> float:
    qt = quote.get("quoteType", "").upper()
    if qt not in {"EQUITY", "ETF", ""}:
        return -1.0

    symbol: str = quote.get("symbol", "")
    score = 0.0

    suffixes = _COUNTRY_SUFFIXES.get(country_code, [])
    for rank, suf in enumerate(suffixes):
        if symbol.endswith(suf):
            score += 10.0 - rank * 0.5  # prefer primary exchange
            break
    else:
        # No matching suffix — penalise unless it's a US-like bare symbol
        if "." in symbol:
            score -= 5.0

    if qt == "EQUITY":
        score += 1.0

    return score


# ── Core lookup ────────────────────────────────────────────────────────────────

def _lookup(isin: str, wkn_hint: str | None = None) -> str | None:
    country_code = isin[:2].upper()

    # 1. Manual override map
    manual = _load_manual_map()
    if isin in manual:
        return manual[isin]

    # 2. WKN hint — try first when available (shorter, more specific than ISIN
    #    for Yahoo Finance search; German brokers like Smartbroker provide this)
    if wkn_hint:
        quotes = _yahoo_search(wkn_hint)
        if quotes:
            scored = sorted(quotes, key=lambda q: _score_quote(q, country_code), reverse=True)
            best = scored[0]
            if _score_quote(best, country_code) >= 0:
                symbol = best.get("symbol", "").strip()
                if symbol:
                    logger.debug("WKN hint %r resolved %s → %s", wkn_hint, isin, symbol)
                    return symbol

    # 3. Yahoo Finance search API by ISIN (country-aware ranking)
    quotes = _yahoo_search(isin)
    if quotes:
        scored = sorted(
            quotes,
            key=lambda q: _score_quote(q, country_code),
            reverse=True,
        )
        best = scored[0]
        if _score_quote(best, country_code) >= 0:
            symbol = best.get("symbol", "").strip()
            if symbol:
                return symbol

    # 4. yf.Search fallback (always runs for US; also catches stragglers)
    def _yf_search() -> str | None:
        for q in yf.Search(isin, max_results=5).quotes:
            sym = q.get("symbol", "").strip()
            if sym and q.get("quoteType", "").upper() in {"EQUITY", "ETF", ""}:
                return sym
        return None

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_yf_search).result(timeout=_LOOKUP_TIMEOUT)
    except Exception as exc:
        logger.debug("yf.Search failed for %s: %s", isin, exc)

    return None


# ── Public API ─────────────────────────────────────────────────────────────────

def resolve_isin(isin: str, wkn_hint: str | None = None) -> str | None:
    if not isin or not isinstance(isin, str):
        return None
    isin = isin.strip().upper()
    cache = _load_cache()
    if isin in cache:
        return cache[isin] or None
    ticker = _lookup(isin, wkn_hint=wkn_hint)
    cache[isin] = ticker or ""
    _save_cache(cache)
    return ticker


def batch_resolve(isins: list[str], wkn_map: dict[str, str] | None = None) -> dict[str, str]:
    cache = _load_cache()
    result: dict[str, str] = {}
    updated = False
    _wkn = wkn_map or {}

    for raw in isins:
        if not raw:
            continue
        isin = raw.strip().upper()
        if isin in cache:
            if cache[isin]:
                result[isin] = cache[isin]
        else:
            ticker = _lookup(isin, wkn_hint=_wkn.get(isin))
            cache[isin] = ticker or ""
            updated = True
            if ticker:
                result[isin] = ticker

    if updated:
        _save_cache(cache)
    return result
