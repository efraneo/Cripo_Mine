"""
control.py — Canal de control compartido (dashboard ↔ daemon ↔ Telegram)
=========================================================================
El motor agresivo corre como DAEMON independiente (`run_miner.py`) para que
la minería siga aunque cierres Streamlit o tu navegador. Este módulo define
el "mando a distancia" por archivo (data/control.json) que los tres actores
comparten:

  • app.py (Streamlit)   → botones Iniciar/Detener/Pausar el daemon
  • run_miner.py         → lee órdenes cada pocos segundos
  • telegram_bot.py      → comandos remotos (/pausar /reanudar /cambiar)

Claves del archivo:
  daemon_pid      → PID del daemon en ejecución (None si parado)
  action          → "none" | "start" | "stop"
  paused_manual   → pausa manual (botón o /pausar)
  paused_thermal  → pausa por temperatura (watchdog)
  force_target    → "" | "next" | id de objetivo del motor agresivo
  threads         → hilos CPU solicitados (None = usar secrets)
  updated_by      → quién hizo el último cambio (app/telegram/watchdog)
"""
import json
import os
import subprocess
import sys
import threading
import time

from config import BASE_DIR, DATA_DIR, LOG_DIR

CONTROL_FILE = os.path.join(DATA_DIR, "control.json")
_LOCK = threading.Lock()

try:
    import psutil
except Exception:
    psutil = None


# ---------------------------------------------------------------------------
# Lock ENTRE PROCESOS: el threading.Lock solo protege dentro de un proceso,
# pero control.json lo escriben Streamlit (botones), el daemon y la
# supervisora a la vez → se pisaban updates (una pausa térmica podía borrarse).
class _FileLock:
    """Lock de archivo con timeout. En Windows usa msvcrt, en POSIX fcntl.
    Si el lock no se consigue en `timeout`, se procede igual (mejor un write
    tardío que bloquear el daemon)."""

    def __init__(self, path: str, timeout: float = 3.0):
        self.path = path
        self.timeout = timeout
        self._fd = None

    def __enter__(self):
        deadline = time.time() + self.timeout
        try:
            self._fd = os.open(self.path + ".lock",
                               os.O_CREAT | os.O_RDWR, 0o666)
        except OSError:
            return self
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.time() >= deadline:
                    return self        # sin lock: escribimos igual (best-effort)
                time.sleep(0.05)

    def __exit__(self, *exc):
        if self._fd is not None:
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(self._fd, 0, os.SEEK_SET)
                    msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        return False


# ---------------------------------------------------------------------------
def read() -> dict:
    """Lee el estado de control (nunca explota si falta o está corrupto)."""
    base = {
        "daemon_pid": None, "action": "none", "action_ts": 0.0,
        "paused_manual": False, "paused_thermal": False,
        "force_target": "", "threads": None, "updated_by": "",
    }
    try:
        with open(CONTROL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            base.update({k: v for k, v in data.items() if k in base})
    except Exception:
        pass
    return base


def write(**kwargs) -> dict:
    """Fusiona cambios en control.json de forma atómica y thread-safe
    (tanto entre hilos como ENTRE procesos: Streamlit + daemon + supervisora)."""
    with _LOCK:
        with _FileLock(CONTROL_FILE):
            state = read()
            state.update(kwargs)
            state["action_ts"] = time.time()
            tmp = CONTROL_FILE + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2)
                os.replace(tmp, CONTROL_FILE)
            except Exception:
                pass
            return state


# ---------------------------------------------------------------------------
def is_pid_alive(pid) -> bool:
    """Comprueba si un PID vive (multiplataforma, sin explotar)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if psutil is not None:
        return psutil.pid_exists(pid)
    # Fallback sin psutil: señal 0 = "¿existe?"
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def daemon_alive() -> bool:
    return is_pid_alive(read().get("daemon_pid"))


def daemon_pid():
    return read().get("daemon_pid")


# ---------------------------------------------------------------------------
def start_daemon(mode: str = "aggressive"):
    """Arranca run_miner.py como proceso DESACOPLADO de Streamlit.

    En Windows usa DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP; en Linux/macOS
    start_new_session=True. La salida va a logs/daemon.log.
    """
    if daemon_alive():
        return daemon_pid()
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "daemon.log")
    logf = open(log_path, "ab")
    cmd = [sys.executable, "-u", os.path.join(BASE_DIR, "run_miner.py"),
           "--mode", mode]
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP |
                                   subprocess.DETACHED_PROCESS)
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(cmd, cwd=BASE_DIR, stdout=logf,
                                stderr=subprocess.STDOUT, **kwargs)
    except Exception:
        logf.close()
        raise
    write(daemon_pid=proc.pid, action="none", paused_manual=False,
          paused_thermal=False, force_target="", updated_by="app")
    return proc.pid


def stop_daemon(timeout: float = 15.0) -> bool:
    """Pide parada amable; si no obedece, termina el proceso a la fuerza."""
    pid = daemon_pid()
    if pid is None:
        write(action="none", daemon_pid=None, updated_by="app")
        return True
    write(action="stop", updated_by="app")
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not is_pid_alive(pid):
            write(action="none", daemon_pid=None)
            return True
        time.sleep(0.7)
    # Escalada: terminar directamente
    try:
        if psutil is not None:
            p = psutil.Process(int(pid))
            # Primero los hijos (xmrig): si solo matamos al daemon, el
            # minero queda HUÉRFANO minando al 100 % CPU sin control.
            try:
                for hijo in p.children(recursive=True):
                    try:
                        hijo.terminate()
                    except Exception:
                        pass
            except Exception:
                pass
            p.terminate()
            try:
                p.wait(timeout=6)
            except Exception:
                # última pasada: kill forzoso de hijos y padre
                try:
                    for hijo in p.children(recursive=True):
                        try:
                            hijo.kill()
                        except Exception:
                            pass
                except Exception:
                    pass
                p.kill()
        else:
            os.kill(int(pid), 9)
    except Exception:
        pass
    final = not is_pid_alive(pid)
    if final:
        write(action="none", daemon_pid=None)
    return final
