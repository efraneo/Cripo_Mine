"""
panel_agresivo.py — Pestaña "Motor agresivo" del dashboard Streamlit
====================================================================
Todo el control y observación de la intervención:
  • Arrancar/detener/pausar el DAEMON (corre aunque cierres el navegador)
  • Estado del objetivo actual, historial de failovers y latencias
  • Gráfico de hashrate del daemon (data/metrics_daemon.json)
  • Telegram: prueba de alertas + ayuda para conseguir tu chat_id
  • Pipeline de pagos: unMineable (BTC) · MoneroOcean (XMR) · Binance
"""
import json
import os
import time

import pandas as pd
import streamlit as st

import control
import telegram_bot as tg
from config import (DATA_DIR, format_hashrate, format_btc)
from aggressive_engine import TARGETS, probe_pool
from payout_manager import (fetch_unmineable, fetch_moneroocean,
                            fetch_binance_deposits)
from pool_stats import get_price
import ui_components as ui

ENGINE_STATE_FILE = os.path.join(DATA_DIR, "engine_state.json")
PAYOUT_STATE_FILE = os.path.join(DATA_DIR, "payout_state.json")
DAEMON_METRICS = os.path.join(DATA_DIR, "metrics_daemon.json")


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@st.cache_data(ttl=120, show_spinner=False)
def _latencias_paralelo(urls: tuple) -> dict:
    """Sondea todos los pools EN PARALELO (un pool caído no frena a los
    demás) y cachea el resultado 2 min: sin esto, cada rerun del dashboard
    esperaba hasta 3 s POR POOL en serie y el arranque se congelaba."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(4, len(urls))) as ex:
        resultados = list(ex.map(
            lambda u: (u, probe_pool(u, timeout=2.5)), urls))
    return dict(resultados)


def _daemon_df(n: int = 400) -> pd.DataFrame:
    data = _read_json(DAEMON_METRICS)
    hist = (data.get("history") or [])[-n:]
    if not hist:
        return pd.DataFrame(columns=["ts", "hashrate", "diff", "ok", "rej"])
    df = pd.DataFrame(hist)
    df["dt"] = df["ts"].apply(lambda t: time.strftime("%H:%M:%S",
                                                      time.localtime(t)))
    return df


def _target_badges(cfg):
    """Qué objetivos están listos según los secrets del usuario."""
    has_btc = bool((cfg.get("BTC_PAYOUT_ADDRESS") or "").strip())
    has_xmr = bool((cfg.get("WALLET_XMR") or "").strip())
    rows = []
    for t in TARGETS:
        listo = has_btc if t["id"] == "unmineable" else has_xmr
        rows.append({
            "id": t["id"],
            "objetivo": t["nombre"],
            "pool": t["url"],
            "algo": t["algo"],
            "pago": t["pago"],
            "estado": "LISTO" if listo else "falta dirección en secrets",
        })
    return pd.DataFrame(rows), has_btc, has_xmr


# ===========================================================================
def render(RT: dict, CFG: dict):
    st.header("Intervención agresiva: multi-pool + failover + Telegram")
    store = RT["store"]

    with st.expander("Por qué tu minero anterior no generó NADA (léeme)"):
        st.markdown(
            "Tu modo anterior era SHA-256 de BTC con CPU: la red Bitcoin "
            "corre a cientos de EH/s y tu CPU a ~0.5 MH/s. La probabilidad "
            "de encontrar un bloque es 1 entre billones: **matemáticamente "
            "era una lotería con boleto nulo**. La intervención cambia el "
            "juego:\n\n"
            "1. **unMineable** (RandomX): tu CPU SÍ rinde en RandomX; el "
            "pool convierte tu trabajo a **BTC y lo paga directo a tu "
            "dirección de depósito de Binance**.\n"
            "2. **MoneroOcean**: cambia de algoritmo solo (fork XMRig-MO) "
            "para minar siempre lo más rentable para tu CPU; paga XMR.\n"
            "3. **Failover automático**: si un pool no da shares, salta al "
            "siguiente y te avisa por Telegram.\n"
            "4. **Daemon 24/7**: mina aunque cierres el dashboard; "
            "pausa/reanuda desde Telegram o con control térmico.\n\n"
            "Expectativa honesta en laptop: **USD 0.02–0.15/día** (la CPU "
            "no hace milagros), pero ahora sí es flujo continuo y real que "
            "llega a Binance.")

    # ------------------------------------------------------------------
    st.subheader("1 · Estado del daemon")
    alive = control.daemon_alive()
    pid = control.daemon_pid()
    ctrl = control.read()
    eng_state = _read_json(ENGINE_STATE_FILE)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Daemon", "ACTIVO" if alive else "DETENIDO",
              f"PID {pid}" if alive else "sin proceso")
    target_id = eng_state.get("target") or "—"
    tnombre = next((t["nombre"] for t in TARGETS if t["id"] == target_id),
                   target_id)
    c2.metric("Objetivo actual", tnombre if alive else "—")
    c3.metric("Pausado", "sí" if (ctrl.get("paused_manual") or
                                  ctrl.get("paused_thermal")) else "no",
              ("térmica" if ctrl.get("paused_thermal") else
               "manual" if ctrl.get("paused_manual") else ""))
    last = _read_json(DAEMON_METRICS)
    hr = 0.0
    if last.get("history"):
        hr = (last["history"][-1] or {}).get("hashrate", 0) or 0
    c4.metric("Hashrate daemon", format_hashrate(hr))

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("INICIAR DAEMON", type="primary", width="stretch",
                 disabled=alive):
        try:
            control.start_daemon()
            st.success("Daemon lanzado: mira logs/daemon.log y los eventos "
                       "aquí en unos segundos.")
            time.sleep(1.5)
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo iniciar: {e}")
    if b2.button("DETENER DAEMON", width="stretch", disabled=not alive):
        ok = control.stop_daemon()
        (st.success if ok else st.warning)(
            "Daemon detenido." if ok else "Se pidió parada; revisa el PID.")
        st.rerun()
    paused_now = bool(ctrl.get("paused_manual"))
    if b3.button("PAUSAR (libera CPU)" if not paused_now else
                 "REANUDAR MINADO", width="stretch", disabled=not alive):
        control.write(paused_manual=not paused_now,
                      updated_by="app")
        st.rerun()
    if b4.button("FORZAR FAILOVER", width="stretch", disabled=not alive):
        control.write(force_target="next", updated_by="app")
        st.info("Failover solicitado: el motor cambia de pool en ≤20 s.")

    hilos_max = (os.cpu_count() or 4)
    t_default = int(ctrl.get("threads") or CFG.get("CPU_THREADS", 2))
    t_sel = st.slider("Hilos CPU para el daemon (se aplica al (re)iniciar)",
                      1, hilos_max, min(t_default, hilos_max),
                      key="agro_threads",
                      help="Más hilos = más hashrate = más calor. El "
                           "watchdog pausa si superas CPU_TEMP_MAX.")
    c_a, c_b = st.columns([1, 2])
    if c_a.button("Guardar hilos", width="stretch"):
        control.write(threads=int(t_sel), updated_by="app")
        st.success(f"Hilos={t_sel} guardados.")
    if c_b.button("Aplicar ahora (reinicia daemon)", width="stretch",
                  disabled=not alive):
        control.write(threads=int(t_sel), updated_by="app")
        control.stop_daemon()
        time.sleep(1)
        control.start_daemon()
        st.success(f"Daemon reiniciado con {t_sel} hilos.")
        st.rerun()

    # ------------------------------------------------------------------
    st.subheader("2 · Failover y gráfico en vivo")
    df = _daemon_df()
    if not df.empty:
        st.plotly_chart(ui.chart_hashrate(df), width="stretch",
                        key="agro_hr")
    else:
        st.caption("Sin métricas del daemon todavía: arrancalo arriba (el "
                   "primer arranque descarga XMRig ~3 MB).")

    sw = eng_state.get("switch_log") or []
    if sw:
        rows = [{"hora": time.strftime("%m-%d %H:%M",
                                       time.localtime(s["ts"])),
                 "de": s.get("from", ""), "a": s.get("to", ""),
                 "motivo": s.get("reason", "")} for s in reversed(sw)]
        st.markdown("**Historial de failovers**")
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    st.markdown("**Objetivos del motor agresivo** (estado según tus secrets)")
    df_t, has_btc, has_xmr = _target_badges(CFG)
    lat_por_url = _latencias_paralelo(tuple(t["url"] for t in TARGETS))
    url_de = {t["id"]: t["url"] for t in TARGETS}
    df_t["latencia"] = df_t["id"].map(
        lambda i: (f"{lat_por_url[url_de[i]]:.0f} ms"
                   if lat_por_url.get(url_de[i]) else "sin respuesta"))
    st.dataframe(df_t, width="stretch", hide_index=True)
    if not (has_btc or has_xmr):
        st.warning("Configura BTC_PAYOUT_ADDRESS y/o WALLET_XMR en "
                   ".streamlit/secrets.toml para que haya objetivos "
                   "disponibles.")

    # ------------------------------------------------------------------
    st.subheader("3 · Telegram: alertas y control remoto")
    if tg.configured(CFG):
        st.success("Telegram configurado: recibirás failovers, depósitos y "
                   "resumen diario. Comandos: /estado /pausar /reanudar "
                   "/cambiar /ganancias")
        if st.button("Enviar mensaje de PRUEBA"):
            ok = tg.send(CFG, "<b>Prueba</b> desde BTC Miner Studio: las "
                              "alertas del minero llegarán aquí.", "ok")
            (st.success if ok else st.error)(
                "Enviado" if ok else "Falló el envío: revisa token/chat_id")
    else:
        st.info("Sin Telegram. Configura TELEGRAM_BOT_TOKEN y "
                "TELEGRAM_CHAT_ID para que el minero te avise al instante "
                "(failovers, depósitos en Binance, resumen diario) y para "
                "controlarlo por chat: /pausar /reanudar /estado.")
        if st.button("¿Cuál es mi chat_id? (escribe /start a tu bot antes)"):
            try:
                found = tg.print_chat_ids(CFG)
                if found:
                    st.code(json.dumps(found, ensure_ascii=False))
                    st.caption("Pon tu chat_id en TELEGRAM_CHAT_ID.")
                else:
                    st.warning("No hay mensajes: abre tu bot y envíale "
                               "cualquier texto, luego reintenta.")
            except Exception as e:
                st.error(f"{e} — revisa TELEGRAM_BOT_TOKEN")

    # ------------------------------------------------------------------
    st.subheader("4 · Pipeline de pagos → Binance")
    st.caption("Ruta: tu CPU mina RandomX → unMineable convierte a BTC → "
               "paga a tu dirección de depósito de Binance → este vigilante "
               "te avisa por Telegram en el momento.")
    if st.button("Consultar balances y depósitos ahora"):
        with st.spinner("Consultando pools y Binance…"):
            price, psrc = get_price("binance")
            um = fetch_unmineable((CFG.get("BTC_PAYOUT_ADDRESS") or "").strip())
            mo = fetch_moneroocean((CFG.get("WALLET_XMR") or "").strip())
            deps = fetch_binance_deposits(RT["binance"], 10)
        k1, k2, k3 = st.columns(3)
        k1.metric("unMineable (sin pagar)",
                  format_btc(um["balance"]) if um else "—",
                  (f"pagable {um['balance_payable']:.8f} BTC · umbral pool "
                   f"{um['payment_threshold']:.5f}") if um else
                  "requiere BTC_PAYOUT_ADDRESS")
        k2.metric("MoneroOcean (pendiente)",
                  f"{mo['due_xmr']:.4f} XMR" if mo else "—",
                  f"pagado {mo['paid_xmr']:.4f} XMR" if mo else
                  "requiere WALLET_XMR")
        k3.metric("Precio BTC", f"USD {price:,.2f}" if price else "—",
                  psrc)
        if deps:
            rows = [{"fecha": time.strftime("%Y-%m-%d %H:%M",
                                            time.localtime(
                                                d.get("insertTime", 0) / 1000)),
                     "BTC": d.get("amount"),
                     "estado": {0: "pendiente", 1: "acreditado"}.get(
                         d.get("status"), d.get("status")),
                     "tx": str(d.get("txId", ""))[:20] + "…"} for d in deps]
            st.dataframe(pd.DataFrame(rows), width="stretch",
                         hide_index=True)
        else:
            st.caption("Aún no hay depósitos BTC en tu Binance: el primer "
                       "pago llega cuando el balance pagable cruce el umbral "
                       "del pool (~0.00075 BTC por defecto; ajústalo en "
                       "unmineable.com → Addresses para cobrar antes).")
    pay_state = _read_json(PAYOUT_STATE_FILE)
    if pay_state:
        st.caption(f"Vigilante de pagos: {len(pay_state.get('known_txids', []))}"
                   f" depósitos rastreados · total visto "
                   f"{pay_state.get('deposit_total_btc', 0):.8f} BTC "
                   f"(desde que corre el daemon).")

    # ------------------------------------------------------------------
    with st.expander("Nuevas variables de secrets que usa esta pestaña"):
        st.code(
            'TELEGRAM_BOT_TOKEN = "123456:ABC..."   # @BotFather\n'
            'TELEGRAM_CHAT_ID = "123456789"          # botón de arriba\n'
            'WALLET_XMR = "48..."                    # wallet Monero (MO/SupportXMR)\n'
            '# BTC_PAYOUT_ADDRESS ya la tienes (dirección de depósito Binance)\n'
            'AGGRESSIVE_MODE = true\n'
            'FAILOVER_MINUTES = 12                   # salta de pool si no hay shares\n'
            'ROTATE_MINUTES = 0                      # 0 = desactivado\n'
            'CPU_TEMP_MAX = 85.0                     # pausa térmica\n'
            'DAILY_SUMMARY_HOUR = 20                 # resumen diario por Telegram\n'
            'PAYOUT_ALERT_MIN_BTC = 0.0005           # aviso de payout en camino',
            language="toml")
