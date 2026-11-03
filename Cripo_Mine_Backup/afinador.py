"""
afinador.py — v4.5 · AUTO-TUNING DE TU CPU (HP Pavilion i5 + Iris Graphics)
===========================================================================
"Haz tú las pruebas, prueba hasta conseguir la proximidad, saca el máximo."
Este módulo hace EXACTAMENTE eso, EN TU MÁQUINA (el sandbox no tiene tus
thermals ni tu L3, y aquí las medición de RandomX miente):

  1) Barrido de hilos: corre xmrig con N = 8,7,6,4,2... hilos (5 min cada
     uno, mismos pool/wallet), mide hashrate 10s cada 10 s vía API :4068
     y se queda con el SOSTENIDO (promedio del último minuto, inmune al
     pico de arranque y al throttle inicial).
  2) Regla RandomX integrada: con la L3 conocida prueba el tope 2MB/hilo
     (i5 con 8MB de L3 → 4 hilos reales, no 8 lógicos).
  3) Sonda GPU (Iris Graphics): 3.5 min con OpenCL activo y CPU apagado.
     Si tu driver la deja minar, se activa como cabecera extra (MoneroOcean
     le asigna el algoritmo más rentable: kawpow/autolykos/etc). Si falla
     o cuelga, el timeout la mata y queda desactivada. Cero riesgo.
  4) Resultado → data/afinado.json: el daemon (FUEGO) lo respeta a partir
     del próximo CORRER_BOT.bat. Cada corrida sobreescribe con lo medido.

Salida por consola 100% ASCII (sin acentos: consolas Windows lo agradecen).
"""
import json
import os
import platform
import statistics
import subprocess
import sys
import time

import requests

from hidra_minera import info_cpu

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
AFINADO_FILE = os.path.join(DATA, "afinado.json")
LOG_LAST = os.path.join(DATA, "afinador_last.log")
API = "http://127.0.0.1:4068/2/summary"
UMBRAL_TIE = 0.03          # empate <3%: gana MENOS hilos (menos calor)
THROTTLE_RATIO = 0.70      # sostenido <70% del pico = throttle visible
INIT_MAX = 420             # s para inicializar RandomX (peor caso laptop)
SEG_CAND = 300             # s de medición por candidato de hilos
SEG_GPU = 210              # s de sonda GPU


# ---------------------------------------------------------------------------
# CPU: L3 y candidatos
# ---------------------------------------------------------------------------
def l3_cache_mb() -> int | None:
    """MB de caché L3 (None si no se puede saber). Windows/Linux."""
    try:
        if os.name == "nt":
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_Processor).L3CacheSize"],
                capture_output=True, text=True, timeout=30)
            kb = int((r.stdout or "0").strip().splitlines()[0] or 0)
            return round(kb / 1024) if kb else None
        for i in (0, 1, 2, 3):
            p = f"/sys/devices/system/cpu/cpu0/cache/index{i}/size"
            lv = f"/sys/devices/system/cpu/cpu0/cache/index{i}/level"
            try:
                with open(lv) as f:
                    if f.read().strip() != "3":
                        continue
                with open(p) as f:
                    s = f.read().strip().upper()
                return int(s[:-1]) // 1024 if s.endswith("K") else \
                    int(s[:-1]) * 1024 if s.endswith("M") else None
            except Exception:              # noqa: BLE001
                continue
    except Exception:                      # noqa: BLE001
        pass
    return None


def candidatos(logicos: int, fisicos: int, l3: int | None) -> list[int]:
    """Candidatos de hilos: lógicos, -2, físicos, mitad, tope L3 (2MB/h)."""
    fis = fisicos or max(1, logicos // 2)
    base = {logicos, max(1, logicos - 2), fis, max(2, fis // 2), 1}
    if l3 and l3 >= 2:
        base.add(min(logicos, l3 // 2))
    return sorted({c for c in base if 1 <= c <= max(1, logicos)},
                  reverse=True)


# ---------------------------------------------------------------------------
# Config xmrig por candidato (proyecto: donate 0, huge pages, MSR, API)
# ---------------------------------------------------------------------------
def escribir_config(hilos: int, pool_url: str, user: str, path: str,
                    opencl: bool = False, cpu_on: bool = True) -> str:
    cfg = {
        "autosave": False,
        "donate-level": 0,
        "cpu": {
            "enabled": cpu_on,
            "hw-aes": None,
            "priority": 2,
            "max-threads-hint": max(1, int(hilos)),
            "huge-pages": True,
            "huge-pages-jit": True,
            "memory-pool": True,
            "yield": True,
            "asm": True,
        },
        "randomx": {"init": -1, "mode": "auto", "1gb-pages": True,
                    "rdmsr": True, "wrmsr": True, "numa": True,
                    "scratchpad_prefetch_mode": 1},
        "opencl": ({"enabled": True, "cache": True, "intel": True,
                    "amd": False, "nvidia": False} if opencl
                   else {"enabled": False}),
        "pools": [{"url": pool_url, "user": user, "pass": "afinar",
                   "rig-id": None, "nicehash": False, "tls": False,
                   "keepalive": True, "enabled": True}],
        "print-time": 60,
        "http": {"enabled": True, "host": "127.0.0.1", "port": 4068,
                 "access-token": None, "restricted": True},
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return path


# ---------------------------------------------------------------------------
# Medición
# ---------------------------------------------------------------------------
def api_summary(timeout=4):
    try:
        r = requests.get(API, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:                      # noqa: BLE001
        pass
    return None


def h10_actual(resumen: dict) -> float:
    try:
        tot = (resumen.get("hashrate") or {}).get("total") or []
        return float(tot[0] or 0) if tot else 0.0
    except Exception:                      # noqa: BLE001
        return 0.0


def api_viva() -> bool:
    """Si :4068 ya responde hay OTRO xmrig (el bot): AFINAR pide cerrarlo."""
    return api_summary(timeout=2) is not None


def _matar(proc):
    try:
        proc.terminate()
        proc.wait(timeout=8)
    except Exception:                      # noqa: BLE001
        try:
            proc.kill()
        except Exception:                  # noqa: BLE001
            pass


def medir(bin_path: str, hilos: int, seg: int, pool_url: str, user: str,
          etiqueta: str, opencl: bool = False, cpu_on: bool = True) -> dict:
    """Corre xmrig 1 vez, espera init, mide y mata. Nunca explota."""
    cfgp = escribir_config(hilos, pool_url, user,
                           os.path.join(DATA, f"afinador_{etiqueta}.json"),
                           opencl=opencl, cpu_on=cpu_on)
    res = {"etiqueta": etiqueta, "hilos": hilos, "ok": False,
           "h_sostenido": 0.0, "h_pico": 0.0, "throttle": False,
           "init_s": None, "muestras": 0}
    log = open(LOG_LAST, "ab", buffering=0)
    try:
        log.write(f"\n=== {etiqueta} hilos={hilos} opencl={opencl} "
                  f"{time.strftime('%H:%M:%S')}\n".encode())
        proc = subprocess.Popen(
            [bin_path, "-c", cfgp], cwd=DATA,
            stdout=log, stderr=subprocess.STDOUT)
    except Exception as e:                 # noqa: BLE001
        res["motivo"] = f"no se pudo lanzar xmrig: {e}"
        return res
    t0 = time.time()
    while time.time() - t0 < INIT_MAX:
        time.sleep(5)
        r = api_summary()
        if r and h10_actual(r) > 0:
            res["init_s"] = round(time.time() - t0)
            break
        if proc.poll() is not None:
            res["motivo"] = "xmrig se salio (revisa data/afinador_last.log)"
            return res
    else:
        _matar(proc)
        res["motivo"] = (f"no inicializo en {INIT_MAX}s "
                         "(en admin va mas rapido: MSR + huge pages)")
        return res
    fin = time.time() + seg
    ts_h = []
    while time.time() < fin:
        time.sleep(10)
        h = h10_actual(api_summary() or {})
        ts_h.append((time.time(), h))
    _matar(proc)
    if not ts_h or max(h for _, h in ts_h) <= 0:
        res["motivo"] = "sin hashrate tras inicializar"
        return res
    res["muestras"] = len(ts_h)
    res["h_pico"] = round(max(h for _, h in ts_h), 1)
    corte = fin - 120
    cola = [h for t, h in ts_h if t >= corte] or [h for _, h in ts_h[-3:]]
    res["h_sostenido"] = round(statistics.mean(cola), 1)
    res["throttle"] = bool(res["h_pico"] > 0 and
                           res["h_sostenido"] < THROTTLE_RATIO * res["h_pico"])
    res["ok"] = True
    return res


# ---------------------------------------------------------------------------
# Elección y persistencia
# ---------------------------------------------------------------------------
def elegir(resultados: list[dict]) -> dict | None:
    """Gana el mayor sostenido; empate <3% → menos hilos (menos calor)."""
    oks = [r for r in resultados if r.get("ok") and r.get("h_sostenido", 0) > 0]
    if not oks:
        return None
    oks.sort(key=lambda r: (-r["h_sostenido"], r["hilos"]))
    mejor = oks[0]
    for r in oks[1:]:
        if r["h_sostenido"] >= mejor["h_sostenido"] * (1 - UMBRAL_TIE) \
                and r["hilos"] < mejor["hilos"]:
            mejor = r
    return mejor


def guardar_afinado(data: dict):
    os.makedirs(DATA, exist_ok=True)
    data["host"] = platform.node()
    data["ts"] = time.time()
    with open(AFINADO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def leer_afinado() -> dict:
    try:
        with open(AFINADO_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:                      # noqa: BLE001
        return {}


def _bin_xmrig() -> str:
    nombre = "xmrig.exe" if os.name == "nt" else "xmrig"
    p = os.path.join(DATA, "bin", "xmrig-mo", nombre)
    return p if os.path.exists(p) else ""


def _pool_user() -> tuple[str, str]:
    from config import load_secrets
    from pools_catalog import TARGETS
    from wallet_monero import ensure_wallet
    pool = TARGETS[0]["url"]               # MoneroOcean: VIVO y auto-algo
    cfg = load_secrets()
    addr, _ = ensure_wallet(cfg)
    return pool, addr


def _imprimir_fila(r: dict):
    if r.get("ok"):
        print(f"  {r['etiqueta']:<12} sostenido={r['h_sostenido']:>9,.1f} H/s "
              f"pico={r['h_pico']:>9,.1f} throttle="
              f"{'SI' if r['throttle'] else 'no'} init={r['init_s']}s")
    else:
        print(f"  {r['etiqueta']:<12} NO MEDIDO: {r.get('motivo', '?')}")


# ---------------------------------------------------------------------------
def main() -> int:
    print("=" * 62)
    print(" AFINADOR CRIPRO_MINE v4.5 - maximo hashrate para TU maquina")
    print("=" * 62)
    if api_viva():
        print("[X] El bot esta corriendo (API :4068 viva).")
        print("    Cierra todo con DETENER_TODO.bat y vuelve a lanzar AFINAR.bat")
        return 2
    bina = _bin_xmrig()
    if not bina:
        print("[X] No encuentro xmrig en data/bin/xmrig-mo/.")
        print("    Corre CORRER_BOT.bat una vez (el MEDICO lo descarga).")
        return 2
    pool, user = _pool_user()
    info = info_cpu()
    l3 = l3_cache_mb()
    logicos = int(info.get("logicos") or os.cpu_count() or 1)
    fisicos = int(info.get("fisicos") or 0)
    print(f"CPU: {logicos} logicos / {fisicos or '?'} fisicos | "
          f"L3={l3 if l3 else '?'} MB | pool={pool}")
    print(f"Wallet: {user[:10]}...{user[-6:] if len(user) > 16 else ''}")
    cands = candidatos(logicos, fisicos, l3)
    print(f"Plan: {len(cands)} candidatos x {SEG_CAND // 60} min + sonda GPU "
          f"~{(len(cands) * (SEG_CAND + 90) + SEG_GPU) // 60} min total")
    print("NO uses la laptop durante la medicion (ensuciaria los datos).")
    resultados = []
    for n in cands:
        print(f"[..] midiendo con {n} hilos...")
        r = medir(bina, n, SEG_CAND, pool, user, etiqueta=f"hilos={n}")
        _imprimir_fila(r)
        resultados.append(r)
    print("[..] sonda GPU Iris (OpenCL, CPU apagado)...")
    gpu = medir(bina, 0, SEG_GPU, pool, user, etiqueta="gpu-iris",
                opencl=True, cpu_on=False)
    _imprimir_fila(gpu)
    ganador = elegir(resultados)
    estado = {"resultados": resultados, "gpu": gpu,
              "l3_mb": l3, "logicos": logicos, "fisicos": fisicos}
    if ganador:
        estado["hilos"] = ganador["hilos"]
        estado["opencl"] = bool(gpu.get("ok") and gpu.get("h_sostenido", 0) > 0)
        estado["gpu_h"] = gpu.get("h_sostenido", 0.0)
        guardar_afinado(estado)
        print("=" * 62)
        print(f" GANADOR: {ganador['hilos']} hilos "
              f"({ganador['h_sostenido']:,.1f} H/s sostenidos)")
        if estado["opencl"]:
            print(f" GPU Iris ACTIVA como segunda cabeza "
                  f"({estado['gpu_h']:,.1f} H/s de regalo)")
        print(" APLICADO en data/afinado.json: el proximo CORRER_BOT.bat")
        print(" minara con esta configuracion (FUEGO la respeta).")
        print("=" * 62)
    else:
        estado["hilos"] = 0
        estado["opencl"] = False
        guardar_afinado(estado)
        print("=" * 62)
        print(" Ningun candidato midio hashrate (entorno sin RandomX o")
        print(" sin admin). NO se cambio nada: FUEGO seguira usando su")
        print(" regla fisica. En tu laptop, corre AFINAR.bat como admin.")
        print("=" * 62)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[!] Cancelado por el usuario.")
        sys.exit(130)
