import pandas as pd

from indicators import compute_indicators, compute_raw_rs_score, normalise_rs_scores

RS_PASS_THRESHOLD = 70.0


def check_rs_rating(rs_rating: float | None) -> bool | None:
    if rs_rating is None:
        return None
    return rs_rating >= RS_PASS_THRESHOLD


def check_trend_template(indicators: dict) -> dict:
    p = indicators.get("current_price")
    sma50 = indicators.get("sma50")
    sma150 = indicators.get("sma150")
    sma200 = indicators.get("sma200")
    high_52w = indicators.get("high_52w")
    low_52w = indicators.get("low_52w")
    slope = indicators.get("sma200_slope")

    def _cond(a, b, fn):
        if a is None or b is None:
            return None
        return fn(a, b)

    above_sma50 = _cond(p, sma50, lambda a, b: a >= b)
    above_sma150 = _cond(p, sma150, lambda a, b: a >= b)
    above_sma200 = _cond(p, sma200, lambda a, b: a >= b)
    sma50_above_sma150 = _cond(sma50, sma150, lambda a, b: a >= b)
    sma50_above_sma200 = _cond(sma50, sma200, lambda a, b: a >= b)
    sma200_uptrend = None if slope is None else slope > 0
    # Condition 7: price must be >= 75% of 52w high (within 25% of high)
    within_25pct_of_high = _cond(p, high_52w, lambda a, b: a >= b * 0.75)
    # Condition 8: price must be >= 130% of 52w low (30% above low)
    above_30pct_of_low = _cond(p, low_52w, lambda a, b: a >= b * 1.30)

    conditions = [
        above_sma50, above_sma150, above_sma200,
        sma50_above_sma150, sma50_above_sma200,
        sma200_uptrend, within_25pct_of_high, above_30pct_of_low,
    ]
    all_pass = all(c is True for c in conditions)

    return {
        "above_sma50": above_sma50,
        "above_sma150": above_sma150,
        "above_sma200": above_sma200,
        "sma50_above_sma150": sma50_above_sma150,
        "sma50_above_sma200": sma50_above_sma200,
        "sma200_uptrend": sma200_uptrend,
        "within_25pct_of_high": within_25pct_of_high,
        "above_30pct_of_low": above_30pct_of_low,
        "all_pass": all_pass,
    }


def detect_breakout(df: pd.DataFrame, volume_indicators: dict) -> dict:
    # base_high = max close of the prior 20 trading days (excludes today's bar)
    prior = df["Close"].iloc[:-1].tail(20)
    base_high = None if prior.empty else float(prior.max())

    raw_price = df["Close"].iloc[-1]
    current_price = None if pd.isna(raw_price) else float(raw_price)

    if current_price is None or base_high is None or base_high == 0:
        return {
            "breakout_detected": None,
            "base_high": base_high,
            "pct_from_base": None,
            "in_buy_range": None,
        }

    pct_from_base = round((current_price - base_high) / base_high * 100, 2)
    vol_surge = volume_indicators.get("vol_surge")
    breakout_detected = bool(current_price >= base_high and vol_surge is True)
    in_buy_range = bool(0 <= pct_from_base <= 5)

    return {
        "breakout_detected": breakout_detected,
        "base_high": base_high,
        "pct_from_base": pct_from_base,
        "in_buy_range": in_buy_range,
    }


def run_full_screen(
    ticker_data_dict: dict,
    benchmark_df: pd.DataFrame,
    progress_fn=None,
) -> tuple[list[dict], list[str]]:
    """Screen all tickers. Returns (results_rows, excluded_tickers).

    progress_fn: optional callable(fraction: float, text: str) for UI progress updates.
    """
    excluded: list[str] = []
    raw_rs: dict[str, float] = {}
    stage1: dict[str, tuple] = {}

    total = len(ticker_data_dict)
    for i, (ticker, df) in enumerate(ticker_data_dict.items()):
        if progress_fn:
            progress_fn((i + 1) / total, f"Screening {ticker} ({i + 1}/{total})...")
        if len(df) < 64:
            excluded.append(ticker)
            continue
        indicators = compute_indicators(df)
        raw_score = compute_raw_rs_score(df, benchmark_df)
        if raw_score is not None:
            raw_rs[ticker] = raw_score
        stage1[ticker] = (df, indicators)

    normalised_rs = normalise_rs_scores(raw_rs)

    rows: list[dict] = []
    for ticker, (df, indicators) in stage1.items():
        rs_rating = normalised_rs.get(ticker)
        trend = check_trend_template(indicators)
        rs_pass = check_rs_rating(rs_rating)
        breakout = detect_breakout(df, indicators)
        sepa_pass = trend["all_pass"] is True and rs_pass is True

        rows.append({
            "Ticker": ticker,
            "Price": indicators.get("current_price"),
            "RS Rating": rs_rating,
            "Above SMA50": trend["above_sma50"],
            "Above SMA150": trend["above_sma150"],
            "Above SMA200": trend["above_sma200"],
            "SMA50>SMA150": trend["sma50_above_sma150"],
            "SMA50>SMA200": trend["sma50_above_sma200"],
            "SMA200 Uptrend": trend["sma200_uptrend"],
            "Near 52W High": trend["within_25pct_of_high"],
            "Above 52W Low": trend["above_30pct_of_low"],
            "Volume Surge": indicators.get("vol_surge"),
            "Breakout": breakout["breakout_detected"],
            "SEPA Pass": sepa_pass,
        })

    return rows, excluded
