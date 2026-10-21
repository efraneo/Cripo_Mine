"""
stratum_miner.py — Minero Stratum SHA-256 nativo en Python
==========================================================
Implementa el protocolo Stratum V1 (subscribe/authorize/notify/submit) con
double-SHA256 real sobre CPU. Es funcional (shares reales en pools con
dificultad baja) aunque lento: es educativo y de prueba de concepto.
Referencia: github.com/ricmoo/nightminer y docs de stratum V1.

Incluye tres motores con la misma interfaz pública:
  • StratumMiner → conecta a un pool real (stratum+tcp / stratum+ssl)
  • BenchMiner   → hashea en local sin pool (mide tu CPU)
  • DemoMiner    → simulación con datos sintéticos para probar el dashboard

Interfaz común:  .start()  .stop()  .is_running()  .stats()
Callbacks: on_event(msg, level), on_share(job, nonce, status), on_stats(dict)
"""
import binascii
import hashlib
import json
import random
import socket
import ssl as ssl_mod
import struct
import threading
import time
from fractions import Fraction

DIFF1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000


def dsha(data: bytes) -> bytes:
    """Double SHA-256."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def difficulty_to_target(difficulty: float) -> int:
    """Target entero a partir de la dificultad del pool (exacto con Fraction)."""
    d = Fraction(max(float(difficulty), 1e-9)).limit_denominator(10 ** 9)
    tgt = Fraction(DIFF1) / d
    return max(int(tgt), 1)


def build_header(job: dict, extranonce1: bytes, extranonce2: bytes) -> bytes:
    """Construye la coinbase, el merkle root y los primeros 76 bytes del header.

    ⚠️ Orden de bytes (validado contra el bloque génesis de Bitcoin):
      • prevhash llega en orden de visualización → se REVERSA para el header.
      • El merkle root entra tal cual su digest dsha (NO se revierte).
      • version/ntime/nbits se empaquetan little-endian.
    """
    coinbase = (binascii.unhexlify(job["coinb1"]) + extranonce1 +
                extranonce2 + binascii.unhexlify(job["coinb2"]))
    root = dsha(coinbase)
    for branch in job["merkle_branch"]:
        root = dsha(root + binascii.unhexlify(branch))
    ver = struct.pack("<I", int(job["version"], 16) & 0xFFFFFFFF)
    prev = binascii.unhexlify(job["prevhash"])[::-1]
    ntime = struct.pack("<I", int(job["ntime"], 16))
    nbits = struct.pack("<I", int(job["nbits"], 16))
    return ver + prev + root + ntime + nbits


def parse_stratum_url(url: str):
    """'stratum+tcp://host:port' → (host, port, use_ssl)."""
    url = (url or "").strip()
    use_ssl = "+ssl" in url
    if "://" in url:
        url = url.split("://", 1)[1]
    host, _, port = url.partition(":")
    return host.strip(), int(port or 3333), use_ssl


class BaseMiner:
    """Estado y contadores compartidos por todos los motores."""

    MODE = "base"

    def __init__(self, on_event=None, on_share=None, on_stats=None):
        self.on_event = on_event or (lambda m, l="info": None)
        self.on_share = on_share or (lambda j, n, s: None)
        self.on_stats = on_stats or (lambda s: None)
        self._stop = threading.Event()
        self._started_at = None
        self._lock = threading.Lock()
        self._hash_count = 0
        self._last_hash_count = 0
        self._last_stat_time = time.time()
        self.difficulty = 0.0
        self.shares_ok = 0
        self.shares_rej = 0
        self.threads = {}

    # -- ciclo de vida -----------------------------------------------------
    def start(self):
        self._stop.clear()
        self._started_at = time.time()
        self.on_event(f"Motor {self.MODE} iniciado", "ok")

    def stop(self):
        self._stop.set()
        self.on_event(f"Motor {self.MODE} detenido", "warn")

    def is_running(self) -> bool:
        return not self._stop.is_set() and self._started_at is not None

    # -- contadores ----------------------------------------------------------
    def _add_hashes(self, n: int):
        with self._lock:
            self._hash_count += n

    def _make_stats(self, extra: dict = None) -> dict:
        now = time.time()
        with self._lock:
            total = self._hash_count
        dt = max(now - self._last_stat_time, 0.001)
        rate = (total - self._last_hash_count) / dt
        self._last_hash_count = total
        self._last_stat_time = now
        st = {
            "mode": self.MODE,
            "hashrate": max(rate, 0.0),
            "hashes_total": total,
            "hashes_delta": int(total - self._last_hash_count) if False else None,
            "difficulty": self.difficulty,
            "shares_ok": self.shares_ok,
            "shares_rej": self.shares_rej,
            "uptime": (now - self._started_at) if self._started_at else 0,
            "alive": self.is_running(),
        }
        st["hashes_delta"] = max(int(total - (getattr(self, "_prev_total", total))), 0)
        self._prev_total = total
        if extra:
            st.update(extra)
        return st

    # -- plantilla del bucle de estadísticas ---------------------------------
    def _stats_loop(self, interval: float = 3.0):
        while not self._stop.is_set():
            time.sleep(interval)
            if self._stop.is_set():
                break
            try:
                self.on_stats(self._make_stats())
            except Exception:
                pass


# ===========================================================================
# MINERO STRATUM REAL
# ===========================================================================
class StratumMiner(BaseMiner):
    """Cliente stratum V1 con N hilos de hash y reconexión automática."""

    MODE = "python"

    def __init__(self, pool_url: str, user: str, password: str = "x",
                 threads: int = 2, on_event=None, on_share=None, on_stats=None):
        super().__init__(on_event, on_share, on_stats)
        self.pool_url = pool_url
        self.user = user
        self.password = password or "x"
        self.threads_n = max(1, int(threads))
        # estado stratum
        self.extranonce1 = b""
        self.extranonce2_size = 4
        self.authorized = False
        self.subscribed = False
        self.connected = False
        self.job = None
        self.job_id = ""
        self._en2_counter = 0
        self._send_lock = threading.Lock()
        self._sock = None
        self._next_id = 1
        self._conn_gen = 0
        self._pending = {}          # id → respuesta (subscribe/authorize)
        self._target = DIFF1 // 1000000
        self._t_recv = None
        self._t_stats = None
        self._hash_threads = []

    # ------------------------------------------------------------------
    def start(self):
        super().start()
        self._t_recv = threading.Thread(target=self._conn_loop, daemon=True,
                                        name="stratum-conn")
        self._t_stats = threading.Thread(target=self._stats_loop, daemon=True,
                                         name="stratum-stats")
        self._t_recv.start()
        self._t_stats.start()
        for i in range(self.threads_n):
            t = threading.Thread(target=self._hash_loop, args=(i,), daemon=True,
                                 name=f"hash-{i}")
            self._hash_threads.append(t)
            t.start()
        self.on_event(f"Minero Python lanzado con {self.threads_n} hilo(s) de CPU",
                      "ok")

    def stop(self):
        super().stop()
        self._close_sock()
        self.connected = False

    # ------------------------------------------------------------------
    # Conexión / recepción
    # ------------------------------------------------------------------
    def _conn_loop(self):
        backoff = 3
        while not self._stop.is_set():
            host, port, use_ssl = parse_stratum_url(self.pool_url)
            try:
                self.on_event(f"Conectando a {host}:{port} (ssl={use_ssl})...",
                              "info")
                raw = socket.create_connection((host, port), timeout=15)
                if use_ssl:
                    ctx = ssl_mod._create_unverified_context()
                    raw = ctx.wrap_socket(raw, server_hostname=host)
                raw.settimeout(120)
                with self._lock:
                    self._sock = raw
                    self._conn_gen += 1
                    gen = self._conn_gen
                self.connected = True
                backoff = 3
                # El lector vive en SU PROPIO hilo: sin él nunca llegarían las
                # respuestas de subscribe/authorize al diccionario _pending.
                reader = threading.Thread(target=self._reader_thread,
                                          args=(gen,), daemon=True,
                                          name="stratum-recv")
                reader.start()
                self._subscribe_and_authorize()
                self._spawn_hash_threads_if_needed()
                while not self._stop.is_set() and self.connected:
                    time.sleep(0.5)
            except Exception as e:
                if self._stop.is_set():
                    break
                self.on_event(f"Fallo de conexión: {e} → reintentando en "
                              f"{backoff}s", "error")
            self.authorized = False
            self._close_sock()
            if self._stop.is_set():
                break
            t0 = 0.0
            while t0 < backoff and not self._stop.is_set():
                time.sleep(0.5)
                t0 += 0.5
            backoff = min(backoff * 1.6, 30)

    def _reader_thread(self, gen: int):
        """Envuelve _recv_loop y marca la conexión como caída al morir."""
        try:
            self._recv_loop()
            if not self._stop.is_set() and gen == self._conn_gen:
                self.on_event("El pool cerró la conexión", "warn")
        except Exception as e:
            if not self._stop.is_set() and gen == self._conn_gen:
                self.on_event(f"Conexión perdida: {e}", "error")
        finally:
            if gen == self._conn_gen:
                self.connected = False
                self.authorized = False

    def _spawn_hash_threads_if_needed(self):
        live = [t for t in self._hash_threads if t.is_alive()]
        for t in list(self._hash_threads):
            if t not in live:
                self._hash_threads.remove(t)
        while len(live) < self.threads_n:
            t = threading.Thread(target=self._hash_loop, args=(len(live),),
                                 daemon=True, name=f"hash-{len(live)}")
            self._hash_threads.append(t)
            t.start()
            live.append(t)

    def _subscribe_and_authorize(self):
        res = self._request("mining.subscribe", [])
        if not res or not isinstance(res.get("result"), list) or \
                len(res["result"]) < 3:
            raise RuntimeError("respuesta de subscribe inválida")
        with self._lock:
            self.extranonce1 = binascii.unhexlify(res["result"][1])
            self.extranonce2_size = int(res["result"][2])
            self.subscribed = True
        self.on_event(f"Suscrito (extranonce1={res['result'][1]}, "
                      f"en2_size={self.extranonce2_size})", "ok")
        user = self.user
        res2 = self._request("mining.authorize", [user, self.password])
        ok = bool(res2 and res2.get("result"))
        with self._lock:
            self.authorized = ok
        if ok:
            self.on_event(f"Autorizado en el pool como {user}", "ok")
        else:
            err = (res2 or {}).get("error")
            self.on_event(f"Pool rechazó la autorización de {user}: {err} "
                          f"(¿dirección BTC válida?)", "error")

    def _request(self, method: str, params: list) -> dict:
        with self._lock:
            # ids de petición < 1000 (los ids >= 1000 son para submits)
            rid = (self._next_id % 900) + 1
            self._next_id += 1
        self._send_json({"id": rid, "method": method, "params": params})
        # La respuesta llega por _recv_loop; para subscribe/authorize hacemos
        # una espera corta sobre _pending:
        t0 = time.time()
        while time.time() - t0 < 15:
            if self._stop.is_set():
                return {}
            with self._lock:
                if rid in self._pending:
                    return self._pending.pop(rid)
            time.sleep(0.05)
        return {}

    def _send_json(self, obj: dict):
        data = (json.dumps(obj) + "\n").encode()
        with self._lock:
            sock = self._sock
        if sock is None:
            raise ConnectionError("socket cerrado")
        with self._send_lock:
            sock.sendall(data)

    def _recv_loop(self):
        buf = b""
        sock = None
        with self._lock:
            sock = self._sock
        while not self._stop.is_set():
            try:
                chunk = sock.recv(65536)
                if not chunk:
                    raise ConnectionError("pool cerró la conexión")
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        self._handle_line(line.decode(errors="replace"))
            except Exception as e:
                if self._stop.is_set():
                    return
                raise ConnectionError(f"lectura: {e}") from e

    def _handle_line(self, line: str):
        try:
            msg = json.loads(line)
        except Exception:
            return
        if "method" in msg and msg.get("method") == "mining.notify":
            self._on_notify(msg["params"])
        elif msg.get("method") == "mining.set_difficulty":
            with self._lock:
                self.difficulty = float(msg["params"][0])
                self._target = difficulty_to_target(self.difficulty)
            self.on_event(f"Dificultad fijada por el pool: {self.difficulty}",
                          "info")
        elif msg.get("method") == "mining.set_extranonce":
            with self._lock:
                self.extranonce1 = binascii.unhexlify(msg["params"][0])
                self.extranonce2_size = int(msg["params"][1])
            self.on_event("Pool actualizó el extranonce", "info")
        elif "id" in msg and msg["id"] is not None:
            mid = msg["id"]
            if isinstance(mid, int) and mid >= 1000:
                # resultado de un mining.submit
                ok = bool(msg.get("result"))
                with self._lock:
                    self.shares_ok += int(ok)
                    self.shares_rej += int(not ok)
                label = "aceptado" if ok else "rechazado"
                err = "" if ok else f" ({(msg.get('error') or [''])[0]})"
                self.on_event(f"Share {label}{err}", "ok" if ok else "warn")
            else:
                # respuesta a subscribe/authorize → la espera _request
                with self._lock:
                    self._pending[mid] = msg

    def _on_notify(self, params):
        job = {
            "job_id": str(params[0]),
            "prevhash": str(params[1]),
            "coinb1": str(params[2]),
            "coinb2": str(params[3]),
            "merkle_branch": [str(x) for x in params[4]],
            "version": str(params[5]),
            "nbits": str(params[6]),
            "ntime": str(params[7]),
        }
        clean = bool(params[8]) if len(params) > 8 else True
        with self._lock:
            self.job = job
            self.job_id = job["job_id"]
        if clean:
            self.on_event(f"Nuevo trabajo {job['job_id']} (clean)", "info")

    # ------------------------------------------------------------------
    # Envío de shares
    # ------------------------------------------------------------------
    def _submit(self, job: dict, en2: bytes, ntime: int, nonce: int):
        try:
            self._send_json({
                "id": 1000 + (nonce % 100000),
                "method": "mining.submit",
                "params": [self.user, job["job_id"], en2.hex(),
                           f"{ntime:08x}", f"{nonce:08x}"],
            })
            self.on_share(job["job_id"], f"{nonce:08x}", "enviado")
        except Exception as e:
            self.on_event(f"No se pudo enviar share: {e}", "error")

    # ------------------------------------------------------------------
    # Hilos de hashing
    # ------------------------------------------------------------------
    def _next_en2(self) -> bytes:
        with self._lock:
            n = self._en2_counter
            self._en2_counter += 1
        try:
            return n.to_bytes(self.extranonce2_size, "big")
        except OverflowError:
            with self._lock:
                self._en2_counter = 1
            return b"\x00" * max(self.extranonce2_size, 1)

    def _current_job(self):
        with self._lock:
            return self.job

    def _hash_loop(self, tid: int):
        scan_start = (tid * 0x10000000) & 0xFFFFFFFF
        scan_stride = 0x40000000  # amplio rango por hilo sin solaparse en la práctica
        while not self._stop.is_set():
            job = self._current_job()
            if job is None:
                time.sleep(0.2)
                continue
            with self._lock:
                en1 = self.extranonce1
                target = self._target
            en2 = self._next_en2()
            try:
                base = build_header(job, en1, en2)
            except Exception:
                time.sleep(0.2)
                continue
            ntime_int = int(job["ntime"], 16)
            job_id = job["job_id"]
            nonce = scan_start
            hashes = 0
            last_check = time.time()
            while nonce < 0xFFFFFFFF:
                if self._stop.is_set():
                    return
                if time.time() - last_check > 1.0:
                    self._add_hashes(hashes)
                    hashes = 0
                    last_check = time.time()
                    if self._current_job() is None or \
                            self._current_job()["job_id"] != job_id:
                        break
                h = dsha(base + struct.pack("<I", nonce))
                hashes += 1
                if int.from_bytes(h, "little") <= target:
                    self._add_hashes(hashes)
                    hashes = 0
                    is_block = int.from_bytes(h, "little") <= DIFF1
                    self.on_event(f"¡{'BLOQUE' if is_block else 'Share'} válido "
                                  f"encontrado! nonce={nonce:08x}", "ok")
                    self.on_share(job_id, f"{nonce:08x}",
                                  "bloque" if is_block else "enviado")
                    self._submit(job, en2, ntime_int, nonce)
                nonce += 1
                if nonce % scan_stride == 0:
                    nonce = scan_start + ((nonce - scan_start) // 0x10000000 + 1) \
                        * 0x10000000
            # bucle termina → tomar nuevo trabajo

    def _close_sock(self):
        with self._lock:
            sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


# ===========================================================================
# BENCH LOCAL (sin pool)
# ===========================================================================
class BenchMiner(BaseMiner):
    """Hashea sin parar en local para medir la CPU. No envía nada."""

    MODE = "bench"
    BENCH_DIFF = 1_000_000

    def __init__(self, threads: int = 2, on_event=None, on_share=None,
                 on_stats=None):
        super().__init__(on_event, on_share, on_stats)
        self.threads_n = max(1, int(threads))
        self._threads = []
        self.difficulty = float(self.BENCH_DIFF)

    def start(self):
        super().start()
        self._target = difficulty_to_target(self.BENCH_DIFF)
        t = threading.Thread(target=self._stats_loop, daemon=True)
        self._threads.append(t)
        t.start()
        for i in range(self.threads_n):
            th = threading.Thread(target=self._hash_loop, args=(i,),
                                  daemon=True, name=f"bench-{i}")
            self._threads.append(th)
            th.start()
        self.on_event(f"Benchmark local con {self.threads_n} hilo(s)", "ok")

    def _hash_loop(self, tid: int):
        nonce = (tid * 0x11111111) & 0xFFFFFFFF
        data = b"BTC-MINER-STUDIO-BENCH-" + str(tid).encode() + b"\x00" * 20
        hashes = 0
        last = time.time()
        while not self._stop.is_set():
            h = dsha(data + struct.pack("<I", nonce))
            nonce = (nonce + 1) & 0xFFFFFFFF
            hashes += 1
            if time.time() - last > 1.0:
                self._add_hashes(hashes)
                hashes = 0
                last = time.time()
                if int.from_bytes(h, "little") <= self._target:
                    self.on_share("bench", f"{nonce:08x}", "local")


# ===========================================================================
# DEMO (simulación)
# ===========================================================================
class DemoMiner(BaseMiner):
    """Simulación con datos sintéticos, claramente etiquetada como DEMO."""

    MODE = "demo"

    def __init__(self, threads: int = 2, on_event=None, on_share=None,
                 on_stats=None):
        super().__init__(on_event, on_share, on_stats)
        self.threads_n = max(1, int(threads))
        self._threads = []
        self._base_rate = 180_000.0 * self.threads_n  # ~180 kH/s por hilo

    def start(self):
        super().start()
        self.difficulty = 0.15
        t = threading.Thread(target=self._demo_loop, daemon=True)
        self._threads.append(t)
        t.start()

    def _demo_loop(self):
        job_n = 0
        next_share = time.time() + random.uniform(4, 7)   # primer share rápido
        while not self._stop.is_set():
            time.sleep(2)
            noise = random.uniform(0.82, 1.12)
            self._add_hashes(int(self._base_rate * noise * 2))
            self.difficulty = 0.15
            job_n += 1
            now = time.time()
            if now >= next_share:
                ok = random.random() > 0.07
                self.on_share(f"demo-{job_n % 97:02d}", f"{random.getrandbits(32):08x}",
                              "aceptado" if ok else "rechazado")
                self.on_event(f"[DEMO] Share {'aceptado' if ok else 'rechazado'} "
                              f"en trabajo demo-{job_n % 97:02d}",
                              "ok" if ok else "warn")
                next_share = now + random.uniform(5, 12)
                if ok:
                    with self._lock:
                        self.shares_ok += 1
                else:
                    with self._lock:
                        self.shares_rej += 1


# ===========================================================================
# Fábrica
# ===========================================================================
def make_miner(mode: str, pool_url: str, user: str, password: str,
               threads: int, on_event, on_share, on_stats) -> BaseMiner:
    """Crea el motor según el modo seleccionado."""
    mode = (mode or "python").lower()
    if mode == "demo":
        return DemoMiner(threads, on_event, on_share, on_stats)
    if mode == "bench":
        return BenchMiner(threads, on_event, on_share, on_stats)
    return StratumMiner(pool_url, user, password, threads,
                        on_event, on_share, on_stats)
