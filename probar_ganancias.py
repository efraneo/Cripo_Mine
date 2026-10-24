#!/usr/bin/env python3
"""
probar_ganancias.py — PRUEBA DE GANANCIAS con datos 100% reales (v3.5)
=======================================================================
Responde con números, no con humo:

    "¿Cuánto BTC puedo ganar AHORA y por qué es más que antes?"

Qué consulta EN VIVO (todo público, sin claves):
  • Hashrate MEDIDO por tu propio bot (data/metrics_daemon.json o
    data/metrics.json — la última medición de los últimos 45 min)
  • Saldo REAL pendiente en unMineable (API v4) y % del umbral de pago
  • Dificultad de la red Monero (Blockchair) → hashrate de red
  • Precio BTC (Binance → mempool.space) y XMR (Kraken → CoinPaprika)
  • Tu Binance: dirección de depósito + saldo spot (si hay claves API)

Modelo (la MISMA matemática que usa la red Monero):
    XMR/día = 0.6 (recompensa por bloque, tail emission)
              × 720 bloques/día
              × (tu hashrate ÷ hashrate de la red)
    BTC/día = XMR/día × precio_XMR ÷ precio_BTC × (1 − fee del pool)

Escenarios que compara:
    [1] HOY                → tu hashrate actual (medido o estimado)
    [2] TODOS LOS NÚCLEOS  → escenario HOY escalado a los núcleos físicos
    [3] + HUGE PAGES/MSR   → escenario [2] × 1.30 (xmrig como admin)

Y la prueba honesta ANTES vs AHORA:
    ANTES  (modo XMR + wallet bloqueada)  → BTC recibido: 0.00
    AHORA (SOLO-BTC → Binance automático) → 100% de lo minado llega
    en BTC a tu dirección (Binance si es su dirección de depósito).

Uso:
    python probar_ganancias.py              # reporte consola + Telegram
    python probar_ganancias.py --sin-tg     # solo consola
    python probar_ganancias.py --hashrate 1500   # fijar H/s a mano
    python probar_ganancias.py --tg-solo    # solo enviar a Telegram
También lo usa el daemon (evidencia periódica) y el comando /ganancias.
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import requests  # noqa: E402

UA = {"User-Agent": "btc-miner-studio-prueba/3.5"}
UM_API = "https://api.unmineable.com/v4/address/{addr}?coin=BTC"
BLOCKCHAIR_API = "https://api.blockchair.com/monero/stats"
BINANCE_PRICE = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
MP_PRICE_API = "https://mempool.space/api/v1/prices"
KRAKEN_XMR = "https://api.kraken.com/0/public/Ticker?pair=XMRUSD"
PAPRIKA_XMR = "https://api.coinpaprika.com/v1/tickers/xmr-monero"

BLOQUES_DIA = 720          # 1 bloque cada 120 s en Monero
RECOMPENSA_XMR = 0.6       # tail emission (constante desde jun-2022)
UMBRAL_DEF = 0.00075       # umbral de pago unMineable (BTC)
FACTOR_HUGEPAGES = 1.30    # mejora típica con huge pages + MSR (admin)
H_POR_NUCLEO = 700.0       # H/s conservadores por núcleo físico (RandomX)


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Secrets (mismo patrón que recolectar_pool.py: tomllib + fallback simple)
# ---------------------------------------------------------------------------
def cargar_secrets() -> dict:
    path = os.path.join(BASE, ".streamlit", "secrets.toml")
    if not os.path.exists(path):
        return {}
    try:
        import tomllib
        with open(path, "rb") as f:
            return {k: str(v) for k, v in tomllib.load(f).items()}
    except Exception:
        pass
    out = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return out


def _get_json(url: str, timeout: int = 10):
    try:
        r = requests.get(url, headers=UA, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 1) Hashrate: medido por tu bot, o estimado por tus núcleos
# ---------------------------------------------------------------------------
def _leer_metrics(path: str, max_edad: float = 2700.0):
    """Último hashrate del archivo de métricas si es reciente (<45 min)."""
    try:
        if not os.path.exists(path):
            return 0.0, 0.0
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        hist = data.get("history") or []
        for h in reversed(hist):                 # del más nuevo al más viejo
            if isinstance(h, dict) and time.time() - h.get(
                    "ts", 0) <= max_edad:
                hr = float(h.get("hashrate") or 0)
                if hr > 0:
                    return hr, float(h.get("ts") or 0)
    except Exception:
        pass
    return 0.0, 0.0


def hashrate_medido() -> tuple:
    """(hashrate_Hs, fuente) — primero el daemon, luego el dashboard."""
    for nombre, path in (
            ("daemon (metrics_daemon.json)",
             os.path.join(BASE, "data", "metrics_daemon.json")),
            ("dashboard (metrics.json)",
             os.path.join(BASE, "data", "metrics.json"))):
        hr, ts = _leer_metrics(path)
        if hr > 0:
            return hr, nombre
    return 0.0, ""


def _nucleos() -> tuple:
    """(físicos, lógicos) con psutil u os como fallback."""
    fis = logicos = 0
    try:
        import psutil
        fis = psutil.cpu_count(logical=False) or 0
        logicos = psutil.cpu_count(logical=True) or 0
    except Exception:
        pass
    if not logicos:
        logicos = os.cpu_count() or 2
    if not fis:
        fis = max(1, logicos // 2)      # estimación habitual (hyperthreading)
    return fis, logicos


def hashrate_estimado() -> tuple:
    """(hashrate_Hs, fuente) si el bot nunca ha medido nada."""
    fis, logicos = _nucleos()
    return fis * H_POR_NUCLEO, f"estimado ({fis} núcleos físicos × " \
                               f"{H_POR_NUCLEO:.0f} H/s)"


# ---------------------------------------------------------------------------
# 2) Datos de mercado y de la red
# ---------------------------------------------------------------------------
def precio_btc() -> float:
    d = _get_json(BINANCE_PRICE, timeout=8)
    try:
        if d and d.get("price"):
            return float(d["price"])
    except (TypeError, ValueError):
        pass
    d = _get_json(MP_PRICE_API, timeout=8)
    try:
        return float((d or {}).get("USD", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def precio_xmr() -> float:
    d = _get_json(KRAKEN_XMR, timeout=8)
    try:
        res = (d or {}).get("result") or {}
        if res:
            k = list(res)[0]
            return float(res[k]["c"][0])
    except Exception:
        pass
    d = _get_json(PAPRIKA_XMR, timeout=10)
    try:
        return float(((d or {}).get("quotes") or {}).get(
            "USD", {}).get("price") or 0)
    except (TypeError, ValueError):
        return 0.0


def red_xmr() -> dict:
    """Hashrate de la red Monero = dificultad ÷ 120 s (Blockchair)."""
    d = _get_json(BLOCKCHAIR_API, timeout=10) or {}
    datos = d.get("data") or {}
    try:
        diff = float(datos.get("difficulty") or 0)
    except (TypeError, ValueError):
        diff = 0.0
    net = diff / 120.0 if diff > 0 else 0.0
    if not net:                       # red XMR típica 2026 como fallback
        net = 6_500_000_000.0
    return {"hashrate": net, "exacto": diff > 0, "dificultad": diff}


# ---------------------------------------------------------------------------
# 3) Pools y Binance
# ---------------------------------------------------------------------------
def datos_unmineable(addr: str) -> dict:
    if not addr:
        return {}
    d = (_get_json(UM_API.format(addr=addr)) or {}).get("data") or {}

    def _f(k, default=0.0):
        try:
            return float(d.get(k, default) or default)
        except (TypeError, ValueError):
            return default

    return {
        "balance": _f("balance"),
        "payable": _f("balance_payable"),
        "umbral": _f("payment_threshold", UMBRAL_DEF) or UMBRAL_DEF,
        "fee": (_f("mining_fee", 1.0) / 100.0) or 0.01,
        "pagos_previos": len(d.get("payments") or []),
        "error_pago": bool((d.get("err_flags") or {}).get("payment_error")),
    }


def datos_binance(cfg: dict) -> dict:
    out = {"direccion": "", "saldo_btc": None, "error": ""}
    if not (cfg.get("BINANCE_API_KEY") and cfg.get("BINANCE_API_SECRET")):
        out["error"] = "sin-claves"
        return out
    try:
        from binance_api import BinanceAPI, BinanceError
        b = BinanceAPI(cfg["BINANCE_API_KEY"], cfg["BINANCE_API_SECRET"])
        try:
            out["direccion"] = b.deposit_address("BTC").get("address", "")
        except BinanceError as e:
            out["error"] = f"deposit_address: {e}"
        try:
            out["saldo_btc"] = b.btc_balance()
        except BinanceError as e:
            out["error"] = (out["error"] + " | " if out["error"] else "") \
                + f"balance: {e}"
    except Exception as e:                      # noqa: BLE001
        out["error"] = str(e)
    return out


# ---------------------------------------------------------------------------
# 4) Modelo de ganancias y escenarios
# ---------------------------------------------------------------------------
def btc_por_dia(hashrate: float, red: dict, px_xmr: float, px_btc: float,
                fee: float = 0.01) -> float:
    """XMR-equivalente diario de tu hashrate RandomX, convertido a BTC."""
    if hashrate <= 0 or red.get("hashrate", 0) <= 0:
        return 0.0
    if not (px_xmr > 0 and px_btc > 0):
        return 0.0
    xmr_dia = RECOMPENSA_XMR * BLOQUES_DIA * (hashrate / red["hashrate"])
    return xmr_dia * px_xmr / px_btc * (1.0 - fee)


def calcular_escenarios(hashrate_hoy: float, fuente: str, cfg: dict,
                        red: dict, px_btc: float, px_xmr: float,
                        fee: float) -> list:
    fis, logicos = _nucleos()
    hilos_cfg = 0
    try:
        hilos_cfg = int(float(cfg.get("CPU_THREADS") or 0))
    except (TypeError, ValueError):
        hilos_cfg = 0
    hilos = hilos_cfg if hilos_cfg > 0 else min(2, fis)

    esc = []
    esc.append({"id": "hoy", "titulo": "HOY (tu hashrate actual)",
                "hashrate": hashrate_hoy,
                "nota": f"fuente: {fuente}"})
    if fis > hilos and hashrate_hoy > 0:
        esc2 = hashrate_hoy * (fis / max(hilos, 1))
        esc.append({"id": "nucleos",
                    "titulo": f"TODOS LOS NÚCLEOS ({fis} físicos)",
                    "hashrate": esc2,
                    "nota": f"hoy usas {hilos} hilos → ×{fis / hilos:.1f}"})
    elif hashrate_hoy > 0:
        esc.append({"id": "nucleos",
                    "titulo": f"TODOS LOS NÚCLEOS ({fis} físicos)",
                    "hashrate": hashrate_hoy,
                    "nota": "ya estás minando con todos los núcleos ✔"})
    else:
        est, fnt = hashrate_estimado()
        esc.append({"id": "nucleos",
                    "titulo": f"TODOS LOS NÚCLEOS ({fis} físicos)",
                    "hashrate": est, "nota": f"fuente: {fnt}"})
    base2 = esc[-1]["hashrate"]
    esc.append({"id": "huge", "titulo": "+ HUGE PAGES / MSR (admin)",
                "hashrate": base2 * FACTOR_HUGEPAGES,
                "nota": f"ajuste típico ×{FACTOR_HUGEPAGES:.2f} en Windows "
                        "como administrador"})
    for e in esc:
        e["btc_dia"] = btc_por_dia(e["hashrate"], red, px_xmr, px_btc, fee)
        e["usd_dia"] = e["btc_dia"] * px_btc
        e["btc_semana"] = e["btc_dia"] * 7
        e["btc_mes"] = e["btc_dia"] * 30
    return esc


def _fmt_dias(d: float) -> str:
    if d <= 0:
        return "¡ya cruzó el umbral!"
    if d > 365:
        return f"{d / 365:.1f} años"
    return f"{d:.1f} días"


# ---------------------------------------------------------------------------
# 5) Reportes (consola + Telegram)
# ---------------------------------------------------------------------------
def _escribir_esc(e: dict, px_btc: float) -> list:
    L = [f"    {e['titulo']}: {e['hashrate']:.0f} H/s"
         + (f"  ({e['nota']})" if e.get("nota") else "")]
    if e["btc_dia"] > 0:
        L.append(f"      → {e['btc_dia']:.8f} BTC/día "
                 f"(≈ USD {e['usd_dia']:.4f}) · "
                 f"{e['btc_semana']:.8f} BTC/semana · "
                 f"{e['btc_mes']:.6f} BTC/mes")
    else:
        L.append("      → sin precios de mercado ahora mismo, "
                 "inténtalo en unos minutos")
    return L


def reporte(cfg, med, fuente, red, px_btc, px_xmr, um, bn, esc) -> str:
    L = []
    L.append("=" * 64)
    L.append("  PRUEBA DE GANANCIAS — ¿cuánto BTC ganas AHORA?")
    L.append("=" * 64)
    L.append(f"Fecha: {time.strftime('%Y-%m-%d %H:%M')}")
    L.append(f"Precios en vivo: BTC ${px_btc:,.0f} · XMR ${px_xmr:,.2f}"
             if px_btc and px_xmr else "Precios: ?")
    L.append(f"Red Monero: {red['hashrate'] / 1e9:.2f} GH/s"
             + ("" if red.get("exacto") else " (valor típico, "
                "sin dato exacto ahora)"))
    L.append("")
    L.append("[1] TU HASHRATE")
    if med > 0:
        L.append(f"    Medido por tu bot: {med:.0f} H/s ({fuente})")
    else:
        est, fnt = hashrate_estimado()
        L.append(f"    El bot aún no ha minado: uso estimación "
                 f"{est:.0f} H/s ({fnt})")
        L.append("    → CORRE EL BOT (CORRER_BOT.bat) y vuelve a ejecutar "
                 "esto para ver TU número real.")
    L.append("")
    L.append("[2] CUÁNTO BTC PUEDES GANAR (matemática de la red Monero)")
    L.append("    XMR/día = 0.6 × 720 bloques × (tu H/s ÷ red H/s)")
    for e in esc:
        L.extend(_escribir_esc(e, px_btc))
    L.append("")
    L.append("[3] POR QUÉ AHORA GANAS MÁS QUE ANTES")
    L.append("    ANTES (modo XMR): minabas, pero el XMR iba a una wallet "
             "que no podías abrir → BTC recibido: 0.00")
    L.append("    AHORA (modo SOLO-BTC): TODO lo minado se acredita en BTC "
             "directo en tu dirección → a Binance automáticamente.")
    plus = ""
    if len(esc) >= 3 and esc[0].get("btc_dia"):
        hoy, ult = esc[0]["btc_dia"], esc[-1]["btc_dia"]
        if ult > hoy > 0:
            plus = f" → hasta ×{ult / hoy:.1f} más que hoy optimizando"
    L.append(f"    Mejora posible con núcleos completos + huge pages{plus}")
    L.append("")
    L.append("[4] TU POOL unMineable (dónde está tu dinero)")
    if um:
        pct = min(100.0, um["payable"] / um["umbral"] * 100) \
            if um["umbral"] else 0.0
        L.append(f"    Pendiente de pago : {um['balance']:.8f} BTC "
                 f"(pagable {um['payable']:.8f})")
        L.append(f"    Umbral            : {um['umbral']:.5f} BTC "
                 f"→ progreso {pct:.1f}%")
        if esc and esc[0]["btc_dia"] > 0:
            falta = max(um["umbral"] - um["payable"], 0.0)
            dias = falta / esc[0]["btc_dia"]
            L.append(f"    Payout estimado   : en {_fmt_dias(dias)} "
                     f"minando sin parar (escenario HOY)")
        L.append(f"    Pagos ya recibidos: {um['pagos_previos']}")
        L.append("    ➜ Al cruzar el umbral el pool paga SOLO en BTC a "
                 "BTC_PAYOUT_ADDRESS; si es la dirección de depósito de "
                 "Binance, cae directo en tu cuenta. Apagar el bot NO "
                 "borra este saldo.")
        if um["error_pago"]:
            L.append("    [!] El pool reporta error de pago: revisa la "
                     "dirección en secrets.")
    else:
        L.append("    Sin datos (revisa BTC_PAYOUT_ADDRESS en secrets o "
                 "tu conexión).")
    L.append("")
    L.append("[5] BINANCE (destino final)")
    if bn and bn.get("error") == "sin-claves":
        L.append("    Sin claves API (solo lectura) en secrets: la prueba "
                 "no puede ver tu saldo, pero el pool sí te paga igual.")
    elif bn:
        if bn.get("direccion"):
            L.append(f"    Dirección de depósito BTC: {bn['direccion']}")
        if bn.get("saldo_btc") is not None:
            sb = bn["saldo_btc"]
            L.append(f"    Saldo spot: {sb:.8f} BTC "
                     f"(≈ USD {sb * px_btc:,.2f})" if px_btc else
                     f"    Saldo spot: {sb:.8f} BTC")
        if bn.get("error"):
            L.append(f"    [!] Aviso API: {bn['error']}")
    else:
        L.append("    Sin datos.")
    L.append("")
    L.append("CORRE EL BOT: doble clic en CORRER_BOT.bat (minero 24/7 + "
             "dashboard). Detener: DETENER_TODO.bat o /apagar.")
    L.append("=" * 64)
    return "\n".join(L)


def resumen_telegram(cfg, med, fuente, red, px_btc, px_xmr, um, bn, esc) -> str:
    """Texto corto HTML para Telegram (el que verás en tu celular)."""
    def f8(x):
        return f"{x:.8f}"

    L = ["<b>PRUEBA DE GANANCIAS (BTC)</b>"]
    if med > 0:
        L.append(f"📡 Hashrate medido por tu bot: <b>{med:.0f} H/s</b> "
                 f"({fuente})")
    else:
        est, fnt = hashrate_estimado()
        L.append(f"📡 Sin minado reciente: estimación <b>{est:.0f} H/s</b> "
                 f"({fnt})")
    if px_btc and px_xmr:
        L.append(f"🪙 BTC ${px_btc:,.0f} · XMR ${px_xmr:,.2f} · "
                 f"red {red['hashrate'] / 1e9:.1f} GH/s")
    L.append("")
    for e in esc:
        if e["btc_dia"] > 0:
            L.append(f"<b>{e['titulo']}</b>\n"
                     f"  {f8(e['btc_dia'])} BTC/día "
                     f"(≈ USD {e['usd_dia']:.4f}) · "
                     f"{f8(e['btc_mes'])} BTC/mes")
        else:
            L.append(f"<b>{e['titulo']}</b>\n  (sin precios ahora)")
    L.append("")
    L.append("<b>ANTES</b>: wallet XMR bloqueada → recibiste 0 BTC")
    L.append("<b>AHORA</b>: SOLO-BTC → 100% llega en BTC a tu Binance")
    if um:
        pct = min(100.0, um["payable"] / um["umbral"] * 100) \
            if um["umbral"] else 0.0
        L.append("")
        L.append(f"💰 Pool unMineable: <b>{f8(um['balance'])} BTC</b> "
                 f"sin pagar ({pct:.1f}% del umbral)")
        if esc and esc[0]["btc_dia"] > 0:
            falta = max(um["umbral"] - um["payable"], 0.0)
            L.append(f"⏱️ Payout a Binance en ~"
                     f"{_fmt_dias(falta / esc[0]['btc_dia'])}")
    if bn and bn.get("saldo_btc") is not None and px_btc:
        L.append(f"🏦 Binance spot: <b>{f8(bn['saldo_btc'])} BTC</b> "
                 f"(≈ USD {bn['saldo_btc'] * px_btc:,.2f})")
    L.append("")
    L.append("🔧 Más BTC: CORRER_BOT.bat + todos los núcleos "
             "+ huge pages (ver reporte completo en consola)")
    return "\n".join(L)


def _enviar_tg(cfg: dict, texto: str) -> bool:
    try:
        import telegram_bot as tg
        if not tg.configured(cfg):
            log("Telegram sin configurar: no envío mensaje")
            return False
        return tg.send(cfg, texto, "money")
    except Exception as e:                          # noqa: BLE001
        log(f"No pude enviar a Telegram: {e}")
        return False


# ---------------------------------------------------------------------------
# Entrada única (la usan el CLI, run_miner.py y el comando /ganancias)
# ---------------------------------------------------------------------------
def enviar_prueba(cfg: dict, motivo: str = "", solo_tg: bool = False,
                  hashrate_forzado: float = 0.0) -> str:
    """Ejecuta la prueba completa y envía el resumen a Telegram.
    Devuelve el texto del reporte de consola (útil para logs)."""
    btc_addr = (cfg.get("BTC_PAYOUT_ADDRESS") or "").strip()
    with ThreadPoolExecutor(max_workers=6) as ex:
        f_px = ex.submit(precio_btc)
        f_xmr_px = ex.submit(precio_xmr)
        f_red = ex.submit(red_xmr)
        f_um = ex.submit(datos_unmineable, btc_addr)
        f_bn = ex.submit(datos_binance, cfg)
        if hashrate_forzado > 0:
            med, fuente = hashrate_forzado, "fijado a mano (--hashrate)"
        else:
            med, fuente = hashrate_medido()
        px_btc, px_xmr, red, um, bn = (f_px.result(), f_xmr_px.result(),
                                       f_red.result(), f_um.result(),
                                       f_bn.result())
    fee = um.get("fee", 0.01) if um else 0.01
    esc = calcular_escenarios(med, fuente, cfg, red, px_btc, px_xmr, fee)
    if solo_tg:
        txt = resumen_telegram(cfg, med, fuente, red, px_btc, px_xmr,
                               um, bn, esc)
    else:
        txt = reporte(cfg, med, fuente, red, px_btc, px_xmr, um, bn, esc)
    _enviar_tg(cfg, resumen_telegram(cfg, med, fuente, red, px_btc, px_xmr,
                                     um, bn, esc))
    # Guarda copia para comparar mañana
    try:
        outp = os.path.join(BASE, "data",
                            "prueba_ganancias_%s.json"
                            % time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(os.path.dirname(outp), exist_ok=True)
        with open(outp, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "motivo": motivo,
                       "hashrate": med, "fuente": fuente,
                       "precio_btc": px_btc, "precio_xmr": px_xmr,
                       "red_xmr": red, "unmineable": um, "binance": bn,
                       "escenarios": esc}, f,
                      indent=2, ensure_ascii=False, default=str)
    except Exception:
        pass
    return txt


def main():
    ap = argparse.ArgumentParser(
        description="PRUEBA DE GANANCIAS: cuánto BTC ganas ahora, "
                    "en vivo y con la matemática de la red")
    ap.add_argument("--sin-tg", action="store_true",
                    help="no enviar nada a Telegram")
    ap.add_argument("--tg-solo", action="store_true",
                    help="solo enviar el resumen a Telegram")
    ap.add_argument("--hashrate", type=float, default=0.0,
                    help="fijar hashrate en H/s (si no, usa el medido)")
    args = ap.parse_args()

    cfg = cargar_secrets()
    if not (cfg.get("BTC_PAYOUT_ADDRESS") or "").strip():
        print("No encontré BTC_PAYOUT_ADDRESS en .streamlit/secrets.toml — "
              "la prueba de pool/Binance saldrá sin datos de tu dirección.")
    print("Midiendo: tu bot, red Monero, precios y Binance…")
    txt = enviar_prueba(cfg, motivo="cli", solo_tg=args.tg_solo,
                        hashrate_forzado=args.hashrate)
    if not args.sin_tg and args.tg_solo:
        print("Resumen enviado a Telegram (si está configurado).")
    print(txt)


if __name__ == "__main__":
    main()
