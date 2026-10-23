"""
miner_manager.py — Gestor de minero binario externo (XMRig / cpuminer-opt…)
===========================================================================
Lanza un binario de minado real como subproceso, lee su salida en vivo y
extrae hashrate / shares aceptados / rechazados con expresiones regulares
compatibles con los formatos de log de XMRig y cpuminer.

Interfaz:  .start()  .stop()  .is_running()  .stats()
Callbacks: on_event(msg, level), on_share(job, nonce, status), on_stats(dict)
Descarga segura de XMRig: https://github.com/xmrig/xmrig/releases
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time

from config import DATA_DIR

try:
    import psutil
    HAS_PSUTIL = True
except Exception:
    HAS_PSUTIL = False


XMRIG_CONFIG_FILE = os.path.join(DATA_DIR, "xmrig_config.json")


def write_xmrig_config(pool_url: str, user: str, password: str,
                       threads: int, path: str = XMRIG_CONFIG_FILE) -> str:
    """Genera un config.json mínimo y válido para XMRig (docs: xmrig.com/docs/miner/config/pool)."""
    # Preserva la caché de calibración del fork MoneroOcean (algo-perf):
    # sin ella, CADA arranque re-mide ~13 algoritmos (~4-9 min) y durante
    # esa calibración ni siquiera ata el puerto HTTP de la API 4068.
    prev_perf = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            prev_perf = json.load(f).get("algo-perf")
    except Exception:
        prev_perf = None
    cfg = {
        "autosave": True,
        # OJO: max-threads-hint es un PORCENTAJE (0-100) de hilos, no un
        # conteo — poner 2 limitaba el minero al 2 % de la CPU (¡1 hilo!).
        # El conteo exacto se pasa con -t en _build_command.
        "cpu": {"enabled": True, "hw-aes": None, "priority": None,
                "max-threads-hint": 100, "memory-pool": False},
        "pools": [{
            "url": pool_url,
            "user": user,
            "pass": password or "x",
            "rig-id": None,
            "nicehash": False,
            "tls": False,
            "keepalive": True,
        }],
        "print-time": 5,
        "http": {"enabled": True, "host": "127.0.0.1", "port": 4068,
                 "access-token": None, "restricted": True},
    }
    if prev_perf:
        cfg["algo-perf"] = prev_perf
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return path


class ExternalMiner:
    """Controla un minero externo y traduce su log a métricas del dashboard."""

    MODE = "external"

    def __init__(self, binary_path: str, extra_args: str = "",
                 pool_url: str = "", user: str = "", password: str = "x",
                 threads: int = 2, on_event=None, on_share=None, on_stats=None):
        self.binary_path = binary_path
        self.extra_args = extra_args or ""
        self.pool_url = pool_url
        self.user = user
        self.password = password or "x"
        self.threads = max(1, int(threads))
        self.on_event = on_event or (lambda m, l="info": None)
        self.on_share = on_share or (lambda j, n, s: None)
        self.on_stats = on_stats or (lambda s: None)
        self.proc = None
        self._stop = threading.Event()
        self._started_at = None
        self._reader = None
        # métricas
        self.hashrate = 0.0
        self.shares_ok = 0
        self.shares_rej = 0
        self.difficulty = 0.0
        self.last_line = ""
        # regex estilo XMRig:  speed 10s/60s/15m: 12.3 kH/s ...
        self._re_speed = re.compile(
            r"speed\s+10s/60s/15m[:\s]+([\d.]+)\s*([kKmMgG])H?/?s",
            re.IGNORECASE)
        # regex estilo cpuminer/xmrig shares:  accepted: 12/34 (100%)  /  (1/1)
        self._re_shares = re.compile(r"\((\d+)/(\d+)\)")
        self._re_acc = re.compile(r"accepted", re.IGNORECASE)
        self._re_rej = re.compile(r"rejected", re.IGNORECASE)
        self._re_diff = re.compile(r"difficulty[:\s]+([\d.]+)", re.IGNORECASE)
        self._re_hps = re.compile(r"([\d.]+)\s*([kKmMgG]?)H/s", re.IGNORECASE)

    # ------------------------------------------------------------------
    def _build_command(self) -> list:
        name = os.path.basename(self.binary_path).lower()
        cmd = [self.binary_path]
        if "xmrig" in name:
            cfg = write_xmrig_config(self.pool_url, self.user, self.password,
                                     self.threads)
            # -t fija el nº real de hilos (max-threads-hint es % y no basta).
            # El http lo da la sección "http" del config (así funcionó en la
            # sesión de 1 h); --http-port en CLI rompía el bind en este fork.
            cmd += ["-c", cfg, "-t", str(self.threads)]
        else:
            # convención cpuminer-opt / minerd
            url = self.pool_url.replace("stratum+tcp://", "").replace(
                "stratum+ssl://", "ssl://")
            cmd += ["-o", url, "-u", self.user or "wallet.worker",
                    "-p", self.password or "x", "-t", str(self.threads)]
        if self.extra_args:
            cmd += self.extra_args.split()
        return cmd

    def start(self):
        if self.is_running():
            self.on_event("El minero externo ya está en ejecución", "warn")
            return
        if not self.binary_path or not os.path.exists(self.binary_path):
            self.on_event(f"No encuentro el binario: {self.binary_path}. "
                          f"Descárgalo (ej: github.com/xmrig/xmrig/releases) y "
                          f"pon la ruta en EXTERNAL_MINER_PATH", "error")
            raise FileNotFoundError(self.binary_path)
        cmd = self._build_command()
        self.on_event("Lanzando: " + " ".join(cmd), "info")
        self._stop.clear()
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, cwd=DATA_DIR,
            errors="replace")
        self._started_at = time.time()
        self._reader = threading.Thread(target=self._read_loop, daemon=True,
                                        name="ext-reader")
        self._reader.start()
        self.on_event(f"Minero externo iniciado (PID {self.proc.pid})", "ok")
        t = threading.Thread(target=self._stats_loop, daemon=True)
        t.start()

    def stop(self):
        self._stop.set()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                self.on_event("Minero externo detenido", "warn")
            except Exception as e:
                self.on_event(f"Error al detener: {e}", "error")
        self.proc = None
        self._started_at = None

    def is_running(self) -> bool:
        return (self.proc is not None and self.proc.poll() is None
                and not self._stop.is_set())

    # ------------------------------------------------------------------
    def _read_loop(self):
        try:
            for line in self.proc.stdout:      # type: ignore[union-attr]
                if self._stop.is_set():
                    break
                line = line.strip()
                if not line:
                    continue
                self.last_line = line[:300]
                self._parse_line(line)
        except Exception:
            pass
        if not self._stop.is_set():
            self.on_event("El minero externo terminó inesperadamente", "error")
            self._stop.set()

    def _parse_line(self, line: str):
        low = line.lower()
        m = self._re_speed.search(line)
        if m:
            val, unit = float(m.group(1)), m.group(2).lower()
            mult = {"k": 1e3, "m": 1e6, "g": 1e9}.get(unit, 1.0)
            self.hashrate = val * mult
            return
        m = self._re_hps.search(line)
        if m and ("speed" in low or "h/s" in low):
            val, unit = float(m.group(1)), (m.group(2) or "").lower()
            mult = {"k": 1e3, "m": 1e6, "g": 1e9}.get(unit, 1.0)
            self.hashrate = val * mult
        if self._re_acc.search(low):
            mm = self._re_shares.search(line)
            ok, total = (int(mm.group(1)), int(mm.group(2))) if mm else \
                (self.shares_ok + 1, None)
            if total is not None:
                self.shares_ok, self.shares_rej = ok, max(total - ok, 0)
            else:
                self.shares_ok = ok
            self.on_share("ext", "-", "aceptado")
            self.on_event(f"Share aceptado ({self.shares_ok}/"
                          f"{self.shares_ok + self.shares_rej})", "ok")
        elif self._re_rej.search(low):
            mm = self._re_shares.search(line)
            if mm:
                self.shares_rej = max(int(mm.group(2)) - int(mm.group(1)), 0)
            self.on_share("ext", "-", "rechazado")
            self.on_event("Share rechazado por el pool", "warn")
        m = self._re_diff.search(line)
        if m:
            try:
                self.difficulty = float(m.group(1))
            except ValueError:
                pass
        if "error" in low or "failed" in low:
            self.on_event("LOG: " + line[:200], "error")

    def _stats_loop(self, interval: float = 3.0):
        while not self._stop.is_set():
            time.sleep(interval)
            if self._stop.is_set():
                break
            cpu_pct = None
            if HAS_PSUTIL and self.proc:
                try:
                    p = psutil.Process(self.proc.pid)
                    cpu_pct = p.cpu_percent(interval=0.2)
                except Exception:
                    pass
            self.on_stats({
                "mode": self.MODE,
                "hashrate": self.hashrate,
                "hashes_delta": int(self.hashrate * interval),
                "difficulty": self.difficulty,
                "shares_ok": self.shares_ok,
                "shares_rej": self.shares_rej,
                "uptime": (time.time() - self._started_at) if self._started_at else 0,
                "alive": self.is_running(),
                "cpu_pct": cpu_pct,
                "last_line": self.last_line,
            })

    # ------------------------------------------------------------------
    @staticmethod
    def detect_common_paths() -> list:
        """Rutas típicas donde suele vivir xmrig/cpuminer (útil como sugerencia)."""
        cands = ["/usr/bin/xmrig", "/usr/local/bin/xmrig", "./xmrig",
                 "C:\\miners\\xmrig.exe", "C:\\miners\\xmrig\\xmrig.exe",
                 "/usr/bin/cpuminer", "/usr/local/bin/cpuminer",
                 "C:\\miners\\cpuminer\\cpuminer.exe"]
        out = []
        for c in cands:
            if os.path.exists(c):
                out.append(c)
        if shutil.which("xmrig"):
            out.append(shutil.which("xmrig"))
        return out
