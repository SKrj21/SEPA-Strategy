import pandas as pd
import streamlit as st
import yfinance


def load_tickers_from_csv(uploaded_file) -> list[str]:
    df = pd.read_csv(uploaded_file)
    if "Ticker" not in df.columns:
        raise ValueError("CSV must contain a 'Ticker' column")
    tickers = df["Ticker"].str.strip().dropna()
    tickers = tickers[tickers != ""]
    # Preserve order while deduplicating
    return list(dict.fromkeys(tickers.tolist()))


def _download_with_fallback(ticker: str) -> pd.DataFrame | None:
    """Download OHLCV for one ticker; tries dot→dash variant (BRK.B → BRK-B) on failure."""
    candidates = [ticker]
    parts = ticker.split(".")
    # Share-class dot (e.g. BRK.B, BF.B) has a single letter after the last dot
    if len(parts) == 2 and len(parts[-1]) == 1:
        candidates.append("-".join(parts))
    for sym in candidates:
        try:
            df = yfinance.download(sym, period="2y", interval="1d", auto_adjust=False, progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                return df
        except Exception:
            pass
    return None


def fetch_single_ohlcv(ticker: str) -> pd.DataFrame | None:
    """Non-cached single-ticker fetch used for ISIN retry on failed tickers."""
    return _download_with_fallback(ticker)


@st.cache_data(ttl=3600)
def fetch_ohlcv(tickers: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    # Progress bar only fires on cache miss; on cache hit this function is not called.
    results: dict[str, pd.DataFrame] = {}
    progress = st.progress(0, text="Fetching market data...")

    for i, ticker in enumerate(tickers):
        df = _download_with_fallback(ticker)
        if df is not None:
            results[ticker] = df

        label = f"Fetched {ticker}" if ticker in results else f"Skipped {ticker}"
        progress.progress((i + 1) / len(tickers), text=label)

    progress.empty()
    return results


@st.cache_data(ttl=86400)
def fetch_ticker_names(tickers: tuple[str, ...]) -> dict[str, str]:
    """Fetch company display names from yfinance. Cached for 24 h."""
    names: dict[str, str] = {}
    for ticker in tickers:
        try:
            info = yfinance.Ticker(ticker).info
            name = info.get("shortName") or info.get("longName", "")
            if name:
                names[ticker] = name
        except Exception:
            pass
    return names


@st.cache_data(ttl=3600)
def fetch_spy_benchmark() -> pd.DataFrame:
    try:
        df = yfinance.download("SPY", period="2y", interval="1d", auto_adjust=False, progress=False)
        if df.empty:
            st.warning("Could not fetch SPY benchmark data.")
            return df
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:
        st.warning(f"Failed to fetch SPY benchmark: {e}")
        return pd.DataFrame()
