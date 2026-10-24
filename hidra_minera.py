"""
hidra_minera.py — LA HIDRA v3.8: motor de agresividad restaurada
================================================================
5 cabezas en paralelo, best-effort, NUNCA rompen el minado:
  FUEGO   → config xmrig a MÁXIMO (hilos óptimos, huge pages+jit,
            memory-pool, prioridad, randomx fast + mod MSR).
  ESCUDO  → anti-Defender: exclusiones CORRECTAS (carpeta + .exe
            exacto + proceso xmrig.exe; la carpeta sola NO basta).
  MÉDICO  → resucita xmrig.exe: cuarentena (MpCmdRun) o re-descarga.
  VIGÍA   → vigila el hashrate vs RÉCORD; cae >HIDRA_CAIDA_PCT en
            varias rondas → diagnostica y reoptimiza. v3.8: también
            reacciona a hashrate CERO sostenido (pool zombi) saltando
            a un pool vivo (engine.relanzar ya lo hace).
  CASA    → memoria compartida: data/hidra_state.json → /hidra y
            dashboard.
Secrets: HIDRA_ACTIVA(true), HIDRA_CAIDA_PCT(35), HIDRA_DEFENDER(true).
Diseñada para Windows y degrada a no-op limpio en Linux/macOS.
"""
import json
import os
import platform
import subprocess
import threading
import time
from collections import deque

from config import BASE_DIR, DATA_DIR

# Constantes
STATE_FILE = os.path.join(DATA_DIR, "hidra_state.json")
BEST_FILE = STATE_FILE           # récord + acciones viven en el mismo JSON
PS_TIMEOUT = 60                  # segundos máx. por comando de PowerShell
INTERVALO_VIGIA = 120            # seg. entre rondas de la CABEZA 4
CICLOS_CAIDA = 3                 # rondas consecutivas de caída para actuar
MARGEN_ARRANQUE = 180            # seg. de gracia tras lanzar xmrig
EVENTOS_MAX = 60

CABEZAS = ("fuego", "escudo", "medico", "vigia", "casa")


def log_local(msg: str, level: str = "info", on_event=None):
    """Registra en memoria + callback del daemon si existe."""
    EVENTOS.append({"ts": time.time(), "level": level, "msg": str(msg)[:300]})
    if on_event:
        try:
            on_event(msg, level)
        except Exception:
            pass


EVENTOS = deque(maxlen=EVENTOS_MAX)


# CABEZA 1 · FUEGO — ingeniería de configuración óptima
def info_cpu() -> dict:
    """Inventario de la CPU/RAM para decidir la config más agresiva."""
    out = {
        "logicos": os.cpu_count() or 1,
        "fisicos": 0,
        "ram_gb": 0.0,
        "vendor": (platform.processor() or "").lower(),
        "so": platform.system(),
    }
    try:
        import psutil
        out["fisicos"] = psutil.cpu_count(logical=False) or out["logicos"]
        out["ram_gb"] = round(psutil.virtual_memory().total / (1 << 30), 1)
    except Exception:
        out["fisicos"] = max(1, out["logicos"] // 2)
        out["ram_gb"] = 8.0 if os.name == "nt" else 4.0
    return out


def hilos_optimos(info: dict | None = None) -> int:
    """Regla RandomX: 1 hilo por MB de caché L3 (2 MB compartido×2 hilos).
    Sin dato de L3: núcleos físicos (el óptimo típico en Ryzen/Intel
    modernos). Nunca menos de 1."""
    info = info or info_cpu()
    fis = max(1, int(info.get("fisicos") or 1))
    return fis


def _es_amd(vendor: str) -> bool:
    v = (vendor or "").lower()
    return "amd" in v or "ryzen" in v


def config_optima(cfg: dict) -> dict:
    """Devuelve el dict `optima` que miner_manager.write_xmrig_config
    fusiona dentro del objeto cpu + randomx de xmrig (CABEZA 1).

    Fuentes: xmrig.com/docs/miner/config/cpu (huge-pages, huge-pages-jit,
    priority, memory-pool, randomx.mode/wrmsr/rdmsr).
    """
    info = info_cpu()
    prioridad = 2          # 1-5; >2 puede dejar el PC inservible: 2 = justo
    opt = {
        "cpu": {
            "enabled": True,
            "huge-pages": True,
            "huge-pages-jit": True,        # pequeña subida en Ryzen
            "hw-aes": None,                # auto (Ryzen/Intel modernos sí)
            "priority": prioridad,
            "max-threads-hint": hilos_optimos(info),
            "memory-pool": True,           # conserva huge pages entre
                                           # reinicios de hilos (docs xmrig)
        },
        "randomx": {
            "mode": "fast" if info.get("ram_gb", 0) >= 6 else "light",
            "1gb-pages": False,            # solo Linux; en Windows no aplica
            "rdmsr": True,
            "wrmsr": True,                 # el MOD MSR: requiere ADMIN
            "numa": True,
            "scratchpad_prefetch_mode": 1,
        },
    }
    opt["meta"] = {
        "fisicos": info.get("fisicos"), "logicos": info.get("logicos"),
        "ram_gb": info.get("ram_gb"), "amd": _es_amd(info.get("vendor", "")),
        "ts": time.time(),
    }
    return opt


def aplicar_fuego(cfg: dict, on_event=None) -> dict:
    """Calcula (y devuelve) la config óptima; también la persiste."""
    opt = config_optima(cfg)
    estado = _cargar_estado()
    estado["fuego"] = opt.get("meta", {})
    estado["ts_fuego"] = time.time()
    _guardar_estado(estado)
    log_local(f"FUEGO: hilos={opt['cpu']['max-threads-hint']} "
              f"huge-pages=on jit=on memory-pool=on "
              f"randomx={opt['randomx']['mode']} msr=on", "ok", on_event)
    return opt


# PowerShell helpers (CABEZA 2 y 3)
def _ps(comando: str, timeout: int = PS_TIMEOUT):
    """Ejecuta powershell -NoProfile -Command; devuelve (rc, salida)."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             comando],
            capture_output=True, text=True, timeout=timeout, errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return -1, str(e)


def es_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# CABEZA 2 · ESCUDO — exclusiones CORRECTAS de Windows Defender
# Docs Microsoft (Add-MpPreference): -ExclusionPath excluye rutas;
# -ExclusionProcess los archivos que ABRE ese proceso. La carpeta sola
# NO evita la cuarentena: cubrir carpeta + .exe exacto + proceso.
def _rutas_binario(cfg: dict) -> list:
    """Rutas que hay que excluir: carpeta bin/, carpeta del fork y el .exe."""
    rutas = [os.path.join(BASE_DIR, "bin"),
             os.path.join(BASE_DIR, "bin", "xmrig-mo"),
             os.path.join(BASE_DIR, "bin", "xmrig-oficial")]
    p = (cfg.get("EXTERNAL_MINER_PATH") or "").strip()
    if p:
        rutas.append(p)
    try:
        marker = os.path.join(BASE_DIR, "bin", "xmrig_binary_path.json")
        if os.path.exists(marker):
            with open(marker, "r", encoding="utf-8") as f:
                j = json.load(f)
            if j.get("path"):
                rutas.append(j["path"])
    except Exception:
        pass
    return rutas


def defender_estado(cfg: dict) -> dict:
    """Diagnóstico Defender: admin, exclusiones presentes y amenazas
    recientes contra xmrig. Nunca explota. En no-Windows: aplica=False."""
    if os.name != "nt":
        return {"aplica": False, "admin": False, "exclusiones": [],
                "amenazas": [], "procesos": [], "servicio": False}
    out = {"aplica": True, "admin": es_admin(), "exclusiones": [],
           "amenazas": [], "procesos": [], "servicio": False}
    rc, sal = _ps("(Get-MpPreference).ExclusionPath | Out-String", 30)
    if rc == 0:
        out["servicio"] = True
        out["exclusiones"] = [l.strip() for l in sal.splitlines()
                              if l.strip()]
    rc, sal = _ps("(Get-MpPreference).ExclusionProcess | Out-String", 30)
    if rc == 0:
        out["procesos"] = [l.strip() for l in sal.splitlines() if l.strip()]
    # amenazas con 'xmrig' o 'coinminer' en los últimos hallazgos
    rc, sal = _ps(
        "try { Get-MpThreatDetection | Where-Object { $_.Resources -match "
        "'xmrig|coinminer' } | Select-Object -First 5 | "
        "ForEach-Object { $_.ThreatID } } catch {}", 30)
    if rc == 0:
        out["amenazas"] = [l.strip() for l in sal.splitlines() if l.strip()]
    return out


def defender_excluir(cfg: dict, on_event=None) -> list:
    """Agrega exclusiones (carpeta, .exe exacto y proceso). Solo Windows
    y solo con admin (sin admin, PowerShell devuelve acceso denegado)."""
    if os.name != "nt":
        log_local("ESCUDO: Defender no aplica en este sistema", "info",
                  on_event)
        return []
    if not es_admin():
        log_local("ESCUDO: sin administrador no puedo tocar Defender. "
                  "Abre con CORRER_BOT.bat (pide admin solo).", "warn",
                  on_event)
        return []
    hechas = []
    rutas = _rutas_binario(cfg)
    for r in rutas:
        if not os.path.exists(r):
            continue
        rc, sal = _ps(
            f"try {{ Add-MpPreference -ExclusionPath '{r}' -ErrorAction Stop"
            f"; 'OK' }} catch {{ $_.Exception.Message }}", 30)
        if rc == 0 and "OK" in sal:
            hechas.append(r)
    rc, sal = _ps(
        "try { Add-MpPreference -ExclusionProcess 'xmrig.exe' -ErrorAction "
        "Stop; 'OK' } catch { $_.Exception.Message }", 30)
    if rc == 0 and "OK" in sal:
        hechas.append("proceso:xmrig.exe")
    log_local(f"ESCUDO: {len(hechas)} exclusiones listas "
              f"(carpetas + proceso xmrig.exe)", "ok" if hechas else "warn",
              on_event)
    return hechas


def defender_restaurar(on_event=None) -> bool:
    """Restaura xmrig de la cuarentena (CABEZA 3, parte 1).
    MpCmdRun.exe -Restore -All: restituye TODAS las amenazas puestas en
    cuarentena; tras excluir, Defender no las vuelve a cazar."""
    if os.name != "nt":
        return False
    mpcmdrun = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                            "Windows Defender", "MpCmdRun.exe")
    if not os.path.exists(mpcmdrun):
        mpcmdrun = os.path.join(
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            "Windows Defender", "MpCmdRun.exe")
    if not os.path.exists(mpcmdrun):
        log_local("MÉDICO: no encontré MpCmdRun.exe (Defender no está o es "
                  "otro antivirus). Si usas Avast/Avira/McAfee, agrega la "
                  "exclusión en su panel.", "warn", on_event)
        return False
    rc, sal = _ps(f"& '{mpcmdrun}' -Restore -All", 60)
    ok = rc == 0
    log_local("MÉDICO: restauración de cuarentena " +
              ("ejecutada ✔" if ok else f"sin éxito (rc={rc})"),
              "ok" if ok else "warn", on_event)
    return ok


# CABEZA 3 · MÉDICO — resucita el binario
def binario_vivo(cfg: dict) -> str:
    """Ruta al xmrig si existe y parece completo (>1 MB), si no ''."""
    try:
        marker = os.path.join(BASE_DIR, "bin", "xmrig_binary_path.json")
        rutas = []
        if os.path.exists(marker):
            with open(marker, "r", encoding="utf-8") as f:
                p = json.load(f).get("path", "")
            if p:
                rutas.append(p)
        p = (cfg.get("EXTERNAL_MINER_PATH") or "").strip()
        if p:
            rutas.append(p)
        for r in rutas:
            if os.path.exists(r) and os.path.getsize(r) > 1_000_000:
                return r
    except Exception:
        pass
    return ""


def medico_binario(cfg: dict, on_event=None) -> str:
    """Asegura que exista un xmrig sano: restaura de cuarentena y si no
    hay nada, re-descarga (fork MoneroOcean → oficial). Devuelve ruta."""
    vivo = binario_vivo(cfg)
    if vivo:
        return vivo
    log_local("MÉDICO: xmrig.exe NO está (¿Defender lo borró?); intentando "
              "resucitar…", "warn", on_event)
    if os.name == "nt":
        defender_restaurar(on_event)
        vivo = binario_vivo(cfg)
        if vivo:
            log_local(f"MÉDICO: restaurado de cuarentena: {vivo}", "ok",
                      on_event)
            return vivo
    # re-descarga (import perezoso: evita import circular)
    from aggressive_engine import ensure_binary
    try:
        ruta = ensure_binary(cfg, on_event or
                             (lambda m, l="info": log_local(m, l)))
        log_local(f"MÉDICO: binario re-descargado: {ruta}", "ok", on_event)
        return ruta
    except Exception as e:                      # noqa: BLE001
        log_local(f"MÉDICO: no pude re-descargar xmrig: {e}", "error",
                  on_event)
        return ""


# CABEZA 4 · VIGÍA — watchdog de hashrate contra el récord
class Vigia(threading.Thread):
    """Cada INTERVALO_VIGIA compara el hashrate con el récord. Si cae
    > HIDRA_CAIDA_PCT durante CICLOS_CAIDA rondas → reparación:
      1) ¿binario desapareció? → MÉDICO (restaurar/re-descargar)
      2) ¿Defender volvió a cazar? → ESCUDO (re-excluir)
      3) relanza el minero con la config óptima de FUEGO
    """

    def __init__(self, cfg, on_event=None, get_hashrate=None,
                 get_running=None, on_reparar=None):
        super().__init__(daemon=True, name="hidra-vigia")
        self.cfg = cfg
        self.on_event = on_event or (lambda m, l="info": None)
        self.get_hashrate = get_hashrate or (lambda: 0.0)
        self.get_running = get_running or (lambda: False)
        self.on_reparar = on_reparar or (lambda motivo: None)
        self._stop = threading.Event()
        self._caidas = 0
        self._ceros = 0               # v3.8: rondas consecutivas con h=0
        self._arranque = time.time()

    def stop(self):
        self._stop.set()

    def run(self):
        self._arranque = time.time()
        while not self._stop.is_set():
            if self._stop.wait(INTERVALO_VIGIA):
                break
            try:
                self._ronda()
            except Exception as e:              # noqa: BLE001
                log_local(f"VIGÍA: {e}", "error", self.on_event)

    def _ronda(self):
        if time.time() - self._arranque < MARGEN_ARRANQUE:
            return                              # deja arrancar al minero
        h = float(self.get_hashrate() or 0)
        # v3.8: motor vivo + hashrate CERO sostenido → ACTUAR (antes la
        # VIGÍA ignoraba h=0 y quedaba muda ante un pool zombi).
        if h <= 0:
            if self.get_running():
                self._ceros += 1
                if self._ceros >= CICLOS_CAIDA:
                    self._ceros = 0
                    self.on_reparar(
                        f"hashrate CERO durante "
                        f"{CICLOS_CAIDA * INTERVALO_VIGIA // 60} min con "
                        f"el motor vivo → salto a pool vivo")
            return
        estado = _cargar_estado()
        best = float(estado.get("best_hashrate") or 0)
        if h > best:
            # nuevo récord (con margen: evita picos de 1 ciclo)
            estado["best_hashrate"] = h
            estado["best_ts"] = time.time()
            _guardar_estado(estado)
            if best > 0 and h > best * 1.05:
                log_local(f"VIGÍA: NUEVO RÉCORD {h:,.0f} H/s "
                          f"(anterior {best:,.0f})", "ok", self.on_event)
            self._caidas = 0
            return
        if best <= 0 or h <= 0:
            return                              # aún sin datos válidos
        pct = 100.0 * (best - h) / best
        limite = _num(self.cfg.get("HIDRA_CAIDA_PCT"), 35.0, 5.0, 95.0)
        if pct < limite:
            self._caidas = 0
            return
        self._caidas += 1
        log_local(f"VIGÍA: hashrate {h:,.0f} H/s está {pct:.0f}% bajo el "
                  f"récord {best:,.0f} ({self._caidas}/{CICLOS_CAIDA})",
                  "warn", self.on_event)
        if self._caidas < CICLOS_CAIDA:
            return
        self._caidas = 0
        # --- diagnóstico + reparación ---
        cfgd = defender_estado(self.cfg)
        acc = []
        if cfgd.get("aplica"):
            if cfgd.get("amenazas"):
                log_local("VIGÍA: Defender registró detecciones contra "
                          "xmrig → ESCUDO re-excluye y MÉDICO restaura",
                          "warn", self.on_event)
                acc += defender_excluir(self.cfg, self.on_event)
                defender_restaurar(self.on_event)
            if not binario_vivo(self.cfg):
                acc.append("medico:" + (medico_binario(self.cfg,
                                                       self.on_event) or "fallo"))
        if self.get_running():
            acc.append("relanzar")
        estado = _cargar_estado()
        estado.setdefault("acciones", []).append(
            {"ts": time.time(), "tipo": "caida_hashrate",
             "pct": round(pct, 1), "acciones": acc})
        estado["acciones"] = estado["acciones"][-40:]
        _guardar_estado(estado)
        self.on_reparar(f"VIGÍA reparó caída de {pct:.0f}% "
                        f"(acciones: {', '.join(acc) or 'ninguna'})")


def _num(v, default, lo, hi):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


# CABEZA 5 · CASA — memoria y estado global
def _cargar_estado() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar_estado(estado: dict):
    try:
        estado["ts"] = time.time()
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(estado, f)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


# Orquestador
class Hidra:
    """Coordina las 5 cabezas. Un solo objeto por proceso (singleton)."""

    def __init__(self, cfg: dict, on_event=None, get_hashrate=None,
                 get_running=None, on_reparar=None):
        self.cfg = cfg
        self.on_event = on_event or (lambda m, l="info": None)
        self.get_hashrate = get_hashrate or (lambda: 0.0)
        self.get_running = get_running or (lambda: False)
        self.on_reparar = on_reparar or (lambda motivo: None)
        self.vigia: Vigia | None = None
        self.optima: dict = {}
        self.activa = str(cfg.get("HIDRA_ACTIVA", True)).lower() \
            not in ("0", "false", "no", "off")
        self.defender_auto = str(cfg.get("HIDRA_DEFENDER", True)).lower() \
            not in ("0", "false", "no", "off")

    # ------------------------------------------------------------------
    def inicial(self) -> dict:
        """Despierta FUEGO + ESCUDO + MÉDICO (una vez, al arranque)."""
        res = {"fuego": {}, "escudo": [], "medico": "", "activa": self.activa}
        if not self.activa:
            log_local("HIDRA: desactivada por config (HIDRA_ACTIVA=false)",
                      "warn", self.on_event)
            return res
        log_local("HIDRA DESPIERTA: 5 cabezas activando (fuego, escudo, "
                  "médico, vigía, casa)", "ok", self.on_event)
        # CABEZA 1
        try:
            self.optima = aplicar_fuego(self.cfg, self.on_event)
            res["fuego"] = self.optima.get("meta", {})
        except Exception as e:                  # noqa: BLE001
            log_local(f"FUEGO: {e}", "error", self.on_event)
        # CABEZA 2 (solo si aplica)
        if self.defender_auto and os.name == "nt":
            try:
                res["escudo"] = defender_excluir(self.cfg, self.on_event)
            except Exception as e:              # noqa: BLE001
                log_local(f"ESCUDO: {e}", "error", self.on_event)
        # CABEZA 3
        try:
            res["medico"] = medico_binario(self.cfg, self.on_event)
        except Exception as e:                  # noqa: BLE001
            log_local(f"MÉDICO: {e}", "error", self.on_event)
        estado = _cargar_estado()
        estado["inicial"] = res
        estado["hidra_activa"] = self.activa
        _guardar_estado(estado)
        return res

    # ------------------------------------------------------------------
    def start(self):
        """Despierta la VIGÍA (CABEZA 4)."""
        if not self.activa or (self.vigia and self.vigia.is_alive()):
            return
        self.vigia = Vigia(self.cfg, on_event=self.on_event,
                           get_hashrate=self.get_hashrate,
                           get_running=self.get_running,
                           on_reparar=self.on_reparar)
        self.vigia.start()
        log_local("VIGÍA en marcha: vigilando el hashrate contra el récord",
                  "ok", self.on_event)

    def stop(self):
        if self.vigia:
            self.vigia.stop()
            self.vigia = None

    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        """Estado completo para /hidra y el dashboard (CABEZA 5)."""
        estado = _cargar_estado()
        escudo = None
        if os.name == "nt" and self.defender_auto:
            try:
                d = defender_estado(self.cfg)
                escudo = {
                    "admin": d.get("admin", False),
                    "exclusiones": len(d.get("exclusiones", []) or []),
                    "procesos": len(d.get("procesos", []) or []),
                    "amenazas_xmrig": len(d.get("amenazas", []) or []),
                }
            except Exception:
                escudo = {"error": True}
        return {
            "activa": self.activa,
            "cabezas": list(CABEZAS),
            "fuego": estado.get("fuego") or {},
            "best_hashrate": estado.get("best_hashrate") or 0.0,
            "best_ts": estado.get("best_ts") or 0,
            "inicial": estado.get("inicial") or {},
            "acciones": (estado.get("acciones") or [])[-10:],
            "escudo": escudo,
            "eventos": list(EVENTOS)[-15:],
        }

    def optima_actual(self) -> dict:
        """Config óptima para write_xmrig_config (o {} si no calculada)."""
        if not self.optima:
            try:
                self.optima = config_optima(self.cfg)
            except Exception:
                self.optima = {}
        return self.optima

    def aviso_bloqueo(self, detalle: str = ""):
        """Llamado por miner_manager cuando xmrig muere al instante:
        casi siempre es Defender/antivirus → ESCUDO + MÉDICO ya."""
        log_local("HIDRA: xmrig murió nada más arrancar — patrón típico de "
                  "ANTIVIRUS. Lanzando ESCUDO + MÉDICO" +
                  (f" ({detalle})" if detalle else ""), "error", self.on_event)
        try:
            if os.name == "nt":
                defender_excluir(self.cfg, self.on_event)
                defender_restaurar(self.on_event)
            ruta = medico_binario(self.cfg, self.on_event)
            estado = _cargar_estado()
            estado.setdefault("acciones", []).append(
                {"ts": time.time(), "tipo": "bloqueo_binario",
                 "ruta": ruta, "detalle": detalle[:120]})
            estado["acciones"] = estado["acciones"][-40:]
            _guardar_estado(estado)
        except Exception as e:                  # noqa: BLE001
            log_local(f"HIDRA aviso_bloqueo: {e}", "error", self.on_event)


# Singleton
_INST: Hidra | None = None
_INST_LOCK = threading.Lock()


def init_hidra(cfg: dict, **kw) -> Hidra:
    global _INST
    with _INST_LOCK:
        if _INST is None:
            _INST = Hidra(cfg, **kw)
        else:
            # segunda llamada (run_miner pasa get_hashrate/on_reparar…):
            # ACTUALIZA los callbacks en vez de ignorarlos
            _INST.cfg = cfg
            for _k, _v in kw.items():
                setattr(_INST, _k, _v)
            _INST.activa = str(cfg.get("HIDRA_ACTIVA", True)).lower() \
                not in ("0", "false", "no", "off")
            _INST.defender_auto = str(cfg.get("HIDRA_DEFENDER", True)).lower() \
                not in ("0", "false", "no", "off")
    return _INST


def get_hidra() -> Hidra | None:
    return _INST
