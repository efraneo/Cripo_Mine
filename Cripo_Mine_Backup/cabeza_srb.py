"""
cabeza_srb.py — v4.6 MULTI · CABEZA SRBMINER (rutas que NO son RandomX)
=======================================================================
SRBMiner-Multi es el minero multi-algoritmo que permite a la CPU minar
VerusHash y GhostRider (algoritmos que xmrig NO soporta) contra Zpool,
que convierte TODO a BTC y lo paga directo a tu direccion de Binance
(sin cuentas: el usuario del stratum ES la direccion).

MIMICA DEL PATRON HIDRA (v3.7):
  - MÉDICO: si el binario no esta, se descarga SOLO (GitHub releases
    oficiales doktor83, version leida del feed + fallback fijada;
    verificado en vivo: v3.8.0 win64.zip / Linux.tar.gz).
  - VIGÍA: hilo propio cada 20s lee la API local (:21555), escribe
    metricas compatibles con el panel (StateStore.set_last_stats) y
    reinicia con el siguiente host si el proceso muere o el hashrate
    queda en 0 >15 min. 3 fallos seguidos => ruta marcada muerta y el
    daemon vuelve a la ruta XMR (nunca queda el bot sin minar).
  - ESCUDO (parcial): en Windows se recomienda agregar bin/srb a las
    exclusiones de Defender igual que bin/ (EXCLUSIONES_DEFENDER.ps1).
  - GPU: --disable-gpu (la Iris queda para la sonda OpenCL de v4.5;
    SRBMiner por defecto ya ignora iGPU).

Sin tocar la HIDRA original: mientras esta cabeza mina, el daemon NO
arranca el motor xmrig ni la Hidra (cero dobles, leccion v4.2).
"""
import json
import os
import re
import socket
import subprocess
import sys
import tarfile
import threading
import time
import zipfile

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(BASE_DIR, "bin", "srb")
LOG_PATH = os.path.join(BASE_DIR, "logs", "srb.log")

REPO = "doktor83/SRBMiner-Multi"
ATOM = f"https://github.com/{REPO}/releases.atom"
PIN_VERSION = "3.8.0"          # verificada en vivo 28-10-2026
API_PORT = 21555               # API local (xmrig usa 4068; sin choque)
POLL_S = 20
REINICIO_HASHRATE0_MIN = 15
MAX_FALLOS = 3

# Hosts stratum de Zpool (sandbox no resuelve *.zpool.ca por DNS propio;
# en la laptop del usuario si — se sondea y se usa el primero vivo).
ZPOOL_HOSTS = ["us.zpool.ca", "eu.zpool.ca", "zpool.ca"]
PUERTOS = {"verushash": 6143, "ghostrider": 5354}
# puerto SSL alternativo si el TCP falla (mismo host)
PUERTOS_SSL = {"verushash": 56143, "ghostrider": 55354}


def log_local(msg: str, level: str = "info", on_event=None):
    if on_event:
        try:
            on_event(msg, level)
        except Exception:                              # noqa: BLE001
            pass
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%m-%d %H:%M:%S')}] [{level}] {msg}\n")
    except Exception:                                  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# MEDICO: binario auto-gestionado
# ---------------------------------------------------------------------------
def _exe_name() -> str:
    return "SRBMiner-MULTI.exe" if os.name == "nt" else "SRBMiner-MULTI"


def binario_path() -> str:
    p = os.path.join(BIN_DIR, _exe_name())
    return p if os.path.exists(p) else ""


def _ultima_version() -> str:
    try:
        r = requests.get(ATOM, timeout=12,
                         headers={"User-Agent": "CripoMine/4.6"})
        tags = re.findall(r"/releases/tag/([\w.\-]+)", r.text)
        tags = [t for t in tags if re.match(r"^\d+\.\d+\.\d+$", t)]
        if tags:
            return sorted(tags, reverse=True)[0]
    except Exception:                                  # noqa: BLE001
        pass
    return PIN_VERSION


def _descargar(url: str, destino: str, on_event=None) -> bool:
    try:
        log_local(f"MÉDICO SRB: descargando {url.rsplit('/', 1)[-1]}…",
                  "info", on_event)
        with requests.get(url, stream=True, timeout=180,
                          headers={"User-Agent": "CripoMine/4.6"}) as r:
            r.raise_for_status()
            with open(destino, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    if chunk:
                        f.write(chunk)
        return os.path.exists(destino) and \
            os.path.getsize(destino) > 1_000_000
    except Exception as e:                             # noqa: BLE001
        log_local(f"MÉDICO SRB fallo descarga: {type(e).__name__}: "
                  f"{str(e)[:120]}", "warn", on_event)
        return False


def ensure_binario(on_event=None) -> str:
    """Devuelve ruta del binario; si no existe, lo descarga y extrae."""
    p = binario_path()
    if p:
        return p
    os.makedirs(BIN_DIR, exist_ok=True)
    ver = _ultima_version()
    vtag = ver.replace(".", "-")
    if os.name == "nt":
        url = (f"https://github.com/{REPO}/releases/download/{ver}/"
               f"SRBMiner-Multi-{vtag}-win64.zip")
        paq = os.path.join(BIN_DIR, "srb.zip")
        ok = _descargar(url, paq, on_event)
        if not ok and ver != PIN_VERSION:               # fallback fijada
            ok = _descargar(
                f"https://github.com/{REPO}/releases/download/{PIN_VERSION}"
                f"/SRBMiner-Multi-{PIN_VERSION.replace('.', '-')}-win64.zip",
                paq, on_event)
        if not ok:
            return ""
        try:
            with zipfile.ZipFile(paq) as z:
                for m in z.namelist():
                    if m.endswith(_exe_name()):
                        with open(os.path.join(BIN_DIR, _exe_name()),
                                  "wb") as f:
                            f.write(z.read(m))
                        break
            os.remove(paq)
        except Exception as e:                          # noqa: BLE001
            log_local(f"MÉDICO SRB fallo unzip: {e}", "warn", on_event)
            return ""
    else:
        url = (f"https://github.com/{REPO}/releases/download/{ver}/"
               f"SRBMiner-Multi-{vtag}-Linux.tar.gz")
        paq = os.path.join(BIN_DIR, "srb.tgz")
        ok = _descargar(url, paq, on_event)
        if not ok:
            return ""
        try:
            with tarfile.open(paq) as t:
                for m in t.getmembers():
                    if m.name.endswith("/SRBMiner-MULTI") and m.isfile():
                        m.name = os.path.basename(m.name)
                        t.extract(m, BIN_DIR)
                        break
            os.chmod(os.path.join(BIN_DIR, "SRBMiner-MULTI"), 0o755)
            os.remove(paq)
        except Exception as e:                          # noqa: BLE001
            log_local(f"MÉDICO SRB fallo untar: {e}", "warn", on_event)
            return ""
    log_local(f"MÉDICO SRB: binario listo v{ver}", "ok", on_event)
    return binario_path()


# ---------------------------------------------------------------------------
# Hosts: primero vivo (patron pools_salud.stratum_ok)
# ---------------------------------------------------------------------------
def host_vivo(hosts: list, puerto: int, timeout: int = 6) -> str:
    for h in hosts:
        try:
            ip = socket.gethostbyname(h)
            s = socket.create_connection((ip, puerto), timeout=timeout)
            s.close()
            return h
        except Exception:                              # noqa: BLE001
            continue
    return ""


# ---------------------------------------------------------------------------
# Cabeza SRB (proceso + vigilancia + API local)
# ---------------------------------------------------------------------------
class CabezaSRB:
    """Gestor del proceso SRBMiner para UNA ruta (btc_vrsc / btc_gr)."""

    def __init__(self, on_event=None, on_stats=None):
        self.on_event = on_event or (lambda m, l="info": None)
        self.on_stats = on_stats or (lambda s: None)
        self.proc = None
        self.ruta = {}
        self.cfg = {}
        self.fallos = 0
        self.hashrate0_desde = 0.0
        self.stop_flag = threading.Event()
        self.hilo = None
        self.host = ""
        self.ultima_stats = {}

    # -- ciclo de vida ------------------------------------------------------
    def start(self, ruta: dict, cfg: dict) -> bool:
        self.ruta, self.cfg = ruta, cfg
        self.stop_flag.clear()
        exe = ensure_binario(self.on_event)
        if not exe:
            self.on_event("SRB: binario no disponible (MÉDICO fallo); "
                          "el selector volverá a la ruta XMR", "error")
            self.fallos = MAX_FALLOS
            return False
        algo = ruta.get("algo", "verushash")
        self.host = host_vivo(ZPOOL_HOSTS, PUERTOS.get(algo, 6143))
        if not self.host:
            self.on_event(f"SRB: ningun host Zpool responde para {algo} "
                          "(revisar red/DNS); el selector decidira",
                          "warn")
            self.fallos = MAX_FALLOS
            return False
        cmd = self._cmd(exe, algo)
        try:
            logf = open(LOG_PATH, "a", encoding="utf-8", errors="replace")
            self.proc = subprocess.Popen(
                cmd, stdout=logf, stderr=subprocess.STDOUT,
                cwd=BIN_DIR if os.path.isdir(BIN_DIR) else None)
        except Exception as e:                         # noqa: BLE001
            self.on_event(f"SRB: no pude arrancar {algo}: {e}", "error")
            self.fallos = MAX_FALLOS
            return False
        self.on_event(f"SRB ARRANCA: {algo} @ {self.host}:{PUERTOS[algo]} "
                      f"(pid {self.proc.pid}, pago BTC directo)", "ok")
        self.hilo = threading.Thread(target=self._vigia, daemon=True,
                                     name="cabeza-srb")
        self.hilo.start()
        return True

    def _cmd(self, exe: str, algo: str) -> list:
        addr = (self.cfg.get("BTC_PAYOUT_ADDRESS") or "").strip()
        worker = (self.cfg.get("WORKER_NAME") or "cpu01").strip() or "cpu01"
        pct = self._pct_hilos()
        cmd = [exe,
               "--algorithm", algo,
               "--pool", f"stratum+tcp://{self.host}:{PUERTOS[algo]}",
               "--wallet", f"{addr}.{worker}",
               "--password", "x",
               "--api-enable", "--api-port", str(API_PORT),
               "--disable-gpu"]
        if pct:
            cmd += ["--cpu-threads-percent", str(pct)]
        return cmd

    def _pct_hilos(self) -> int:
        """Respeta el afinado v4.5 sin pelear con la cache L3."""
        try:
            with open(os.path.join(BASE_DIR, "data", "afinado.json"),
                      encoding="utf-8") as f:
                hilos = int((json.load(f) or {}).get("hilos") or 0)
            logicos = os.cpu_count() or hilos
            if hilos >= 1 and logicos >= 1:
                return max(10, min(90, int(hilos * 100 / logicos)))
        except Exception:                              # noqa: BLE001
            pass
        return 0

    def stop(self):
        self.stop_flag.set()
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=10)
            except Exception:                          # noqa: BLE001
                try:
                    p.kill()
                except Exception:                      # noqa: BLE001
                    pass
        self.on_event("SRB detenido", "info")

    def alive(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    # -- vigilancia + API ----------------------------------------------------
    def _api_stats(self) -> dict:
        try:
            r = requests.get(f"http://127.0.0.1:{API_PORT}", timeout=5)
            return r.json() if r.status_code == 200 else {}
        except Exception:                              # noqa: BLE001
            return {}

    def _vigia(self):
        while not self.stop_flag.is_set():
            time.sleep(POLL_S)
            if self.stop_flag.is_set():
                break
            data = self._api_stats()
            stats = self._parse(data)
            self.ultima_stats = stats
            self.on_stats(stats)
            hr = float(stats.get("hashrate") or 0)
            if not self.alive() or (hr <= 0 and self.hashrate0_desde and
                                    time.time() - self.hashrate0_desde >
                                    REINICIO_HASHRATE0_MIN * 60):
                self.fallos += 1
                if self.fallos >= MAX_FALLOS:
                    self.on_event("SRB: 3 fallos seguidos; ruta marcada "
                                  "muerta, el daemon volverá a XMR", "error")
                    self.stop_flag.set()
                    break
                self.on_event(f"SRB: reinicio {self.fallos}/{MAX_FALLOS} "
                              "(proceso muerto o hashrate 0)", "warn")
                self._reiniciar()
            elif hr > 0:
                self.fallos = 0
                self.hashrate0_desde = 0.0
            elif hr <= 0 and not self.hashrate0_desde:
                self.hashrate0_desde = time.time()

    def _reiniciar(self):
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=8)
            except Exception:                          # noqa: BLE001
                pass
        time.sleep(5)
        self.start(self.ruta, self.cfg)

    @staticmethod
    def _parse(data: dict) -> dict:
        """API SRBMiner -> metricas del panel. Parse defensivo total."""
        out = {"mode": "srb", "ruta": "", "hashrate": 0.0, "shares_ok": 0,
               "shares_rej": 0, "alive": False}
        if not isinstance(data, dict):
            return out
        try:
            for k, v in data.items():
                kl = str(k).lower()
                if "hashrate_total" in kl and isinstance(v, list) and v:
                    out["hashrate"] = float(v[0] or 0)
                elif "total_shares_accepted" in kl:
                    out["shares_ok"] = int(float(v or 0))
                elif "total_shares_rejected" in kl:
                    out["shares_rej"] = int(float(v or 0))
            algs = data.get("algorithms") or data.get("Algorithms") or []
            if isinstance(algs, list) and algs:
                a0 = algs[0] or {}
                if not out["hashrate"]:
                    out["hashrate"] = float(a0.get("hashrate_total") or
                                            a0.get("Hashrate_total") or 0) \
                        if not isinstance(a0.get("hashrate_total"), list) \
                        else float(a0["hashrate_total"][0] or 0)
                out["ruta"] = str(a0.get("algorithm") or "")
                if a0.get("accepted_shares") is not None:
                    out["shares_ok"] = int(float(a0["accepted_shares"] or 0))
                if a0.get("rejected_shares") is not None:
                    out["shares_rej"] = int(float(a0["rejected_shares"] or 0))
        except Exception:                              # noqa: BLE001
            pass
        out["alive"] = out["hashrate"] > 0
        return out


def crear_cabeza(on_event=None, on_stats=None) -> CabezaSRB:
    return CabezaSRB(on_event=on_event, on_stats=on_stats)
