import datetime
import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from charts import build_detail_chart
from csv_loader import discover_csv_files, load_csv_file, load_csv_name_map
from data_fetcher import fetch_ohlcv, fetch_spy_benchmark, fetch_ticker_names
from indicators import compute_indicators
from isin_resolver import resolve_isin
from classifier import classify_signal
from screener import run_full_screen

APP_DIR = Path(__file__).parent
DEPOT_CONFIG_PATH = APP_DIR / "depot_config.json"

try:
    from streamlit_autorefresh import st_autorefresh
    _HAS_AUTOREFRESH = True
except ImportError:
    _HAS_AUTOREFRESH = False

# ── Widget key manager ─────────────────────────────────────────────────────────
# Prevents DuplicateElementKey errors when the same widget type appears in
# multiple tabs (e.g. multiple download buttons, selectboxes).
_wc: dict[str, int] = {}


def _gk(prefix: str) -> str:
    n = _wc.get(prefix, 0)
    _wc[prefix] = n + 1
    return f"{prefix}_{n}"


# ── Sound alert ────────────────────────────────────────────────────────────────
def _play_sound(tone: str = "buy") -> None:
    freq = 880 if tone == "buy" else 440
    components.html(
        f"""<script>(function(){{try{{
        var c=new(window.AudioContext||window.webkitAudioContext)();
        var o=c.createOscillator();var g=c.createGain();
        o.connect(g);g.connect(c.destination);
        o.frequency.value={freq};o.type='sine';
        g.gain.setValueAtTime(0.3,c.currentTime);
        g.gain.exponentialRampToValueAtTime(0.001,c.currentTime+0.6);
        o.start(c.currentTime);o.stop(c.currentTime+0.6);
        }}catch(e){{}}}})()</script>""",
        height=0,
    )


# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Minervini SEPA Screener",
    page_icon="📈",
    layout="wide",
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("SEPA Screener")
    st.markdown("**Minervini Trend Template**")
    st.markdown(
        """
        Screens stocks against all 8 SEPA conditions:
        - Price above 50 / 150 / 200 SMA
        - 50 SMA above 150 and 200 SMA
        - 200 SMA trending upward
        - Within 25% of 52-week high
        - At least 30% above 52-week low
        - RS Rating ≥ 70
        """
    )
    st.divider()

    if _HAS_AUTOREFRESH:
        refresh_mins = st.number_input(
            "Auto-refresh (minutes, 0 = off)",
            min_value=0, max_value=60, value=0, step=5,
            key=_gk("refresh_input"),
        )
        if refresh_mins > 0:
            st_autorefresh(interval=int(refresh_mins * 60_000), key="autorefresh_ticker")

    if st.button("🔄 Re-scan", width='stretch'):
        for k in [k for k in st.session_state if k.startswith(("auto_load_", "depot_", "screen_"))]:
            st.session_state.pop(k, None)
        st.rerun()

    st.caption(f"CSV files loaded from:\n`{APP_DIR}`")


# ── Depot config loading ───────────────────────────────────────────────────────
# depot_config.json format:
# { "depots": [{ "name": "Smartbroker", "files": ["depot.csv"] }] }

def _load_depot_config() -> list[dict] | None:
    if not DEPOT_CONFIG_PATH.exists():
        return None
    try:
        cfg = json.loads(DEPOT_CONFIG_PATH.read_text(encoding="utf-8"))
        depots = cfg.get("depots") or []
        return depots if depots else None
    except Exception as exc:
        st.warning(f"Could not read depot_config.json: {exc}")
        return None


def _entries_from_depot_def(depot_def: dict) -> list[str]:
    entries: list[str] = []
    for fname in depot_def.get("files", []):
        fpath = APP_DIR / fname
        try:
            entries.extend(load_csv_file(fpath))
        except Exception as exc:
            st.warning(f"Could not load {fname}: {exc}")
    return list(dict.fromkeys(e.strip().upper() for e in entries if e.strip()))


def _names_from_depot_def(depot_def: dict) -> dict[str, str]:
    """Build {isin_or_ticker: display_name} from all files in a depot definition."""
    name_map: dict[str, str] = {}
    for fname in depot_def.get("files", []):
        name_map.update(load_csv_name_map(APP_DIR / fname))
    return name_map


def _build_ticker_to_name(isin_map: dict[str, str], raw_tickers: list[str], isin_name_map: dict[str, str]) -> dict[str, str]:
    """Map resolved tickers → display names using the per-file ISIN→name map."""
    ticker_to_name: dict[str, str] = {}
    for isin, ticker in isin_map.items():
        if isin in isin_name_map:
            ticker_to_name[ticker] = isin_name_map[isin]
    for ticker in raw_tickers:
        if ticker not in ticker_to_name and ticker in isin_name_map:
            ticker_to_name[ticker] = isin_name_map[ticker]
    return ticker_to_name


def _resolve_entries(depot_name: str, entries: list[str]) -> tuple[list[str], list[str], dict[str, str]]:
    """Resolve ISINs to ticker symbols; returns (tickers, failed_isins, isin_to_ticker)."""
    key_t = f"depot_{depot_name}_tickers"
    if key_t in st.session_state:
        return (
            st.session_state[key_t],
            st.session_state.get(f"depot_{depot_name}_failed", []),
            st.session_state.get(f"depot_{depot_name}_isin_map", {}),
        )

    raw_isins = [e for e in entries if len(e) == 12 and e[:2].isalpha()]
    raw_tickers = [e for e in entries if not (len(e) == 12 and e[:2].isalpha())]
    resolved: dict[str, str] = {}
    failed: list[str] = []

    if raw_isins:
        prog = st.progress(0, text=f"Resolving ISINs for {depot_name}…")
        for i, isin in enumerate(raw_isins):
            ticker = resolve_isin(isin)
            if ticker:
                resolved[isin] = ticker
            else:
                failed.append(isin)
            prog.progress((i + 1) / len(raw_isins), text=f"{depot_name}: {isin}")
        prog.empty()

    tickers = list(dict.fromkeys(list(resolved.values()) + raw_tickers))
    st.session_state[key_t] = tickers
    st.session_state[f"depot_{depot_name}_failed"] = failed
    st.session_state[f"depot_{depot_name}_isin_map"] = resolved
    return tickers, failed, resolved


# ── Build depot list ───────────────────────────────────────────────────────────
depot_config = _load_depot_config()

# Each depot: {name, tickers, failed_isins, isin_map}
depots: list[dict] = []

if depot_config:
    with st.sidebar:
        st.markdown("**Depots (depot_config.json):**")
    for depot_def in depot_config:
        name = depot_def.get("name", "Depot")
        entries = _entries_from_depot_def(depot_def)
        isin_name_map = _names_from_depot_def(depot_def)
        tickers, failed, isin_map = _resolve_entries(name, entries)
        raw_t = [e for e in entries if not (len(e) == 12 and e[:2].isalpha())]
        ticker_to_name = _build_ticker_to_name(isin_map, raw_t, isin_name_map)
        depots.append({"name": name, "tickers": tickers, "failed_isins": failed, "isin_map": isin_map, "ticker_to_name": ticker_to_name})
        with st.sidebar:
            st.caption(f"📁 {name}: {len(tickers)} tickers")

else:
    # Auto-discovery fallback
    if "auto_load_discovered" not in st.session_state:
        with st.spinner("Scanning for CSV files…"):
            st.session_state["auto_load_discovered"] = discover_csv_files(APP_DIR)

    discovered: dict[str, list[str]] = st.session_state["auto_load_discovered"]

    with st.sidebar:
        if discovered:
            st.markdown("**Discovered files:**")
            for fname, entries in discovered.items():
                isin_count = sum(1 for e in entries if len(e.strip()) == 12 and e.strip()[:2].isalpha())
                label = f"{isin_count} ISINs" if isin_count else f"{len(entries)} tickers"
                st.caption(f"📄 {fname} ({label})")
        else:
            st.caption("No broker CSV files found.")

    # Separate ISINs from legacy tickers across all discovered files
    raw_isins: list[str] = []
    raw_tickers: list[str] = []
    for _fname, _entries in discovered.items():
        for e in _entries:
            e = e.strip().upper()
            if len(e) == 12 and e[:2].isalpha():
                raw_isins.append(e)
            else:
                raw_tickers.append(e)
    raw_isins = list(dict.fromkeys(raw_isins))
    raw_tickers = list(dict.fromkeys(raw_tickers))

    if "auto_load_tickers" not in st.session_state and raw_isins:
        st.header("Resolving ISIN Codes")
        st.info(
            f"Found **{len(raw_isins)}** ISIN code(s) across {len(discovered)} file(s). "
            "Resolving to ticker symbols… (results cached in `isin_cache.json`)"
        )
        prog = st.progress(0, text="Starting ISIN resolution…")
        resolved_map: dict[str, str] = {}
        failed_isins: list[str] = []
        for i, isin in enumerate(raw_isins):
            ticker = resolve_isin(isin)
            if ticker:
                resolved_map[isin] = ticker
            else:
                failed_isins.append(isin)
            prog.progress(
                (i + 1) / len(raw_isins),
                text=f"Resolving ISINs: {i + 1}/{len(raw_isins)} — {isin}",
            )
        prog.empty()
        st.session_state["auto_load_isin_to_ticker"] = resolved_map
        st.session_state["auto_load_failed_isins"] = failed_isins
        st.session_state["auto_load_tickers"] = list(dict.fromkeys(list(resolved_map.values()) + raw_tickers))

    elif "auto_load_tickers" not in st.session_state:
        st.session_state["auto_load_isin_to_ticker"] = {}
        st.session_state["auto_load_failed_isins"] = []
        st.session_state["auto_load_tickers"] = raw_tickers

    _resolved_map = st.session_state.get("auto_load_isin_to_ticker", {})
    if discovered:
        depots = []
        for _fname, _fentries in discovered.items():
            _depot_name = Path(_fname).stem
            _file_isins, _file_tickers = [], []
            for _e in _fentries:
                _e = _e.strip().upper()
                if len(_e) == 12 and _e[:2].isalpha():
                    _file_isins.append(_e)
                else:
                    _file_tickers.append(_e)
            _file_resolved = {isin: _resolved_map[isin] for isin in _file_isins if isin in _resolved_map}
            _file_failed = [isin for isin in _file_isins if isin not in _resolved_map]
            _tickers = list(dict.fromkeys(list(_file_resolved.values()) + _file_tickers))
            _isin_name_map = load_csv_name_map(APP_DIR / _fname)
            _ticker_to_name = _build_ticker_to_name(_file_resolved, _file_tickers, _isin_name_map)
            depots.append({
                "name": _depot_name,
                "tickers": _tickers,
                "failed_isins": _file_failed,
                "isin_map": _file_resolved,
                "ticker_to_name": _ticker_to_name,
            })
    else:
        depots = [{
            "name": "All",
            "tickers": st.session_state.get("auto_load_tickers", []),
            "failed_isins": st.session_state.get("auto_load_failed_isins", []),
            "isin_map": _resolved_map,
            "ticker_to_name": {},
        }]


# ── Combined ticker list ───────────────────────────────────────────────────────
all_tickers: list[str] = list(dict.fromkeys(t for d in depots for t in d["tickers"]))

# ── Global ticker→name map (depot CSV primary, yfinance fallback) ──────────────
_global_ticker_to_name: dict[str, str] = {}
for _d in depots:
    _global_ticker_to_name.update(_d.get("ticker_to_name", {}))
_missing_names = tuple(t for t in all_tickers if t not in _global_ticker_to_name)
if _missing_names:
    _global_ticker_to_name.update(fetch_ticker_names(_missing_names))


# ── No data guard ──────────────────────────────────────────────────────────────
if not all_tickers:
    st.header("1. Data Sources")
    if depot_config:
        st.warning("No tickers could be resolved from `depot_config.json`. Check your CSV file paths.")
    else:
        st.info(
            f"No broker CSV files were found in `{APP_DIR}`.\n\n"
            "Place one of the following next to `app.py` and click **Re-scan**:\n"
            "- **Smartbroker** depot export (CSV with `ASSETKLASSE` column)\n"
            "- **Trade Republic** depot export (`ISIN;Name;Stücke;…`)\n"
            "- **ISIN reference list** (`ISIN;Name` per line)\n"
            "- **Legacy format** (CSV with a `Ticker` column)\n\n"
            "Or create a `depot_config.json` for named multi-depot support."
        )
    with st.expander("➕ Upload a CSV manually"):
        uf = st.file_uploader("CSV with a **Ticker** column", type="csv", key=_gk("fallback_upload"))
        if uf is not None:
            try:
                extra = pd.read_csv(uf)
                if "Ticker" in extra.columns:
                    all_tickers = extra["Ticker"].str.strip().dropna().tolist()
                    depots = [{"name": "Uploaded", "tickers": all_tickers, "failed_isins": [], "isin_map": {}}]
                    st.success(f"Loaded {len(all_tickers)} ticker(s) from upload.")
                else:
                    st.error("Uploaded file must have a 'Ticker' column.")
            except Exception as exc:
                st.error(f"Could not read uploaded file: {exc}")
    if not all_tickers:
        st.stop()


# ── Section 1: Data Sources ────────────────────────────────────────────────────
st.header("1. Data Sources")

with st.expander("➕ Add tickers from an additional file"):
    uploaded_file = st.file_uploader(
        "Upload a CSV with a **Ticker** column to add extra symbols",
        type="csv",
        key=_gk("extra_upload"),
    )
    if uploaded_file is not None:
        try:
            extra_df = pd.read_csv(uploaded_file)
            if "Ticker" in extra_df.columns:
                extra = extra_df["Ticker"].str.strip().dropna().tolist()
                new_tickers = [t for t in extra if t and t not in all_tickers]
                if new_tickers:
                    all_tickers = all_tickers + new_tickers
                    depots[0]["tickers"] = depots[0]["tickers"] + new_tickers
                    st.success(f"Added {len(new_tickers)} extra ticker(s).")
                else:
                    st.info("All tickers in the uploaded file are already included.")
            else:
                st.error("Uploaded file does not have a 'Ticker' column.")
        except Exception as exc:
            st.error(f"Could not read uploaded file: {exc}")

col1, col2, col3 = st.columns(3)
col1.metric("Files / Depots", len(depots) if depot_config else len(st.session_state.get("auto_load_discovered", {})))
col2.metric("Tickers total", len(all_tickers))
total_failed = sum(len(d["failed_isins"]) for d in depots)
if total_failed:
    col3.metric("ISINs failed", total_failed, delta_color="inverse")

for d in depots:
    if d["failed_isins"]:
        with st.expander(f"⚠️ {d['name']}: {len(d['failed_isins'])} ISIN(s) could not be resolved"):
            st.write(", ".join(d["failed_isins"]))
            st.caption(
                "These ISINs were not found. They may be delisted, use a different exchange, "
                "or require a manual override in `manual_ticker_map.csv`."
            )


# ── Section 2: Market Data ─────────────────────────────────────────────────────
st.header("2. Market Data")
st.write(f"Fetching 2 years of daily OHLCV data for **{len(all_tickers)}** ticker(s)…")
ohlcv_data = fetch_ohlcv(tuple(all_tickers))
spy_df = fetch_spy_benchmark()

loaded = len(ohlcv_data)
failed_fetch = len(all_tickers) - loaded
st.success(
    f"Loaded data for **{loaded}** ticker(s)."
    + (f" {failed_fetch} ticker(s) had no data and were skipped." if failed_fetch else "")
)


# ── Section 3: Screening ───────────────────────────────────────────────────────
st.header("3. Screening")

depot_results: list[tuple[list[dict], list[str]]] = []
_screen_prog = st.progress(0, text="Starting SEPA screen…")
for idx, depot in enumerate(depots):
    depot_ohlcv = {t: ohlcv_data[t] for t in depot["tickers"] if t in ohlcv_data}
    if depot_ohlcv:
        results, excluded = run_full_screen(
            depot_ohlcv,
            spy_df,
            progress_fn=lambda v, t, _d=depot["name"]: _screen_prog.progress(
                (idx + v) / len(depots), text=f"{_d}: {t}"
            ),
        )
    else:
        results, excluded = [], []
    for i, row in enumerate(results):
        try:
            row["Signal"] = classify_signal(row)
        except ValueError:
            row["Signal"] = "Sell-Panic"
        row["Score"] = row.get("RS Rating")
        name = _global_ticker_to_name.get(row.get("Ticker", ""), "")
        results[i] = {"Ticker": row["Ticker"], "Name": name, **{k: v for k, v in row.items() if k not in ("Ticker", "Name")}}
    depot_results.append((results, excluded))
_screen_prog.empty()
st.session_state["scan_completed_at"] = datetime.datetime.now()


# ── Helpers ────────────────────────────────────────────────────────────────────
_BOOL_COLS = [
    "Above SMA50", "Above SMA150", "Above SMA200",
    "SMA50>SMA150", "SMA50>SMA200", "SMA200 Uptrend",
    "Near 52W High", "Above 52W Low", "Volume Surge", "Breakout",
]

_SIGNAL_COLOURS = {
    "Buy":        "background-color: #198754; color: #ffffff",
    "Bullish":    "background-color: #d4edda; color: #155724",
    "Recovered":  "background-color: #20c997; color: #0d3d2b",
    "Neutral":    "background-color: #fff3cd; color: #856404",
    "Warning":    "background-color: #fd7e14; color: #4a1a00",
    "Chronic":    "background-color: #6c757d; color: #ffffff",
    "Sell-Panic": "background-color: #dc3545; color: #ffffff",
}


def _colour(val):
    if val is True:
        return "background-color: #d4edda; color: #155724"
    if val is False:
        return "background-color: #f8d7da; color: #721c24"
    return ""


def _signal_colour(val):
    return _SIGNAL_COLOURS.get(val, "")


def _styled(rows: list[dict]):
    df = pd.DataFrame(rows)
    df = df.drop(columns=["SEPA Pass"], errors="ignore")
    if "Score" in df.columns:
        df = df.sort_values("Score", ascending=False, na_position="last")
    present_bool = [c for c in _BOOL_COLS if c in df.columns]
    styler = df.style
    apply_fn = getattr(styler, "map", None) or styler.applymap
    styler = apply_fn(_colour, subset=present_bool)
    if "Signal" in df.columns:
        apply_fn2 = getattr(styler, "map", None) or styler.applymap
        styler = apply_fn2(_signal_colour, subset=["Signal"])
    return styler


def _build_depot_summary(depots: list[dict], depot_results: list) -> list[dict]:
    from classifier import SIGNAL_ORDER as _SO
    rows = []
    for depot, (results, excluded) in zip(depots, depot_results):
        counts = {tier: sum(1 for r in results if r.get("Signal") == tier) for tier in _SO}
        scores = [r["Score"] for r in results if r.get("Score") is not None]
        rows.append({
            "Depot": depot["name"],
            "Stocks": len(results),
            "Score Ø": round(sum(scores) / len(scores), 1) if scores else None,
            **{tier: counts[tier] for tier in _SO},
            "Errors": len(excluded),
        })
    if len(rows) > 1:
        totals: dict = {"Depot": "GESAMT", "Stocks": sum(r["Stocks"] for r in rows)}
        all_scores_flat = [
            r["Score"]
            for results, _ in depot_results
            for r in results
            if r.get("Score") is not None
        ]
        totals["Score Ø"] = round(sum(all_scores_flat) / len(all_scores_flat), 1) if all_scores_flat else None
        for tier in _SO:
            totals[tier] = sum(r[tier] for r in rows)
        totals["Errors"] = sum(r["Errors"] for r in rows)
        rows.append(totals)
    return rows


# ── Section 4: Results ─────────────────────────────────────────────────────────
st.header("4. Results")

tab_labels = ["Overview"] + [d["name"] for d in depots]
tabs = st.tabs(tab_labels)

# ── Overview tab ──────────────────────────────────────────────────────────────
with tabs[0]:
    # Status bar (W25)
    _completed_at = st.session_state.get("scan_completed_at")
    _refresh_mins = st.session_state.get("refresh_input_0", 60)
    _sb_c1, _sb_c2, _sb_c3, _sb_c4 = st.columns([3, 3, 2, 2])
    if _completed_at:
        _sb_c1.success(f"✓ Scan completed {_completed_at.strftime('%H:%M:%S')}")
        _sb_c2.caption(f"Last scan: {_completed_at.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        _sb_c1.info("Scan not yet run")
        _sb_c2.caption("")
    _sb_c3.caption(f"Auto-scan interval: {_refresh_mins} min")
    if _sb_c4.button("↺ Re-scan", key=_gk("rescan_overview")):
        for k in list(st.session_state.keys()):
            if k.startswith(("auto_load_", "depot_", "screen_")):
                del st.session_state[k]
        st.rerun()

    # Depot-Übersicht table (W27)
    _summary_rows = _build_depot_summary(depots, depot_results)
    if _summary_rows:
        st.subheader("Depot-Übersicht")
        _summary_df = pd.DataFrame(_summary_rows)

        def _style_summary(df: pd.DataFrame):
            from classifier import SIGNAL_ORDER as _SO2
            styler = df.style
            tier_cols = [c for c in _SO2 if c in df.columns]

            def _cell_colour(val, col):
                if col in tier_cols and isinstance(val, (int, float)) and val > 0:
                    return _SIGNAL_COLOURS.get(col, "")
                return ""

            for col in tier_cols:
                apply_fn = getattr(styler, "map", None) or styler.applymap
                styler = apply_fn(lambda v, c=col: _cell_colour(v, c), subset=[col])
            return styler

        st.dataframe(_style_summary(_summary_df), width='stretch')

    all_buy_signals = [
        {**r, "Depot": depots[i]["name"]}
        for i, (results, _) in enumerate(depot_results)
        for r in results
        if r.get("Signal") == "Buy"
    ]
    all_results_flat = [
        {**r, "Depot": depots[i]["name"]}
        for i, (results, _) in enumerate(depot_results)
        for r in results
    ]

    ov_c1, ov_c2, ov_c3, ov_c4 = st.columns(4)
    ov_c1.metric("Depots", len(depots))
    ov_c2.metric("Tickers screened", len(all_results_flat))
    ov_c3.metric("Buy signals", len(all_buy_signals))
    total_excl = sum(len(e) for _, e in depot_results)
    if total_excl:
        ov_c4.metric("Excluded (data)", total_excl)

    # Sound alert when new buy signals appear since last scan
    prev_buy = st.session_state.get("screen_prev_buy_count", -1)
    curr_buy = len(all_buy_signals)
    if prev_buy >= 0 and curr_buy > prev_buy:
        _play_sound("buy")
    st.session_state["screen_prev_buy_count"] = curr_buy

    # Category-count summary across all depots
    from classifier import SIGNAL_ORDER as _SO
    _tier_counts = {tier: sum(1 for r in all_results_flat if r.get("Signal") == tier) for tier in _SO}
    if all_results_flat:
        summary_parts = " / ".join(f"{_tier_counts[t]} {t}" for t in _SO)
        st.caption(f"Signal breakdown: {summary_parts}")
    else:
        st.caption("Signal breakdown: " + " / ".join(f"0 {t}" for t in _SO))

    if all_buy_signals:
        st.subheader("Buy Signals (all depots)")
        st.dataframe(_styled(all_buy_signals), width='stretch')
        buy_dl_df = pd.DataFrame(all_buy_signals).drop(columns=["SEPA Pass"], errors="ignore")
        if "Score" in buy_dl_df.columns:
            buy_dl_df = buy_dl_df.sort_values("Score", ascending=False, na_position="last")
        st.download_button(
            "⬇ Download buy signals CSV",
            buy_dl_df.to_csv(index=False).encode("utf-8"),
            "buy_signals.csv",
            "text/csv",
            key=_gk("dl_overview_buy"),
        )
    else:
        st.info("No buy signals found across all depots.")

    if all_results_flat:
        with st.expander("All results (all depots)"):
            st.dataframe(_styled(all_results_flat), width='stretch')
            all_dl_df = pd.DataFrame(all_results_flat).drop(columns=["SEPA Pass"], errors="ignore")
            if "Score" in all_dl_df.columns:
                all_dl_df = all_dl_df.sort_values("Score", ascending=False, na_position="last")
            st.download_button(
                "⬇ Download full CSV",
                all_dl_df.to_csv(index=False).encode("utf-8"),
                "sepa_results_all.csv",
                "text/csv",
                key=_gk("dl_overview_all"),
            )


# ── Per-depot tabs ─────────────────────────────────────────────────────────────
for i, depot in enumerate(depots):
    results, excluded = depot_results[i]
    with tabs[i + 1]:
        failed = depot.get("failed_isins", [])

        # KPI row
        buy_count = sum(1 for r in results if r.get("Signal") == "Buy")
        kc1, kc2, kc3, kc4 = st.columns(4)
        kc1.metric("Tickers", len(depot["tickers"]))
        kc2.metric("Screened", len(results))
        kc3.metric("Buy signals", buy_count)
        if failed:
            kc4.metric("ISIN failures", len(failed), delta_color="inverse")

        if failed:
            with st.expander(f"⚠️ {len(failed)} unresolved ISIN(s)"):
                st.write(", ".join(failed))
                st.caption("Add overrides to `manual_ticker_map.csv` (ISIN,Ticker).")

        if excluded:
            with st.expander(f"Excluded ({len(excluded)}) — insufficient history"):
                st.write(", ".join(excluded))

        if not results:
            st.info("No data available for this depot.")
            continue

        _TIER_ICONS = {
            "Buy": "🟢", "Bullish": "📈", "Recovered": "🔵",
            "Neutral": "🟡", "Warning": "🟠", "Chronic": "⚫", "Sell-Panic": "🔴",
        }
        from classifier import SIGNAL_ORDER as _SO_d
        _tier_tab_labels = ["📋 All Results"] + [f"{_TIER_ICONS.get(t, '')} {t}" for t in _SO_d] + ["📊 Detail Chart"]
        _all_sub, *_tier_tabs, _chart_sub = st.tabs(_tier_tab_labels)
        sub_chart = _chart_sub

        with _all_sub:
            sorted_results = sorted(
                results,
                key=lambda r: (_SO_d.index(r["Signal"]) if r.get("Signal") in _SO_d else len(_SO_d),
                               -(r.get("Score") or 0)),
            )
            st.dataframe(_styled(sorted_results), width='stretch')
            st.download_button(
                "⬇ Download CSV",
                pd.DataFrame(sorted_results).to_csv(index=False).encode("utf-8"),
                f"{depot['name']}_sepa_results.csv",
                "text/csv",
                key=_gk("dl_depot_all"),
            )

        for _tier, _tier_tab in zip(_SO_d, _tier_tabs):
            with _tier_tab:
                _tier_rows = sorted(
                    [r for r in results if r.get("Signal") == _tier],
                    key=lambda r: r.get("Score") or 0,
                    reverse=(_tier != "Sell-Panic"),
                )
                if _tier_rows:
                    st.dataframe(_styled(_tier_rows), width='stretch')
                    st.download_button(
                        "⬇ Download CSV",
                        pd.DataFrame(_tier_rows).to_csv(index=False).encode("utf-8"),
                        f"{depot['name']}_{_tier.lower().replace('-', '_')}.csv",
                        "text/csv",
                        key=_gk(f"dl_depot_{_tier}"),
                    )
                else:
                    st.info(f"No {_tier} signals for this depot.")

        with sub_chart:
            ticker_options = [r["Ticker"] for r in results]
            buy_sorted = sorted(
                [r for r in results if r.get("Signal") == "Buy"],
                key=lambda r: r.get("Score") or 0, reverse=True,
            )
            default = buy_sorted[0]["Ticker"] if buy_sorted else ticker_options[0]

            selected = st.selectbox(
                "Select ticker for detail view",
                options=ticker_options,
                index=ticker_options.index(default),
                key=_gk("ticker_select"),
            )
            if selected in ohlcv_data:
                df_sel = ohlcv_data[selected]
                ind_sel = compute_indicators(df_sel)
                fig = build_detail_chart(df_sel, ind_sel, spy_df)
                st.plotly_chart(fig, width='stretch')
            else:
                st.warning(f"No price data available for {selected}.")
