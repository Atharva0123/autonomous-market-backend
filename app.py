"""Bloomberg-inspired simplified market intelligence desk.

Run locally with ``streamlit run app.py``. Provider updates retain their upstream
cadence; the app never labels daily or delayed data as a live quote.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from io import BytesIO
from collections.abc import Iterator
from typing import Any

import plotly.graph_objects as go
import streamlit as st
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:  # Local run before requirements have been installed.
    st_autorefresh = None

from agent.dashboard_analytics import HistoricalScenario, historical_scenario
from agent.market_dashboard import load_global_pulse
from agent.orchestrator import ResearchAgent
from config import get_settings

logging.basicConfig(level=getattr(logging, get_settings().log_level.upper(), logging.INFO),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _find_series(value: Any) -> tuple[list[str], list[float], list[float | None]] | None:
    """Find a dated price/NAV series in common provider JSON payloads."""
    if isinstance(value, dict):
        rows = value.get("data")
        if isinstance(rows, list):
            points = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                date = row.get("date") or row.get("datetime") or row.get("timestamp")
                raw = row.get("nav") or row.get("close") or row.get("price") or row.get("value")
                try:
                    if date is not None and raw is not None:
                        volume = row.get("volume")
                        points.append((str(date), float(raw), float(volume) if volume is not None else None))
                except (TypeError, ValueError):
                    continue
            if points:
                points.reverse()
                return [x[0] for x in points], [x[1] for x in points], [x[2] for x in points]
        for child in value.values():
            found = _find_series(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_series(child)
            if found:
                return found
    return None


def _walk_dicts(value: Any) -> Iterator[dict[str, Any]]:
    """Yield nested JSON objects for provider-agnostic panel extraction."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _records(value: Any) -> list[dict[str, Any]]:
    """Find feed records without binding the dashboard to provider field casing."""
    result: list[dict[str, Any]] = []
    if isinstance(value, list):
        for child in value:
            result.extend(_records(child))
    elif isinstance(value, dict):
        lowered = {str(key).lower() for key in value}
        if lowered & {"ticker", "symbol", "headline", "title", "event", "sentiment_score"}:
            result.append(value)
        else:
            for child in value.values():
                result.extend(_records(child))
    return result


def _text(record: dict[str, Any], *names: str) -> str:
    lowered = {str(key).lower(): value for key, value in record.items()}
    for name in names:
        value = lowered.get(name.lower())
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)
    return ""


def _metric_any(results: list[dict[str, Any]], names: set[str]) -> str:
    """Render the first provider-supplied value from nested result payloads."""
    for result in results:
        for item in _walk_dicts(result.get("data")):
            for key, value in item.items():
                if key.lower().replace("_", "") in {x.replace("_", "") for x in names} and value is not None:
                    if isinstance(value, dict):
                        detail = next((v for k, v in value.items()
                                       if k.lower() in {"score", "index", "level", "label", "value", "assessment"}
                                       and isinstance(v, (str, int, float))), None)
                        if detail is not None:
                            return f"{detail:.2f}" if isinstance(detail, float) else str(detail)[:40]
                        continue
                    if isinstance(value, float):
                        return f"{value:.2f}"
                    return str(value)[:40]
    return "—"


def _pulse_results() -> list[dict[str, Any]]:
    """Refresh button callback; errors are normalized by each provider adapter."""
    results = asyncio.run(load_global_pulse(get_settings()))
    return [item.model_dump(mode="json") for item in results]


def _sentiment_score(results: list[dict[str, Any]]) -> float | None:
    values: list[float] = []
    for result in results:
        if not result.get("ok"):
            continue
        for item in _records(result.get("data")):
            raw = item.get("sentiment_score", item.get("sentiment", item.get("compound")))
            try:
                number = float(raw)
                if -1 <= number <= 1:
                    values.append(number)
            except (TypeError, ValueError):
                continue
            raw_fx = item.get("score")
            if result.get("provider") == "FXNewsBias" and isinstance(raw_fx, (int, float)):
                values.append(max(-1, min(1, (float(raw_fx) - 50) / 50)))
    return sum(values) / len(values) if values else None


def _render_sentiment_gauge(value: float | None) -> None:
    """Show the normalized -1..+1 feed sentiment aggregate."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value or 0.0, number={"suffix": "", "valueformat": "+.2f"},
        gauge={"axis": {"range": [-1, 1]}, "bar": {"color": "#65e6c1"},
                "steps": [{"range": [-1, -.2], "color": "#542b36"},
                          {"range": [-.2, .2], "color": "#283746"},
                          {"range": [.2, 1], "color": "#214d43"}]},
    ))
    fig.update_layout(height=190, margin=dict(l=16, r=16, t=10, b=0),
                      paper_bgcolor="rgba(0,0,0,0)", font_color="#d5e2ee")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    if value is None:
        st.caption("No normalized sentiment scores in the available feeds.")


def _headline_rows(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for result in results:
        if not result.get("ok"):
            continue
        for item in _records(result.get("data")):
            title = _text(item, "headline", "title", "event", "name", "summary")
            if not title or len(title) < 8:
                continue
            sentiment = _text(item, "sentiment", "sentiment_label", "bias", "sentiment_score") or "Not supplied"
            rows.append({"Trend / headline": title[:220], "Source": result.get("provider", "Provider"),
                         "Sentiment": sentiment, "Updated": _text(item, "updated_at", "timestamp", "date", "published_at") or "Provider timestamp unavailable"})
    return rows


def _pdf_bytes(report: dict[str, Any]) -> bytes:
    """Create a small PDF of the synthesized research report."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from xml.sax.saxutils import escape
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, title="Market research report")
    styles = getSampleStyleSheet()
    story = [Paragraph("Market Research Report", styles["Title"]), Spacer(1, 12),
             Paragraph(f"<b>Question:</b> {escape(report['query'])}", styles["BodyText"]), Spacer(1, 8),
             Paragraph(f"<b>Bias:</b> {escape(report['bias'].title())} · <b>Confidence:</b> {report['confidence']:.0%}", styles["BodyText"]), Spacer(1, 8),
             Paragraph(escape(report["executive_summary"]), styles["BodyText"]), Spacer(1, 12),
             Paragraph("Key findings", styles["Heading2"])]
    story.extend(Paragraph("• " + escape(item), styles["BodyText"]) for item in report.get("key_findings", []))
    story.append(Paragraph("Risks", styles["Heading2"]))
    story.extend(Paragraph("• " + escape(item), styles["BodyText"]) for item in report.get("risks", []))
    doc.build(story)
    return output.getvalue()


@st.fragment
def _render_global_pulse() -> None:
    """Market monitor with explicit feed status, source time and compact trend view."""
    # Keep refreshes scoped to this fragment so user input and the rest of the
    # dashboard stay mounted. The feed itself is fetched at most every 5 minutes.
    if st_autorefresh is not None:
        st_autorefresh(interval=30_000, key="global_pulse_autorefresh")
    col, refresh_col = st.columns([5, 1])
    col.markdown("### Global pulse")
    if refresh_col.button("↻ Refresh", type="primary", key="refresh_pulse"):
        with st.spinner("Updating configured global feeds…"):
            st.session_state["pulse_results"] = _pulse_results()
            st.session_state["pulse_updated"] = datetime.now().astimezone().isoformat(timespec="seconds")
            st.session_state["pulse_fetched_epoch"] = time.time()
    stale = time.time() - st.session_state.get("pulse_fetched_epoch", 0) >= 300
    if "pulse_results" not in st.session_state or stale:
        with st.spinner("Loading global context and retail sentiment…"):
            st.session_state["pulse_results"] = _pulse_results()
            st.session_state["pulse_updated"] = datetime.now().astimezone().isoformat(timespec="seconds")
            st.session_state["pulse_fetched_epoch"] = time.time()
    results: list[dict[str, Any]] = st.session_state["pulse_results"]
    st.caption(f"Snapshot fetched {st.session_state.get('pulse_updated', '—')} · upstream feed cadence varies · not an exchange quote")
    ok_count = sum(bool(item.get("ok")) for item in results)
    sentiment = _sentiment_score(results)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Feeds online", f"{ok_count}/{len(results)}")
    k2.metric("Retail / news sentiment", f"{sentiment:+.2f}" if sentiment is not None else "N/A", help="Mean of provider-normalized observations in the current snapshot.")
    k3.metric("Market regime", _metric_any(results, {"regime", "market_regime", "regime_label"}))
    k4.metric("Provider risk", _metric_any(results, {"risk_level", "risk_score", "risk_index", "risk"}))

    left, right = st.columns([1.05, 1.95], gap="large")
    with left:
        st.markdown("#### Sentiment tape")
        _render_sentiment_gauge(sentiment)
        wsb = next((item for item in results if item.get("provider") == "WallstreetBets" and item.get("ok")), None)
        if wsb:
            rows = []
            for item in _records(wsb.get("data")):
                ticker = _text(item, "ticker", "symbol")
                if ticker:
                    rows.append({"Ticker": ticker.upper(), "Sentiment": _text(item, "sentiment_score", "sentiment") or "—",
                                 "Mentions": _text(item, "no_of_comments", "comments", "mentions") or "—"})
            if rows:
                st.dataframe(rows[:12], width="stretch", hide_index=True, height=330)
        st.caption("Retail sentiment reflects public Reddit discussion, not investor positioning.")

    with right:
        st.markdown("#### Global trends & simplified news")
        headlines = _headline_rows(results)
        search = st.text_input("Filter by topic, company, or source", key="global_headline_filter")
        if search.strip():
            headlines = [row for row in headlines if search.lower() in " ".join(row.values()).lower()]
        if headlines:
            st.dataframe(headlines[:30], width="stretch", hide_index=True, height=465,
                         column_config={"Trend / headline": st.column_config.TextColumn(width="large")})
        else:
            st.info("No headline/event rows were returned. Add provider credentials or endpoints in .env to expand coverage.")
    with st.expander("Feed telemetry and raw payloads"):
        st.dataframe([{"Feed": item["provider"], "Status": "Online" if item["ok"] else "Unavailable",
                       "HTTP": item.get("status_code") or "—", "Latency ms": round(item.get("elapsed_ms", 0), 1),
                       "Cached": item.get("from_cache", False), "Error": item.get("error") or "—"} for item in results],
                     width="stretch", hide_index=True)
        for item in results:
            with st.expander(f"{item['provider']} payload"):
                st.json(item.get("data") if item.get("ok") else {"error": item.get("error")})


def _render_price_chart(series: tuple[list[str], list[float], list[float | None]]) -> None:
    """Render historical prices with interactive 7/30/90-session scenarios."""
    from plotly.subplots import make_subplots
    dates, prices, volumes = series
    chart = make_subplots(specs=[[{"secondary_y": True}]])
    chart.add_trace(go.Scatter(x=dates, y=prices, mode="lines", name="Historical close / NAV",
                               line={"color": "#48d8b5", "width": 2}), secondary_y=False)
    if any(value is not None for value in volumes):
        chart.add_trace(go.Bar(x=dates, y=volumes, name="Volume", opacity=.22, marker_color="#77a6d1"), secondary_y=True)
    forecasts = [(horizon, historical_scenario(prices, horizon)) for horizon in (7, 30, 90)]
    forecasts = [(horizon, estimate) for horizon, estimate in forecasts if estimate is not None]
    if forecasts:
        end = prices[-1]
        xfuture = [dates[-1], *(f"+{horizon} sessions" for horizon, _ in forecasts)]
        bases = [end, *(end * (1 + estimate.trend_growth_pct / 100) for _, estimate in forecasts)]
        bulls = [end, *(end * (1 + estimate.upper_scenario_pct / 100) for _, estimate in forecasts)]
        bears = [end, *(end * (1 + estimate.lower_scenario_pct / 100) for _, estimate in forecasts)]
        chart.add_trace(go.Scatter(x=xfuture, y=bulls, mode="lines", line={"width": 0},
                                   showlegend=False, hovertemplate="Bull scenario: %{y:.2f}<extra></extra>"), secondary_y=False)
        chart.add_trace(go.Scatter(x=xfuture, y=bears, mode="lines", line={"width": 0},
                                   fill="tonexty", fillcolor="rgba(244,183,93,.15)", name="Historical scenario range",
                                   hovertemplate="Bear scenario: %{y:.2f}<extra></extra>"), secondary_y=False)
        chart.add_trace(go.Scatter(x=xfuture, y=bases, mode="lines+markers", name="Base trend scenario",
                                   line={"color": "#f4b75d", "dash": "dash", "width": 2},
                                   hovertemplate="%{x}<br>Base trend: %{y:.2f}<extra></extra>"), secondary_y=False)
        chart.add_trace(go.Scatter(x=xfuture, y=bulls, mode="lines+markers", name="Bull scenario",
                                   line={"color": "#65e6c1", "dash": "dot", "width": 1.5},
                                   hovertemplate="%{x}<br>Bull scenario: %{y:.2f}<extra></extra>"), secondary_y=False)
        chart.add_trace(go.Scatter(x=xfuture, y=bears, mode="lines+markers", name="Bear scenario",
                                   line={"color": "#e97979", "dash": "dot", "width": 1.5},
                                   hovertemplate="%{x}<br>Bear scenario: %{y:.2f}<extra></extra>"), secondary_y=False)
    chart.update_layout(height=390, margin=dict(l=8, r=8, t=18, b=8), paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)", font_color="#c6d5e3", legend={"orientation": "h", "y": 1.1})
    chart.update_yaxes(title_text="Price / NAV", secondary_y=False, gridcolor="#233444")
    chart.update_yaxes(title_text="Volume", secondary_y=True, showgrid=False)
    st.plotly_chart(chart, width="stretch", config={"displayModeBar": "hover", "scrollZoom": True})


def _render_asset_research() -> None:
    """On-demand research page with sourced signals and historical scenarios."""
    st.markdown("### Asset research")
    symbol_col, horizon_col, run_col = st.columns([2, 1, 1])
    if "asset_symbol" not in st.session_state:
        st.session_state["asset_symbol"] = "NVDA"
    symbol = symbol_col.text_input("Ticker / fund scheme code", max_chars=16, key="asset_symbol").strip().upper()
    horizon = horizon_col.selectbox("Trend horizon", ["20 sessions", "60 sessions"], index=0)
    if run_col.button("Run asset research", type="primary", disabled=not symbol):
        query = (f"Analyze {symbol} historical price trend, latest available news, retail sentiment, "
                 f"fundamentals, growth outlook, risk outlook, and catalysts")
        with st.spinner(f"Researching {symbol} across configured feeds…"):
            agent = ResearchAgent(get_settings())
            events: list[str] = []
            report = asyncio.run(agent.run(query, on_event=events.append))
        st.session_state["asset_report"] = report.model_dump(mode="json")
        st.session_state["asset_trace"] = events
        st.session_state["asset_report_symbol"] = symbol
    raw = st.session_state.get("asset_report")
    if not raw:
        st.info("Enter a ticker or fund scheme code and run research to load its chart, source-backed sentiment, and scenarios.")
        return
    # The report symbol is separate from the text_input's widget state. This
    # avoids mutating a widget key after Streamlit has instantiated it.
    symbol = st.session_state.get("asset_report_symbol", symbol)
    results = raw.get("tool_results", [])
    series = next((_find_series(result.get("data")) for result in results
                   if result.get("ok") and _find_series(result.get("data"))), None)
    prices = series[1] if series else []
    sessions = 20 if horizon.startswith("20") else 60
    scenario = historical_scenario(prices, sessions) if prices else None

    st.markdown(f"#### {symbol} · research snapshot")
    sentiment = _sentiment_score(results)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Research bias", raw["bias"].title(), help="Synthesis of returned, explicitly scored provider data.")
    m2.metric("Sentiment", f"{sentiment:+.2f}" if sentiment is not None else "N/A")
    m3.metric(f"{sessions}-session trend scenario", f"{scenario.trend_growth_pct:+.1f}%" if scenario else "Not available")
    m4.metric("Historical risk profile", f"{scenario.risk_label} · {scenario.risk_score:.0f}/100" if scenario else "Not available")
    left, right = st.columns([1.6, 1], gap="large")
    with left:
        st.markdown("#### Price / NAV and volume")
        if series:
            st.caption("Historical provider observations · latest available; delayed or end-of-day data may be shown.")
            _render_price_chart(series)
        else:
            st.warning("No configured provider returned price history. Configure Marketstack or another equity data feed for this ticker.")
    with right:
        st.markdown("#### Executive readout")
        st.write(raw["executive_summary"])
        if scenario:
            st.markdown("#### Growth & risk scenario")
            st.write(f"The log-linear historical trend implies **{scenario.trend_growth_pct:+.1f}%** over {sessions} sessions. "
                     f"A realized-volatility scenario range is **{scenario.lower_scenario_pct:+.1f}% to {scenario.upper_scenario_pct:+.1f}%**.")
            st.write(f"Historical annualized volatility was **{scenario.annualized_volatility_pct:.1f}%**; observed maximum drawdown was **{scenario.max_drawdown_pct:.1f}%**.")
            st.caption("Transparent descriptive model; range uses realized daily volatility, is not calibrated, and is not investment advice.")
        else:
            st.caption("Trend/risk scenario needs at least 10 positive historical observations from a configured price provider.")
        for item in raw.get("risks", [])[:5]:
            st.write("• " + item)

    relevant = []
    for result in results:
        if not result.get("ok"):
            continue
        for item in _records(result.get("data")):
            ticker = _text(item, "ticker", "symbol").upper()
            title = _text(item, "headline", "title", "event", "summary")
            if ticker == symbol or (title and symbol.lower() in title.lower()):
                relevant.append({"News / discussion": title or ticker, "Source": result.get("provider"),
                                 "Sentiment": _text(item, "sentiment_score", "sentiment", "score") or "Not supplied",
                                 "Mentions": _text(item, "no_of_comments", "mentions") or "—"})
    st.markdown("#### Related news & sentiment")
    if relevant:
        st.dataframe(relevant[:20], width="stretch", hide_index=True)
    else:
        st.caption("No related, symbol-tagged story rows were returned in this run. Review provider coverage and raw payloads.")

    st.markdown("#### Findings and sources")
    for item in raw.get("key_findings", []):
        st.write("• " + item)
    st.dataframe([{"Source": row["provider"], "Status": "Online" if row["ok"] else "Unavailable",
                   "HTTP": row.get("status_code") or "—", "Latency ms": round(row.get("elapsed_ms", 0), 1),
                   "Freshness": raw.get("data_freshness", {}).get(row["provider"], "timestamp unavailable"),
                   "Error": row.get("error") or "—"} for row in results], width="stretch", hide_index=True)
    markdown = (f"# {symbol} research report\n\n{raw['executive_summary']}\n\n"
                f"**Bias:** {raw['bias']} · **Confidence:** {raw['confidence']:.0%}\n\n"
                + "## Findings\n" + "\n".join(f"- {x}" for x in raw.get("key_findings", []))
                + "\n\n## Risks\n" + "\n".join(f"- {x}" for x in raw.get("risks", [])))
    ex1, ex2, ex3 = st.columns(3)
    ex1.download_button("Download Markdown", markdown, file_name=f"{symbol.lower()}_research.md")
    ex2.download_button("Download JSON", json.dumps(raw, indent=2), file_name=f"{symbol.lower()}_research.json", mime="application/json")
    ex3.download_button("Download PDF", _pdf_bytes(raw), file_name=f"{symbol.lower()}_research.pdf", mime="application/pdf")
    trace = st.session_state.get("asset_trace", [])
    with st.expander("Execution trace and raw provider payloads"):
        st.code("\n".join(trace) or "No trace captured.")
        st.json(results)


def _render_overview() -> None:
    """High-density terminal-style landing page and navigation."""
    with st.sidebar:
        st.markdown("## MARKET INTELLIGENCE")
        def open_template(asset: str | None = None) -> None:
            st.session_state["workspace_page"] = "Asset Research" if asset is not None else "Global Pulse"
            if asset is not None:
                st.session_state["asset_symbol"] = asset

        st.divider()
        st.markdown("**Research templates**")
        st.button("Tech macro + NVDA sentiment", on_click=open_template, args=("NVDA",), use_container_width=True)
        st.button("Forex bias + energy CPI", on_click=open_template, args=(None,), use_container_width=True)
        st.button("India mutual fund allocation", on_click=open_template, args=("",), use_container_width=True)
        page = st.radio("Workspace", ["Global Pulse", "Asset Research"], key="workspace_page",
                        label_visibility="collapsed")
        st.caption("Data subscriptions and optional LLM providers are configured in `.env`.")
        st.markdown("---")
        st.caption("Research outputs are source-attributed and informational. Verify market data and scenarios independently.")
    st.markdown(f"<div class='tickerbar'>GLOBAL MARKETS&nbsp;&nbsp; / &nbsp;&nbsp;RESEARCH DESK <span>● SYSTEM ONLINE</span></div>", unsafe_allow_html=True)
    st.title("Market Intelligence Desk")
    st.caption("Global themes · simplified news · source-backed asset research")
    if page == "Asset Research":
        _render_asset_research()
    else:
        _render_global_pulse()


st.set_page_config(page_title="Market Intelligence Desk", layout="wide", page_icon="📊")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap');
:root{--bg:#080e15;--panel:#101a25;--line:#203141;--text:#d7e2ec;--muted:#8fa4b6;--green:#65e6c1;--amber:#f4b75d}
.stApp{background:radial-gradient(ellipse at 12% -10%,#142a39 0,transparent 42%),var(--bg);color:var(--text);font-family:'Manrope',sans-serif}
.block-container{max-width:1680px;padding-top:1.25rem;padding-bottom:2.5rem}
[data-testid="stMetric"]{background:linear-gradient(135deg,#101b26,#0e1721);border:1px solid var(--line);border-radius:9px;padding:15px 17px}
[data-testid="stMetricLabel"]{color:var(--muted);font-size:.77rem;text-transform:uppercase;letter-spacing:.07em}
[data-testid="stMetricValue"]{font-family:'DM Mono',monospace;font-size:1.55rem;color:#e7f1f8}
[data-testid="stSidebar"]{background:#0b131c;border-right:1px solid var(--line)}
h1,h2,h3{letter-spacing:-.035em} h1{font-size:2.15rem!important} h3{font-size:1.22rem!important}
.tickerbar{font:500 11px 'DM Mono',monospace;color:#9bb2c4;letter-spacing:.12em;border-bottom:1px solid var(--line);padding:8px 0 12px;margin-bottom:14px}
.tickerbar span{float:right;color:var(--green)}
div[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:8px;overflow:hidden}
button[kind="primary"]{background:#136d5b;border:1px solid #218e75}
</style>
""", unsafe_allow_html=True)
_render_overview()
