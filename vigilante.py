"""
vigilante.py — Salud del sistema: térmica, conexión y resumen diario
====================================================================
(Nombre elegido a propósito: se llamaba watchdog.py y eso SECUESTRABA el
paquete pip 'watchdog' que Streamlit usa internamente, rompiendo el arranque
en la nube. NUNCA nombres módulos propios igual que dependencias.)
Un hilo ligero que cada 30 s:

  • Temperatura CPU (psutil.sensors_temperatures, si está disponible):
    si supera CPU_TEMP_MAX (secrets, default 85 °C) → pausa el motor vía
    control.json (paused_thermal=True) y avisa por Telegram una sola vez;
    reanuda cuando baja 8 °C por debajo del límite.

  • Conexión a internet (mempool.space, cada ~5 min): si se cae o vuelve,
    avisa por Telegram una sola vez por transición.

  • Resumen diario a la hora configurada (DAILY_SUMMARY_HOUR, default 20h):
    hashrate medio del día, shares, objetivo actual y balances de pools.
"""
import json
import os
import threading
import time

import control
from config import BASE_DIR

WD_STATE_FILE = os.path.join(BASE_DIR, "data", "watchdog_state.json")

try:
    import psutil
except Exception:
    psutil = None


def _load_state() -> dict:
    try:
        with open(WD_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(st: dict):
    try:
        os.makedirs(os.path.dirname(WD_STATE_FILE), exist_ok=True)
        with open(WD_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f)
    except Exception:
        pass


def cpu_temperature():
    """Temperatura CPU máx legible (°C) o None si el SO no la expone."""
    if psutil is None:
        return None
    try:
        temps = psutil.sensors_temperatures()  # type: ignore[attr-defined]
    except (AttributeError, Exception):
        return None
    best = None
    for _chip, entries in (temps or {}).items():
        for e in entries:
            try:
                cur = float(e.current)
            except (TypeError, ValueError):
                continue
            if cur > 0 and (best is None or cur > best):
                best = cur
    return best


def internet_ok(timeout: float = 5.0) -> bool:
    try:
        import requests
        r = requests.get("https://mempool.space/api/blocks/tip/height",
                         timeout=timeout,
                         headers={"User-Agent": "btc-miner-studio/2.0"})
        return r.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
class Watchdog(threading.Thread):
    def __init__(self, cfg: dict, engine=None, get_status_fn=None,
                 send_fn=None, on_event=None, poll: int = 30):
        super().__init__(daemon=True, name="watchdog")
        self.cfg = cfg
        self.engine = engine            # AggressiveEngine (opcional)
        self.get_status = get_status_fn or (lambda *a, **k: {})
        self.send = send_fn or (lambda *a, **k: None)
        self.on_event = on_event or (lambda m, l="info": None)
        self.poll = max(15, int(poll))
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    # ------------------------------------------------------------------
    def run(self):
        state = _load_state()
        checks = 0
        while not self._stop.is_set():
            try:
                checks += 1
                # --- térmica ------------------------------------------
                temp = cpu_temperature()
                if temp is not None:
                    try:
                        limit = float(self.cfg.get("CPU_TEMP_MAX", 85.0))
                    except (TypeError, ValueError):
                        limit = 85.0
                    ctrl = control.read()
                    if temp >= limit and not ctrl.get("paused_thermal"):
                        control.write(paused_thermal=True,
                                      updated_by="watchdog")
                        state["thermal_events"] = \
                            state.get("thermal_events", 0) + 1
                        _save_state(state)
                        self.send(f"<b>PAUSA TÉRMICA</b> · CPU {temp:.0f}°C "
                                  f"(límite {limit:.0f}). Se reanuda sola.",
                                  "warn")
                        self.on_event(f"Watchdog: pausa térmica a "
                                      f"{temp:.0f}°C", "warn")
                    elif ctrl.get("paused_thermal") and \
                            temp <= limit - 8.0:
                        control.write(paused_thermal=False,
                                      updated_by="watchdog")
                        self.send(f"Reanudado tras enfriarse ({temp:.0f}°C)",
                                  "ok")
                        self.on_event("Watchdog: temperatura normalizada",
                                      "ok")
                # --- conexión (cada ~10 ciclos ≈ 5 min) -----------------
                if checks % 10 == 0:
                    online = internet_ok()
                    if state.get("net_online") is False and online:
                        self.send("Internet recuperado: minando de nuevo",
                                  "ok")
                    elif state.get("net_online") is True and not online:
                        self.send("<b>Internet CAÍDO</b>: el minero no "
                                  "puede enviar shares hasta que vuelva",
                                  "error")
                    state["net_online"] = online
                    _save_state(state)
                # --- resumen diario -------------------------------------
                self._daily_summary(state)
            except Exception:
                pass
            self._stop.wait(self.poll)

    # ------------------------------------------------------------------
    def _daily_summary(self, state: dict):
        try:
            hour = int(self.cfg.get("DAILY_SUMMARY_HOUR", 20) or 20)
        except (TypeError, ValueError):
            hour = 20
        now = time.localtime()
        today = time.strftime("%Y-%m-%d", now)
        if now.tm_hour == hour and state.get("last_summary") != today:
            state["last_summary"] = today
            _save_state(state)
            st = self.get_status() or {}
            tot = st.get("totals") or {}
            eng = st.get("engine") or {}
            pay = st.get("payout") or {}
            um = (pay.get("unmineable") or {})
            t = (eng.get("target") or {}).get("nombre", "—")
            self.send("\n".join([
                "<b>RESUMEN DIARIO</b>",
                f"Objetivo actual: {t}",
                f"Shares OK hoy (histórico): {tot.get('shares_ok', 0)}",
                f"Hashrate: {st.get('hashrate_txt', '—')}",
                f"Uptime: {st.get('uptime_txt', '—')}",
                f"Balance unMineable: {um.get('balance', 0):.8f} BTC",
                f"Depósitos BTC detectados: "
                f"{pay.get('binance_total_btc', 0):.8f} BTC",
            ]), "info")
