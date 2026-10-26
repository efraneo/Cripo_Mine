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


# ---------------------------------------------------------------------------
# v3.6: traducción de mensajes conocidos de XMRig a CONSEJOS ACCIONABLES.
# En vez de mostrar el log seco ("FAILED TO APPLY MSR MOD"), el daemon
# explica en consola y Telegram qué hacer exactamente. Cada aviso se emite
# UNA sola vez por corrida del minero (no spamear).
# ---------------------------------------------------------------------------
AVISO_MSR = (
    "MSR MOD NO APLICADO → estás minando a MENOS DE LA MITAD de tu "
    "potencial (en AMD Ryzen esto casi DUPLICA el hashrate; en Intel suma "
    "15-40%). SOLUCIÓN (1 minuto): cierra todo con DETENER_TODO.bat y "
    "vuelve a abrir CORRER_BOT.bat — ahora pide permisos de ADMINISTRADOR "
    "solo: acepta la ventanita de Windows (UAC). Si aun así reaparece, "
    "agrega en Windows Defender una exclusión para la carpeta "
    "bin\\xmrig-mo (el antivirus bloquea el driver que usa xmrig).")
AVISO_HUGEPAGES = (
    "HUGE PAGES incompletas → hashrate reducido ~10-30%. SOLUCIÓN: corre "
    "el bot como ADMINISTRADOR (CORRER_BOT.bat ya lo pide al inicio). "
    "Si tras aceptar la ventanita sigue incompleto, reinicia Windows una "
    "vez: eso desfragmenta la memoria reservada y xmrig completa las "
    "páginas.")
AVISO_CONEXION = (
    "Error de conexión con el pool: no toques nada, el motor repite solo "
    "y si el pool sigue mal el FAILOVER cambia de pool automáticamente.")
AVISO_BLOQUEO = (
    "xmrig murió INMEDIATAMENTE tras arrancar → patrón típico de "
    "ANTIVIRUS (Defender lo cuarentena aunque excluyas la carpeta: falta "
    "la exclusión de PROCESO y del .exe exacto). La HIDRA ya está "
    "reparándolo sola (ESCUDO + MÉDICO: exclusiones correctas, restaurar "
    "de cuarentena y re-descargar si hace falta). Si tu antivirus NO es "
    "Defender, agrega la exclusión de la carpeta bin\\xmrig-mo en su "
    "panel, o ejecuta defender_fix.ps1 como administrador.")


def es_admin() -> bool:
    """True si el proceso corre con permisos de administrador.
    En no-Windows devuelve True (el aviso de MSR no aplica igual)."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def write_xmrig_config(pool_url: str, user: str, password: str,
                       threads: int, path: str = XMRIG_CONFIG_FILE,
                       optima: dict | None = None) -> str:
    """Genera un config.json válido para XMRig (docs: xmrig.com/docs/miner
    /config/pool). v3.8: TLS automático si la url es stratum+ssl://.
    `optima` (CABEZA FUEGO de la HIDRA) fusiona ajustes agresivos: huge-
    pages, huge-pages-jit, memory-pool, prioridad, randomx mode/wrmsr."""
    usa_tls = "ssl" in (pool_url or "").split("://")[0]
    n_threads = max(1, int(threads))
    # Config base agresiva: huge-pages, jit, memory-pool y prioridad alta
    # ya en el base — no depender de que optima llegue para activarlos.
    cpu = {
        "enabled": True,
        "hw-aes": None,
        "priority": 3,
        "max-threads-hint": 100,   # 100% = todos los núcleos lógicos
        "huge-pages": True,
        "huge-pages-jit": True,
        "memory-pool": True,
        "yield": True,
        "asm": True,
    }
    rx = {
        "init": -1,
        # v4.1: AUTO (xmrig elige fast/light según la caché L3 REAL de la
        # CPU; forzar fast con poca L3 baja el hashrate)
        "mode": "auto",
        # v4.1.1: 1GB pages ON — si falta el privilegio "Lock pages in
        # memory", xmrig avisa y cae a 2MB huge pages (sin riesgo)
        "1gb-pages": True,
        "rdmsr": True,
        "wrmsr": True,
        "numa": True,
    }
    cfg = {
        "autosave": False,        # no sobreescribir con defaults de xmrig
        "donate-level": 0,        # v4.1.1: 0% donación → +1% minado real
        "cpu": cpu,
        "randomx": rx,
        "pools": [{
            "url": pool_url,
            "user": user,
            "pass": password or "x",
            "rig-id": None,
            "nicehash": False,
            "tls": usa_tls,
            "keepalive": True,
            "enabled": True,
        }],
        "print-time": 10,
        "health-print-time": 60,
        "http": {"enabled": True, "host": "127.0.0.1", "port": 4068,
                 "access-token": None, "restricted": True},
    }
    if optima:
        try:
            cpu_opt = dict(optima.get("cpu") or {})
            # max-threads-hint del control manual manda sobre FUEGO
            cpu_opt["max-threads-hint"] = 100
            cfg["cpu"].update(cpu_opt)
            rx_opt = optima.get("randomx") or {}
            if rx_opt:
                cfg["randomx"].update(rx_opt)
        except Exception:
            pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        import json
        json.dump(cfg, f, indent=2)
    return path


class ExternalMiner:
    """Controla un minero externo y traduce su log a métricas del dashboard."""

    MODE = "external"

    def __init__(self, binary_path: str, extra_args: str = "",
                 pool_url: str = "", user: str = "", password: str = "x",
                 threads: int = 2, on_event=None, on_share=None, on_stats=None,
                 optima: dict | None = None):
        self.binary_path = binary_path
        self.extra_args = extra_args or ""
        self.optima = optima or None       # HIDRA · CABEZA FUEGO
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
        self._arranque_ts = 0.0
        self._reader = None
        # métricas
        self.hashrate = 0.0
        self.shares_ok = 0
        self.shares_rej = 0
        self.difficulty = 0.0
        self.last_line = ""
        # regex estilo XMRig:
        #   SHA-256/otros:  "speed 10s/60s/15m: 12.3 kH/s ..."
        #   RandomX:        "speed 10s/60s/15m: 1234.5 1200.0 1180.0 H/s max: ..."
        # Captura el primer número (vel. 10s) y el prefijo de escala OPCIONAL
        # (RandomX reporta H/s directo sin k/M/G).
        self._re_speed = re.compile(
            r"speed\s+10s/60s/15m[:\s]+([\d.]+)(?:\s+[\d.]+)*\s*([kKmMgG]?)H/?s",
            re.IGNORECASE)
        # regex estilo cpuminer/xmrig shares:  accepted: 12/34 (100%)  /  (1/1)
        self._re_shares = re.compile(r"\((\d+)/(\d+)\)")
        self._re_acc = re.compile(r"accepted", re.IGNORECASE)
        self._re_rej = re.compile(r"rejected", re.IGNORECASE)
        self._re_diff = re.compile(r"difficulty[:\s]+([\d.]+)", re.IGNORECASE)
        self._re_hps = re.compile(r"([\d.]+)\s*([kKmMgG]?)H/s", re.IGNORECASE)
        self._re_huge = re.compile(r"huge pages\s+(\d+)%/100%",
                                   re.IGNORECASE)
        self._avisos_dados: set = set()      # v3.6: cada consejo 1 sola vez

    # ------------------------------------------------------------------
    def _build_command(self) -> list:
        name = os.path.basename(self.binary_path).lower()
        cmd = [self.binary_path]
        if "xmrig" in name:
            cfg = write_xmrig_config(self.pool_url, self.user, self.password,
                                     self.threads, optima=self.optima)
            cmd += ["-c", cfg]
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
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, cwd=DATA_DIR,
                errors="replace")
        except OSError:
            # v3.7: WinError 5 / acceso denegado = antivirus bloqueando
            self.on_event(AVISO_BLOQUEO, "error")
            raise
        self._started_at = time.time()
        self._arranque_ts = time.time()
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
            # v3.7: ¿murió NADA MÁS arrancar? → bloqueo de antivirus
            vivo_seg = time.time() - self._arranque_ts if \
                self._arranque_ts else 999
            if vivo_seg < 15:
                self.on_event(AVISO_BLOQUEO, "error")
                self.on_event(f"El minero externo terminó a los "
                              f"{vivo_seg:.1f}s de arrancar", "error")
            else:
                self.on_event("El minero externo terminó inesperadamente",
                              "error")
            self._stop.set()

    def _avisos_conocidos(self, line: str) -> list:
        """(clave, nivel, consejo) para mensajes conocidos de xmrig."""
        low = line.lower()
        out = []
        if "failed to apply msr mod" in low:
            out.append(("msr", "warn", AVISO_MSR))
        if (self._re_huge.search(line) and
                int(self._re_huge.search(line).group(1)) < 100) or \
                "huge pages unavailable" in low:
            out.append(("huge", "warn", AVISO_HUGEPAGES))
        if "connection error" in low or "connect error" in low:
            out.append(("conn", "warn", AVISO_CONEXION))
        return out

    def _parse_line(self, line: str):
        low = line.lower()
        m = self._re_speed.search(line)
        if m:
            val = float(m.group(1))
            unit = (m.group(2) or "").lower()
            mult = {"k": 1e3, "m": 1e6, "g": 1e9}.get(unit, 1.0)
            self.hashrate = val * mult
            return
        # Fallback para mineros que no usan "speed 10s/60s/15m:" pero sí
        # "XXX H/s". Solo aplica si la línea menciona "speed" explícitamente
        # (evita capturar números de líneas de diagnóstico como huge pages,
        # MSR, memoria, etc. que también contienen H/s).
        m = self._re_hps.search(line)
        if m and "speed" in low:
            val = float(m.group(1))
            unit = (m.group(2) or "").lower()
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
        # v3.6: primero los consejos accionables (cada uno 1 sola vez)
        avisos = self._avisos_conocidos(line)
        for key, nivel, consejo in avisos:
            if key not in self._avisos_dados:
                self._avisos_dados.add(key)
                self.on_event(consejo, nivel)
        # El resto de errores sigue al log genérico (sin duplicar los ya
        # traducidos a consejo)
        if not avisos and ("error" in low or "failed" in low):
            self.on_event("LOG: " + line[:200], "error")

    def _poll_xmrig_api(self) -> dict | None:
        """Consulta la API HTTP de XMRig (puerto 4068) para obtener
        hashrate y dificultad directamente, sin depender del log.
        Devuelve un dict con 'hashrate' y 'difficulty', o None si falla."""
        try:
            import urllib.request
            url = "http://127.0.0.1:4068/2/summary"
            with urllib.request.urlopen(url, timeout=2) as r:
                import json as _json
                data = _json.loads(r.read())
            # XMRig API v2: {"hashrate":{"total":[10s, 60s, 15m, max]}, ...}
            hr_total = (data.get("hashrate") or {}).get("total") or []
            hr = float(hr_total[0] or 0) if hr_total else 0.0
            # dificultad de la conexión actual
            conn = (data.get("connection") or {})
            diff = float(conn.get("diff") or 0)
            return {"hashrate": hr, "difficulty": diff}
        except Exception:
            return None

    def _stats_loop(self, interval: float = 3.0):
        while not self._stop.is_set():
            time.sleep(interval)
            if self._stop.is_set():
                break
            # v3.9: intentar API HTTP de XMRig primero (más fiable que regex)
            api = self._poll_xmrig_api()
            if api and api["hashrate"] > 0:
                self.hashrate = api["hashrate"]
                if api["difficulty"] > 0:
                    self.difficulty = api["difficulty"]
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


# ---------------------------------------------------------------------------
# Apagado de emergencia: matar binarios de minado huérfanos
# ---------------------------------------------------------------------------
def matar_mineros_huerfanos(nombres=("xmrig", "cpuminer", "minerd")) -> int:
    """Termina cualquier binario de minado vivo en el sistema (xmrig.exe
    lanzado a mano, procesos huérfanos tras un cierre brusco, etc.).

    Lo usan: el apagado del daemon (/apagar por Telegram o botón Detener)
    y DETENER_TODO.bat. Devuelve el nº de procesos terminados (mejor
    esfuerzo). Nunca explota.
    """
    matados = 0
    if HAS_PSUTIL:
        objetivos = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                nom = (p.info.get("name") or "").lower()
                if nom and any(n in nom for n in nombres):
                    objetivos.append(p)
            except Exception:
                continue
        for p in objetivos:
            try:
                p.terminate()
                matados += 1
            except Exception:
                continue
        try:
            _, vivos = psutil.wait_procs(objetivos, timeout=3)
            for p in vivos:
                try:
                    p.kill()
                except Exception:
                    pass
        except Exception:
            pass
        return matados
    # Fallback sin psutil (Windows: taskkill admite comodín en /FI)
    try:
        if os.name == "nt":
            for n in nombres:
                rc = subprocess.run(
                    ["taskkill", "/F", "/FI", f"IMAGENAME eq {n}*.exe"],
                    capture_output=True, timeout=10)
                if rc.returncode == 0:
                    matados += 1
        else:
            rc = subprocess.run(["pkill", "-f", "|".join(nombres)],
                                capture_output=True, timeout=10)
            if rc.returncode == 0:
                matados += 1
    except Exception:
        pass
    return matados
