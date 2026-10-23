#!/usr/bin/env python3
"""
run_miner.py — DAEMON headless del motor agresivo (sin Streamlit)
=================================================================
Minería 24/7 con failover multi-pool + vigilancia térmica + alertas
Telegram + detección de pagos. Corre desacoplado del dashboard; el
dashboard (app.py) solo lo arranca/para y MUESTRA sus métricas.

Uso:
    python run_miner.py                     # modo aggressive (default)
    python run_miner.py --mode aggressive   # ídem
    python run_miner.py --once              # una pasada de diagnóstico

Métricas: se escriben en data/metrics_daemon.json (separadas de las del
modo python del dashboard para no pisarse). Log: logs/daemon.log.

Parada amable: escribe {"action": "stop"} en data/control.json (el botón
Detener del dashboard o Telegram /pausar→stop lo hacen), o Ctrl+C.
"""
import argparse
import os
import signal
import sys
import time

# ---------------------------------------------------------------------------
# Args ANTES de importar config (el daemon escribe métricas en otro archivo)
# ---------------------------------------------------------------------------
_parser = argparse.ArgumentParser(description="Daemon minero agresivo")
_parser.add_argument("--mode", default="aggressive",
                     choices=["aggressive"],
                     help="modo de operación del daemon")
_parser.add_argument("--once", action="store_true",
                     help="diagnóstico de una pasada (no mina)")
_args = _parser.parse_args()

os.environ["MINER_METRICS_FILE"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "metrics_daemon.json")

# ---------------------------------------------------------------------------
import control                      # noqa: E402
import telegram_bot as tg           # noqa: E402
from config import load_secrets, format_hashrate, format_uptime  # noqa: E402
from state_store import StateStore  # noqa: E402
from aggressive_engine import AggressiveEngine, TARGETS  # noqa: E402
from payout_manager import PayoutWatcher  # noqa: E402
from vigilante import Watchdog       # noqa: E402
from binance_api import make_binance  # noqa: E402


def log(msg: str, level: str = "info"):
    store.append_event(msg, level)
    print(f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


# ---------------------------------------------------------------------------
store = StateStore.get()
cfg = load_secrets()
payout = None                             # se asigna en main() (PayoutWatcher)

# throttle de alertas de share (segundos entre aviso y aviso)
_share_alert = {"ts": 0.0}


def on_stats(stats: dict):
    store.set_last_stats(stats)
    store.append_history(stats.get("hashrate", 0), stats.get("difficulty", 0),
                         stats.get("shares_ok", 0), stats.get("shares_rej", 0))


def on_share(job, nonce, status):
    """Registra el share en el store Y avisa a Telegram (con throttle).

    Antes el daemon descartaba los shares (lambda: None): /estado, el
    resumen diario y los contadores salían siempre en 0. Ahora cada
    aceptado alimenta el histórico y dispara un aviso para que puedas
    ver la ganancia acercándose al umbral de pago."""
    store.append_share(job, nonce, status)
    if status not in ("aceptado", "bloque"):
        return
    now = time.time()
    try:
        gap = float(cfg.get("SHARE_ALERT_MIN_SEC", 120) or 120)
    except (TypeError, ValueError):
        gap = 120.0
    if now - _share_alert["ts"] < gap:
        return
    _share_alert["ts"] = now
    try:
        hr = format_hashrate((store.last() or {}).get("hashrate", 0) or 0)
        tot = store.totals()
        pay = payout.snapshot_light() if payout is not None else {}
        um = pay.get("unmineable") or {}
        coin = pay.get("coin", "USDT")
        bal = float(um.get("balance", 0) or 0)
        thr = float(um.get("threshold", 0) or 0)
        pct = (bal / thr * 100.0) if thr else 0.0
        tg.send(cfg, (
            f"<b>SHARE {status.upper()}</b> · nº {tot.get('shares_ok', 0)} "
            f"· hashrate {hr}\n"
            f"Saldo en unMineable: <b>{bal:.6f} {coin}</b> "
            f"({pct:.2f}% del umbral {thr:g} {coin})"), "ok")
    except Exception:
        pass


engine = AggressiveEngine(
    cfg,
    on_event=lambda m, l="info": log(m, l),
    on_share=on_share,                     # shares → store + aviso Telegram
    on_stats=on_stats)


def alert(msg: str, level: str = "info"):
    log(msg, level)
    tg.send(cfg, msg, level)


def get_status(include_earnings: bool = False) -> dict:
    """Snapshot agregado para /estado de Telegram y resumen diario."""
    tot = store.totals()
    eng = engine.snapshot()
    pay = payout.snapshot_light() if (include_earnings and payout) else \
        {"coin": str(cfg.get("PAYOUT_COIN") or "BTC").upper(),
         "unmineable": {"balance": 0, "paid": 0, "threshold": 0},
         "moneroocean": {"due_xmr": 0},
         "binance_total_btc": 0.0}
    hashrate = (store.last() or {}).get("hashrate", 0) or 0
    return {
        "engine": eng,
        "totals": tot,
        "payout": pay,
        "hashrate_txt": format_hashrate(hashrate),
        "uptime_txt": format_uptime(tot.get("uptime", 0)),
    }


# ---------------------------------------------------------------------------
def validate_environment() -> bool:
    """Sin direcciones no hay pipeline: avisa y aborta con instrucciones."""
    coin = str(cfg.get("PAYOUT_COIN") or "BTC").strip().upper() or "BTC"
    pay_key = "USDT_PAYOUT_ADDRESS" if coin == "USDT" else "BTC_PAYOUT_ADDRESS"
    has_pay = bool((cfg.get(pay_key) or "").strip())
    has_xmr = bool((cfg.get("WALLET_XMR") or "").strip())
    if not (has_pay or has_xmr):
        log(f"FALTAN DIRECCIONES: pon {pay_key} (para cobrar en {coin} "
            "vía unMineable) o WALLET_XMR (MoneroOcean/SupportXMR) en "
            ".streamlit/secrets.toml", "error")
        tg.send(cfg, f"<b>No puedo arrancar</b>: falta {pay_key} o "
                     "WALLET_XMR en secrets.", "error")
        return False
    if not tg.configured(cfg):
        log("Telegram sin configurar: habrá alertas en el log pero no en tu "
            "celular", "warn")
    return True


def shutdown(reason: str = ""):
    try:
        engine.stop()
        payout.stop()
        wd.stop()
        tctrl.stop()
        tg.msg_daemon_stopped(cfg, reason)
        control.write(action="none", daemon_pid=None, updated_by="daemon")
    except Exception:
        pass


# ---------------------------------------------------------------------------
def main():
    if not validate_environment():
        sys.exit(2)

    control.write(action="none", daemon_pid=os.getpid(),
                  updated_by="daemon")
    binance = make_binance(cfg.get("BINANCE_API_KEY", ""),
                           cfg.get("BINANCE_API_SECRET", ""))

    global payout, wd, tctrl
    payout = PayoutWatcher(cfg, binance, on_alert=lambda m, l: alert(m, l))
    wd = Watchdog(cfg, engine=engine, get_status_fn=get_status,
                  send_fn=lambda m, l="info": tg.send(cfg, m, l),
                  on_event=lambda m, l="info": log(m, l))
    tctrl = tg.TelegramController(cfg, get_status,
                                  on_event=lambda m, l="info": log(m, l))

    if _args.once:
        log("Modo --once: diagnóstico de una pasada", "info")
        for t in TARGETS:
            log(f"  objetivo: {t['id']:12s} url={t['url']}", "info")
        engine.start()
        time.sleep(25)
        snap = engine.snapshot()
        log(f"Snapshot: target={(snap.get('target') or {}).get('id')} "
            f"binary={snap.get('binary')}", "info")
        payout.tick()
        engine.stop()
        return

    engine.start()
    payout.start()
    wd.start()
    tctrl.start()
    tg.msg_daemon_started(cfg, get_status())
    log("Daemon agresivo en marcha (Ctrl+C o botón Detener para parar)",
        "ok")

    stop_reason = ""
    try:
        while True:
            time.sleep(5)
            store.save()
            ctrl = control.read()
            if ctrl.get("action") == "stop":
                stop_reason = "orden de parada (dashboard/Telegram)"
                break
    except KeyboardInterrupt:
        stop_reason = "Ctrl+C"
    except SystemExit:
        # SIGTERM → sys.exit(0): sin este catch el finally es el único que
        # garantiza parar xmrig (antes quedaba huérfano al 100 % CPU).
        stop_reason = "señal de terminación (SIGTERM)"
        raise
    finally:
        # finally garantiza que xmrig NUNCA quede huérfano (crash, SIGTERM,
        # Ctrl+C o parada amable): engine.stop mata al subproceso.
        shutdown(stop_reason)
    log(f"Daemon terminado ({stop_reason})", "warn")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    main()
