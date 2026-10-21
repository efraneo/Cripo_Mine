"""
app.py — BTC MINER STUDIO · Dashboard Streamlit en tiempo real
==============================================================
Ejecutar:   streamlit run app.py

Pestañas: Panel en vivo · Red y Pool · Binance · Historial · Ayuda y Secrets
Los claves van en .streamlit/secrets.toml (ver pestaña Ayuda o el README).
"""
import time

import streamlit as st

from config import (load_secrets, POOL_CATALOG, SECRETS_HELP,
                    format_hashrate, format_btc, format_uptime)
from state_store import StateStore
from stratum_miner import make_miner
from binance_api import make_binance, BinanceAPI, format_deposit_status
from pool_stats import (get_price, network_stats, estimate_profitability,
                        f2pool_stats, nicehash_stats)
import ui_components as ui

st.set_page_config(page_title="⛏️ BTC Miner Studio", page_icon="⛏️",
                   layout="wide", initial_sidebar_state="expanded")

# ---------------------------------------------------------------------------
# Runtime compartido (sobrevive a los reruns de Streamlit)
# ---------------------------------------------------------------------------


@st.cache_resource
def get_runtime() -> dict:
    cfg = load_secrets()
    store = StateStore.get()
    binance = make_binance(cfg["BINANCE_API_KEY"], cfg["BINANCE_API_SECRET"])
    store.append_event("App iniciada", "info")
    return {"cfg": cfg, "store": store, "binance": binance,
            "miner": None, "deposit_address": "", "payout_override": ""}


RT = get_runtime()
STORE = RT["store"]
CFG = RT["cfg"]


@st.cache_data(ttl=60, show_spinner=False)
def get_price_cached(source: str):
    return get_price(source)


@st.cache_data(ttl=120, show_spinner=False)
def network_stats_cached():
    return network_stats()


# ---------------------------------------------------------------------------
# Control del minero
# ---------------------------------------------------------------------------
def miner_callbacks():
    return (lambda m, l="info": STORE.append_event(m, l),
            lambda j, n, s: STORE.append_share(j, n, s),
            on_stats_callback)


def on_stats_callback(stats: dict):
    STORE.set_last_stats(stats)
    STORE.append_history(stats.get("hashrate", 0), stats.get("difficulty", 0),
                         stats.get("shares_ok", 0), stats.get("shares_rej", 0))


def start_miner():
    if RT["miner"] is not None:
        try:
            RT["miner"].stop()
        except Exception:
            pass
        RT["miner"] = None
    mode = st.session_state.get("mode_sel", CFG["MINER_MODE"])
    pool_url = st.session_state.get("pool_url_sel", CFG["POOL_URL"])
    user = (st.session_state.get("pool_user_in", "")
            or CFG["POOL_USER"] or CFG["BTC_PAYOUT_ADDRESS"]
            or RT.get("payout_override", "")).strip()
    worker = st.session_state.get("worker_in", CFG["WORKER_NAME"]).strip()
    if user and worker and "." not in user:
        user = f"{user}.{worker}"
    password = st.session_state.get("pool_pass_in", CFG["POOL_PASSWORD"]) or "x"
    threads = int(st.session_state.get("threads_in", CFG["CPU_THREADS"]))
    STORE.mark_started()
    on_event, on_share, on_stats = miner_callbacks()
    try:
        if mode == "external":
            from miner_manager import ExternalMiner
            path = CFG["EXTERNAL_MINER_PATH"]
            miner = ExternalMiner(path, CFG["EXTERNAL_MINER_ARGS"], pool_url,
                                  user, password, threads,
                                  on_event, on_share, on_stats)
            miner.start()
        else:
            miner = make_miner(mode, pool_url, user, password, threads,
                               on_event, on_share, on_stats)
            miner.start()
        RT["miner"] = miner
        STORE.append_event(f"Modo {mode.upper()} · pool={pool_url} · "
                           f"user={user} · hilos={threads}", "ok")
    except Exception as e:
        RT["miner"] = None
        STORE.append_event(f"No se pudo iniciar: {e}", "error")
        st.error(f"No se pudo iniciar el minero: {e}")


def stop_miner():
    m = RT.get("miner")
    if m is not None:
        try:
            m.stop()
        except Exception:
            pass
    RT["miner"] = None
    STORE.append_event("Minero detenido desde el dashboard", "warn")
    STORE.save(force=True)


def miner_alive() -> bool:
    m = RT.get("miner")
    return bool(m and m.is_running())


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## ⛏️ BTC Miner Studio")
    st.caption("Minado SHA-256 en Python · métricas reales · envío a Binance")

    c1, c2 = st.columns(2)
    c1.markdown("🟢 **Pool**" if miner_alive() else "🔴 **Pool**")
    c2.markdown("🟢 **Minero**" if miner_alive() else "🔴 **Minero**")

    st.divider()
    mode = st.radio(
        "Motor de minado",
        ["python", "bench", "demo", "external"],
        index=["python", "bench", "demo", "external"].index(
            CFG.get("MINER_MODE", "python")),
        format_func=lambda m: {
            "python": "🐍 Python nativo (pool real)",
            "bench": "🧪 Benchmark local (sin pool)",
            "demo": "🎭 Demo simulada",
            "external": "⚙️ Binario externo (XMRig…)",
        }[m],
        key="mode_sel")

    pool_opts = [p["url"] for p in POOL_CATALOG]
    pool_idx = pool_opts.index(CFG["POOL_URL"]) if CFG["POOL_URL"] in pool_opts else 0
    pool_url = st.selectbox("Pool (pago en BTC)", pool_opts, index=pool_idx,
                            key="pool_url_sel",
                            help="Public Pool tiene dificultad mínima baja: "
                                 "ideal para ver shares con CPU.")
    if mode == "python" or mode == "external":
        st.caption(f"ℹ️ {POOL_CATALOG[pool_idx]['nota']}")

    user_in = st.text_input(
        "Usuario del pool (dirección BTC)",
        value=(RT.get("payout_override") or CFG["POOL_USER"]
               or CFG["BTC_PAYOUT_ADDRESS"]),
        placeholder="bc1q… o 1A1zP…",
        key="pool_user_in",
        help="Se usa tu dirección BTC; si es de depósito de Binance, los sats "
             "llegan directamente a tu cuenta.")
    worker_in = st.text_input("Nombre del worker", value=CFG["WORKER_NAME"],
                              key="worker_in")
    pass_in = st.text_input("Contraseña del pool", value=CFG["POOL_PASSWORD"],
                            key="pool_pass_in")
    threads_in = st.slider("Hilos de CPU", 1, 8, CFG["CPU_THREADS"],
                           key="threads_in")

    b1, b2 = st.columns(2)
    if b1.button("▶️ INICIAR", type="primary", width="stretch"):
        start_miner()
        st.rerun()
    if b2.button("⏹️ DETENER", width="stretch"):
        stop_miner()
        st.rerun()

    st.divider()
    auto = st.toggle("🔄 Refresco automático", value=True, key="auto_refresh")
    st.caption(f"Cada {CFG['AUTO_REFRESH_SECONDS']} s (configurable en secrets: "
               f"AUTO_REFRESH_SECONDS)")
    if miner_alive():
        st.caption(f"⏱️ Uptime: {format_uptime(STORE.totals().get('uptime', 0))}")

# ---------------------------------------------------------------------------
# TABS
# ---------------------------------------------------------------------------
tab_live, tab_net, tab_bin, tab_hist, tab_help = st.tabs(
    ["📊 Panel en vivo", "🌐 Red y Pool", "🏦 Binance",
     "📜 Historial y logs", "⚙️ Ayuda y Secrets"])


# ===========================================================================
# PESTAÑA 1 · PANEL EN VIVO (fragmento auto-refrescante)
# ===========================================================================
def render_live():
    stats = STORE.last()
    if not stats:
        mode = st.session_state.get("mode_sel", "python")
        stats = {"mode": mode, "hashrate": 0, "shares_ok": 0, "shares_rej": 0,
                 "difficulty": 0, "uptime": 0, "alive": miner_alive()}
    totals = STORE.totals()
    price, price_src = get_price_cached(CFG.get("PRICE_SOURCE", "binance"))
    net = network_stats_cached()
    est = estimate_profitability(stats.get("hashrate", 0) or 0, net, price)

    ui.kpi_grid(stats, totals, est, price)

    left, right = st.columns([2, 1])
    with left:
        st.plotly_chart(ui.chart_hashrate(STORE.history_df(240)),
                        width="stretch", key=f"hr{time.time()//5}")
        st.plotly_chart(ui.chart_shares(STORE.history_df(240)),
                        width="stretch", key=f"sh{time.time()//5}")
    with right:
        st.plotly_chart(ui.gauge_aceptacion(stats.get("shares_ok", 0),
                                            stats.get("shares_rej", 0)),
                        width="stretch", key=f"gg{time.time()//5}")
        m1, m2 = st.columns(2)
        m1.metric("📈 Proyección USD 30 días",
                  f"{est.get('usd_mes', 0):,.2f}" if price else "—")
        m2.metric("🎲 Prob. bloque/día",
                  f"1 en {1/max(est.get('prob_bloque_dia',0),1e-30):,.0f}"
                  if est.get("prob_bloque_dia") else "—")
        st.caption(f"Precio BTC: **{price:,.2f} USD** ({price_src})" if price
                   else "Precio no disponible")
        st.caption(f"Hashrate red: **{format_hashrate(net.get('network_hashrate') or 0)}**")
        st.caption(f"Recompensa bloque: **{est.get('reward_btc', 0):.4f} BTC**")
        st.progress(min(1.0, (stats.get("hashrate", 0) or 0) /
                        max(net.get("network_hashrate") or 1, 1)),
                    text=f"Tu hash vs red (log-imaginario 😅)")

    st.divider()
    st.subheader("📜 Consola en vivo")
    ui.render_event_log(STORE.events_list(80))


live_fragment = st.fragment(run_every=CFG["AUTO_REFRESH_SECONDS"])(render_live)

with tab_live:
    if st.session_state.get("auto_refresh", True):
        live_fragment()
    else:
        render_live()
        if st.button("🔄 Refrescar ahora"):
            st.rerun()


# ===========================================================================
# PESTAÑA 2 · RED Y POOL
# ===========================================================================
with tab_net:
    st.header("🌐 Estado real de la red Bitcoin")
    net = network_stats_cached()
    stats = STORE.last()
    c1, c2, c3 = st.columns(3)
    c1.metric("Hashrate de red", format_hashrate(net.get("network_hashrate") or 0),
              "mempool.space")
    c2.metric("Dificultad", f"{net.get('difficulty') or 0:,.0f}")
    c3.metric("Recompensa/bloque", f"{net.get('last_reward_btc') or 0:.4f} BTC")

    price, _ = get_price_cached("binance")
    est = estimate_profitability((stats or {}).get("hashrate", 0) or 0, net, price)
    a, b, d = st.columns(3)
    a.metric("BTC esperado/día", f"{est['btc_dia']:.10f}")
    b.metric("USD esperado/día", f"{est['usd_dia']:,.4f}" if price else "—")
    d.metric("Años esperados para 1 bloque",
             f"{est['anios_esperados_bloque']:,.0f}" if
             est.get("anios_esperados_bloque") else "—")

    st.plotly_chart(ui.chart_red_vs_tu(net.get("network_hashrate") or 0,
                                       (stats or {}).get("hashrate", 0) or 0),
                    width="stretch")
    st.info("💡 **Honestidad matemática**: con CPU tu hashrate es ínfimo frente "
            "a los ~700 EH/s de la red. El valor de esta app es el pipeline "
            "completo real (pool → shares → Binance) y el aprendizaje. "
            "Para hashrate serio necesitas ASIC (S19/S21) o minar Monero con "
            "XMRig y convertir a BTC.")

    st.subheader("📡 API del pool (si tienes cuenta)")
    f2 = CFG.get("F2POOL_ACCOUNT")
    nh = None
    if f2:
        f2s = f2pool_stats(f2)
        if f2s:
            c1, c2, c3 = st.columns(3)
            c1.metric("Hashrate F2Pool", format_hashrate(f2s["hashrate"]))
            c2.metric("Workers", f2s["workers"])
            c3.metric("No pagado", format_btc(f2s["unpaid_btc"]))
    if CFG.get("NICEHASH_API_KEY") and CFG.get("NICEHASH_API_SECRET") \
            and CFG.get("NICEHASH_ORG_ID"):
        nh = nicehash_stats(CFG["NICEHASH_API_KEY"], CFG["NICEHASH_API_SECRET"],
                            CFG["NICEHASH_ORG_ID"])
        if nh:
            st.metric("Hashrate NiceHash", format_hashrate(nh.get("hashrate", 0)))
    if not f2 and not nh:
        st.caption("Configura F2POOL_ACCOUNT o las claves NICEHASH_* en secrets "
                   "para ver estadísticas de tu cuenta en el pool.")

    st.subheader("🗂️ Catálogo de pools soportados")
    import pandas as pd
    df_pools = pd.DataFrame(POOL_CATALOG)
    st.dataframe(df_pools, width="stretch", hide_index=True)


# ===========================================================================
# PESTAÑA 3 · BINANCE
# ===========================================================================
with tab_bin:
    st.header("🏦 Conexión con Binance")
    bx = RT["binance"]
    is_sim = isinstance(bx, object) and not isinstance(bx, BinanceAPI)
    if is_sim:
        st.warning("⚠️ Modo SIMULADO: no hay claves configuradas. Añade "
                   "BINANCE_API_KEY y BINANCE_API_SECRET en "
                   "`.streamlit/secrets.toml` (permiso de lectura es suficiente).")
    else:
        try:
            ping = bx.ping()
            st.success(f"✅ Conectado a Binance · latencia {ping['latency_ms']} ms · "
                       f"claves con permiso de lectura")
        except Exception as e:
            st.error(f"❌ No se pudo conectar: {e}")

    price, src = get_price_cached("binance")
    if price:
        st.metric("₿ Precio BTC/USDT", f"{price:,.2f} USD", f"vía {src}")

    st.subheader("📥 Dirección de depósito BTC")
    st.caption("Los pools pagan a una dirección BTC. Si pones aquí tu dirección "
               "de depósito de Binance como *usuario del pool*, los sats minados "
               "llegan directos a tu cuenta sin mover un dedo.")
    if st.button("🔍 Obtener mi dirección de depósito vía API", type="primary"):
        try:
            d = bx.deposit_address("BTC", "BTC")
            RT["deposit_address"] = d.get("address", "")
            RT["deposit_sim"] = bool(d.get("simulado"))
        except Exception as e:
            st.error(f"No se pudo obtener la dirección: {e}")
    addr = RT.get("deposit_address")
    if addr:
        if RT.get("deposit_sim"):
            st.code(addr, language="text")
            st.caption("(Dirección SIMULADA de ejemplo)")
        else:
            st.code(addr, language="text")
        col_a, col_b = st.columns(2)
        if col_b.button("➡️ Usar como usuario del pool"):
            RT["payout_override"] = addr
            st.session_state["pool_user_in"] = addr
            st.success("Listo: se usará al iniciar el minero (pestaña lateral).")

    st.subheader("💰 Balance spot")
    try:
        bals = bx.spot_balances()
        if bals:
            import pandas as pd
            st.dataframe(pd.DataFrame(bals), width="stretch",
                         hide_index=True)
        else:
            st.caption("Sin saldos distintos de cero (todavía 😎).")
    except Exception as e:
        st.error(f"Balance no disponible: {e}")

    st.subheader("🧾 Historial de depósitos BTC")
    try:
        deps = bx.deposit_history("BTC", 15)
        if deps:
            import pandas as pd
            rows = [{
                "fecha": time.strftime("%Y-%m-%d %H:%M",
                                       time.localtime(d.get("insertTime", 0) / 1000)),
                "monto": d.get("amount"),
                "estado": format_deposit_status(d.get("status", -1)),
                "tx": str(d.get("txId", ""))[:24] + "…",
            } for d in deps]
            st.dataframe(pd.DataFrame(rows), width="stretch",
                         hide_index=True)
        else:
            st.caption("Aún no hay depósitos BTC en tu cuenta.")
    except Exception as e:
        st.error(f"Historial no disponible: {e}")

    st.info("🔒 **Seguridad**: esta app solo necesita permiso de **lectura**. "
            "Los sats llegan a Binance porque el pool paga a tu dirección de "
            "depósito: no se necesitan retiros por API. Nunca actives el permiso "
            "de retiro para esta key.")


# ===========================================================================
# PESTAÑA 4 · HISTORIAL Y LOGS
# ===========================================================================
with tab_hist:
    st.header("📜 Historial de la sesión")
    totals = STORE.totals()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Shares OK (histórico)", totals.get("shares_ok", 0))
    c2.metric("Shares rechazados", totals.get("shares_rej", 0))
    c3.metric("Hashes calculados", f"{totals.get('hashes_total', 0):,}")
    c4.metric("Bloques encontrados", totals.get("blocks_found", 0))

    df = STORE.history_df(2000)
    st.download_button("⬇️ Descargar métricas CSV",
                       df.to_csv(index=False).encode("utf-8"),
                       file_name=f"btc_miner_metrics_{time.strftime('%Y%m%d')}.csv",
                       mime="text/csv")
    st.plotly_chart(ui.chart_hashrate(df, 260), width="stretch",
                    key="hist_hr")
    st.plotly_chart(ui.chart_difficulty(df, 180), width="stretch",
                    key="hist_df")

    st.subheader("⛏️ Últimos shares")
    ui.render_shares_table(STORE.shares_list(120))

    st.subheader("📋 Log completo de eventos")
    ui.render_event_log(STORE.events_list(200), height=360)
    if st.button("🗑️ Borrar historial"):
        STORE.clear()
        st.rerun()


# ===========================================================================
# PESTAÑA 5 · AYUDA Y SECRETS
# ===========================================================================
with tab_help:
    st.header("⚙️ Variables de secrets (.streamlit/secrets.toml)")
    st.markdown("Copia `.streamlit/secrets.toml.example` a "
                "`.streamlit/secrets.toml` y rellena lo que necesites. "
                "En Streamlit Cloud: **App → Settings → Secrets** y pega el "
                "mismo contenido.")
    import pandas as pd
    st.dataframe(pd.DataFrame(SECRETS_HELP, columns=["Variable", "Descripción"]),
                 width="stretch", hide_index=True)

    st.code("""# Ejemplo mínimo para empezar
BTC_PAYOUT_ADDRESS = "bc1qTU-DIRECCION-DE-BINANCE"
POOL_URL = "stratum+tcp://public-pool.io:21496"
POOL_PASSWORD = "x"
WORKER_NAME = "cpu01"
MINER_MODE = "python"
CPU_THREADS = 2
BINANCE_API_KEY = "..."
BINANCE_API_SECRET = "..."
""", language="toml")

    st.subheader("🚀 Puesta en marcha en 5 pasos")
    st.markdown("""
1. `pip install -r requirements.txt`
2. Copia `secrets.toml.example` → `secrets.toml` y pon tu dirección BTC
   (la de depósito de Binance es perfecta).
3. `streamlit run app.py`
4. Elige el pool **Public Pool** (lowdiff) y pulsa ▶️ INICIAR.
5. Observa shares, hashrate y tu dirección en la pestaña Binance.
""")

    st.subheader("🧠 Realidad del minado con CPU (léeme)")
    st.markdown("""
- La red BTC tiene ~700 EH/s: una CPU con ~0.5 MH/s es una **lotería simbólica**
  (probabilidad de bloque ≈ 1 en billones). Los ASIC son los que minan de verdad.
- Esta app te da el **pipeline completo y real**: stratum → shares → stats →
  Binance. Sube el hash conectando un binario externo (`MINER_MODE="external"`)
  o apuntando a hardware dedicado.
- Alternativa más rentable en CPU/GPU: minar **Monero (RandomX) con XMRig** y
  convertir a BTC — XMRig está soportado en el modo externo.
""")

    st.subheader("🔗 Referencias (infraestructura y repos)")
    st.markdown("""
| Recurso | Enlace |
|---|---|
| Public Pool (solo, lowdiff, open source) | https://web.public-pool.io · github.com/benjamin-wilson/public-pool |
| Solo CKPool | https://solo.ckpool.org |
| 69Pool solo público | https://solo.69pool.org |
| XMRig (minero CPU/GPU) | https://github.com/xmrig/xmrig/releases |
| cpuminer-opt | https://github.com/JayDDee/cpuminer-opt |
| Referencia stratum en Python | https://github.com/ricmoo/nightminer |
| API mempool.space (red real) | https://mempool.space/docs/api/rest |
| API Binance (docs oficiales) | https://developers.binance.com/docs |
| API NiceHash | https://www.nicehash.com/docs |
""")

    st.caption("BTC Miner Studio · hecho con ❤️ y sats · el futuro es tuyo, socio 🚀")
