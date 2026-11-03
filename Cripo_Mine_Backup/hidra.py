"""
hidra.py — HIDRA 2.0 · matemática real, salud de pools y plan honesto
=====================================================================
La Hidra ya no es solo "más máquinas": es un tablero de VERDAD.

  1) SALUD EN VIVO de los pools (handshake stratum real, no solo TCP):
     aquí se ve por qué no recolectabas (unMineable zombi, 2026-10-24).
  2) MATEMÁTICA REAL de TU CPU: hashrate × red XMR × precio − electricidad
     = NETO/día. Con tu i5-1235U (~730 H/s) el resultado es honesto y duro.
  3) TABLA DE HARDWARE: qué máquina sí alcanza $5-10/día (datos minerstat/
     CoinWarz oct-2026) y cuánto cuesta llegar ahí.
  4) LAS 3 RUTAS honestas a $5-10/día (hardware / capital / habilidades).

Fuentes de datos vivos: Kraken (precio XMR), MoneroOcean (hashrate de red).
Todo cacheado (5-10 min) para no golpear las APIs en cada rerun.
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import streamlit as st
import requests

from config import DATA_DIR, format_hashrate
from pools_catalog import TARGETS
from pools_salud import probe_salud   # handshake stratum real (v4.0: antes
# este archivo importaba 'stratum_ok' desde aggressive_engine, donde no
# existe → ImportError → la pestaña HIDRA nunca aparecía: 'la hidra rota')

DAEMON_METRICS = os.path.join(DATA_DIR, "metrics_daemon.json")

# Constantes de red Monero (RandomX, oct-2026; se refrescan vivas abajo)
BLOCK_REWARD_XMR = 0.6          # XMR por bloque (tail emission)
BLOCK_TIME_S = 115.0            # segundos por bloque
NET_HS_FALLBACK = 6.64e9        # hashrate de red si la API falla
KWH_DEFAULT = 0.19              # USD/kWh residencial Colombia aprox

UA = {"User-Agent": "btc-miner-studio-hidra/2.0"}


def _daemon_hashrate() -> float:
    """Último hashrate medido del daemon (0 si aún no hay métricas)."""
    try:
        with open(DAEMON_METRICS, "r", encoding="utf-8") as f:
            d = json.load(f)
        hist = d.get("history") or []
        if hist:
            return float((hist[-1] or {}).get("hashrate", 0) or 0)
    except Exception:
        pass
    return 0.0


@st.cache_data(ttl=600, show_spinner=False)
def xmr_price() -> float:
    """Precio XMR/USD vivo (Kraken; Binance delistó XMR en 2024)."""
    try:
        r = requests.get("https://api.kraken.com/0/public/Ticker?pair=XMRUSD",
                         headers=UA, timeout=6)
        d = r.json()
        return float(d["result"]["XXMRZUSD"]["c"][0])
    except Exception:
        return 600.0


@st.cache_data(ttl=600, show_spinner=False)
def xmr_network_hashrate() -> float:
    """Hashrate de la red Monero vía API pública de MoneroOcean."""
    try:
        r = requests.get("https://api.moneroocean.stream/pool/stats",
                         headers=UA, timeout=6)
        d = r.json()
        for path in ((d, "network", "hashrate"),
                     (d, "networkHashrate",),
                     (d.get("pool_statistics") or {}, "hashRate",)):
            try:
                v = float(path[0].get(path[1], 0) or 0)
                if v > 0:
                    return v
            except Exception:
                continue
    except Exception:
        pass
    return NET_HS_FALLBACK


@st.cache_data(ttl=300, show_spinner=False)
def salud_pools() -> pd.DataFrame:
    """Chequeo stratum REAL (handshake) de todos los pools, en paralelo.
    v4.0: usa probe_salud (pool_salud) — ms de respuesta real al
    mining.subscribe; None = zombi/muerto (y queda en cooldown 5 min)."""
    def chk(t):
        ms = probe_salud(t["url"], force=True)
        vivo = ms is not None
        return {
            "pool": t["id"],
            "url": t["url"],
            "pago": t["pago"],
            "estado": "🟢 VIVO" if vivo else "🔴 ZOMBI (TCP sí, stratum no)",
            "respuesta": f"{ms:.0f} ms" if vivo else "sin handshake",
        }
    with ThreadPoolExecutor(max_workers=len(TARGETS)) as ex:
        rows = list(ex.map(chk, TARGETS))
    return pd.DataFrame(rows)


def ingresos_xmr(hs: float, net_hs: float, price: float):
    """(XMR/día, USD/día brutos) para un hashrate dado."""
    if hs <= 0 or net_hs <= 0:
        return 0.0, 0.0
    xmr_dia = (hs / net_hs) * (86400.0 / BLOCK_TIME_S) * BLOCK_REWARD_XMR
    return xmr_dia, xmr_dia * price


def hs_necesario_para(usd_objetivo: float, net_hs: float, price: float):
    """Hashrate (H/s) bruto necesario para USD objetivo/día (sin luz)."""
    if price <= 0 or net_hs <= 0:
        return 0.0
    usd_por_hs = (1.0 / net_hs) * (86400.0 / BLOCK_TIME_S) * \
        BLOCK_REWARD_XMR * price
    return usd_objetivo / usd_por_hs if usd_por_hs > 0 else 0.0


# ===========================================================================
def render(RT: dict, CFG: dict):
    st.header("🐉 HIDRA 2.0 — la verdad completa")
    price = xmr_price()
    net_hs = xmr_network_hashrate()

    # ------------------------------------------------------------------
    st.subheader("0 · Veredicto: por qué no recolectabas NADA")
    df_salud = salud_pools()
    zombis = df_salud[~df_salud["estado"].str.contains("VIVO")]
    if len(zombis):
        urls_z = ", ".join(zombis["url"].tolist())
        st.error(f"**Pools zombi detectados ahora mismo: {urls_z}.** Aceptan "
                 f"conexión TCP pero NO responden al protocolo stratum: tu "
                 f"minero se quedaba horas ahí esperando instrucciones que "
                 f"nunca llegan. El motor ya los salta solo (cooldown 5 min).")
    vivos = df_salud[df_salud["estado"].str.contains("VIVO")]
    if len(vivos):
        st.success(f"**Pools vivos**: {', '.join(vivos['pool'].tolist())} → "
                   f"la rotación ahora arranca por el vivo más rentable "
                   f"(MoneroOcean, auto-algoritmo).")
    st.dataframe(df_salud, width="stretch", hide_index=True)

    # ------------------------------------------------------------------
    st.subheader("1 · Matemática real de TU CPU (RandomX)")
    st.caption(f"Precio XMR: **USD {price:,.2f}** (Kraken) · red Monero: "
               f"**{format_hashrate(net_hs)}** · recompensa "
               f"{BLOCK_REWARD_XMR} XMR/bloque cada {BLOCK_TIME_S:.0f} s")

    c1, c2, c3 = st.columns(3)
    hs_medido = _daemon_hashrate()
    hs_def = hs_medido if hs_medido > 0 else 730.0
    hs = c1.number_input("Tu hashrate (H/s)", min_value=0.0, value=hs_def,
                         step=50.0,
                         help="Se autorrellena con el último hashrate "
                              "medido del daemon en esta máquina.")
    watts = c2.number_input("Consumo extra del minado (W)", min_value=0.0,
                            value=30.0, step=5.0,
                            help="Una laptop 6 hilos RandomX: ~25-35 W "
                                 "encima del consumo normal.")
    kwh = c3.number_input("Precio electricidad (USD/kWh)", min_value=0.0,
                          value=float(CFG.get("USD_KWH", KWH_DEFAULT)),
                          step=0.01,
                          help="Colombia residencial ≈ 0.15-0.22. Pon el "
                               "de tu factura.")

    xmr_dia, usd_dia = ingresos_xmr(hs, net_hs, price)
    luz_dia = watts * 24.0 * kwh / 1000.0
    neto_dia = usd_dia - luz_dia

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Ingreso bruto", f"USD {usd_dia:.4f}/día",
              f"{xmr_dia:.8f} XMR/día")
    k2.metric("Costo electricidad", f"USD {luz_dia:.2f}/día",
              f"{watts:.0f} W × 24 h")
    k3.metric("NETO real", f"USD {neto_dia:.4f}/día",
              "🩸 PÉRDIDA" if neto_dia < 0 else "✔ positivo")
    k4.metric("Días para 1 pago (1.5 USDT)",
              f"{1.5 / usd_dia:.0f} días" if usd_dia > 0.001 else "≈ años",
              f"= USD {usd_dia * 30:.2f}/mes" if usd_dia > 0 else "")

    if neto_dia < 0:
        st.warning("**Conclusión matemática: en esta máquina MINAR PIERDE "
                   "DINERO.** El ingreso bruto no cubre la electricidad "
                   "marginal. La Hidra multiplica centavos, no dólares: "
                   "10 laptops = ~USD 0.30/día brutos. Minar aquí solo "
                   "tiene sentido educativo o si la energía ya está pagada "
                   "y no la usarás para nada más.")
    elif neto_dia < 1.0:
        st.info("Margen positivo pero pequeño: cada cabeza suma centavos. "
                "Para $5-10/día mira la tabla y las rutas de abajo.")

    st.divider()
    st.subheader("2 · Qué haría falta para USD 5 y 10 al día (brutos)")
    hs5 = hs_necesario_para(5.0, net_hs, price)
    hs10 = hs_necesario_para(10.0, net_hs, price)
    a, b = st.columns(2)
    a.metric("Hashrate para $5/día", format_hashrate(hs5),
             f"≈ {hs / hs5:,.0f}× tu CPU" if hs > 0 and hs5 > 0 else "")
    b.metric("Hashrate para $10/día", format_hashrate(hs10),
             f"≈ {hs / hs10:,.0f}× tu CPU" if hs > 0 and hs10 > 0 else "")
    st.caption("Y ojo: eso es BRUTO. Con luz a ~$0.19/kWh el neto es "
               "mucho menor (ver tabla).")

    st.markdown("**Hardware real 2026 (minerstat/CoinWarz) y su veredicto**")
    df_hw = pd.DataFrame([
        {"Equipo": "Tu laptop (i5-1235U, 6 hilos)", "H/s": "730",
         "W": 28, "Capex": "0 (ya la tienes)",
         "Bruto/día": f"${usd_dia:.3f}", "Luz/día": f"${luz_dia:.2f}",
         "Neto/día": f"${neto_dia:.3f}",
         "Veredicto": "pierde dinero con luz a $0.19/kWh"},
        {"Equipo": "Ryzen 9 7950X (16c)", "H/s": "22,000", "W": 230,
         "Capex": "~$550", "Bruto/día": "~$0.97", "Luz/día": "~$1.05",
         "Neto/día": "≈ $0", "Veredicto": "empate; no llega a $5"},
        {"Equipo": "Threadripper 3990X (usado)", "H/s": "43,000", "W": 280,
         "Capex": "~$2,500", "Bruto/día": "~$1.90", "Luz/día": "~$1.28",
         "Neto/día": "~$0.60", "Veredicto": "ROI 11+ años: no"},
        {"Equipo": "EPYC 9654 (1×)", "H/s": "88,000", "W": 360,
         "Capex": "~$5,500", "Bruto/día": "~$3.90", "Luz/día": "~$1.64",
         "Neto/día": "~$2.30", "Veredicto": "ROI ~6 años: no"},
        {"Equipo": "Antminer X5 (ASIC RandomX)", "H/s": "212,000", "W": 1350,
         "Capex": "~$2,000-4,000", "Bruto/día": "~$9.40",
         "Luz/día": "~$6.16", "Neto/día": "~$3.20",
         "Veredicto": "para $5-10 neto necesitas 2-3: $6-12k, ruido y calor"},
        {"Equipo": "ASIC BTC S21 (200 TH/s)", "H/s": "200 TH (SHA-256)",
         "W": 3500, "Capex": "~$4,000-6,000", "Bruto/día": "~$9.70",
         "Luz/día": "~$15.96", "Neto/día": "-$6.30",
         "Veredicto": "solo viable con luz < $0.08/kWh"},
    ])
    st.dataframe(df_hw, width="stretch", hide_index=True)
    st.caption("Los ASIC RandomX compiten entre sí: cada X5 vendido sube la "
               "dificultad y baja el ingreso de todos. Cifras oct-2026 con "
               "XMR ~$600 y BTC ~$81k.")

    st.divider()
    st.subheader("3 · Las 3 rutas honestas a $5-10/día")
    st.markdown(
        "🧱 **Ruta A — Hardware de minado (capex alto, ROI malo hoy).**\n\n"
        "Necesitas 2-3 Antminer X5 o un rack EPYC: **$6,000-12,000** "
        "inicial, 1.3-4 kW continuos, ruido de servidor y un ROI de "
        "**2-6 años** asumiendo que XMR no caiga y la dificultad no suba "
        "más rápido. Con luz residencial colombiana (~$0.19/kWh) los ASIC "
        "BTC pierden dinero directo. Solo tiene sentido si tienes luz muy "
        "barata o hardware conseguido casi gratis.\n\n"
        "🏦 **Ruta B — Capital rendido (necesita capital).**\n\n"
        "$5/día = $150/mes. A un 10% anual realista (staking/DeFi de "
        "riesgo medio) necesitas **~$18,000** depositados; a 20% (riesgo "
        "alto, riesgo de perdida total) ~$9,000. La minería CPU nunca "
        "compite con esto: es matemática, no esfuerzo.\n\n"
        "🚀 **Ruta C — Habilidades + bots (la tuya: capex ~0).**\n\n"
        "Tu costo de desarrollo con IA es casi cero y YA tienes un stack "
        "real (daemon multi-pool, Telegram, Binance API, dashboard). Ese "
        "paquete — monitoreo de infraestructura con alertas, bots de "
        "automatización, dashboards de datos — se vende: **1-2 encargos "
        "pequeños al mes = $5-10/día**. Es la única ruta que escala sin "
        "capital y sin quemar electricidad.")

    st.divider()
    st.subheader("4 · Checklist Hidra (multi-cabeza) — expectativa honesta")
    has_btc = bool((CFG.get("BTC_PAYOUT_ADDRESS") or "").strip())
    has_usdt = bool((CFG.get("USDT_PAYOUT_ADDRESS") or "").strip())
    has_xmr = bool((CFG.get("WALLET_XMR") or "").strip())
    cobro_txt = "✔ configurada" if (has_btc or has_usdt) else "❌ falta"
    xmr_txt = "✔ configurada" if has_xmr else "❌ falta"
    st.markdown(
        f"- Dirección de cobro: {cobro_txt} (BTC/USDT) · Wallet XMR: "
        f"{xmr_txt}\n"
        f"- Con `WALLET_XMR` el motor ya puede rotar a los 2 pools VIVOS "
        f"(MoneroOcean/SupportXMR): **crea una wallet Monero (p.ej. "
        f"monero.com o Exodus), pégala en secrets y reinicia el daemon**. "
        f"Sin ella, si un pool cae te quedas sin nada que hacer.\n"
        f"- Cada cabeza extra (otra laptop/PC) suma ~730 H/s ≈ "
        f"**+$0.03/día brutos**. 10 cabezas = $0.30/día. La Hidra sirve "
        f"para agrupar pagos y aprender, no para llegar a $5/día.\n"
        f"- Cuando unMineable vuelva a responder stratum, el motor lo "
        f"reintenta solo cada 5 min y reintegra el cobro directo BTC→"
        f"Binance. Mientras tanto, los XMR de MoneroOcean (umbral "
        f"0.001 XMR) se acumulan en tu wallet.")
    st.caption("Hidra 2.0 · datos vivos Kraken/MoneroOcean · sin promesas, "
               "solo matemática.")
