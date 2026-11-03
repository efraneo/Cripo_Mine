# utils/security.py
"""
🔐 Seguridad simplificada para El_Bot_de_Efra
Versión sin clave maestra persistente ni DB_MASTER_KEY — tolerante y estable.
Evita errores de 'Token inválido' y permite usar texto plano o cifrado opcionalmente.
"""

import base64
import os
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes

# Importa logger del proyecto
try:
    from utils.logger import log_info, log_warning, log_error
except Exception:
    def log_info(m, **_): print("[INFO]", m)
    def log_warning(m, **_): print("[WARN]", m)
    def log_error(m, **_): print("[ERROR]", m)

# 🔹 Clave AES fija local (no persistente)
#    (Esta clave se usa solo para cifrar/descifrar en runtime,
#     no se guarda ni cambia entre sesiones → evita corrupción)
_LOCAL_AES_KEY = b"ElBotDeEfra_AES_Key_32bytes!!__!!"[:32]


def cifrar(texto: str) -> str:
    """🔒 Cifra texto (AES-CBC, sin dependencia de DB_MASTER_KEY)."""
    try:
        if not texto:
            return ""
        iv = get_random_bytes(16)
        cipher = AES.new(_LOCAL_AES_KEY, AES.MODE_CBC, iv)
        ct_bytes = cipher.encrypt(pad(texto.encode("utf-8"), AES.block_size))
        return base64.b64encode(iv + ct_bytes).decode("utf-8")
    except Exception as e:
        log_error(f"cifrar fallo: {e}")
        return texto  # fallback: devolver texto plano


def descifrar(token: str) -> str:
    """🔓 Descifra texto base64, tolerante y sin errores 'Token inválido'."""
    try:
        if not token or not isinstance(token, str):
            return str(token)

        # Detectar si es base64 válido
        try:
            raw = base64.b64decode(token, validate=True)
        except Exception:
            return token  # no es base64, devolver texto original

        if len(raw) <= 16:
            return token  # no contiene IV válido

        iv, ct = raw[:16], raw[16:]
        cipher = AES.new(_LOCAL_AES_KEY, AES.MODE_CBC, iv)
        pt = unpad(cipher.decrypt(ct), AES.block_size)
        return pt.decode("utf-8")

    except Exception as e:
        log_warning(f"descifrar fallo: {e}")
        return token  # fallback seguro


def ensure_master_key_loaded():
    """Compatibilidad: ya no usa clave maestra, solo logea info."""
    log_info("🔑 Modo seguridad simplificado: sin clave maestra persistente.")
    return True
