import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def build_detail_chart(
    df: pd.DataFrame,
    indicators: dict,
    benchmark_df: pd.DataFrame,
) -> go.Figure:
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.6, 0.2, 0.2],
        vertical_spacing=0.03,
        subplot_titles=("Price & SMAs", "Volume", "RS vs SPY"),
    )

    # ── Row 1: Candlestick ────────────────────────────────────────────────────
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"],
            name="Price",
            showlegend=False,
            increasing_line_color="green",
            decreasing_line_color="red",
        ),
        row=1, col=1,
    )

    # ── Row 1: SMA lines (skipped when insufficient data; notice added) ─────────
    skipped_smas: list[str] = []
    for window, name, color in [(50, "SMA50", "blue"), (150, "SMA150", "orange"), (200, "SMA200", "red")]:
        if len(df) >= window:
            sma = df["Close"].rolling(window).mean()
            fig.add_trace(
                go.Scatter(x=df.index, y=sma, name=name, line=dict(color=color, width=1.5)),
                row=1, col=1,
            )
        else:
            skipped_smas.append(name)

    if skipped_smas:
        fig.add_annotation(
            text=f"Not shown (insufficient data): {', '.join(skipped_smas)}",
            xref="paper", yref="paper",
            x=0.01, y=0.97, xanchor="left", yanchor="top",
            showarrow=False, font=dict(size=11, color="gray"),
        )

    # ── Row 1: 52-week high/low as dashed reference lines ────────────────────
    high_52w = indicators.get("high_52w")
    low_52w = indicators.get("low_52w")
    if high_52w is not None:
        fig.add_hline(y=high_52w, line_dash="dash", line_color="green", line_width=1, row=1, col=1)
    if low_52w is not None:
        fig.add_hline(y=low_52w, line_dash="dash", line_color="red", line_width=1, row=1, col=1)

    # ── Row 2: Volume bars coloured by direction ──────────────────────────────
    vol_colors = [
        "green" if c >= o else "red"
        for c, o in zip(df["Close"], df["Open"])
    ]
    fig.add_trace(
        go.Bar(x=df.index, y=df["Volume"], name="Volume", marker_color=vol_colors, showlegend=False),
        row=2, col=1,
    )

    # ── Row 3: RS line (stock / SPY cumulative return, indexed to 100) ────────
    if not benchmark_df.empty and "Close" in benchmark_df.columns:
        aligned = pd.concat(
            [df["Close"].rename("stock"), benchmark_df["Close"].rename("spy")],
            axis=1,
        ).dropna()
        if len(aligned) >= 2:
            rs = (aligned["stock"] / aligned["stock"].iloc[0]) / (aligned["spy"] / aligned["spy"].iloc[0]) * 100
            fig.add_trace(
                go.Scatter(x=aligned.index, y=rs, name="RS vs SPY", line=dict(color="purple", width=1.5)),
                row=3, col=1,
            )

    # ── Layout ────────────────────────────────────────────────────────────────
    fig.update_layout(
        height=700,
        showlegend=True,
        xaxis_rangeslider_visible=False,
        margin=dict(l=0, r=0, t=40, b=0),
    )
    fig.update_yaxes(title_text="Price ($)", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    fig.update_yaxes(title_text="RS (100 = start)", row=3, col=1)

    return fig
