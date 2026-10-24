"""
pools_salud.py — SALUD REAL de los pools: handshake stratum + registro zombi
===========================================================================
Problema que resuelve (causa raíz del "hashrate 0 desde hace rato", v3.8):

  El motor elegía pool por LATENCIA TCP. Un pool ZOMBI (accepta la conexión
  TCP pero nunca responde al protocolo stratum — pasó con rx.unmineable.com
  el 2026-10-23 y 24, TCP y SSL) se ve "rápido" a nivel TCP, así que el
  motor lo elegía, xmrig conectaba, no recibía JAMÁS un job y el hashrate
  quedaba en 0 PARA SIEMPRE (con 1 solo objetivo el failover no rota).

Solución:
  • stratum_ok(): handshake REAL — envía mining.subscribe y espera respuesta
    JSON válida (docs: xmrig.com/developer → stratum; SPEC stratum JSON).
  • Registro persistente de zombis (data/pool_salud.json) con COOLDOWN:
    mientras un pool está en cooldown ni siquiera se le toca la red (cero
    latencia añadida); al vencer el cooldown se le re-sondea una vez.
  • probe_salud(url): ms de respuesta REAL o None si zombi/muerto.
  • limpiar_marca(url) y estado_salud() para diagnóstico, /hidra y dashboard.

Nunca explota y es seguro importarlo desde cualquier hilo (lock interno).
"""
import json
import os
import socket
import ssl
import threading
import time

from config import DATA_DIR

SALUD_FILE = os.path.join(DATA_DIR, "pool_salud.json")
ZOMBI_COOLDOWN = 300           # 5 min sin tocar un pool marcado zombi
                               # (v3.9: reducido de 20 min para detectar
                               # recuperación de pools más rápido)
HANDSHAKE_TIMEOUT = 5.0        # seg. para TODO el handshake stratum
_LOCK = threading.Lock()

_SUBSCRIBE = json.dumps({"id": 1, "method": "mining.subscribe",
                         "params": ["cripo-mine/3.8"]}) + "\n"


# ---------------------------------------------------------------------------
# Registro persistente de salud
# ---------------------------------------------------------------------------
def _cargar() -> dict:
    try:
        with open(SALUD_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _guardar(reg: dict):
    try:
        os.makedirs(os.path.dirname(SALUD_FILE), exist_ok=True)
        tmp = SALUD_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(reg, f)
        os.replace(tmp, SALUD_FILE)
    except Exception:
        pass


def _parse_url(url: str):
    """'stratum+ssl://host:port' | 'host:port' → (host, port, ssl)."""
    u = (url or "").strip()
    use_ssl = "ssl" in u.split("://")[0] if "://" in u else False
    host = u.split("://")[-1]
    host, _, port = host.partition(":")
    try:
        port = int(port or 3333)
    except ValueError:
        port = 3333
    return host, port, use_ssl


def limpiar_marca(url: str):
    """Borra la marca zombi de un pool para forzar re-sondeo inmediato."""
    with _LOCK:
        reg = _cargar()
        host, port, _ = _parse_url(url)
        key = f"{host}:{port}"
        if key in reg:
            reg.pop(key, None)
            _guardar(reg)


def estado_salud() -> dict:
    """Copia del registro para /hidra, dashboard y diagnostico.py."""
    with _LOCK:
        reg = _cargar()
    ahora = time.time()
    out = {}
    for key, v in reg.items():
        zombi = v.get("zombi_hasta", 0) > ahora
        out[key] = {
            "zombi": zombi,
            "cooldown_restante": round(v.get("zombi_hasta", 0) - ahora)
                                 if zombi else 0,
            "ultimo_ok": v.get("ultimo_ok", 0),
            "ultimo_ms": v.get("ultimo_ms", 0),
            "detalle": (v.get("detalle") or "")[:120],
        }
    return out


def zombi_hasta(url: str) -> float:
    host, port, _ = _parse_url(url)
    with _LOCK:
        v = _cargar().get(f"{host}:{port}") or {}
    return float(v.get("zombi_hasta", 0) or 0)


# ---------------------------------------------------------------------------
# Handshake stratum REAL
# ---------------------------------------------------------------------------
def stratum_ok(host: str, port: int, use_ssl: bool = False,
               timeout: float = HANDSHAKE_TIMEOUT):
    """Handshake de verdad: mining.subscribe → respuesta JSON con id=1.
    Devuelve (ok: bool, detalle: str, ms: float|None).
      ok=True  → el pool habla stratum (aunque sea con un error de auth)
      ok=False → zombi (TCP OK, 0 bytes) o error de red/DNS/TLS
    """
    t0 = time.time()
    try:
        raw = socket.create_connection((host, port), timeout=timeout)
        raw.settimeout(timeout)
        if use_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            s = ctx.wrap_socket(raw, server_hostname=host)
        else:
            s = raw
        s.sendall(_SUBSCRIBE.encode())
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            if b"\n" in buf:
                break
        try:
            s.close()
        except Exception:
            pass
        ms = round((time.time() - t0) * 1000)
        if not buf:
            return False, "zombi: TCP OK pero 0 bytes al subscribe", ms
        for line in buf.split(b"\n"):
            line = line.strip()
            if not line:
                continue
            try:
                j = json.loads(line)
            except Exception:
                continue
            if j.get("id") == 1 and ("result" in j or "error" in j):
                return True, f"subscribe OK ({str(j.get('result'))[:30]})", ms
        return True, f"respuesta stratum no estándar: {buf[:50]!r}", ms
    except Exception as e:                      # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:70]}", None


# ---------------------------------------------------------------------------
# API principal: sondeo con memoria de zombis
# ---------------------------------------------------------------------------
def probe_salud(url: str, timeout: float = HANDSHAKE_TIMEOUT,
                force: bool = False):
    """Devuelve ms de respuesta REAL del pool, o None si está zombi/muerto
    (o en cooldown de zombi). Con force=True ignora el cooldown."""
    host, port, use_ssl = _parse_url(url)
    key = f"{host}:{port}"
    if not force:
        with _LOCK:
            v = _cargar().get(key) or {}
        if float(v.get("zombi_hasta", 0) or 0) > time.time():
            return None
    ok, detalle, ms = stratum_ok(host, port, use_ssl, timeout)
    with _LOCK:
        reg = _cargar()
        prev = reg.get(key) or {}
        entry = {"detalle": detalle, "ultimo_ms": ms or prev.get("ultimo_ms", 0)}
        if ok:
            entry["ultimo_ok"] = time.time()
            entry["zombi_hasta"] = 0
        else:
            entry["ultimo_fail"] = time.time()
            entry["zombi_hasta"] = time.time() + ZOMBI_COOLDOWN
        reg[key] = entry
        _guardar(reg)
    return ms if ok else None


def sondear_muchos(urls: list, timeout: float = HANDSHAKE_TIMEOUT) -> dict:
    """Sondea varios pools EN PARALELO → {url: ms o None}. Sin bloquear."""
    from concurrent.futures import ThreadPoolExecutor
    out = {}
    with ThreadPoolExecutor(max_workers=min(8, max(2, len(urls) or 1))) as ex:
        futs = {ex.submit(probe_salud, u, timeout): u for u in urls}
        for f in futs:
            u = futs[f]
            try:
                out[u] = f.result()
            except Exception:                   # noqa: BLE001
                out[u] = None
    return out
