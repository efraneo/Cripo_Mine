"""
aggressive_engine.py — MOTOR AGRESIVO multi-pool con failover automático
========================================================================
La "intervención" sobre el minero original: en lugar de hashes SHA-256 de
BTC con CPU (probabilidad de bloque ≈ 0, la red corre a cientos de EH/s),
el motor rota objetivos RandomX que SÍ retribuyen el hash de CPU:

  1) unMineable  (rx/0) → mina RandomX y PAGA EN BTC directo a tu dirección
     de depósito de Binance (formato user: "BTC:<dirección>.<worker>")
  2) MoneroOcean (auto) → pool con auto-cambio de algoritmo (fork xmrig-MO,
     13+ algos según rentabilidad del momento); paga en XMR a tu wallet
  3) SupportXMR  (rx/0) → pool veterano de Monero como respaldo (paga XMR)

Funciones clave:
  • Descarga automática del binario XMRig (fork MO v6.26.0-mo5 precompilado
    desde github.com/MoneroOcean/xmrig_setup; fallback: xmrig oficial 6.26.0
    estático). No necesitas instalar nada a mano.
  • FAILOVER: si no hay shares aceptados en FAILOVER_MINUTES, si el proceso
    muere repetidamente o si el pool no responde → salta al siguiente
    objetivo y registra el motivo.
  • Obedece data/control.json: pausa térmica/manual, cambio forzado, hilos.
  • Sonda de latencia: elige el pool con mejor ping al arrancar.
"""
import json
import os
import platform
import socket
import stat
import threading
import time
import zipfile
from collections import deque

import requests

import control
from config import BASE_DIR, BIN_DIR
from miner_manager import ExternalMiner

UA = {"User-Agent": "btc-miner-studio-agresivo/2.0"}
DL_TIMEOUT = (10, 300)          # (conexión, lectura) para descargas grandes

# URLs de descarga (verificadas 2026-10):
#   fork MO con auto-switching: github.com/MoneroOcean/xmrig_setup (v6.26.0-mo5)
#   xmrig oficial estático:     github.com/xmrig/xmrig/releases (v6.26.0)
MO_LINUX = ("https://github.com/MoneroOcean/xmrig_setup/raw/master/"
            "xmrig.tar.gz")
MO_WINDOWS = ("https://github.com/MoneroOcean/xmrig_setup/raw/master/"
              "xmrig.zip")
OFFICIAL_LINUX = ("https://github.com/xmrig/xmrig/releases/download/v6.26.0/"
                  "xmrig-6.26.0-linux-static-x64.tar.gz")
OFFICIAL_WINDOWS = ("https://github.com/xmrig/xmrig/releases/download/"
                    "v6.26.0/xmrig-6.26.0-windows-x64.zip")

STATE_FILE = os.path.join(BASE_DIR, "data", "engine_state.json")


# ---------------------------------------------------------------------------
# Catálogo de objetivos agresivos
# ---------------------------------------------------------------------------
def _user_unmineable(cfg, worker):
    addr = (cfg.get("BTC_PAYOUT_ADDRESS") or "").strip()
    if not addr:
        raise ValueError("Falta BTC_PAYOUT_ADDRESS (necesaria para que "
                         "unMineable pague en BTC a tu Binance)")
    return f"BTC:{addr}.{(worker or 'cpu01').strip() or 'cpu01'}"


def _user_wallet(cfg, worker):
    w = (cfg.get("WALLET_XMR") or "").strip()
    if not w:
        raise ValueError("Falta WALLET_XMR (wallet Monero para "
                         "MoneroOcean/SupportXMR)")
    return w


TARGETS = [
    {
        "id": "unmineable",
        "nombre": "unMineable (paga en BTC directo a Binance)",
        "url": "rx.unmineable.com:3333",
        "algo": "rx/0",
        "pago": "BTC",
        "user_fn": _user_unmineable,
        "nota": "Endpoint RandomX oficial (soporte unMineable 2026: "
                "rx.unmineable.com:3333; alternativa SSL stratum+ssl://rx." 
                "unmineable.com:443). Formato user: BTC:<dirección>.<worker> "
                "o alias de la sección Addresses. Umbral de pago real lo da "
                "la API (~0.00075 BTC) y puedes ajustarlo en unmineable.com.",
    },
    {
        "id": "moneroocean",
        "nombre": "MoneroOcean (auto-cambio de algoritmo, paga XMR)",
        "url": "gulf.moneroocean.stream:10128",
        "algo": "auto",
        "pago": "XMR",
        "user_fn": _user_wallet,
        "nota": "Con el fork xmrig-MO el pool/minero prueba 13+ algoritmos y "
                "se queda con el más rentable para tu CPU. Umbral bajo "
                "(0.001 XMR). Paga a tu wallet Monero.",
    },
    {
        "id": "supportxmr",
        "nombre": "SupportXMR (pool veterano de respaldo, paga XMR)",
        "url": "pool.supportxmr.com:3333",
        "algo": "rx/0",
        "pago": "XMR",
        "user_fn": _user_wallet,
        "nota": "Pool Monero estable desde 2016, vardiff bajo: good para "
                "CPU pequeñas. PPLNS, fee 0.6%.",
    },
]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def probe_pool(url: str, timeout: float = 3.0):
    """Latencia TCP al pool en ms (None si no responde)."""
    host, _, port = url.partition(":")
    try:
        t0 = time.time()
        s = socket.create_connection((host, int(port or 3333)),
                                     timeout=timeout)
        s.close()
        return round((time.time() - t0) * 1000, 1)
    except Exception:
        return None


def _extract(archive_path: str, dest: str):
    os.makedirs(dest, exist_ok=True)
    if archive_path.lower().endswith(".zip"):
        with zipfile.ZipFile(archive_path) as z:
            z.extractall(dest)
    else:
        import tarfile
        with tarfile.open(archive_path) as t:
            t.extractall(dest)


def _find_binary(root: str) -> str:
    """Busca el ejecutable xmrig dentro del directorio extraído."""
    exe_suffix = ".exe" if os.name == "nt" else ""
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.lower() in ("xmrig" + exe_suffix, "xmrig-mo" + exe_suffix):
                p = os.path.join(dirpath, f)
                if os.name != "nt":
                    try:
                        os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
                    except Exception:
                        pass
                return p
        # límite de profundidad razonable
        if dirpath.count(os.sep) - root.count(os.sep) > 4:
            break
    return ""


def _download(url: str, dest: str, on_event):
    on_event(f"Descargando {url.split('/')[-1]} (~3 MB)…", "info")
    with requests.get(url, headers=UA, stream=True, timeout=DL_TIMEOUT) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)
    return dest


def ensure_binary(cfg, on_event) -> str:
    """Devuelve ruta a un binario xmrig, descargándolo si hace falta."""
    override = (cfg.get("EXTERNAL_MINER_PATH") or "").strip()
    if override and os.path.exists(override):
        on_event(f"Usando binario externo configurado: {override}", "info")
        return override

    marker = os.path.join(BIN_DIR, "xmrig_binary_path.json")
    try:
        if os.path.exists(marker):
            with open(marker, "r", encoding="utf-8") as f:
                p = json.load(f).get("path", "")
            if p and os.path.exists(p):
                return p
    except Exception:
        pass

    os.makedirs(BIN_DIR, exist_ok=True)
    mo_root = os.path.join(BIN_DIR, "xmrig-mo")
    oficial_root = os.path.join(BIN_DIR, "xmrig-oficial")

    # 1) Fork de MoneroOcean (auto algoritmos)
    try:
        if os.name == "nt":
            src, root, arch = MO_WINDOWS, mo_root, os.path.join(BIN_DIR, "mo.zip")
        else:
            src, root, arch = MO_LINUX, mo_root, os.path.join(BIN_DIR, "mo.tar.gz")
        _download(src, arch, on_event)
        _extract(arch, root)
        bin_path = _find_binary(root)
        if bin_path:
            json.dump({"path": bin_path}, open(marker, "w", encoding="utf-8"))
            on_event(f"XMRig-MO listo: {bin_path}", "ok")
            return bin_path
    except Exception as e:
        on_event(f"Fork MO no disponible ({e}); probando xmrig oficial…", "warn")

    # 2) Fallback: xmrig oficial estático
    try:
        if os.name == "nt":
            src, root, arch = (OFFICIAL_WINDOWS, oficial_root,
                               os.path.join(BIN_DIR, "oficial.zip"))
        else:
            src, root, arch = (OFFICIAL_LINUX, oficial_root,
                               os.path.join(BIN_DIR, "oficial.tar.gz"))
        _download(src, arch, on_event)
        _extract(arch, root)
        bin_path = _find_binary(root)
        if bin_path:
            json.dump({"path": bin_path}, open(marker, "w", encoding="utf-8"))
            on_event(f"XMRig oficial listo: {bin_path}", "ok")
            return bin_path
    except Exception as e:
        on_event(f"No se pudo descargar XMRig: {e}", "error")

    raise FileNotFoundError(
        "Sin binario XMRig. Descárgalo manualmente de github.com/xmrig/xmrig"
        "/releases y pon la ruta en EXTERNAL_MINER_PATH (secrets). En macOS: "
        "`brew install xmrig`.")


# ---------------------------------------------------------------------------
class AggressiveEngine:
    """Gestiona el ciclo de vida del minero agresivo con failover."""

    MODE = "aggressive"

    def __init__(self, cfg: dict, on_event=None, on_share=None, on_stats=None):
        self.cfg = cfg
        self.on_event = on_event or (lambda m, l="info": None)
        self.on_share = on_share or (lambda j, n, s: None)
        self.on_stats = on_stats or (lambda s: None)

        self.binary_path = ""
        self.miner: ExternalMiner | None = None
        self.current_target = None
        self.target_started = 0.0
        self.paused = False
        self.switch_log = deque(maxlen=60)
        self._stop = threading.Event()
        self._monitor = None
        self._restarts = 0
        self._last_shares_seen = -1
        self._last_share_ts = 0.0
        self.failover_min = self._num(cfg.get("FAILOVER_MINUTES"), 12, 1, 240)
        self.rotate_min = self._num(cfg.get("ROTATE_MINUTES"), 0, 0, 1440)

    # ------------------------------------------------------------------
    @staticmethod
    def _num(v, default, lo, hi):
        try:
            return max(lo, min(hi, float(v)))
        except (TypeError, ValueError):
            return default

    def targets_available(self) -> list:
        """Objetivos cuyas credenciales (dirección BTC / wallet XMR) están."""
        out = []
        for t in TARGETS:
            try:
                t["_user"] = t["user_fn"](self.cfg, "probe")
                out.append(t)
            except ValueError:
                t["_user"] = ""
        return out

    def _wrap_share(self):
        def inner(job, nonce, status):
            self._last_share_ts = time.time()
            self.on_share(job, nonce, status)
        return inner

    def _make_miner(self, target, threads) -> ExternalMiner:
        user = target["user_fn"](self.cfg, "cpu01")
        return ExternalMiner(
            binary_path=self.binary_path,
            extra_args="--no-color --donate-level=1",
            pool_url=target["url"], user=user, password="x",
            threads=threads,
            on_event=self.on_event, on_share=self._wrap_share(),
            on_stats=self.on_stats)

    # ------------------------------------------------------------------
    def start(self):
        if self.is_running():
            self.on_event("El motor agresivo ya está en marcha", "warn")
            return
        self.binary_path = ensure_binary(self.cfg, self.on_event)
        available = self.targets_available()
        if not available:
            raise ValueError("No hay objetivos configurables: pon "
                             "BTC_PAYOUT_ADDRESS (unMineable→BTC) o "
                             "WALLET_XMR (MoneroOcean/SupportXMR) en secrets")
        # elegir por latencia (los que responden primero)
        latencies = []
        for t in available:
            ms = probe_pool(t["url"]) or 9999.0
            latencies.append((ms, t["id"]))
        latencies.sort()
        first = next(t for t in TARGETS if t["id"] == latencies[0][1])
        threads = control.read().get("threads") or self.cfg.get(
            "CPU_THREADS", 2)
        self._launch(first, "arranque inicial (mejor latencia "
                            f"{latencies[0][0]:.0f} ms)", int(threads))
        self._stop.clear()
        self._monitor = threading.Thread(target=self._monitor_loop,
                                         daemon=True, name="agro-monitor")
        self._monitor.start()
        self._save_state()

    def _launch(self, target, reason: str, threads: int):
        with threading.Lock():
            if self.miner is not None:
                try:
                    self.miner.stop()
                except Exception:
                    pass
            self.miner = self._make_miner(target, threads)
            self.miner.start()
            prev = (self.current_target or {}).get("id", "—")
            self.current_target = target
            self.target_started = time.time()
            self._restarts = 0
            self._last_share_ts = time.time()
            self._last_shares_seen = 0
            self.paused = False
            self.switch_log.append({
                "ts": time.time(), "from": prev, "to": target["id"],
                "reason": reason})
            self.on_event(f"Objetivo: {target['nombre']} · pool={target['url']} "
                          f"· algo={target['algo']} · ({reason})", "ok")
        self._save_state()

    # ------------------------------------------------------------------
    def switch_next(self, reason: str):
        avail = self.targets_available()
        if len(avail) < 2:
            self.on_event("Solo hay un objetivo disponible; no puedo rotar "
                          "(configura WALLET_XMR para tener más)", "warn")
            return
        cur = (self.current_target or {}).get("id")
        order = [t["id"] for t in TARGETS]
        nxt = None
        for t in avail:                      # siguiente en orden de catálogo
            if order.index(t["id"]) > order.index(cur or ""):
                nxt = t
                break
        nxt = nxt or avail[0]
        threads = control.read().get("threads") or self.cfg.get("CPU_THREADS", 2)
        self._launch(nxt, reason, int(threads))

    def switch_to(self, target_id: str, reason: str = "solicitud manual"):
        for t in self.targets_available():
            if t["id"] == target_id:
                threads = control.read().get("threads") or \
                    self.cfg.get("CPU_THREADS", 2)
                self._launch(t, reason, int(threads))
                return True
        self.on_event(f"Objetivo '{target_id}' no disponible (revisa secrets)",
                      "warn")
        return False

    # ------------------------------------------------------------------
    def _monitor_loop(self):
        """Vigila salud, pausas y failover cada 20 s."""
        while not self._stop.is_set():
            if self._stop.wait(20):
                break
            try:
                ctrl = control.read()
                # 1) pausas (manual o térmica)
                want_pause = bool(ctrl.get("paused_manual") or
                                  ctrl.get("paused_thermal"))
                if want_pause and not self.paused:
                    if self.miner:
                        self.miner.stop()
                    self.paused = True
                    motivo = "manual" if ctrl.get("paused_manual") else "térmica"
                    self.on_event(f"Motor PAUSADO ({motivo})", "warn")
                    self._save_state()
                    continue
                if not want_pause and self.paused:
                    threads = ctrl.get("threads") or self.cfg.get("CPU_THREADS", 2)
                    if self.current_target:
                        self._launch(self.current_target, "reanudado",
                                     int(threads))
                if self.paused:
                    continue
                # 2) cambio forzado (botón o Telegram)
                force = (ctrl.get("force_target") or "").strip()
                if force:
                    control.write(force_target="", updated_by="telegram")
                    if force == "next":
                        self.switch_next("cambio forzado (control remoto)")
                    else:
                        self.switch_to(force, "objetivo forzado (control)")
                    continue
                # 3) ¿proceso vivo?
                if not self.is_running():
                    self._restarts += 1
                    if self._restarts >= 3:
                        self.switch_next("proceso murió 3 veces seguidas")
                    else:
                        self.on_event(f"Proceso muerto; reintento "
                                      f"{self._restarts}/3", "warn")
                        threads = ctrl.get("threads") or \
                            self.cfg.get("CPU_THREADS", 2)
                        if self.current_target:
                            self._launch(self.current_target, "reinicio",
                                         int(threads))
                    continue
                # 4) ¿avanzan los shares?
                stats_ok = 0
                if self.miner is not None:
                    stats_ok = int(getattr(self.miner, "shares_ok", 0))
                if stats_ok != self._last_shares_seen:
                    self._last_shares_seen = stats_ok
                    self._last_share_ts = time.time()
                elif (time.time() - self._last_share_ts >
                        self.failover_min * 60):
                    self.switch_next(f"sin shares aceptados en "
                                     f"{self.failover_min:.0f} min")
                # 5) rotación preventiva (opcional, desactivada por defecto)
                if (self.rotate_min > 0 and self.current_target and
                        time.time() - self.target_started >
                        self.rotate_min * 60):
                    self.switch_next(f"rotación programada "
                                     f"({self.rotate_min:.0f} min)")
            except Exception as e:
                self.on_event(f"Monitor del motor: {e}", "error")
        self._save_state()

    # ------------------------------------------------------------------
    def is_running(self) -> bool:
        return bool(self.miner and self.miner.is_running() and
                    not self.paused and not self._stop.is_set())

    def stop(self):
        self._stop.set()
        if self.miner:
            try:
                self.miner.stop()
            except Exception:
                pass
        self.miner = None
        self.paused = False
        self._save_state()

    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        lat = {t["id"]: probe_pool(t["url"]) for t in TARGETS}
        return {
            "mode": self.MODE,
            "running": self.is_running(),
            "paused": self.paused,
            "target": dict(self.current_target) if self.current_target
                      else None,
            "target_uptime": (time.time() - self.target_started)
                             if self.target_started else 0,
            "binary": self.binary_path,
            "switch_log": list(self.switch_log)[-20:],
            "latencias_ms": lat,
            "disponibles": [t["id"] for t in self.targets_available()],
        }

    def _save_state(self):
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({"ts": time.time(),
                           "target": (self.current_target or {}).get("id"),
                           "paused": self.paused,
                           "switch_log": list(self.switch_log)[-30:]},
                          f)
        except Exception:
            pass
