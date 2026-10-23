"""
state_store.py — Almacén de estado, métricas y eventos del minero
=================================================================
Guarda en memoria (hilos seguros) y en disco (JSON) el histórico de hashrate,
shares y eventos para que el dashboard muestre datos incluso tras un reinicio.
"""
import json
import os
import threading
import time
from collections import deque

from config import METRICS_FILE

HISTORY_MAX = 2880      # ~2.4 h con muestreo cada 3 s
EVENTS_MAX = 400
SHARES_MAX = 300
SAVE_EVERY = 10.0       # segundos entre guardados a disco


class StateStore:
    """Singleton con locks para uso concurrente (minero + Streamlit)."""

    _instance = None
    _lock_cls = threading.Lock()

    @classmethod
    def get(cls) -> "StateStore":
        if cls._instance is None:
            with cls._lock_cls:
                if cls._instance is None:
                    cls._instance = StateStore()
        return cls._instance

    def __init__(self):
        self.lock = threading.Lock()
        self.history = deque(maxlen=HISTORY_MAX)   # {ts, hashrate, diff, ok, rej}
        self.events = deque(maxlen=EVENTS_MAX)     # {ts, level, msg}
        self.shares = deque(maxlen=SHARES_MAX)     # {ts, job, nonce, status}
        self.counters = {
            "shares_ok": 0,
            "shares_rej": 0,
            "hashes_total": 0,
            "blocks_found": 0,
            "started_at": None,
        }
        self.last_stats = {}          # última dict de stats del minero
        self._dirty = False
        self._last_save = 0.0
        self.load()

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------
    def append_history(self, hashrate: float, diff: float = 0.0,
                       ok: int = 0, rej: int = 0):
        with self.lock:
            self.history.append({
                "ts": time.time(),
                "hashrate": float(hashrate or 0.0),
                "diff": float(diff or 0.0),
                "ok": int(ok),
                "rej": int(rej),
            })
            self._dirty = True

    def append_event(self, msg: str, level: str = "info"):
        with self.lock:
            self.events.append({
                "ts": time.time(),
                "level": level,
                "msg": str(msg)[:400],
            })
            self._dirty = True

    def append_share(self, job_id: str, nonce: str, status: str):
        with self.lock:
            self.shares.append({
                "ts": time.time(),
                "job": str(job_id)[:40],
                "nonce": str(nonce)[:16],
                "status": status,
            })
            if status == "aceptado":
                self.counters["shares_ok"] += 1
            elif status.startswith("rechaz"):
                self.counters["shares_rej"] += 1
            elif status == "bloque":
                self.counters["blocks_found"] += 1
            self._dirty = True

    def set_last_stats(self, stats: dict):
        with self.lock:
            self.last_stats = dict(stats or {})
            if stats and stats.get("hashrate"):
                self.counters["hashes_total"] += int(stats.get("hashes_delta", 0))

    def mark_started(self):
        with self.lock:
            if not self.counters.get("started_at"):
                self.counters["started_at"] = time.time()

    def clear(self):
        with self.lock:
            self.history.clear()
            self.events.clear()
            self.shares.clear()
            self.counters = {"shares_ok": 0, "shares_rej": 0, "hashes_total": 0,
                             "blocks_found": 0, "started_at": None}
            self._dirty = True
        # save() fuera del lock: threading.Lock NO es reentrante (evita deadlock)
        self.save(force=True)

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------
    def history_df(self, n: int = 240):
        import pandas as pd
        with self.lock:
            pts = list(self.history)[-n:]
        if not pts:
            return pd.DataFrame(columns=["ts", "hashrate", "diff", "ok", "rej"])
        df = pd.DataFrame(pts)
        df["dt"] = df["ts"].apply(
            lambda t: time.strftime("%H:%M:%S", time.localtime(t)))
        return df

    def events_list(self, n: int = 120):
        with self.lock:
            return list(self.events)[-n:]

    def shares_list(self, n: int = 120):
        with self.lock:
            return list(self.shares)[-n:]

    def totals(self):
        with self.lock:
            st = dict(self.counters)
            if st.get("started_at"):
                st["uptime"] = time.time() - st["started_at"]
            else:
                st["uptime"] = 0.0
            return st

    def last(self):
        with self.lock:
            return dict(self.last_stats)

    # ------------------------------------------------------------------
    # Persistencia JSON (best-effort)
    # ------------------------------------------------------------------
    def save(self, force: bool = False):
        with self.lock:
            now = time.time()
            if not force and (not self._dirty or now - self._last_save < SAVE_EVERY):
                return
            payload = {
                "history": list(self.history)[-720:],
                "events": list(self.events)[-200:],
                "shares": list(self.shares)[-150:],
                "counters": self.counters,
            }
            self._dirty = False
            self._last_save = now
        try:
            tmp = METRICS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, METRICS_FILE)
        except Exception:
            pass  # nunca romper la app por IO

    def load(self):
        try:
            if not os.path.exists(METRICS_FILE):
                return
            with open(METRICS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self.lock:
                for h in data.get("history", [])[-HISTORY_MAX:]:
                    self.history.append(h)
                for e in data.get("events", [])[-EVENTS_MAX:]:
                    self.events.append(e)
                for s in data.get("shares", [])[-SHARES_MAX:]:
                    self.shares.append(s)
                c = data.get("counters", {})
                self.counters["shares_ok"] = int(c.get("shares_ok", 0))
                self.counters["shares_rej"] = int(c.get("shares_rej", 0))
                self.counters["hashes_total"] = int(c.get("hashes_total", 0))
                self.counters["blocks_found"] = int(c.get("blocks_found", 0))
                # uptime se reinicia: el minero arranca parado en cada sesión
                self.counters["started_at"] = None
        except Exception:
            pass
