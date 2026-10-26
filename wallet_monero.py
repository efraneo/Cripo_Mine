"""
wallet_monero.py — Generador OFFLINE de wallet Monero (HIDRA v4.0)
==================================================================
¿Por qué existe? 27-10-2026: unMineable está ZOMBI (TCP ok, 0 bytes al
subscribe) y ZergPool ya NI RESUELVE DNS (NXDOMAIN). Los únicos pools
vivos (MoneroOcean, SupportXMR, xmrpool.eu — verificados con handshake
stratum real) pagan en XMR y exigen una WALLET_XMR. Si el usuario no la
tiene configurada, el motor solo puede minar en pools muertos →
hashrate 0 para siempre.

Solución: generar la wallet MONERO aquí mismo, 100% offline (las claves
NUNCA salen del PC ni van a ninguna API) y usarla para desbloquear los
pools vivos. El archivo data/wallet_emergencia.json guarda la semilla:
QUIEN TENGA ESE ARCHIVO CONTROLA EL DINERO → el daemon avisa por
Telegram que se respalde y que, si prefieres tu propia wallet, pégala
en secrets.toml (WALLET_XMR) y esta se ignora.

Implementación (sin dependencias obligatorias):
  · keccak-256 → pycryptodome si está (requirements.txt), si no fallback
    puro (Keccak-f[1600], padding original de Keccak, NO SHA3).
  · ed25519 → aritmética de curva pura Python (RFC 8032, coords
    extendidas) tal como la usa Monero: pubkey = B * escalar (SIN clamp).
  · dirección → base58 de Monero (bloques de 8 bytes → 11 chars) sobre
    0x12 || pub_gasto || pub_vista || checksum_keccak[0:4].

CLI:  python wallet_monero.py [semilla_hex]   (imprime claves + dirección)
API:  ensure_wallet(cfg, on_event) -> (direccion, fue_creada)
"""
import hashlib
import json
import os
import stat
import sys
import time

from config import DATA_DIR

WALLET_FILE = os.path.join(DATA_DIR, "wallet_emergencia.json")

# ===========================================================================
# keccak-256 (pycryptodome primero, fallback puro)
# ===========================================================================
try:                                                    # pragma: no cover
    from Crypto.Hash import keccak as _keccak_mod       # type: ignore

    def keccak256(data: bytes) -> bytes:
        h = _keccak_mod.new(digest_bits=256)
        h.update(data)
        return h.digest()

    _KECCAK_FUENTE = "pycryptodome"
except ImportError:                                     # pragma: no cover
    _MASK64 = (1 << 64) - 1
    _RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A,
           0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
           0x8000000080008081, 0x8000000000008009, 0x000000000000008A,
           0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
           0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
           0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
           0x000000000000800A, 0x800000008000000A, 0x8000000080008081,
           0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
    _ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
            [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]

    def _rol(x: int, n: int) -> int:
        n %= 64
        return ((x << n) | (x >> (64 - n))) & _MASK64

    def _keccak_f(a: list) -> list:
        for rc in _RC:
            c = [a[x][0] ^ a[x][1] ^ a[x][2] ^ a[x][3] ^ a[x][4]
                 for x in range(5)]
            d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
            b = [[0] * 5 for _ in range(5)]
            for x in range(5):
                for y in range(5):
                    b[y][(2 * x + 3 * y) % 5] = _rol(a[x][y], _ROT[x][y])
            for x in range(5):
                for y in range(5):
                    a[x][y] = b[x][y] ^ (((~b[(x + 1) % 5][y]) & _MASK64) &
                                         b[(x + 2) % 5][y])
            a[0][0] ^= rc
        return a

    def keccak256(data: bytes) -> bytes:
        rate = 136                                       # keccak-256
        data = bytearray(data)
        # padding original Keccak: 0x01 ... 0x80 (NO SHA3 que usa 0x06)
        data.append(0x01)
        while len(data) % rate:
            data.append(0x00)
        data[-1] |= 0x80
        a = [[0] * 5 for _ in range(5)]
        for off in range(0, len(data), rate):
            blk = data[off:off + rate]
            for i in range(rate // 8):
                x, y = i % 5, i // 5
                a[x][y] ^= int.from_bytes(blk[i * 8:i * 8 + 8], "little")
            a = _keccak_f(a)
        out = bytearray()
        while len(out) < 32:
            for i in range(rate // 8):
                x, y = i % 5, i // 5
                out += a[x][y].to_bytes(8, "little")
                if len(out) >= 32:
                    break
        return bytes(out[:32])

    _KECCAK_FUENTE = "fallback puro"


# ===========================================================================
# ed25519 puro (Monero: pubkey = B*escalar SIN clamp)
# ===========================================================================
_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_I = pow(2, (_P - 1) // 4, _P)
_IDENTITY = (0, 1, 1, 0)


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


def _xrecover(y: int) -> int:
    xx = ((y * y - 1) * _inv(_D * y * y + 1)) % _P
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P:
        x = (x * _I) % _P
    if x % 2:
        x = _P - x
    return x


_BY = (4 * _inv(5)) % _P
_BX = _xrecover(_BY)
_B = (_BX, _BY, 1, (_BX * _BY) % _P)


def _edwards_add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = ((y1 - x1) * (y2 - x2)) % _P
    b = ((y1 + x1) * (y2 + x2)) % _P
    c = (2 * t1 * t2 * _D) % _P
    dd = (2 * z1 * z2) % _P
    e = b - a
    f = dd - c
    g = dd + c
    h = b + a
    return ((e * f) % _P, (g * h) % _P, (f * g) % _P, (e * h) % _P)


def _scalarmult(p, e: int):
    q = _IDENTITY
    while e > 0:
        if e & 1:
            q = _edwards_add(q, p)
        p = _edwards_add(p, p)
        e >>= 1
    return q


def _pub_from_scalar(escalar32: bytes) -> bytes:
    """Punto codificado (y con bit de paridad de x) desde un escalar."""
    n = int.from_bytes(escalar32, "little") % _L
    X, Y, Z, _T = _scalarmult(_B, n)     # coordenadas extendidas
    x = (X * _inv(Z)) % _P               # normalizar a afines
    y = (Y * _inv(Z)) % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


# ===========================================================================
# base58 de Monero
# ===========================================================================
_ALFABETO = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_ANCHO = {1: 2, 2: 3, 3: 5, 4: 6, 5: 7, 6: 9, 7: 10, 8: 11}


def _enc_bloque(bloque: bytes) -> str:
    num = int.from_bytes(bloque, "big")
    out = ""
    for _ in range(_ANCHO[len(bloque)]):
        out = _ALFABETO[num % 58] + out
        num //= 58
    return out


def base58_monero(payload: bytes) -> str:
    out, i = [], 0
    while len(payload) - i >= 8:
        out.append(_enc_bloque(payload[i:i + 8]))
        i += 8
    if i < len(payload):
        out.append(_enc_bloque(payload[i:]))
    return "".join(out)


def base58_monero_decode(s: str) -> bytes:
    """Decodifica una dirección Monero (para validar el round-trip)."""
    inv = {v: k for k, v in _ANCHO.items()}          # chars → bytes
    datos = bytearray()
    while s:
        if len(s) >= 11:
            chars, k = 11, 8                          # bloque completo
        else:
            chars, k = len(s), inv.get(len(s), 0)     # bloque final parcial
            if not k:
                return b""
        num = 0
        for ch in s[:chars]:
            idx = _ALFABETO.find(ch)
            if idx < 0:
                return b""
            num = num * 58 + idx
        try:
            datos += num.to_bytes(k, "big")
        except OverflowError:
            return b""
        s = s[chars:]
    return bytes(datos)


# ===========================================================================
# Wallet
# ===========================================================================
def nueva_wallet(semilla: bytes | None = None) -> dict:
    """Genera claves + dirección Monero. 100% offline. Devuelve dict."""
    semilla = semilla or os.urandom(32)
    pub_gasto = _pub_from_scalar(semilla)
    sem_vista = keccak256(semilla)          # derivación estándar Monero
    pub_vista = _pub_from_scalar(sem_vista)
    bruto = b"\x12" + pub_gasto + pub_vista
    checksum = keccak256(bruto)[:4]
    direccion = base58_monero(bruto + checksum)
    return {
        "address": direccion,
        "spend_key": semilla.hex(),
        "view_key": sem_vista.hex(),
        "spend_pub": pub_gasto.hex(),
        "view_pub": pub_vista.hex(),
        "creada": time.strftime("%Y-%m-%d %H:%M:%S"),
        "keccak": _KECCAK_FUENTE,
        "nota": "SOLO OFFLINE. Respalda este archivo: quien lo tenga "
                "controla los fondos. Puedes restaurar en la GUI Monero "
                "(Restore from keys) con estas claves.",
    }


def validar_direccion(direccion: str) -> bool:
    """Round-trip: decodifica, verifica longitud y checksum keccak."""
    try:
        bruto = base58_monero_decode((direccion or "").strip())
        if len(bruto) != 69 or bruto[0] != 0x12:
            return False
        return keccak256(bruto[:-4])[:4] == bruto[-4:]
    except Exception:                                   # noqa: BLE001
        return False


def cargar_guardada(cfg: dict | None = None) -> dict:
    try:
        with open(WALLET_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                   # noqa: BLE001
        return {}


def ensure_wallet(cfg: dict, on_event=None) -> tuple:
    """Garantiza una WALLET_XMR utilizable.
    1) Si secrets ya trae WALLET_XMR → se respeta (intocable).
    2) Si no, usa data/wallet_emergencia.json (creándola si falta).
    Devuelve (direccion, fue_creada_ahora). Nunca explota."""
    w = (cfg.get("WALLET_XMR") or "").strip()
    if w:
        return w, False
    d = cargar_guardada()
    if d.get("address") and validar_direccion(d["address"]):
        cfg["WALLET_XMR"] = d["address"]
        return d["address"], False
    d = nueva_wallet()
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = WALLET_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
        try:                    # solo el dueño del PC debe leerla
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:                               # noqa: BLE001
            pass
        os.replace(tmp, WALLET_FILE)
    except Exception:                                   # noqa: BLE001
        pass
    cfg["WALLET_XMR"] = d["address"]
    if on_event:
        try:
            on_event("WALLET_MONERO generada OFFLINE y guardada en "
                     "data/wallet_emergencia.json — RESPÁLDALA (quien la "
                     "tenga cobra). Si prefieres la tuya, ponla en "
                     "secrets.toml como WALLET_XMR y esta se ignora.",
                     "warn")
        except Exception:                               # noqa: BLE001
            pass
    return d["address"], True


# ===========================================================================
def main():
    semilla = bytes.fromhex(sys.argv[1]) if len(sys.argv) > 1 else None
    d = nueva_wallet(semilla)
    print(f"keccak      : {_KECCAK_FUENTE}")
    print(f"address     : {d['address']}")
    print(f"spend_key   : {d['spend_key']}")
    print(f"view_key    : {d['view_key']}")
    print(f"spend_pub   : {d['spend_pub']}")
    print(f"view_pub    : {d['view_pub']}")
    print(f"valida      : {validar_direccion(d['address'])}")
    if semilla is None:
        print("nota        : usa 'python wallet_monero.py <semilla_hex>' "
              "para regenerar la MISMA wallet.")


if __name__ == "__main__":
    main()
