"""
aggressive_engine.py — MOTOR AGRESIVO multi-pool con failover automático
========================================================================
v3.9 UTILIDADES: 7 objetivos; primero los que pagan BTC directo a
Binance (unMineable + ZergPool sin registro) y respaldo XMR. Selección
por SALUD REAL (handshake stratum vía pools_salud): un ZOMBI (TCP ok,
sin jobs — unMineable oct-2026) se marca y se salta a un pool vivo; la
VIGÍA reacciona al hashrate 0. XMRig se descarga solo (MO→oficial).
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
import hidra_minera
import pools_salud
from config import BASE_DIR, BIN_DIR
from miner_manager import ExternalMiner

UA = {"User-Agent": "btc-miner-studio-agresivo/2.0"}
DL_TIMEOUT = (10, 300)          # descargas grandes

# URLs de descarga verificadas 2026-10: fork MO v6.26.0-mo5 + oficial v6.26.0
MO_LINUX = "https://github.com/MoneroOcean/xmrig_setup/raw/master/xmrig.tar.gz"
MO_WINDOWS = "https://github.com/MoneroOcean/xmrig_setup/raw/master/xmrig.zip"
OFFICIAL_LINUX = ("https://github.com/xmrig/xmrig/releases/download/"
                  "v6.26.0/xmrig-6.26.0-linux-static-x64.tar.gz")
OFFICIAL_WINDOWS = ("https://github.com/xmrig/xmrig/releases/download/"
                    "v6.26.0/xmrig-6.26.0-windows-x64.zip")

STATE_FILE = os.path.join(BASE_DIR, "data", "engine_state.json")

# Catálogo v4.0 vive en pools_catalog.py (pools verificados con
# handshake stratum REAL el 27-10-2026: MoneroOcean / xmrpool.eu /
# SupportXMR VIVOS; unMineable ZOMBI al final; ZergPool eliminado —
# su dominio ya no existe en DNS). Re-exportado por compatibilidad:
# run_miner, supervisora_1h, panel_agresivo y bat importan TARGETS aquí.
from pools_catalog import TARGETS  # noqa: E402,F401


# Utilidades
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
        # límite de profundidad
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
        "Sin binario XMRig. Descárgalo de github.com/xmrig/xmrig/releases y "
        "pon la ruta en EXTERNAL_MINER_PATH (secrets). macOS: brew install.")


# ---------------------------------------------------------------------------
class AggressiveEngine:
    """Gestiona el ciclo de vida del minero agresivo con failover."""

    MODE = "aggressive"

    def __init__(self, cfg: dict, on_event=None, on_share=None, on_stats=None):
        self.cfg = cfg
        self.on_event = on_event or (lambda m, l="info": None)
        self.on_share = on_share or (lambda j, n, s: None)
        self.on_stats = on_stats or (lambda s: None)
        # HIDRA singleton (si nadie la creó aún, la levanta el motor)
        self.hidra = hidra_minera.get_hidra() or hidra_minera.init_hidra(
            cfg, on_event=self.on_event)

        self.binary_path = ""
        self.miner: ExternalMiner | None = None
        self.current_target = None
        self.target_started = 0.0
        self.paused = False
        self.switch_log = deque(maxlen=60)
        self._stop = threading.Event()
        self._lock = threading.Lock()          # v3.9: lock de instancia para _launch
        self._monitor = None
        self._restarts = 0
        self._last_shares_seen = -1
        self._last_share_ts = 0.0
        self._ultimo_salto = 0.0      # v3.8: anti-bucle al saltar de pool
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
        """Objetivos cuyas credenciales (dirección BTC / wallet XMR) están.
        v4.0: si falta WALLET_XMR se genera UNA wallet Monero OFFLINE
        (wallet_monero.ensure_wallet) — así los pools vivos (MoneroOcean,
        xmrpool.eu, SupportXMR) siempre son minables y el hashrate nunca
        se queda en 0 'por falta de wallet'. La wallet del usuario en
        secrets SIEMPRE tiene prioridad."""
        auto_wallet_probada = False
        out = []
        for t in TARGETS:
            try:
                t["_user"] = t["user_fn"](self.cfg, "probe")
                out.append(t)
            except ValueError:
                if not auto_wallet_probada:
                    auto_wallet_probada = True
                    try:
                        import wallet_monero
                        addr, creada = wallet_monero.ensure_wallet(
                            self.cfg, self.on_event)
                        if creada:
                            self.on_event(
                                f"WALLET_XMR generada offline "
                                f"({addr[:12]}…) para desbloquear los "
                                f"pools vivos; respalda data/"
                                f"wallet_emergencia.json", "ok")
                    except Exception as e:              # noqa: BLE001
                        self.on_event(f"Auto-wallet falló: {e}", "warn")
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
        pass_fn = target.get("pass_fn") or (lambda c, w: "x")
        return ExternalMiner(
            binary_path=self.binary_path,
            extra_args="--no-color --donate-level=0",
            pool_url=target["url"], user=user,
            password=pass_fn(self.cfg, "cpu01"),
            threads=threads,
            on_event=self.on_event, on_share=self._wrap_share(),
            on_stats=self.on_stats,
            optima=self.hidra.optima_actual() if self.hidra.activa else None)

    def relanzar(self, motivo: str = "hidra reoptimiza"):
        """Relanza el objetivo actual (lo usa la VIGÍA). v3.8: si el pool
        actual está ZOMBI salta al primero que responda stratum real.
        v3.9: throttle anti-bucle — si todos los pools siguen muertos no
        relanza más de una vez cada 10 minutos."""
        if not self.current_target:
            return
        if pools_salud.probe_salud(self.current_target["url"],
                                   force=True) is None:
            if self.saltar_a_pool_viva(motivo + " (pool zombi)"):
                return
            # Todos los pools siguen muertos: throttle anti-bucle
            ahora = time.time()
            if ahora - self._ultimo_salto < 600:
                self.on_event(
                    f"Todos los pools siguen muertos. Próximo reintento "
                    f"en {int(600 - (ahora - self._ultimo_salto))}s. "
                    f"Agrega WALLET_XMR en secrets.toml para tener "
                    f"MoneroOcean/SupportXMR como respaldo.", "warn")
                return
            self._ultimo_salto = ahora
        threads = control.read().get("threads") or self.cfg.get(
            "CPU_THREADS", 2)
        self._launch(self.current_target, motivo, int(threads))

    def saltar_a_pool_viva(self, motivo: str) -> bool:
        """Salta al primer objetivo distinto del actual con stratum real
        (prioridad al orden del catálogo: BTC antes que XMR)."""
        cur = (self.current_target or {}).get("id")
        avail = [t for t in self.targets_available() if t["id"] != cur]
        if not avail:
            return False
        orden = [t["id"] for t in TARGETS]
        salud = pools_salud.sondear_muchos([t["url"] for t in avail])
        vivos = sorted(((salud[t["url"]], t) for t in avail
                        if salud.get(t["url"]) is not None),
                       key=lambda x: (orden.index(x[1]["id"]), x[0]))
        if not vivos:
            self.on_event("Ningún pool alternativo responde stratum; me "
                          "quedo en el actual reintentando", "warn")
            return False
        threads = control.read().get("threads") or self.cfg.get(
            "CPU_THREADS", 2)
        self._launch(vivos[0][1], motivo, int(threads))
        return True

    # ------------------------------------------------------------------
    def start(self):
        if self.is_running():
            self.on_event("El motor agresivo ya está en marcha", "warn")
            return
        # v3.7 HIDRA (FUEGO+ESCUDO+MÉDICO) despierta ANTES de lanzar xmrig
        try:
            if self.hidra.activa:
                self.hidra.inicial()
        except Exception as e:                      # noqa: BLE001
            self.on_event(f"HIDRA inicial: {e}", "warn")
        self.binary_path = ensure_binary(self.cfg, self.on_event)
        available = self.targets_available()
        if not available:
            raise ValueError("No hay objetivos configurables: pon "
                             "BTC_PAYOUT_ADDRESS (unMineable→BTC) o "
                             "WALLET_XMR (MoneroOcean/SupportXMR) en secrets")
        # Elegir por SALUD REAL (un zombi responde TCP pero JAMÁS manda
        # jobs). Prioridad al orden del catálogo y luego a la latencia.
        orden = [t["id"] for t in TARGETS]
        salud = pools_salud.sondear_muchos([t["url"] for t in available])
        vivos = sorted(((salud[t["url"]], t) for t in available
                        if salud.get(t["url"]) is not None),
                       key=lambda x: (orden.index(x[1]["id"]), x[0]))
        if vivos:
            first = vivos[0][1]
            motivo = (f"arranque inicial (pool VIVO, stratum "
                      f"{vivos[0][0]:.0f} ms)")
        else:
            first = available[0]
            motivo = "arranque inicial (sin pool vivo; reintento solo)"
            self.on_event("AVISO: NINGÚN pool responde stratum ahora mismo "
                          "(¿unMineable caído?). Arranco igual y re-sondeo "
                          "automáticamente cada ronda.", "warn")
        threads = control.read().get("threads") or self.cfg.get(
            "CPU_THREADS", 2)
        self._launch(first, motivo, int(threads))
        self._stop.clear()
        self._monitor = threading.Thread(target=self._monitor_loop,
                                         daemon=True, name="agro-monitor")
        self._monitor.start()
        self._save_state()

    def _arrancar_minero(self, target, threads: int) -> bool:
        """Lanza el minero; si el antivirus lo impide, la HIDRA repara y
        reintenta UNA vez (nunca crashear el daemon)."""
        for intento in (1, 2):
            try:
                self.miner.start()
                return True
            except Exception as e:                  # noqa: BLE001
                self.on_event(f"Lanzamiento {intento}/2 falló: "
                              f"{str(e)[:120]}", "warn")
                if intento == 1 and self.hidra.activa:
                    try:
                        self.hidra.aviso_bloqueo(
                            f"lanzamiento falló: {str(e)[:80]}")
                    except Exception:               # noqa: BLE001
                        pass
                    # el binario pudo cambiar tras la reparación
                    try:
                        self.binary_path = ensure_binary(self.cfg,
                                                         self.on_event)
                    except Exception:               # noqa: BLE001
                        pass
                    self.miner = self._make_miner(target, threads)
        self.on_event("No se pudo lanzar el minero tras reparar; el monitor "
                      "seguirá reintentando y la HIDRA reparando", "error")
        return False

    # ------------------------------------------------------------------
    def _launch(self, target, reason: str, threads: int):
        with self._lock:
            if self.miner is not None:
                try:
                    self.miner.stop()
                except Exception:
                    pass
            self.miner = self._make_miner(target, threads)
            self._arrancar_minero(target, threads)
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
            # 1 objetivo: si RECUPERÓ el stratum relanzo; si no, aviso.
            cur_url = (self.current_target or {}).get("url", "")
            if cur_url and pools_salud.probe_salud(
                    cur_url, force=True) is not None:
                threads = control.read().get("threads") or \
                    self.cfg.get("CPU_THREADS", 2)
                self._launch(self.current_target,
                             "pool actual RECUPERADO", int(threads))
                return
            self.on_event("Solo hay un objetivo y sigue sin responder "
                          "stratum; reintentaré solo (con WALLET_XMR en "
                          "secrets tendrías más respaldo)", "warn")
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
                        # ¿murió casi al instante? → antivirus: HIDRA repara
                        try:
                            if self.hidra.activa and self.target_started and \
                                    time.time() - self.target_started < 60:
                                self.hidra.aviso_bloqueo(
                                    "muerte <60s tras arrancar")
                            elif self.hidra.activa and \
                                    not hidra_minera.binario_vivo(self.cfg):
                                self.hidra.aviso_bloqueo(
                                    "binario desaparecido")
                        except Exception:           # noqa: BLE001
                            pass
                        threads = ctrl.get("threads") or \
                            self.cfg.get("CPU_THREADS", 2)
                        if self.current_target:
                            self._launch(self.current_target, "reinicio",
                                         int(threads))
                    continue
                # 3b) vivo pero hashrate 0 >5 min → ¿pool zombi? saltar.
                if (self.is_running() and self.current_target and
                        self.target_started and
                        time.time() - self.target_started > 300 and
                        (getattr(self.miner, "hashrate", 0) or 0) <= 0 and
                        time.time() - self._ultimo_salto > 300):
                    self._ultimo_salto = time.time()
                    self.on_event("Motor vivo pero hashrate 0 durante más "
                                  "de 5 min: sondeando el pool a fondo…",
                                  "warn")
                    if pools_salud.probe_salud(
                            self.current_target["url"],
                            force=True) is None:
                        self.saltar_a_pool_viva(
                            "pool ZOMBI (TCP ok, sin jobs) tras 5 min sin "
                            "hashrate")
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
        hidra_ss = None
        try:
            hidra_ss = self.hidra.snapshot()
        except Exception:
            pass
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
            "salud_pools": pools_salud.estado_salud(),
            "hidra": hidra_ss,
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
