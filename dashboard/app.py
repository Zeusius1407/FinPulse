"""FinPulse — interactive Streamlit dashboard.

Run (after the API is up and the DB is seeded/ingested):
    streamlit run dashboard/app.py

Talks to the REST API defined by FINPULSE_API_URL (default http://127.0.0.1:8000).
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

import api_client as api

st.set_page_config(page_title="FinPulse", page_icon="📈", layout="wide")

PERIODS = ["1mo", "3mo", "6mo", "1y", "max"]


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def fmt_mcap(v: float | None) -> str:
    if not v:
        return "—"
    if v >= 1e12:
        return f"₹{v / 1e12:.2f} L Cr"
    if v >= 1e7:
        return f"₹{v / 1e7:.0f} Cr"
    return f"₹{v:,.0f}"


def fmt_inr(v: float | None) -> str:
    return "—" if v is None else f"₹{v:,.2f}"


def fmt_pct(v: float | None) -> str:
    return "—" if v is None else f"{v:+.2f}%"


# --------------------------------------------------------------------------- #
# Cached data access (TTL so a fresh ingest shows up within a minute)
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=60)
def load_stocks():
    return api.get_stocks(limit=100)


@st.cache_data(ttl=60)
def load_summary():
    return api.get_market_summary()


@st.cache_data(ttl=60)
def load_detail(ticker: str):
    return api.get_stock(ticker)


@st.cache_data(ttl=60)
def load_history(ticker: str, period: str):
    return api.get_history(ticker, period)


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
st.sidebar.title("📈 FinPulse")
st.sidebar.caption("NSE market monitor")
st.sidebar.write(f"**API:** `{api.base_url()}`")
if st.sidebar.button("🔄 Refresh data"):
    st.cache_data.clear()
    st.rerun()

# Guard: if the API is unreachable, show a friendly message and stop.
try:
    stocks = load_stocks()
    summary = load_summary()
except api.APIError as exc:
    st.error(str(exc))
    st.info(
        "Start the API first:\n\n"
        "```\nuvicorn backend.main:app --reload\n```\n\n"
        "and seed data with `python -m scripts.seed_demo` "
        "(or `python -m backend.ingest` for live data)."
    )
    st.stop()

df = pd.DataFrame(stocks)
ticker_to_name = {r["ticker"]: r["name"] for r in stocks}
label = lambda t: f"{t}  ·  {ticker_to_name.get(t, '')}"  # noqa: E731

st.title("FinPulse — Indian Market Dashboard")
last = summary.get("last_updated")
st.caption(f"Tracking {summary['companies_tracked']} NSE companies · last updated {last}")

tab_overview, tab_detail, tab_compare = st.tabs(
    ["🏠 Market Overview", "🔎 Company Detail", "⚖️ Compare"]
)

# =========================================================================== #
# TAB 1 — Market Overview
# =========================================================================== #
with tab_overview:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Companies", summary["companies_tracked"])
    c2.metric("Total Mkt Cap", fmt_mcap(summary["total_market_cap"]))
    c3.metric("Advancers", summary["advancers"])
    c4.metric("Decliners", summary["decliners"])
    c5.metric("Avg P/E", f"{summary['avg_pe']:.1f}" if summary["avg_pe"] else "—")

    st.divider()
    g, l = st.columns(2)
    with g:
        st.subheader("🟢 Top Gainers")
        gdf = pd.DataFrame(summary["top_gainers"])[["ticker", "price", "change_pct"]]
        st.dataframe(
            gdf.rename(columns={"price": "Price", "change_pct": "Change %"}),
            hide_index=True,
            width='stretch',
        )
    with l:
        st.subheader("🔴 Top Losers")
        ldf = pd.DataFrame(summary["top_losers"])[["ticker", "price", "change_pct"]]
        st.dataframe(
            ldf.rename(columns={"price": "Price", "change_pct": "Change %"}),
            hide_index=True,
            width='stretch',
        )

    st.divider()
    sc1, sc2 = st.columns([3, 2])
    sectors = pd.DataFrame(summary["sectors"])
    with sc1:
        st.subheader("Market Cap by Sector")
        fig = px.treemap(
            sectors,
            path=[px.Constant("All"), "sector"],
            values="total_market_cap",
            color="avg_change_pct",
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
        )
        fig.update_layout(margin=dict(t=10, l=0, r=0, b=0), height=360)
        st.plotly_chart(fig, width='stretch')
    with sc2:
        st.subheader("Avg P/E by Sector")
        figpe = px.bar(
            sectors.sort_values("avg_pe", na_position="first"),
            x="avg_pe",
            y="sector",
            orientation="h",
            color="avg_pe",
            color_continuous_scale="Blues",
        )
        figpe.update_layout(margin=dict(t=10, l=0, r=0, b=0), height=360,
                            coloraxis_showscale=False, xaxis_title=None, yaxis_title=None)
        st.plotly_chart(figpe, width='stretch')

    st.divider()
    st.subheader("All Tracked Stocks")
    sort_col = st.selectbox(
        "Sort by", ["market_cap", "change_pct", "pe_ratio", "eps", "price", "ticker"]
    )
    show = df.sort_values(sort_col, ascending=False).copy()
    show_disp = show[
        ["ticker", "name", "sector", "price", "change_pct", "market_cap", "pe_ratio", "eps"]
    ].rename(
        columns={
            "name": "Company", "sector": "Sector", "price": "Price",
            "change_pct": "Change %", "market_cap": "Mkt Cap", "pe_ratio": "P/E", "eps": "EPS",
        }
    )
    st.dataframe(
        show_disp.style.format(
            {"Price": "₹{:.2f}", "Change %": "{:+.2f}%", "Mkt Cap": fmt_mcap,
             "P/E": "{:.1f}", "EPS": "₹{:.2f}"}
        ).map(
            lambda v: f"color: {'#16a34a' if v > 0 else '#dc2626'}" if isinstance(v, (int, float)) else "",
            subset=["Change %"],
        ),
        hide_index=True,
        width='stretch',
        height=420,
    )

# =========================================================================== #
# TAB 2 — Company Detail
# =========================================================================== #
with tab_detail:
    tickers = sorted(ticker_to_name)
    sel = st.selectbox("Company", tickers, format_func=label, key="detail_ticker")
    period = st.radio("Period", PERIODS, index=3, horizontal=True, key="detail_period")

    detail = load_detail(sel)
    q = detail.get("quote") or {}
    hist = load_history(sel, period)

    st.subheader(f"{detail['name']}  ·  {detail['ticker']}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Price", fmt_inr(q.get("price")), fmt_pct(q.get("change_pct")))
    m2.metric("Market Cap", fmt_mcap(q.get("market_cap")))
    m3.metric("P/E", f"{q['pe_ratio']:.1f}" if q.get("pe_ratio") else "—")
    m4.metric("EPS", fmt_inr(q.get("eps")))

    n1, n2, n3, n4 = st.columns(4)
    n1.metric("52W High", fmt_inr(q.get("week52_high")))
    n2.metric("52W Low", fmt_inr(q.get("week52_low")))
    n3.metric("P/B", f"{q['pb_ratio']:.2f}" if q.get("pb_ratio") else "—")
    n4.metric("Div Yield", f"{q['dividend_yield']:.2f}%" if q.get("dividend_yield") else "—")

    points = hist.get("points", [])
    if points:
        h = pd.DataFrame(points)
        h["date"] = pd.to_datetime(h["date"])
        fig = go.Figure()
        fig.add_trace(
            go.Candlestick(
                x=h["date"], open=h["open"], high=h["high"], low=h["low"], close=h["close"],
                name="OHLC", increasing_line_color="#16a34a", decreasing_line_color="#dc2626",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=h["date"], y=h["close"].rolling(20).mean(),
                line=dict(color="#2563eb", width=1.3), name="20D MA",
            )
        )
        fig.update_layout(
            height=460, margin=dict(t=20, l=0, r=0, b=0),
            xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.02),
        )
        st.plotly_chart(fig, width='stretch')

        volfig = px.bar(h, x="date", y="volume")
        volfig.update_layout(height=180, margin=dict(t=10, l=0, r=0, b=0),
                             xaxis_title=None, yaxis_title="Volume")
        st.plotly_chart(volfig, width='stretch')
    else:
        st.info("No price history available for this company/period.")

# =========================================================================== #
# TAB 3 — Comparison
# =========================================================================== #
with tab_compare:
    default = sorted(ticker_to_name)[:3]
    chosen = st.multiselect(
        "Pick companies to compare", sorted(ticker_to_name),
        default=default, format_func=label,
    )
    cperiod = st.radio("Period", PERIODS, index=3, horizontal=True, key="cmp_period")

    if not chosen:
        st.info("Select at least one company above.")
    else:
        details = api.compare(chosen)
        rows = []
        for d in details:
            q = d.get("quote") or {}
            rows.append(
                {
                    "Ticker": d["ticker"], "Company": d["name"], "Sector": d.get("sector"),
                    "Price": q.get("price"), "Change %": q.get("change_pct"),
                    "Mkt Cap": q.get("market_cap"), "P/E": q.get("pe_ratio"),
                    "EPS": q.get("eps"), "P/B": q.get("pb_ratio"),
                    "Div Yield %": q.get("dividend_yield"), "ROE %": q.get("roe"),
                }
            )
        cdf = pd.DataFrame(rows)

        st.subheader("Fundamentals")
        st.dataframe(
            cdf.style.format(
                {"Price": "₹{:.2f}", "Change %": "{:+.2f}%", "Mkt Cap": fmt_mcap,
                 "P/E": "{:.1f}", "EPS": "₹{:.2f}", "P/B": "{:.2f}",
                 "Div Yield %": "{:.2f}", "ROE %": "{:.1f}"},
                na_rep="—",
            ),
            hide_index=True,
            width='stretch',
        )

        b1, b2 = st.columns(2)
        with b1:
            st.caption("P/E ratio")
            st.plotly_chart(
                px.bar(cdf, x="Ticker", y="P/E", color="Ticker")
                .update_layout(showlegend=False, height=300, margin=dict(t=10, b=0)),
                width='stretch',
            )
        with b2:
            st.caption("Market cap")
            st.plotly_chart(
                px.bar(cdf, x="Ticker", y="Mkt Cap", color="Ticker")
                .update_layout(showlegend=False, height=300, margin=dict(t=10, b=0)),
                width='stretch',
            )

        st.subheader("Normalised price (rebased to 100)")
        norm = go.Figure()
        for t in chosen:
            h = pd.DataFrame(load_history(t, cperiod).get("points", []))
            if h.empty:
                continue
            h["date"] = pd.to_datetime(h["date"])
            base = h["close"].iloc[0]
            norm.add_trace(
                go.Scatter(x=h["date"], y=h["close"] / base * 100, mode="lines", name=t)
            )
        norm.update_layout(height=420, margin=dict(t=10, b=0),
                           yaxis_title="Indexed (start = 100)",
                           legend=dict(orientation="h", y=1.02))
        st.plotly_chart(norm, width='stretch')