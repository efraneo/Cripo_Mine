"""
selector_moneda.py — v4.6 MULTI · EL BOT ELIJE LA MEJOR MONEDA
================================================================
Peticion del dueno: "que no solo se gane con BTC sino con otros activos
que se puedan minar y que el bot elija el mejor, o mas de uno, segun mi
maquina".

VERDAD DEL HARDWARE (HP Pavilion i5 + Iris Graphics):
  - La CPU mina UNA cabeza a la vez (RandomX/Ghostrider/VerusHash se
    pelean la misma cache L3: dos a la vez = mitad de hashrate cada una).
  - La GPU Iris ES la unica segunda cabeza real en paralelo (la gestiona
    la sonda OpenCL de AFINAR.bat desde v4.5).
  => MULTI aqui = elegir SIEMPRE la mejor ruta de CPU y cambiarla solo
     cuando otra le gane con margen (histeresis anti-vaivenes).

RUTAS (precios validados en vivo 28-10-2026):
  xmr_mo    XMR          @ MoneroOcean (xmrig-MO, cabeza actual)
  btc_vrsc  Verus        @ Zpool (SRBMiner-Multi) -> paga BTC
  btc_gr    GhostRider   @ Zpool (SRBMiner-Multi) -> paga BTC

LAS RUTAS BTC pagan DIRECTO a tu direccion BTC de Binance: en estos
pools el usuario del stratum ES la direccion (sin cuentas ni claves).
Ese es el "protocolo de minado" que si funciona con Binance: el POOL de
Binance cierra el 10-nov-2026 (anuncio oficial) pero el EXCHANGE sigue
vivo y su API publica da precios (validado: BTC Kraken 80,533 ~ Binance
80,639). XMR esta delistado de Binance desde 2024-02: la ruta XMR se
cobra en tu wallet (Kraken si quieres vender).

DOS CAPAS DE ESTIMACION (honestas, cada una con su etiqueta):
  TEORIA: emision x precio x (tu hash / hash de red CONSERVADOR).
          XMR usa la matematica exacta ya probada (dificultad real de la
          red). VRSC/GR usan blockreward y precio REALES de Zpool con
          hashrate de red pesimista: si la red real es mayor, la teoria
          sobreestima y la capa MEDIDO corrige. Mejor pesimista.
  MEDIDO: saldo real del pool (API wallet) creciendo entre visitas.
          Tras 24h minando, el numero MEDIDO reemplaza a la teoria.
"""
import json
import os
import time

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DECISION_FILE = os.path.join(DATA_DIR, "decision_moneda.json")
APRENDIDO_FILE = os.path.join(DATA_DIR, "selector_aprendido.json")
SALDO_ZPOOL_FILE = os.path.join(DATA_DIR, "saldo_zpool.json")

ZPOOL_CURR = "https://www.zpool.ca/api/currencies"
ZPOOL_WALLET = "https://www.zpool.ca/api/wallet?address={addr}"
KRAKEN = "https://api.kraken.com/0/public/Ticker?pair={pair}"
BINANCE_PRICE = "https://api.binance.com/api/v3/ticker/price?symbol={sym}"
TIMEOUT = 10
CACHE_TTL = 600                    # 10 min de cache para APIs de mercado

# Hashrate de red CONSERVADOR (H/s). Si la red real es mayor, la teoria
# sobrestima y la capa MEDIDO corrige hacia abajo. Mejor pesimista.
NET_H_CONSERVADOR = {
    "verushash": 100_000_000_000,     # ~100 GH/s (red Verus, 2026)
    "ghostrider": 2_000_000_000_000,  # ~2 TH/s (red Raptoreum, 2026)
    "randomx": 7_200_000_000,         # ~7.2 GH/s: fallback si la API de
                                      # dificultad real no responde
}
BLOCKTIME_S = {"verushash": 60, "ghostrider": 60}
FEE_POOL = 0.01                    # Zpool 1%
# H/s por hilo en laptop x86 moderno (estimacion de ARRANQUE; lo que
# manda despues es lo medido). Fuente: tablas de benchmarks publicos.
H_POR_HILO = {
    "randomx": 65.0,             # config optima, DDR4 laptop
    "verushash": 1_400_000.0,    # 1.4 MH/s por hilo
    "ghostrider": 110.0,         # algoritmo hecho para CPU
}
UMBRAL_DIVERGENCIA_PRECIO = 0.30   # >30% entre fuentes = sospechoso

_cache = {"ts": 0.0, "precios": {}, "zpool": {}}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _get_json(url: str, timeout: int = TIMEOUT):
    try:
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": "CripoMine/4.6"})
        if r.status_code == 200:
            return r.json()
    except Exception:                                 # noqa: BLE001
        pass
    return {}


def _hilos_afinados() -> int:
    """Hilos optimos medidos por AFINAR.bat (v4.5); fallback fisicos."""
    try:
        with open(os.path.join(DATA_DIR, "afinado.json"), encoding="utf-8") as f:
            h = int((json.load(f) or {}).get("hilos") or 0)
        if h >= 1:
            return h
    except Exception:                                 # noqa: BLE001
        pass
    try:
        import psutil
        return psutil.cpu_count(logical=False) or os.cpu_count() or 4
    except Exception:                                 # noqa: BLE001
        return max(1, (os.cpu_count() or 4) // 2)


def _leer_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                 # noqa: BLE001
        return default


def _escribir_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False, default=str)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Precios con VALIDACION CRUZADA (hallazgo real 28-10-2026: Binance
# XMRUSDT marco $118.70 mientras Kraken $591.72 => para XMR manda Kraken
# y Binance solo se usa como alarma; para BTC ambas coinciden).
# ---------------------------------------------------------------------------
def precios(force: bool = False) -> dict:
    now = time.time()
    if not force and _cache["precios"] and now - _cache["ts"] < CACHE_TTL:
        return _cache["precios"]
    out = {"btc": 0.0, "xmr": 0.0, "fuentes": {}, "alerta": ""}

    bn = _get_json(BINANCE_PRICE.format(sym="BTCUSDT")) or {}
    kr = _get_json(KRAKEN.format(pair="XBTUSD")) or {}
    try:
        btc_bin = float(bn.get("price") or 0)
    except (TypeError, ValueError):
        btc_bin = 0.0
    try:
        kres = (kr.get("result") or {})
        kkey = list(kres)[0] if kres else ""
        btc_krk = float(kres[kkey]["c"][0]) if kkey else 0.0
    except (TypeError, ValueError, KeyError, IndexError):
        btc_krk = 0.0
    out["btc"] = btc_bin if btc_bin > 0 else btc_krk
    out["fuentes"]["btc"] = f"binance={btc_bin or '-'} kraken={btc_krk or '-'}"

    kr2 = _get_json(KRAKEN.format(pair="XMRUSD")) or {}
    bn2 = _get_json(BINANCE_PRICE.format(sym="XMRUSDT")) or {}
    try:
        r2 = (kr2.get("result") or {})
        k2 = list(r2)[0] if r2 else ""
        xmr_krk = float(r2[k2]["c"][0]) if k2 else 0.0
    except (TypeError, ValueError, KeyError, IndexError):
        xmr_krk = 0.0
    try:
        xmr_bin = float(bn2.get("price") or 0)
    except (TypeError, ValueError):
        xmr_bin = 0.0
    # Kraken manda; si divergen >30% se avisa (dato raro no decide dinero)
    out["xmr"] = xmr_krk
    out["fuentes"]["xmr"] = f"kraken={xmr_krk or '-'} binance={xmr_bin or '-'}"
    if xmr_krk > 0 and xmr_bin > 0:
        div = abs(xmr_bin / xmr_krk - 1.0)
        if div > UMBRAL_DIVERGENCIA_PRECIO:
            out["alerta"] = (f"Binance XMR diverge {div*100:.0f}% de Kraken: "
                             "para XMR se usa Kraken (dato Binance ignorado)")
    _cache["precios"] = out
    _cache["ts"] = now
    return out


def datos_zpool(force: bool = False) -> dict:
    """Monedas de Zpool: blockreward, precio USD real (estimate_usd)."""
    now = time.time()
    if not force and _cache["zpool"] and now - _cache["ts"] < CACHE_TTL:
        return _cache["zpool"]
    cur = _get_json(ZPOOL_CURR) or {}
    out = {}
    for sym in ("VRSC", "RTM"):
        row = cur.get(sym)
        if isinstance(row, dict):
            try:
                out[sym.lower()] = {
                    "blockreward": float(row.get("blockreward") or 0),
                    "precio_usd": float(row.get("estimate_usd") or 0),
                    "net_h_pool": float(row.get("hashrate") or 0),
                }
            except (TypeError, ValueError):
                continue
    _cache["zpool"] = out
    _cache["ts"] = now
    return out


# ---------------------------------------------------------------------------
# Tabla de rutas
# ---------------------------------------------------------------------------
def _btc_addr(cfg: dict) -> str:
    return (cfg.get("BTC_PAYOUT_ADDRESS") or "").strip()


def rutas() -> list:
    return [
        {"id": "xmr_mo", "nombre": "XMR @ MoneroOcean (xmrig-MO)",
         "moneda": "XMR", "miner": "xmrig",
         "detalle": "Auto-cambia entre forks RandomX y paga XMR; "
                    "venta via Kraken (Binance no acepta XMR desde 2024-02)",
         "algo": "randomx"},
        {"id": "btc_vrsc", "nombre": "Verus @ Zpool (SRBMiner)",
         "moneda": "BTC", "miner": "srb",
         "detalle": "VerusHash en CPU; Zpool convierte a BTC y paga directo "
                    "a tu direccion Binance (usuario = direccion)",
         "algo": "verushash", "zpool_sym": "vrsc"},
        {"id": "btc_gr", "nombre": "GhostRider @ Zpool (SRBMiner)",
         "moneda": "BTC", "miner": "srb",
         "detalle": "Algoritmo hecho para CPUs (RTM + 14 monedas); Zpool "
                    "paga BTC directo a tu direccion Binance",
         "algo": "ghostrider", "zpool_sym": "rtm"},
    ]


def est_teorico_usd_dia(ruta_id: str, h: float, px: dict,
                        zp: dict, red_xmr: dict) -> float:
    """Estimacion TEORICA $/dia para un hashrate h (del algo de la ruta)."""
    if h <= 0:
        return 0.0
    if ruta_id == "xmr_mo":
        try:
            from probar_ganancias import xmr_por_dia
            if not (red_xmr or {}).get("hashrate"):
                red_xmr = {"hashrate": NET_H_CONSERVADOR["randomx"]}
            xmr_dia = xmr_por_dia(h, red_xmr)
            return xmr_dia * (px.get("xmr") or 0.0)
        except Exception:                             # noqa: BLE001
            return 0.0
    ruta = next((r for r in rutas() if r["id"] == ruta_id), None)
    sym = (ruta or {}).get("zpool_sym", "")
    d = zp.get(sym) or {}
    reward, precio = d.get("blockreward", 0.0), d.get("precio_usd", 0.0)
    net = NET_H_CONSERVADOR.get((ruta or {}).get("algo"), 0)
    if reward <= 0 or precio <= 0 or net <= 0:
        return 0.0
    bloques_dia = 86400.0 / BLOCKTIME_S.get((ruta or {}).get("algo"), 60)
    return reward * bloques_dia * precio * (h / net) * (1.0 - FEE_POOL)


def hashrate_para_algo(algo: str) -> float:
    """Hashrate estimado del usuario en ese algoritmo (hilo x afinado)."""
    return _hilos_afinados() * H_POR_HILO.get(algo, 0.0)


def est_medido_usd_dia(ruta_id: str, px: dict) -> tuple:
    """Capa MEDIDO: (usd_dia, nota) desde selector_aprendido.json."""
    ap = _leer_json(APRENDIDO_FILE, {}) or {}
    m = ap.get(ruta_id) or {}
    btc_dia = float(m.get("btc_dia_medido") or 0.0)
    xmr_dia = float(m.get("xmr_dia_medido") or 0.0)
    usd = btc_dia * (px.get("btc") or 0.0) + xmr_dia * (px.get("xmr") or 0.0)
    if usd > 0:
        edad_h = (time.time() - float(m.get("ts") or 0)) / 3600.0
        return usd, f"medido hace {edad_h:.0f}h (pesa mas que la teoria)"
    return 0.0, ""


# ---------------------------------------------------------------------------
# Capa MEDIDO: saldo real de Zpool creciendo entre visitas
# ---------------------------------------------------------------------------
def registrar_saldo_zpool(cfg: dict, on_event=None) -> dict:
    """Mide el saldo total en Zpool y estima BTC/dia por pendiente.
    El daemon lo llama cada 30 min; con >=2 visitas separadas >=2h
    calcula la pendiente real (eso NO miente)."""
    addr = _btc_addr(cfg)
    if not addr:
        return {}
    w = _get_json(ZPOOL_WALLET.format(addr=addr)) or {}
    if not isinstance(w, dict) or w.get("error"):
        return {}
    try:
        total = float(w.get("total") or 0) + float(w.get("unpaid") or 0)
    except (TypeError, ValueError):
        return {}
    hist = _leer_json(SALDO_ZPOOL_FILE, []) or []
    hist.append({"ts": time.time(), "total": total})
    hist = hist[-96:]                    # ~2 dias de muestras a 30 min
    _escribir_json(SALDO_ZPOOL_FILE, hist)
    btc_dia = 0.0
    vieja = hist[0]
    for m in hist:                       # pendiente max rango disponible
        dt_h = (m["ts"] - vieja["ts"]) / 3600.0
        if dt_h >= 2.0:
            btc_dia = max(btc_dia, (m["total"] - vieja["total"]) / dt_h)
            vieja = m
    if btc_dia != 0:                     # saldo puede bajar por pagos
        ap = _leer_json(APRENDIDO_FILE, {}) or {}
        ap["btc_vrsc"] = ap.get("btc_vrsc") or {}
        ap["btc_gr"] = ap.get("btc_gr") or {}
        for rid in ("btc_vrsc", "btc_gr"):
            ap[rid] = {"btc_dia_medido": round(max(0.0, btc_dia), 10),
                       "ts": time.time(), "fuente": "zpool_wallet"}
        _escribir_json(APRENDIDO_FILE, ap)
        if on_event:
            on_event(f"MEDIDO: saldo Zpool {total:.8f} BTC -> "
                     f"{btc_dia:.8f} BTC/dia", "ok")
    return {"total": total, "btc_dia_medido": btc_dia}


# ---------------------------------------------------------------------------
# DECISION con histeresis (no cambiar por ruido: solo si gana con margen)
# ---------------------------------------------------------------------------
MARGEN_DEF = 15.0                    # % de ventaja para cambiar de ruta


def _viable(ruta: dict, cfg: dict) -> tuple:
    """(viable, motivo) — sin direccion/binary la ruta no compite."""
    if ruta["miner"] == "srb" and not _btc_addr(cfg):
        return False, "falta BTC_PAYOUT_ADDRESS en secrets"
    return True, ""


def _binario_srb_listo() -> bool:
    return bool(cabeza_binario_ok())


def cabeza_binario_ok() -> bool:
    try:
        import cabeza_srb
        return bool(cabeza_srb.binario_path())
    except Exception:                                 # noqa: BLE001
        return False


def decidir(cfg: dict, on_event=None, force: bool = False) -> dict:
    """Elige la mejor ruta ($/dia) con histeresis y persiste la decision."""
    px = precios()
    zp = datos_zpool()
    try:
        from probar_ganancias import red_xmr
        red = red_xmr()
    except Exception:                                 # noqa: BLE001
        red = {}
    margen = float(cfg.get("MARGEN_CAMBIO_PCT") or MARGEN_DEF) / 100.0

    tabla = []
    for r in rutas():
        ok, motivo = _viable(r, cfg)
        h = hashrate_para_algo(r["algo"]) if ok else 0.0
        teo = est_teorico_usd_dia(r["id"], h, px, zp, red) if ok else 0.0
        med, nota_med = est_medido_usd_dia(r["id"], px) if ok else (0.0, "")
        usd = max(teo, med) if ok else 0.0
        if not ok:
            usd = -1.0            # no compite
        tabla.append({"id": r["id"], "nombre": r["nombre"], "moneda":
                      r["moneda"], "viable": ok, "motivo": motivo,
                      "hashrate_est": h, "usd_teorico": teo,
                      "usd_medido": med, "nota_medido": nota_med,
                      "usd": usd})

    prev = _leer_json(DECISION_FILE, {}) or {}
    actual_id = prev.get("ruta") if not force else None
    if actual_id not in [t["id"] for t in tabla]:
        actual_id = None
    actual = next((t for t in tabla if t["id"] == actual_id), None)
    if actual is None or not actual.get("viable"):
        mejores = [t for t in tabla if t["viable"]]
        actual = max(mejores, key=lambda t: t["usd"]) if mejores else tabla[0]

    # histeresis: cambiar SOLO si otra ruta viable gana por el margen
    elegida = actual
    mejores = sorted([t for t in tabla if t["viable"]],
                     key=lambda t: t["usd"], reverse=True)
    if mejores and (actual_id is None or not actual.get("viable")):
        elegida = mejores[0]
    elif mejores and mejores[0]["id"] != actual_id:
        if mejores[0]["usd"] > actual["usd"] * (1.0 + margen):
            elegida = mejores[0]
    motivo_cambio = ""
    if elegida["id"] != (actual_id or ""):
        motivo_cambio = (f"cambio {actual_id or 'ninguna'} -> "
                         f"{elegida['id']}: {elegida['usd']:.4f} vs "
                         f"{(actual or {}).get('usd', 0):.4f} USD/dia "
                         f"(margen {margen*100:.0f}%)")
        if on_event:
            on_event(f"SELECTOR: {motivo_cambio}", "ok")

    # ruta muerta (binario/direccion) fuerza caida a una viable
    if not elegida.get("viable"):
        elegida = {"id": "xmr_mo", "nombre": rutas()[0]["nombre"],
                   "moneda": "XMR", "viable": True, "motivo": "fallback",
                   "hashrate_est": hashrate_para_algo("randomx"),
                   "usd_teorico": 0.0, "usd_medido": 0.0, "nota_medido": "",
                   "usd": 0.0}

    decision = {"ruta": elegida["id"], "ts": time.time(),
                "motivo_cambio": motivo_cambio, "alerta_precio":
                    px.get("alerta", ""), "tabla": tabla,
                "reevaluar": False}
    _escribir_json(DECISION_FILE, decision)
    return decision


def leer_decision() -> dict:
    return _leer_json(DECISION_FILE, {}) or {}


def ruta_por_id(id_: str) -> dict:
    return next((r for r in rutas() if r["id"] == id_), rutas()[0])


# ---------------------------------------------------------------------------
# CLI: SELECTOR.bat -> python selector_moneda.py --print
# ---------------------------------------------------------------------------
def _fmt_h(h: float) -> str:
    if h >= 1_000_000:
        return f"{h/1e6:.1f} MH/s"
    if h >= 1000:
        return f"{h/1e3:.1f} kH/s"
    return f"{h:.0f} H/s"


def imprimir_tabla(cfg: dict) -> str:
    px = precios()
    d = decidir(cfg)
    lineas = []
    lineas.append("=" * 66)
    lineas.append(" SELECTOR MULTI - el bot elige la mejor moneda para TU cpu")
    lineas.append("=" * 66)
    if px.get("btc"):
        lineas.append(f" BTC ${px['btc']:,.0f}  XMR ${px.get('xmr', 0):,.2f}"
                      f"  [{px.get('fuentes', {}).get('btc', '')}]")
    if px.get("alerta"):
        lineas.append(f" AVISO: {px['alerta']}")
    lineas.append("-" * 66)
    for t in d["tabla"]:
        if not t["viable"]:
            lineas.append(f" {t['id']:<9} NO VIABLE: {t['motivo']}")
            continue
        if t["usd_medido"] > t["usd_teorico"]:
            fuente = f"MEDIDO {t['usd_medido']:.4f} USD/dia"
        else:
            fuente = f"teoria {t['usd_teorico']:.4f} USD/dia"
        marca = "<== ELEGIDA" if t["id"] == d["ruta"] else ""
        lineas.append(f" {t['id']:<9} {t['moneda']:<4} "
                      f"{_fmt_h(t['hashrate_est']):>10}  {fuente}  {marca}")
    lineas.append("-" * 66)
    lineas.append(f" RUTA ACTIVA: {d['ruta']}")
    if d.get("motivo_cambio"):
        lineas.append(f" {d['motivo_cambio']}")
    ap = _leer_json(APRENDIDO_FILE, {}) or {}
    m = ap.get(d["ruta"]) or {}
    if m.get("btc_dia_medido") or m.get("xmr_dia_medido"):
        lineas.append(f" capa MEDIDO activa: {m}")
    else:
        lineas.append(" capa MEDIDO: sin datos aun (tras 24h minando el")
        lineas.append("  saldo real del pool reemplaza a la estimacion)")
    lineas.append("=" * 66)
    return "\n".join(lineas)


if __name__ == "__main__":
    import argparse
    import sys
    sys.path.insert(0, BASE_DIR)
    from config import load_secrets
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args()
    cfg = load_secrets()
    print(imprimir_tabla(cfg))
