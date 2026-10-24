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

Parada amable: escribe {"action": "stop"} en data/control.json (botón
Detener del dashboard o /apagar por Telegram), o Ctrl+C. Al apagar se
cierran además los binarios huérfanos (xmrig.exe) vía miner_manager.

v3.5: al arrancar manda la PRUEBA DE GANANCIAS a Telegram (saldo del
pool + BTC/día proyectado) y la repite cada EVIDENCIA_CADA_HORAS.
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
from miner_manager import matar_mineros_huerfanos, es_admin  # noqa: E402
import probar_ganancias  # noqa: E402
import hidra_minera  # noqa: E402


def log(msg: str, level: str = "info"):
    store.append_event(msg, level)
    print(f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


# ---------------------------------------------------------------------------
store = StateStore.get()
cfg = load_secrets()


def on_stats(stats: dict):
    store.set_last_stats(stats)
    store.append_history(stats.get("hashrate", 0), stats.get("difficulty", 0),
                         stats.get("shares_ok", 0), stats.get("shares_rej", 0))


engine = AggressiveEngine(
    cfg,
    on_event=lambda m, l="info": log(m, l),
    on_share=lambda j, n, s: None,          # shares ya se cuentan vía stats
    on_stats=on_stats)


def alert(msg: str, level: str = "info"):
    log(msg, level)
    tg.send(cfg, msg, level)


def get_status(include_earnings: bool = False) -> dict:
    """Snapshot agregado para /estado de Telegram y resumen diario."""
    tot = store.totals()
    eng = engine.snapshot()
    pay = payout.snapshot_light() if include_earnings else \
        {"unmineable": {"balance": 0, "paid": 0},
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
    has_btc = bool((cfg.get("BTC_PAYOUT_ADDRESS") or "").strip())
    has_xmr = bool((cfg.get("WALLET_XMR") or "").strip())
    if not (has_btc or has_xmr):
        log("FALTAN DIRECCIONES: pon BTC_PAYOUT_ADDRESS (para cobrar en BTC "
            "vía unMineable) o WALLET_XMR (MoneroOcean/SupportXMR) en "
            ".streamlit/secrets.toml", "error")
        tg.send(cfg, "<b>No puedo arrancar</b>: falta BTC_PAYOUT_ADDRESS o "
                     "WALLET_XMR en secrets.", "error")
        return False
    if not tg.configured(cfg):
        log("Telegram sin configurar: habrá alertas en el log pero no en tu "
            "celular", "warn")
    # v3.6: sin administrador, xmrig no aplica el mod MSR y el hashrate se
    # queda a menos de la mitad (sobre todo en AMD Ryzen).
    if os.name == "nt" and not es_admin():
        log("SIN PERMISOS DE ADMINISTRADOR: el mod MSR no se aplicará y el "
            "hashrate será menor. Cierra el bot (DETENER_TODO.bat) y corre "
            "CORRER_BOT.bat aceptando la ventanita de Windows.", "warn")
        tg.send(cfg, "<b>Hashrate limitado</b>: el bot NO está corriendo "
                     "como ADMINISTRADOR, así que xmrig no puede aplicar el "
                     "mod MSR y minarás a menos de la mitad de tu "
                     "potencial. Cierra con DETENER_TODO.bat y vuelve a "
                     "abrir CORRER_BOT.bat aceptando la ventanita de "
                     "Windows (UAC).", "warn")
    # v3.7: ¿xmrig.exe desapareció (Defender)? la HIDRA lo repara antes
    # de empezar; si ni reparando hay binario, avisa con instrucciones.
    if not hidra_minera.binario_vivo(cfg):
        log("xmrig no está: LA HIDRA (CABEZA MÉDICO) intenta restaurar de "
            "cuarentena o re-descargar…", "warn")
        ruta = hidra_minera.medico_binario(cfg, on_event=lambda m, l="info":
                                           log(m, l))
        if ruta:
            log(f"Binario recuperado: {ruta}", "ok")
        else:
            tg.send(cfg, "<b>Sin minero</b>: xmrig.exe fue borrado por el "
                         "antivirus y no pude recuperarlo. Ejecuta "
                         "defender_fix.ps1 como administrador y vuelve a "
                         "abrir CORRER_BOT.bat.", "error")
    return True


def shutdown(reason: str = ""):
    try:
        engine.stop()
        payout.stop()
        wd.stop()
        tctrl.stop()
        hidra.stop()
        matar_mineros_huerfanos()   # cierra xmrig.exe/cpuminer huérfanos
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

    global payout, wd, tctrl, hidra
    payout = PayoutWatcher(cfg, binance, on_alert=lambda m, l: alert(m, l))
    wd = Watchdog(cfg, engine=engine, get_status_fn=get_status,
                  send_fn=lambda m, l="info": tg.send(cfg, m, l),
                  on_event=lambda m, l="info": log(m, l))
    # v3.7 LA HIDRA: las 5 cabezas comparten el canal de eventos del daemon
    hidra = hidra_minera.init_hidra(
        cfg,
        on_event=lambda m, l="info": log(m, l),
        get_hashrate=lambda: (store.last() or {}).get("hashrate", 0) or 0,
        get_running=lambda: engine.is_running(),
        on_reparar=lambda motivo: (log(motivo, "warn"),
                                   tg.send(cfg, f"🛠 <b>HIDRA</b>: {motivo}",
                                           "warn"),
                                   engine.relanzar(motivo)))
    tctrl = tg.TelegramController(cfg, get_status,
                                  on_event=lambda m, l="info": log(m, l),
                                  hidra_fn=lambda: hidra.snapshot())

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
    hidra.start()      # CABEZA VIGÍA vigilando el hashrate 24/7
    tg.msg_daemon_started(cfg, get_status())
    # v3.5: PRUEBA DE GANANCIAS inmediata — en tu Telegram verás el saldo
    # del pool, el % del umbral y cuánto BTC/día puedes ganar.
    try:
        probar_ganancias.enviar_prueba(cfg, motivo="arranque")
        log("Prueba de ganancias enviada a Telegram (/ganancias para "
            "repetirla cuando quieras)", "ok")
    except Exception as e:                              # noqa: BLE001
        log(f"Prueba de ganancias no enviada: {e}", "warn")
    log("Daemon agresivo en marcha (Ctrl+C o botón Detener para parar)",
        "ok")

    horas = 0.0
    try:
        horas = float(cfg.get("EVIDENCIA_CADA_HORAS") or 0)
    except (TypeError, ValueError):
        horas = 0.0
    next_ev = time.time() + horas * 3600 if horas > 0 else 0.0

    stop_reason = ""
    try:
        while True:
            time.sleep(5)
            store.save()
            ctrl = control.read()
            if ctrl.get("action") == "stop":
                stop_reason = "orden de parada (dashboard/Telegram)"
                break
            if next_ev and time.time() >= next_ev:
                try:
                    probar_ganancias.enviar_prueba(cfg, motivo="periodica")
                    log("Evidencia periódica de ganancias enviada a "
                        "Telegram", "info")
                except Exception:                       # noqa: BLE001
                    pass
                next_ev = time.time() + horas * 3600
    except KeyboardInterrupt:
        stop_reason = "Ctrl+C"
    shutdown(stop_reason)
    log(f"Daemon terminado ({stop_reason})", "warn")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    main()
