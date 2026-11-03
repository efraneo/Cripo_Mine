"""
dinero_panel.py — v4.5 · DE TUS SHARES AL DINERO (cadena completa) + META
==========================================================================
Responde EN EL PANEL (con números vivos, no teoría) las 3 dudas del dueño:

  1) "Shares OK = 102, ¿cómo se convierten en dinero?"
     → Cadena visual: shares aceptados → PPLNS del pool → balance pendiente
       → umbral 0.003 XMR (MoneroOcean) → pago automático a tu wallet.
       El balance pendiente se lee VIVO de api.moneroocean.stream.

  2) "El payout me salía 5 años, en v1 eran 77 días"
     → El ETA se calcula SOLO con la ruta activa (XMR → MoneroOcean):
         ETA = (umbral − balance pendiente) / XMR ganado por día
       Nunca mezcla rutas muertas (unMineable) — ese era el bug del "5
       años" corregido en v4.3.2 para probar_ganancias; aquí llega al panel.
       Segunda capa honesta: si el hashrate es bajo, el ETA real es días-
       semanas SOLO tras el tuning (AFINAR.bat).

  3) "Meta 10 dls/día"
     → Barra de progreso: % alcanzado con tu hashrate actual, falta USD/día
       y la palanca concreta (del PLAN_COSTO_BENEFICIO) para subir.

Todo never-explode: si la API o el precio fallan, la sección se dibuja con
lo que haya y avisa. Import-safe (solo render usa streamlit).
"""
import json
import os
import time

import requests

UMBRAL_MO = 0.003          # XMR mínimo para que MoneroOcean pague
MO_API = "https://api.moneroocean.stream/miner/{addr}/stats"
TIMEOUT_API = 12

PALANCAS = [
    # (palanca, efecto típico, costo)
    ("AFINAR.bat (hilos correctos para tu i5)", "+15-60% hashrate", "gratis"),
    ("MSR mod con admin (CORRER_BOT elevado)", "+15-40% en Intel", "gratis"),
    ("Huge pages + 1GB (paginas_1gb.ps1)", "+10-20%", "gratis"),
    ("DESVELO.bat (la laptop nunca duerme)", "+24/7 real", "gratis"),
    ("GPU Iris en otros algoritmos (auto)", "+0.5-3 MH/s GPU", "gratis"),
    ("MULTI: el bot elige la mejor moneda (v4.6)", "rutas BTC directo a Binance", "gratis"),
    ("Mas equipos / mejor CPU", "lineal x equipos", "hardware"),
]


# ---------------------------------------------------------------------------
# Utilidades puras (testeables sin streamlit ni red)
# ---------------------------------------------------------------------------
def _num(v) -> float:
    """MO devuelve false para 'sin dato': todo lo no-numérico es 0."""
    return float(v) if isinstance(v, (int, float)) else 0.0


def wallet_activa(cfg: dict) -> str:
    """La wallet XMR que el motor está usando (secrets o auto-generada)."""
    w = (cfg.get("WALLET_XMR") or "").strip()
    if w:
        return w
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "data", "wallet_emergencia.json")
        with open(p, "r", encoding="utf-8") as f:
            return (json.load(f).get("address") or "").strip()
    except Exception:                          # noqa: BLE001
        return ""


def mo_stats(addr: str) -> dict:
    """Balance pendiente/pagado del minero en MoneroOcean. Nunca explota."""
    if not addr:
        return {}
    try:
        r = requests.get(MO_API.format(addr=addr), timeout=TIMEOUT_API,
                         headers={"User-Agent": "CripoMine/4.5"})
        if r.status_code == 200 and isinstance(r.json(), dict):
            return r.json()
    except Exception:                          # noqa: BLE001
        pass
    return {}


def cadena(addr: str, hashrate: float, red: dict, precio: float,
           stats_mo: dict | None = None) -> dict:
    """Matemática de la ruta activa: shares → PPLNS → umbral → pago.

    eta_dias = (umbral − pendiente) / xmr_dia   [solo ruta XMR viva]
    """
    st = stats_mo if stats_mo is not None else mo_stats(addr)
    pendiente = _num(st.get("amtDue"))
    pagado = _num(st.get("amtPaid"))
    shares_val = _num(st.get("validShares"))
    xmr_dia = 0.0
    try:
        from probar_ganancias import xmr_por_dia
        xmr_dia = max(0.0, xmr_por_dia(hashrate, red or {}))
    except Exception:                          # noqa: BLE001
        xmr_dia = 0.0
    pct_umbral = min(100.0, pendiente / UMBRAL_MO * 100.0) if UMBRAL_MO else 0
    eta_dias = None
    if xmr_dia > 0:
        eta_dias = max(0.0, (UMBRAL_MO - pendiente)) / xmr_dia
    return {
        "addr": addr, "pendiente": pendiente, "pagado": pagado,
        "umbral": UMBRAL_MO, "pct_umbral": pct_umbral,
        "shares_pool": shares_val, "xmr_dia": xmr_dia,
        "usd_dia": xmr_dia * (precio or 0),
        "eta_dias": eta_dias,
        "falta_xmr": max(0.0, UMBRAL_MO - pendiente),
        "api_ok": bool(st),
    }


def eta_legible(cad: dict) -> str:
    """Texto honesto del ETA (sin años absurdos: sin datos, se dice)."""
    eta = cad.get("eta_dias")
    if eta is None:
        return "sin datos de hashrate todavia"
    if eta < 1:
        return "menos de 1 dia"
    if eta < 45:
        return f"~{eta:.0f} dias"
    meses = eta / 30.0
    if meses < 18:
        return f"~{meses:.0f} meses (sube el hashrate: AFINAR.bat)"
    return f"~{eta:.0f} dias (hashrate insuficiente: este ETA solo baja " \
           "con mas hashrate, mira las palancas)"


def meta10(usd_dia: float) -> dict:
    """Progreso honesto hacia la meta de 10 USD/día."""
    usd_dia = max(0.0, usd_dia or 0)
    return {
        "meta": 10.0, "hoy": usd_dia,
        "pct": min(100.0, usd_dia / 10.0 * 100.0),
        "falta": max(0.0, 10.0 - usd_dia),
    }


def formato_xmr(x: float) -> str:
    return f"{x:.6f} XMR"


# ---------------------------------------------------------------------------
# Render (streamlit)
# ---------------------------------------------------------------------------
def render_dinero(RT: dict, CFG: dict):
    """Pestaña 'De shares a dinero': cadena viva + ETA honesto + meta."""
    import streamlit as st
    from state_store import leer_daemon_metrics

    st.header("💰 De tus shares al DINERO (cadena completa)")
    st.caption("v4.5 — la misma matemática de probar_ganancias [4b], ahora "
               "viva en el panel: nada de rutas muertas mezcladas (el viejo "
               "ETA de 5 años).")

    d = leer_daemon_metrics()
    hashrate = (d or {}).get("hashrate") or 0.0
    if not hashrate:
        try:
            hashrate = (RT["store"].last() or {}).get("hashrate") or 0.0
        except Exception:                      # noqa: BLE001
            hashrate = 0.0

    try:
        from probar_ganancias import precio_xmr, red_xmr
        precio = precio_xmr()
        red = red_xmr()
    except Exception:                          # noqa: BLE001
        precio, red = 0.0, {}

    addr = wallet_activa(CFG)
    with st.spinner("Consultando MoneroOcean…"):
        cad = cadena(addr, hashrate, red, precio)

    # ---- Cadena visual -----------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown("### ⛏️ 1\\) Shares\\nEl minero manda trabajo; el pool lo "
                "ACEPTA (tus 'Shares OK').")
    c2.markdown("### 🧮 2\\) PPLNS\\nEl pool acumula tu trabajo en una "
                "ventana y reparte recompensas de cada bloque.")
    c3.markdown("### 🏦 3\\) Umbral\\nEl pool junta tu saldo hasta "
                f"**{formato_xmr(UMBRAL_MO)}**; no paga de a centavos.")
    c4.markdown("### 📬 4\\) Pago\\nAl cruzar el umbral el pool envía XMR "
                "a tu wallet. Automático.")
    st.divider()

    # ---- Números vivos -----------------------------------------------------
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("⛏️ Hashrate medido",
              f"{hashrate:,.0f} H/s" if hashrate else "— (sin datos)")
    m2.metric("💰 Saldo pendiente",
              formato_xmr(cad["pendiente"]) if cad["api_ok"] else "—")
    m3.metric("🧮 XMR ganado/día",
              f"{cad['xmr_dia']:.6f}" if cad["xmr_dia"] > 0 else "—")
    m4.metric("💵 Equiv. USD/día",
              f"${cad['usd_dia']:.4f}" if cad["usd_dia"] > 0 else "—")

    if not cad["api_ok"]:
        st.info("ℹ️ MoneroOcean no devuelve balance para esta wallet "
                "(puede tardar en registrar un minero nuevo o de hashrate "
                "bajo). La cadena de arriba sigue siendo la verdad.")
    elif cad["pendiente"] <= 0:
        st.info("ℹ️ El saldo pendiente aún está en 0: con hashrate bajo el "
                "pool tarda horas en contabilizar la primera porción PPLNS. "
                "No es dinero perdido: es tiempo de hashrate.")
    else:
        st.progress(cad["pct_umbral"] / 100.0,
                    text=f"Umbral de pago: {cad['pct_umbral']:.1f}% de "
                         f"{formato_xmr(UMBRAL_MO)} "
                         f"(falta {formato_xmr(cad['falta_xmr'])})")

    st.success(f"📬 **Próximo pago realista: {eta_legible(cad)}** "
               f"(ruta activa XMR→MoneroOcean, umbral "
               f"{formato_xmr(UMBRAL_MO)})")
    if cad["pagado"] > 0:
        st.caption(f"Pagos ya recibidos por el pool: "
                   f"**{formato_xmr(cad['pagado'])}**")
    if addr:
        st.caption(f"Wallet en uso: `{addr[:12]}…{addr[-8:]}` "
                   "(secrets o auto-generada; respalda "
                   "data/wallet_emergencia.json)")
    else:
        st.warning("No hay wallet XMR: corre el bot una vez para generarla "
                   "o pon tu WALLET_XMR en secrets.toml.")

    # ---- Por qué el viejo "5 años" ------------------------------------------
    with st.expander("🧐 ¿Por qué antes eran 77 días y luego '5 años'?"):
        st.markdown("""
1. **77 días (v1):** minabas a unMineable con pago BTC directo — esa ruta
   estaba VIVA entonces y su umbral era alcanzable con tu hashrate de hoy.
2. **5 años (bug):** al morir unMineable (v4.0), el calculo seguía usando
   el UMBRAL de la ruta muerta dividido entre las GANANCIAS de la ruta
   nueva (XMR). Mezcla inválida → número absurdo. Corregido en v4.3.2.
3. **ETA v4.5 (este panel):** solo la ruta viva, con tu balance pendiente
   REAL del pool y tu hashrate medido. Aún así, si el hashrate es bajo el
   ETA es alto: la única palanca que lo baja de verdad es más hashrate
   (AFINAR.bat → MSR → huge pages; todo gratis, mira abajo).
""")

    # ---- Meta 10 dls/dia ----------------------------------------------------
    try:
        m = meta10(cad["usd_dia"])
    except Exception:                          # noqa: BLE001
        m = meta10(0.0)
    st.subheader("🎯 Meta: 10 dls/día")
    st.progress(m["pct"] / 100.0,
                text=f"{m['pct']:.1f}% de la meta — hoy ${m['hoy']:.4f}/día "
                     f"(falta ${m['falta']:.2f}/día)")
    st.markdown("**Palancas ordenadas por costo/beneficio** "
                "(detalle completo: VER_PLAN.bat):")
    import pandas as pd
    df = pd.DataFrame(PALANCAS, columns=["Palanca", "Efecto típico", "Costo"])
    st.dataframe(df, width="stretch", hide_index=True)
    if m["hoy"] < 0.05:
        st.info("🔬 Con un i5 de laptop el techo honesto del XMR puro está "
                "en centavos/día: AFINAR.bat + MSR + huge pages sacan el "
                "MÁXIMO de esta máquina (y el bot lo aplica solo). Para la "
                "meta de 10 dls/día, el plan asigna el resto fuera de la "
                "minería — el bot queda como colector pasivo.")
    st.caption(f"Actualizado {time.strftime('%Y-%m-%d %H:%M')} · fuentes: "
               "api.moneroocean.stream · Kraken/Blockchair · red Monero")
