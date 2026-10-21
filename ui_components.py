"""
ui_components.py — Componentes visuales del dashboard (Plotly + Streamlit)
==========================================================================
KPIs, gráficos en tiempo real y medidores de aceptación. Todos los gráficos
usan Plotly con tema oscuro para integrarse con Streamlit.
"""
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import format_hashrate

ACCENT = "#f7931a"          # naranja Bitcoin
GREEN = "#22c55e"
RED = "#ef4444"
BLUE = "#38bdf8"
BG_PAPER = "rgba(0,0,0,0)"


def _layout(fig, height=280, legend=False, y_title=None):
    fig.update_layout(
        height=height, paper_bgcolor=BG_PAPER, plot_bgcolor=BG_PAPER,
        margin=dict(l=10, r=10, t=30, b=10),
        font=dict(color="#d8dee9", size=12),
        showlegend=legend, legend=dict(orientation="h", y=1.12, x=0),
        xaxis=dict(showgrid=False, color="#6b7280"),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.07)",
                   color="#6b7280", title=y_title),
    )
    return fig


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
def kpi_grid(stats: dict, totals: dict, est: dict, price):
    cols = st.columns(6)
    alive = stats.get("alive", False)
    cols[0].metric(
        "⚡ Hashrate actual",
        format_hashrate(stats.get("hashrate", 0)),
        "en vivo" if alive else "detenido",
        delta_color="off")
    cols[1].metric(
        "✅ Shares OK / ❌ Rej",
        f"{stats.get('shares_ok', 0)} / {stats.get('shares_rej', 0)}",
        f"total {totals.get('shares_ok', 0)} históricos")
    cols[2].metric(
        "🎯 Dificultad",
        f"{stats.get('difficulty', 0) or '—'}",
        stats.get("mode", ""))
    cols[3].metric(
        "🪙 BTC estimado hoy",
        f"{est.get('btc_dia', 0):.10f}",
        f"{est.get('sats_dia', 0):,.0f} sats/día")
    cols[4].metric(
        "💵 USD estimado hoy",
        f"{est.get('usd_dia', 0):,.4f}" if price else "—",
        f"BTC = {price:,.2f} USD" if price else "precio no disp.")
    cols[5].metric(
        "⏱️ Uptime", _fmt_uptime(totals.get("uptime", 0)),
        f"bloques: {totals.get('blocks_found', 0)}")


def _fmt_uptime(s: float) -> str:
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"


# ---------------------------------------------------------------------------
# Gráfico principal: hashrate en vivo
# ---------------------------------------------------------------------------
def chart_hashrate(df: pd.DataFrame, height=300):
    fig = go.Figure()
    if df is None or df.empty:
        fig.add_annotation(text="Esperando datos… inicia el minero ⛏️",
                           showarrow=False, font=dict(size=16, color="#6b7280"))
        _layout(fig, height, y_title="H/s")
        return fig
    fig.add_trace(go.Scatter(
        x=df["dt"], y=df["hashrate"], name="Hashrate",
        line=dict(color=ACCENT, width=2.5, shape="spline"),
        fill="tozeroy", fillcolor="rgba(247,147,26,0.18)"))
    fig.update_traces(hovertemplate="%{x}<br>%{y:,.0f} H/s<extra></extra>")
    _layout(fig, height, y_title="H/s")
    return fig


def chart_shares(df: pd.DataFrame, height=220):
    """Shares aceptados vs rechazados acumulados en la ventana."""
    fig = go.Figure()
    if df is None or df.empty:
        _layout(fig, height, y_title="shares")
        return fig
    ok = df["ok"].astype(float)
    rej = df["rej"].astype(float)
    fig.add_trace(go.Scatter(x=df["dt"], y=ok, name="Shares OK acumulados",
                             line=dict(color=GREEN, width=2),
                             stackgroup=None, fill="tozeroy",
                             fillcolor="rgba(34,197,94,0.15)"))
    fig.add_trace(go.Scatter(x=df["dt"], y=rej, name="Rechazados",
                             line=dict(color=RED, width=1.5, dash="dot")))
    fig.update_traces(hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>")
    _layout(fig, height, legend=True, y_title="shares")
    return fig


def chart_difficulty(df: pd.DataFrame, height=200):
    fig = go.Figure()
    if df is None or df.empty or "diff" not in df:
        _layout(fig, height, y_title="diff")
        return fig
    fig.add_trace(go.Scatter(x=df["dt"], y=df["diff"].astype(float),
                             name="Dificultad", line=dict(color=BLUE, width=1.8)))
    _layout(fig, height, y_title="diff")
    return fig


def gauge_aceptacion(ok: int, rej: int, height=220):
    total = ok + rej
    pct = (ok / total * 100.0) if total else 100.0
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=pct,
        number=dict(suffix="%", valueformat=".1f"),
        delta=dict(reference=95.0, increasing=dict(color=GREEN),
                   decreasing=dict(color=RED)),
        title=dict(text="Shares aceptados", font=dict(size=14)),
        gauge=dict(
            axis=dict(range=[0, 100], tickcolor="#6b7280"),
            bar=dict(color=ACCENT, thickness=0.35),
            bgcolor="rgba(255,255,255,0.05)",
            steps=[
                dict(range=[0, 70], color="rgba(239,68,68,0.35)"),
                dict(range=[70, 92], color="rgba(250,204,21,0.3)"),
                dict(range=[92, 100], color="rgba(34,197,94,0.3)"),
            ],
            threshold=dict(line=dict(color=GREEN, width=3),
                           thickness=0.8, value=95),
        )))
    _layout(fig, height)
    return fig


def chart_red_vs_tu(network_hashrate: float, your_hashrate: float, height=240):
    """Comparación logarítmica: tu CPU frente a la red global (realidad)."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=["Tu minero", "Red BTC global"],
        y=[max(your_hashrate, 1e-3), network_hashrate or 1],
        marker_color=[GREEN, ACCENT],
        text=[format_hashrate(your_hashrate),
              format_hashrate(network_hashrate or 0)],
        textposition="outside"))
    fig.update_yaxes(type="log")
    fig.update_traces(hovertemplate="%{x}: %{text}<extra></extra>")
    _layout(fig, height, y_title="H/s (escala log)")
    return fig


# ---------------------------------------------------------------------------
# Tablas y logs
# ---------------------------------------------------------------------------
def render_event_log(events, height=320):
    if not events:
        st.info("Sin eventos todavía. Arranca el minero para ver la actividad en vivo.")
        return
    lines = []
    for e in reversed(events):
        icon = {"ok": "🟢", "warn": "🟡", "error": "🔴", "info": "⚪"}.get(
            e.get("level"), "⚪")
        t = time.strftime("%H:%M:%S", time.localtime(e.get("ts", 0)))
        lines.append(f"`{t}` {icon} {e.get('msg', '')}")
    with st.container(height=height):
        st.markdown("\n\n".join(lines))


def render_shares_table(shares, height=260):
    if not shares:
        st.caption("Aún no hay shares registrados.")
        return
    rows = []
    for s in reversed(shares):
        rows.append({
            "hora": time.strftime("%H:%M:%S", time.localtime(s.get("ts", 0))),
            "job": s.get("job", ""),
            "nonce": s.get("nonce", ""),
            "estado": s.get("status", ""),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", height=height, hide_index=True)


def badge(text: str, color: str):
    st.markdown(
        f"<span style='background:{color}22;color:{color};padding:2px 10px;"
        f"border-radius:10px;font-size:0.85em;font-weight:600'>{text}</span>",
        unsafe_allow_html=True)
