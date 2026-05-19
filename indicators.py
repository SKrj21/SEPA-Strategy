import numpy as np
import pandas as pd
from scipy.stats import percentileofscore


def _to_none(val):
    if isinstance(val, (pd.Series, pd.DataFrame)):
        val = val.iloc[0] if len(val) == 1 else float("nan")
    return None if pd.isna(val) else float(val)


def compute_volume_indicators(df: pd.DataFrame) -> dict:
    avg_vol_50d = _to_none(df["Volume"].rolling(50, min_periods=1).mean().iloc[-1])
    # Use penultimate bar: iloc[-1] may be a partial intraday bar when fetched mid-session
    latest_vol = _to_none(df["Volume"].iloc[-2] if len(df) >= 2 else df["Volume"].iloc[-1])

    if avg_vol_50d is None or avg_vol_50d == 0 or latest_vol is None:
        vol_ratio = None
        vol_surge = None
    else:
        vol_ratio = round(latest_vol / avg_vol_50d, 2)
        vol_surge = bool(latest_vol >= 1.5 * avg_vol_50d)

    return {
        "avg_vol_50d": avg_vol_50d,
        "latest_vol": latest_vol,
        "vol_ratio": vol_ratio,
        "vol_surge": vol_surge,
    }


def compute_indicators(df: pd.DataFrame) -> dict:
    sma50_val = _to_none(df["Close"].rolling(50).mean().iloc[-1])
    sma150_val = _to_none(df["Close"].rolling(150).mean().iloc[-1])
    sma200_series = df["Close"].rolling(200).mean()
    sma200_val = _to_none(sma200_series.iloc[-1])
    high_52w_val = _to_none(df["High"].rolling(252).max().iloc[-1])
    low_52w_val = _to_none(df["Low"].rolling(252).min().iloc[-1])
    current_price = _to_none(df["Close"].iloc[-1])

    last30 = sma200_series.dropna().iloc[-30:]
    if len(last30) < 2:
        sma200_slope = None
    else:
        sma200_slope = float(np.polyfit(range(len(last30)), last30.values, 1)[0])

    return {
        "sma50": sma50_val,
        "sma150": sma150_val,
        "sma200": sma200_val,
        "high_52w": high_52w_val,
        "low_52w": low_52w_val,
        "sma200_slope": sma200_slope,
        "current_price": current_price,
        **compute_volume_indicators(df),
    }


def compute_raw_rs_score(stock_df: pd.DataFrame, spy_df: pd.DataFrame) -> float | None:
    stock = stock_df[["Close"]].rename(columns={"Close": "stock"})
    spy = spy_df[["Close"]].rename(columns={"Close": "spy"})
    merged = stock.join(spy, how="inner")

    if len(merged) < 64:
        return None

    s = merged["stock"]
    b = merged["spy"]

    def _price(prices, idx):
        return float(prices.iloc[idx]) if abs(idx) <= len(prices) else None

    def _excess(end_idx, start_idx):
        s_end = _price(s, end_idx)
        b_end = _price(b, end_idx)
        s_start = _price(s, start_idx)
        b_start = _price(b, start_idx)
        if any(v is None or v == 0 for v in (s_end, b_end, s_start, b_start)):
            # Period not available or zero-price — treat as neutral (0 excess)
            return 0.0
        return (s_end / s_start - 1) - (b_end / b_start - 1)

    e1 = _excess(-1, -64)    # last 63 trading days  (40%)
    e2 = _excess(-64, -127)  # days 63–126           (20%)
    e3 = _excess(-127, -190) # days 126–189          (20%)
    e4 = _excess(-190, -253) # days 189–252          (20%)

    return 0.4 * e1 + 0.2 * e2 + 0.2 * e3 + 0.2 * e4


def normalise_rs_scores(raw_scores: dict[str, float]) -> dict[str, float]:
    if not raw_scores:
        return {}
    values = list(raw_scores.values())
    return {
        ticker: max(1.0, min(99.0, percentileofscore(values, score, kind="rank")))
        for ticker, score in raw_scores.items()
    }
