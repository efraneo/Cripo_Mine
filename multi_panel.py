"""
multi_panel.py — v4.6 MULTI · EL BOT ELIGE LA MEJOR MONEDA (pestaña)
====================================================================
Muestra en vivo:
  1) La ruta activa y por qué (tabla de rutas con $/día teórico vs medido).
  2) La verdad de Binance: el POOL de Binance cierra 10-nov-2026 (oficial),
     pero el EXCHANGE sigue vivo — el bot usa Binance de 3 formas útiles:
       a) precio BTC en vivo (API pública, validada vs Kraken),
       b) destino del pago: las rutas Verus/GhostRider pagan BTC DIRECTO
          a tu dirección de depósito de Binance (usuario del pool = la
          dirección; sin cuentas, sin claves, sin retiros manuales),
       c) lectura de saldo con tu API key (solo permiso lectura).
     XMR está delistado de Binance desde 2024-02: la ruta XMR cobra en tu
     wallet y se vende en Kraken u otro exchange que sí la liste.
  3) "¿Más de una a la vez?": en UNA CPU solo cabe una cabeza (los
     algoritmos se pelean la L3); la GPU Iris es la única segunda cabeza
     real en paralelo (sonda OpenCL de AFINAR.bat).
  4) Capa MEDIDO: el saldo real de Zpool creciendo entre visitas reemplaza
     a la teoría tras 24h (nada de números mágicos que nadie midió).
Import-safe: solo render usa streamlit.
"""
import os
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DECISION_FILE = os.path.join(BASE_DIR, "data", "decision_moneda.json")
CIERRE_BINANCE_POOL = "2026-11-10 07:00 UTC"


def _fmt_usd(x: float) -> str:
    return f"${x:,.4f}" if x and x > 0 else "—"


def _fmt_h(h: float) -> str:
    if not h or h <= 0:
        return "—"
    if h >= 1_000_000:
        return f"{h/1e6:.1f} MH/s"
    if h >= 1000:
        return f"{h/1e3:.1f} kH/s"
    return f"{h:.0f} H/s"


def forzar_reevaluacion() -> bool:
    """Escribe el flag que el daemon lee cada ciclo (botón del panel)."""
    try:
        import json
        import selector_moneda
        d = selector_moneda.leer_decision()
        if not d:
            return False
        d["reevaluar"] = True
        os.makedirs(os.path.dirname(DECISION_FILE), exist_ok=True)
        with open(DECISION_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1, ensure_ascii=False, default=str)
        return True
    except Exception:                                  # noqa: BLE001
        return False


def render_multi(RT: dict, CFG: dict):
    """Pestaña '🧭 MULTI': rutas, verdad Binance, y capa medido."""
    import pandas as pd
    import streamlit as st
    import selector_moneda

    st.header("🧭 MULTI: el bot elige la mejor moneda para TU máquina")
    st.caption("v4.6 — rutas XMR (MoneroOcean) vs Verus y GhostRider "
               "(Zpool, paga BTC directo a Binance). Histeresis anti-"
               "vaivenes: solo cambia si otra ruta le gana con margen.")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("🔄 Forzar re-evaluación ahora"):
            ok = forzar_reevaluacion()
            (st.success if ok else st.warning)(
                "Flag escrito: el daemon re-decide en su próximo ciclo "
                "(cada 5s). Sin daemon corriendo, corre CORRER_BOT.bat."
                if ok else "Aún no hay decisión guardada: corre el bot.")
    with col_b:
        st.metric("Re-evaluación automática",
                  f"cada {CFG.get('SELECTOR_CADA_HORAS', 6):.0f} h")
    with col_c:
        st.metric("Margen para cambiar de ruta",
                  f"{CFG.get('MARGEN_CAMBIO_PCT', 15):.0f} %")

    # ---- Tabla de rutas ----------------------------------------------------
    with st.spinner("Consultando precios (Kraken/Binance) y Zpool…"):
        try:
            decision = selector_moneda.decidir(CFG)
        except Exception as e:                         # noqa: BLE001
            st.error(f"Selector no disponible: {e}")
            decision = selector_moneda.leer_decision() or {}

    st.subheader(f"🏁 Ruta activa: `{decision.get('ruta', '—')}`")
    if decision.get("motivo_cambio"):
        st.info(f"Último cambio: {decision['motivo_cambio']}")
    if decision.get("alerta_precio"):
        st.warning(f"⚠️ {decision['alerta_precio']}")

    filas, elegida_t = [], decision.get("tabla") or []
    for t in elegida_t:
        filas.append({
            "Ruta": t.get("id"),
            "Moneda": t.get("moneda"),
            "Hash est.": _fmt_h(t.get("hashrate_est", 0)),
            "Teoría $/d": _fmt_usd(t.get("usd_teorico", 0)),
            "Medido $/d": _fmt_usd(t.get("usd_medido", 0)),
            "Estado": "✅ compite" if t.get("viable")
                      else f"❌ {t.get('motivo', '')}",
            "ACTIVA": "🏆" if t.get("id") == decision.get("ruta") else "",
        })
    if filas:
        st.dataframe(pd.DataFrame(filas), width="stretch", hide_index=True)
    st.caption("Teoría = emisión×precio×(tu hash/hash de red conservador). "
               "Medido = saldo REAL del pool creciendo entre visitas; tras "
               "24h minando, el medido manda. Sin BTC_PAYOUT_ADDRESS las "
               "rutas BTC no compiten (ponerla en secrets.toml).")

    # ---- Verdad Binance ------------------------------------------------------
    with st.expander("🏦 Binance: qué SÍ sirve (y qué no) — clic para leer",
                     expanded=False):
        st.markdown(f"""
1. **El POOL de Binance cierra el {CIERRE_BINANCE_POOL}** (anuncio
   oficial: Binance Pool, Pool Savings, Cloud Mining y Transaction
   Accelerator terminan; los stratum dejan de contar shares). O sea: NO
   apuntamos tu CPU ahí, ni vale la pena — el BTC es SHA-256 de ASICs y
   una CPU no compite aunque el pool siguiera abierto.
2. **El EXCHANGE Binance sigue vivo y es tu mejor destino de pagos:**
   las rutas Verus/GhostRider usan Zpool como auto-exchange → el pool
   mina la moneda que tú no ves y te paga **BTC directo a tu dirección
   de depósito de Binance**. Sin cuentas: el "usuario" del stratum ES
   la dirección. Ese es el protocolo que sí funciona.
3. **Precios en vivo:** el bot usa la API pública de Binance para BTC
   (validada hoy contra Kraken) y Kraken para XMR.
4. **XMR está delistado de Binance desde 2024-02** (depósitos XMR
   rechazados): la ruta XMR cobra en tu wallet Monero y se vende en
   Kraken u otro exchange que la liste. El panel de dinero te muestra
   esa ruta con umbral {0.003} XMR.
5. **Lectura de saldo (opcional):** con tu API key de solo-lectura, la
   pestaña Binance muestra el BTC aterrizando. Nunca actives permiso de
   retiro para este bot.
""")

    # ---- Más de una a la vez -------------------------------------------------
    with st.expander("🧩 ¿Se puede minar MÁS DE UNA moneda a la vez?"):
        st.markdown("""
- **En la CPU: no conviene.** RandomX, VerusHash y GhostRider viven de la
  misma caché L3: dos mineros a la vez ≈ mitad de hashrate cada uno (y el
  doble de calor). Por eso el bot tiene UNA cabeza de CPU activa y cambia
  entre rutas SOLO si otra le gana por el margen configurado.
- **La GPU Iris SÍ es una segunda cabeza real:** AFINAR.bat la sondea con
  OpenCL y, si el driver responde, entra en paralelo (v4.5). No compite
  con la CPU: otros recursos, otro algoritmo.
- **La excepción honesta:** MoneroOcean internamente ya es multi-moneda —
  mina el fork RandomX más rentable del momento y te lo paga en XMR.
  Es "más de una moneda" sin costo para ti.
""")

    # ---- Capa MEDIDO -----------------------------------------------------------
    st.subheader("🔬 Capa MEDIDO (la verdad que reemplaza a la teoría)")
    try:
        ap = selector_moneda._leer_json(
            selector_moneda.APRENDIDO_FILE, {}) or {}
        sz = selector_moneda._leer_json(
            selector_moneda.SALDO_ZPOOL_FILE, []) or []
    except Exception:                                  # noqa: BLE001
        ap, sz = {}, []
    m1, m2, m3 = st.columns(3)
    m1.metric("Muestras de saldo Zpool", str(len(sz)),
              "cada 30 min el daemon visita la API wallet")
    if ap:
        for rid, m in ap.items():
            if isinstance(m, dict) and (m.get("btc_dia_medido") or
                                        m.get("xmr_dia_medido")):
                m2.metric(f"BTC/día medido ({rid})",
                          f"{m.get('btc_dia_medido', 0):.8f}")
    else:
        m2.metric("BTC/día medido", "—", "aparece tras 24h minando")
    m3.metric("Saldo Zpool actual",
              f"{sz[-1]['total']:.8f} BTC" if sz else "—")

    st.caption(f"Actualizado {time.strftime('%Y-%m-%d %H:%M')} · fuentes: "
               "Binance pública · Kraken · zpool.ca/api · moneroblocks")
