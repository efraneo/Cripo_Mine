#!/usr/bin/env python3
"""
recolectar_pool.py — RECOLECTA lo minado y lo lleva a Binance (v3.2)
====================================================================
Script LOCAL (sin Streamlit) que hace la "recolección de caja" del
pipeline agresivo. Ejecútalo en la carpeta del proyecto:

    python recolectar_pool.py          # reporte completo + Telegram
    python recolectar_pool.py --sin-tg # solo consola

Qué hace:
  1) Consulta el balance PENDIENTE en cada sitio donde minaste:
       • unMineable   → paga en BTC a BTC_PAYOUT_ADDRESS (umbral 0.00075)
       • MoneroOcean  → paga en XMR a WALLET_XMR (umbral ~0.001 XMR)
       • Cadena BTC   → saldo on-chain real de BTC_PAYOUT_ADDRESS
  2) Consulta tu Binance (si pusiste las claves en secrets):
       dirección de depósito BTC, saldo spot y últimos depósitos.
  3) Imprime un PLAN DE RECOLECCIÓN paso a paso y manda el resumen
     a tu Telegram.

VERDADES QUE DEBES SABER (sin humo):
  • El balance dentro de un pool SOLO lo paga el pool, cuando cruza su
    umbral. Ninguna API pública de unMineable permite forzar un retiro
    por debajo del umbral; sí puedes BAJAR el umbral en su web
    (unmineable.com → Addresses → verifica tu dirección).
  • Apagar el minero NO borra el saldo: queda registrado en cada pool
    asociado a tu dirección, esperando el payout.
  • Binance NO acepta depósitos de XMR (delistado 2024-02): el XMR de
    MoneroOcean va a tu wallet Monero, no a Binance.
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

UA = {"User-Agent": "btc-miner-studio-recolecta/3.2"}
UM_API = "https://api.unmineable.com/v4/address/{addr}?coin=BTC"
MO_API = "https://api.moneroocean.stream/miner/{addr}/stats"
MP_ADDR_API = "https://mempool.space/api/address/{addr}"
MP_PRICE_API = "https://mempool.space/api/v1/prices"


# ---------------------------------------------------------------------------
# Carga de secrets (tomllib en py>=3.11; parser simple como fallback)
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
    # Fallback: parser mínimo para líneas  clave = "valor"
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
# Consultas a cada fuente
# ---------------------------------------------------------------------------
def datos_unmineable(addr: str) -> dict:
    """Balance en unMineable para la dirección BTC (API v4 oficial)."""
    if not addr:
        return {}
    d = (_get_json(UM_API.format(addr=addr)) or {}).get("data") or {}

    def _f(k, default=0.0):
        try:
            return float(d.get(k, default) or default)
        except (TypeError, ValueError):
            return default

    pagos = d.get("payments") or []
    if not isinstance(pagos, list):
        pagos = []
    return {
        "pool": "unMineable",
        "balance": _f("balance"),
        "payable": _f("balance_payable"),
        "umbral": _f("payment_threshold", 0.00075),
        "auto": bool(d.get("auto", True)),
        "error_pago": bool((d.get("err_flags") or {}).get("payment_error")),
        "pagos_previos": len(pagos),
    }


def datos_moneroocean(wallet: str) -> dict:
    """XMR pendientes/pagados en MoneroOcean (amtDue/amtPaid en piconero)."""
    if not wallet:
        return {}
    d = _get_json(MO_API.format(addr=wallet))
    if not d:
        return {}
    stats = d.get("stats", d)
    try:
        due = float(stats.get("amtDue", 0) or 0) / 1e12
        paid = float(stats.get("amtPaid", 0) or 0) / 1e12
    except (TypeError, ValueError):
        return {}
    return {"pool": "MoneroOcean", "due_xmr": due, "paid_xmr": paid}


def datos_onchain(addr: str) -> dict:
    """Saldo real en la cadena de Bitcoin de la dirección (mempool.space)."""
    if not addr:
        return {}
    d = _get_json(MP_ADDR_API.format(addr=addr))
    if not d:
        return {}
    try:
        ch = d.get("chain_stats", {})
        me = d.get("mempool_stats", {})
        sat = (int(ch.get("funded_txo_sum", 0)) -
               int(ch.get("spent_txo_sum", 0)) +
               int(me.get("funded_txo_sum", 0)) -
               int(me.get("spent_txo_sum", 0)))
        return {"sat": sat, "txs": int(ch.get("tx_count", 0))}
    except (TypeError, ValueError):
        return {}


def datos_binance(cfg: dict) -> dict:
    """Dirección de depósito + saldo spot + últimos depósitos (si hay claves)."""
    out = {"direccion": "", "saldo_btc": None, "depositos": [], "error": ""}
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
        try:
            for d in b.deposit_history("BTC", 10):
                out["depositos"].append({
                    "amount": float(d.get("amount", 0) or 0),
                    "status": int(d.get("status", -1)),
                    "tx": str(d.get("txId", ""))[:20],
                })
        except BinanceError as e:
            out["error"] = (out["error"] + " | " if out["error"] else "") \
                + f"historial: {e}"
    except Exception as e:                      # noqa: BLE001
        out["error"] = str(e)
    return out


def precio_btc() -> float:
    d = _get_json("https://api.binance.com/api/v3/ticker/price"
                  "?symbol=BTCUSDT", timeout=8)
    if d and d.get("price"):
        try:
            return float(d["price"])
        except (TypeError, ValueError):
            pass
    d = _get_json(MP_PRICE_API, timeout=8)
    try:
        return float((d or {}).get("USD", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------
def _usd(btc: float, px: float) -> str:
    return f"≈ USD {btc * px:,.2f}" if px and btc else ""


def reporte(cfg: dict, um, mo, oc, bn, px: float) -> str:
    L = []
    btc_addr = (cfg.get("BTC_PAYOUT_ADDRESS") or "").strip()
    L.append("=" * 62)
    L.append("  RECOLECCIÓN DE CAJA — pools → Binance")
    L.append("=" * 62)
    L.append(f"Fecha: {time.strftime('%Y-%m-%d %H:%M')} · "
             f"BTC = ${px:,.0f}" if px else "BTC = ?")

    # --- 1) unMineable -----------------------------------------------------
    L.append("")
    L.append("[1] unMineable (paga en BTC)")
    if um:
        L.append(f"    Balance sin pagar : {um['balance']:.8f} BTC "
                 f"{_usd(um['balance'], px)}")
        L.append(f"    Pagable ahora     : {um['payable']:.8f} BTC")
        L.append(f"    Umbral del pool   : {um['umbral']:.5f} BTC "
                 f"{_usd(um['umbral'], px)}")
        falta = max(um["umbral"] - um["payable"], 0.0)
        pct = min(100.0, um["payable"] / um["umbral"] * 100) if um["umbral"] \
            else 0.0
        L.append(f"    Progreso          : {pct:.1f}% "
                 f"(faltan {falta:.8f} BTC {_usd(falta, px)})")
        if um["payable"] >= um["umbral"]:
            L.append("    ➜ El pago saldrá SOLO en minutos/horas hacia "
                     "BTC_PAYOUT_ADDRESS. Si esa dirección es la de depósito "
                     "de Binance, cae directo a tu cuenta.")
        else:
            L.append("    ➜ AÚN no cruza el umbral: el pool NO permite "
                     "retirarlo por API. Opciones:")
            L.append("       a) Bajar el umbral en unmineable.com → Addresses")
            L.append("          (verifica que eres dueño de la dirección).")
            L.append("       b) Dejarlo acumular: NO se pierde al apagar el "
                     "minero.")
        if um["error_pago"]:
            L.append("    [!] El pool reporta error de pago en tu dirección: "
                     "revisa que sea válida y sin memo.")
    else:
        L.append("    Sin datos (API no respondió o no hay "
                 "BTC_PAYOUT_ADDRESS).")

    # --- 2) Saldo on-chain --------------------------------------------------
    L.append("")
    L.append("[2] Cadena Bitcoin (saldo ya pagado a tu dirección)")
    if oc and oc.get("sat", 0) > 0:
        sat = oc["sat"]
        L.append(f"    Saldo on-chain    : {sat / 1e8:.8f} BTC "
                 f"{_usd(sat / 1e8, px)} en {oc.get('txs', 0)} txs")
        destino = (bn or {}).get("direccion") or "(ve tu dirección en Binance)"
        L.append(f"    ➜ Envíalo desde tu wallet a tu Binance: {destino}")
    elif oc:
        L.append("    Saldo on-chain    : 0 BTC (el pool todavía no ha pagado "
                 "nada a la dirección)")
    else:
        L.append("    Sin datos de mempool.space (o sin dirección).")

    # --- 3) MoneroOcean -----------------------------------------------------
    L.append("")
    L.append("[3] MoneroOcean (paga en XMR)")
    if mo:
        L.append(f"    Pendiente         : {mo['due_xmr']:.6f} XMR "
                 f"(histórico pagado {mo['paid_xmr']:.6f} XMR)")
        if mo["due_xmr"] >= 0.001:
            L.append("    ➜ Por encima del umbral (~0.001 XMR): pago saliente "
                     "a tu wallet Monero.")
        else:
            L.append("    ➜ Por debajo del umbral (~0.001 XMR): sigue "
                     "acumulando en el pool.")
        L.append("    [!] Binance NO acepta XMR (delistado 2024-02): este "
                 "saldo va a tu wallet Monero, no a Binance.")
    else:
        L.append("    Sin datos (no hay WALLET_XMR o el pool no respondió).")

    # --- 4) Binance ----------------------------------------------------------
    L.append("")
    L.append("[4] Binance (destino del dinero)")
    if bn and bn.get("error") == "sin-claves":
        L.append("    Sin claves API: mira la dirección a mano en "
                 "Binance → Cripto → Depositar → BTC → red Bitcoin.")
    elif bn:
        if bn.get("direccion"):
            L.append(f"    Dirección depósito: {bn['direccion']}")
        if bn.get("saldo_btc") is not None:
            sb = bn["saldo_btc"]
            L.append(f"    Saldo spot BTC    : {sb:.8f} BTC "
                     f"{_usd(sb, px)}")
        deps = bn.get("depositos") or []
        if deps:
            L.append("    Últimos depósitos :")
            for d in deps[:5]:
                st = {0: "pendiente", 1: "ACREDITADO"}.get(d["status"],
                                                           f"código {d['status']}")
                L.append(f"      · {d['amount']:.8f} BTC — {st}")
        if bn.get("error"):
            L.append(f"    [!] Aviso API     : {bn['error']}")
    else:
        L.append("    Sin datos.")

    L.append("")
    L.append("APAGAR EL MINERO:")
    L.append("  • Windows : doble clic en DETENER_TODO.bat")
    L.append("  • Telegram: envía /apagar a tu bot")
    L.append("  • Consola : Ctrl+C en la ventana del daemon")
    L.append("  El saldo pendiente en los pools NO se pierde al apagar.")
    L.append("=" * 62)
    return "\n".join(L)


def resumen_telegram(cfg: dict, um, mo, oc, bn, px: float):
    """Manda el resumen corto a Telegram (si está configurado)."""
    try:
        import telegram_bot as tg
        if not tg.configured(cfg):
            return
        L = ["<b>RECOLECCIÓN DE CAJA</b>"]
        if um:
            ok = um["payable"] >= um["umbral"]
            L.append(f"unMineable: <b>{um['balance']:.8f} BTC</b> "
                     f"{_usd(um['balance'], px)} — "
                     + ("payout en camino ✔" if ok else
                        f"umbral {um['umbral']:.5f} aún no alcanzado"))
        if oc and oc.get("sat", 0) > 0:
            L.append(f"On-chain en tu dirección: <b>{oc['sat'] / 1e8:.8f}"
                     f"</b> BTC — envíalo a tu depósito de Binance")
        if mo:
            L.append(f"MoneroOcean: <b>{mo['due_xmr']:.6f} XMR</b> "
                     "(van a tu wallet Monero, Binance no acepta XMR)")
        if bn and bn.get("saldo_btc") is not None:
            L.append(f"Binance spot: <b>{bn['saldo_btc']:.8f} BTC</b>")
        L.append("Para apagar todo: DETENER_TODO.bat o /apagar")
        tg.send(cfg, "\n".join(L), "money")
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="Recolecta balances de pools "
                                             "y prepara el traslado a Binance")
    ap.add_argument("--sin-tg", action="store_true",
                    help="no enviar el resumen por Telegram")
    args = ap.parse_args()

    cfg = cargar_secrets()
    btc_addr = (cfg.get("BTC_PAYOUT_ADDRESS") or "").strip()
    if not btc_addr:
        print("No encontré BTC_PAYOUT_ADDRESS en .streamlit/secrets.toml")
        btc_addr = input("Escribe tu dirección BTC para consultarla: ").strip()
        if not btc_addr:
            print("Sin dirección no puedo consultar nada. Adiós.")
            sys.exit(1)

    print("Consultando pools, cadena y Binance (en paralelo)…")
    with ThreadPoolExecutor(max_workers=5) as ex:
        f_um = ex.submit(datos_unmineable, btc_addr)
        f_oc = ex.submit(datos_onchain, btc_addr)
        f_mo = ex.submit(datos_moneroocean,
                         (cfg.get("WALLET_XMR") or "").strip())
        f_bn = ex.submit(datos_binance, cfg)
        f_px = ex.submit(precio_btc)
        um, oc, mo, bn, px = (f_um.result(), f_oc.result(), f_mo.result(),
                              f_bn.result(), f_px.result())

    txt = reporte(cfg, um, mo, oc, bn, px)
    print(txt)
    if not args.sin_tg:
        resumen_telegram(cfg, um, mo, oc, bn, px)
    # Guarda una copia para referencia
    try:
        outp = os.path.join(BASE, "data", "recolecta_%s.json" %
                            time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(os.path.dirname(outp), exist_ok=True)
        with open(outp, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "precio_btc": px,
                       "unmineable": um, "onchain": oc, "moneroocean": mo,
                       "binance": bn}, f, indent=2, ensure_ascii=False)
        print(f"Copia guardada en: {outp}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
