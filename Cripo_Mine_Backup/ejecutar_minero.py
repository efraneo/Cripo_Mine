# -*- coding: utf-8 -*-
"""ejecutar_minero.py — Ejecuta Cripo_Mine SIN Streamlit, con avisos al
Telegram cada vez que GANE o ENCUENTRE algo (orden del dueño 22/10/2026).

  * Minero Stratum V1 SHA-256 REAL (modo python) contra el pool de secrets
    (default: public-pool.io), autorizado con TU dirección de depósito BTC.
  * Estado en data/metrics.json: el dashboard (app.py) lo muestra igual.
  * Avisos Telegram: shares aceptados (1.º instante y luego agrupados por
    minuto), BLOQUE al instante, depósitos Binance BTC NUEVOS al instante,
    errores del pool con throttle y resumen cada 5 min si hay avance.
  * Secrets SÓLO en .streamlit/secrets.toml (gitignored) — jamás se imprimen.
  * Honestidad: minar BTC con CPU es simbólico (README del repo); esto deja
    el pipeline REAL funcionando de punta a punta.
"""
import json
import os
import sys
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import binance_api  # noqa: E402
import config  # noqa: E402
import telegram_alerts as tg  # noqa: E402
from state_store import StateStore  # noqa: E402
from stratum_miner import make_miner  # noqa: E402

RUTA_VISTOS = os.path.join("data", "depositos_vistos.json")
DEP_CADA = 300.0
PASO = 5.0
PARO_MAX = 180.0            # sin actividad 3 min => reinicio del motor


def _secrets_toml():
    try:
        import tomllib
        with open(os.path.join(".streamlit", "secrets.toml"), "rb") as f:
            return {k: v for k, v in tomllib.load(f).items()
                    if isinstance(v, str)}
    except Exception:
        return {}


SEC = _secrets_toml()
CFG = config.load_secrets()
for k in list(CFG):
    if k in SEC:
        CFG[k] = SEC[k]
BIN_KEY = SEC.get("BINANCE_API_KEY", "")
BIN_SEC = SEC.get("BINANCE_API_SECRET", "")
STORE = StateStore.get()
ULT_ACTIVIDAD = [time.time()]
_DEPOSITOS = [None]         # semilla perezosa


# ----------------------------------------------------------------- callbacks
def on_event(msg, level="info"):
    ULT_ACTIVIDAD[0] = time.time()
    STORE.append_event(msg, level)
    print(f"[{level}] {msg}", flush=True)
    if level in ("error",):
        tg.aviso_inmediato(f"⚠️ <b>Cripo_Mine</b>: {msg}", clave="error",
                           min_seg=120.0)
    elif "Autorizado en el pool" in msg:
        tg.aviso_inmediato(f"✅ <b>Cripo_Mine conectado</b>: {msg}",
                           clave="auth", min_seg=60.0)
    elif "Dificultad fijada" in msg:
        tg.aviso_inmediato(f"🎯 {msg}", clave="diff", min_seg=60.0)


def on_share(job, nonce, status):
    ULT_ACTIVIDAD[0] = time.time()
    STORE.append_share(job, nonce, status)
    if status == "aceptado":
        tg.share_aceptado()
    elif status == "bloque":
        tg.bloque_encontrado(f"job {job} · nonce {nonce}")


def on_stats(stats):
    ULT_ACTIVIDAD[0] = time.time()
    STORE.set_last_stats(stats)
    t = STORE.totals()
    tg.resumen_si_hubo_avance(t.get("shares_ok", 0),
                              float(stats.get("hashrate") or 0),
                              t.get("blocks_found", 0))


# ------------------------------------------------------------- depósitos BTC
def _cargar_vistos():
    try:
        with open(RUTA_VISTOS, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return None


def _guardar_vistos(v):
    try:
        os.makedirs("data", exist_ok=True)
        with open(RUTA_VISTOS, "w", encoding="utf-8") as f:
            json.dump(sorted(v), f)
    except Exception:
        pass


def revisar_depositos():
    """Un depósito BTC nuevo en Binance = dinero que ENTRÓ: aviso ya."""
    if not BIN_KEY:
        return
    b = binance_api.make_binance(BIN_KEY, BIN_SEC)
    try:
        hist = b.deposit_history("BTC", 20) or []
    except Exception as e:
        print(f"[dep] consulta fallida: {e}", flush=True)
        return
    if _DEPOSITOS[0] is None:
        # primera pasada: semilla (sin avisar lo histórico). OJO: si no hay
        # archivo previo había un None aquí y ESTA RAMA CRASHEABA siempre
        # (AttributeError), dejando las alertas de depósito muertas.
        vistos = _cargar_vistos() or set()
        for d in hist:
            vistos.add(str(d.get("id") or d.get("txId")))
        _DEPOSITOS[0] = vistos
        _guardar_vistos(_DEPOSITOS[0])
        if hist:
            print(f"[dep] {len(hist)} depósitos previos conocidos", flush=True)
        return
    for d in hist:
        clave = str(d.get("id") or d.get("txId"))
        if clave in _DEPOSITOS[0]:
            continue
        _DEPOSITOS[0].add(clave)
        try:
            estado = binance_api.format_deposit_status(int(d.get("status", -1)))
        except Exception:
            estado = "?"
        print(f"[dep] NUEVO {d.get('amount')} {d.get('coin')} {estado}",
              flush=True)
        tg.deposito_encontrado(f"{d.get('amount')} {d.get('coin')} · {estado}")
    _guardar_vistos(_DEPOSITOS[0])


# ------------------------------------------------------------------- motor
def arrancar(pool, user, password, threads):
    m = make_miner("python", pool, user, password, threads,
                   on_event, on_share, on_stats)
    m.start()
    return m


def principal():
    payout = (CFG.get("BTC_PAYOUT_ADDRESS") or "").strip()
    b = binance_api.make_binance(BIN_KEY, BIN_SEC) if BIN_KEY else None
    if not payout and b:
        try:
            d = b.deposit_address("BTC") or {}
            addr = str(d.get("address") or "")
            if addr and "SIMULAD" not in addr:
                payout = addr
                os.makedirs("data", exist_ok=True)
                with open(os.path.join("data", "payout_address.txt"),
                          "w", encoding="utf-8") as f:
                    f.write(payout)
                print(f"[payout] dirección BTC de depósito: {payout}",
                      flush=True)
        except Exception as e:
            print(f"[payout] no pude pedirla a Binance: {e}", flush=True)
    user = (CFG.get("POOL_USER") or "").strip() or payout
    pool = CFG.get("POOL_URL") or config.POOL_CATALOG[0]["url"]
    password = CFG.get("POOL_PASSWORD") or "x"
    threads = int(CFG.get("CPU_THREADS") or 2)
    _DEPOSITOS[0] = _cargar_vistos()

    print("=" * 70, flush=True)
    print(f"Cripo_Mine headless · pool {pool} · hilos {threads} · "
          f"binance {'SÍ' if BIN_KEY else 'NO'} · payout {user[:20] or 'FALTA'}",
          flush=True)
    print("=" * 70, flush=True)
    tg.enviar(
        f"⛏️ <b>Cripo_Mine ARRANCADO</b> (BTC, modo headless)\n"
        f"🔌 Pool: {pool} · hilos CPU: {threads}\n"
        f"🏦 Dirección de pago: <code>{user or 'FALTA'}</code>\n"
        f"🔑 Binance API: {'SÍ (depósitos vigilados)' if BIN_KEY else 'NO'}\n"
        f"📊 Avisos: cada share/bloque/depósito · resumen cada 5 min\n"
        f"<i>Minería CPU simbólica — pipeline real de punta a punta</i>")
    if not user:
        tg.aviso_inmediato(
            "⚠️ <b>Cripo_Mine SIN DIRECCIÓN BTC</b>: añade BTC_PAYOUT_ADDRESS "
            "a .streamlit/secrets.toml (o BINANCE_API_KEY para pedirla a "
            "Binance). El pool no puede autorizar.", clave="sindir",  # noqa: E501
            min_seg=3600.0)

    miner = arrancar(pool, user, password, threads) if user else None
    ultimo_dep = 0.0
    paradas = 0
    while True:
        time.sleep(PASO)
        STORE.save()
        ahora = time.time()
        if ahora - ultimo_dep >= DEP_CADA:
            ultimo_dep = ahora
            try:
                revisar_depositos()
            except Exception as e:
                print(f"[dep] error: {e}", flush=True)
        if miner is not None and ahora - ULT_ACTIVIDAD[0] > PARO_MAX:
            # el motor dejó de dar señales: lo reinicio (best-effort)
            paradas += 1
            ULT_ACTIVIDAD[0] = ahora
            print(f"[motor] {int(PARO_MAX)} s sin actividad -> reinicio "
                  f"#{paradas}", flush=True)
            try:
                if hasattr(miner, "stop"):
                    miner.stop()
            except Exception:
                pass
            time.sleep(2)
            miner = arrancar(pool, user, password, threads)
            if paradas % 5 == 0:
                tg.aviso_inmediato(
                    f"🔁 Cripo_Mine: motor reiniciado {paradas} veces "
                    f"(sigue intentando)", clave="reinicio", min_seg=600.0)


if __name__ == "__main__":
    try:
        principal()
    except KeyboardInterrupt:
        sys.exit(0)
