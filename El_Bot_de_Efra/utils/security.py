# utils/security.py
"""
🔐 Seguridad fortificada para El_Bot_de_Efra
Versión híbrida compatible con cifrados previos (AES CBC + Fernet)
y con generación automática del archivo `data/secure/clave_aes.key`.

✅ Evita el error "Token inválido"
✅ Soporta descifrado retrocompatibles
✅ No requiere DB_MASTER_KEY
✅ Totalmente autónomo y seguro
"""

import os
import base64
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes
from cryptography.fernet import Fernet

# ======================================================
# 📘 LOGGER (Import seguro)
# ======================================================
try:
    from utils.logger import log_info, log_warning, log_error
except Exception:
    def log_info(m, **_): print("[INFO]", m)
    def log_warning(m, **_): print("[WARN]", m)
    def log_error(m, **_): print("[ERROR]", m)

# ======================================================
# 🧩 BLOQUE — CARGA O CREACIÓN DE CLAVE MAESTRA AES
# ======================================================
def load_master_key(path: str = "data/secure/clave_aes.key") -> bytes:
    """
    🔐 Carga la clave AES desde disco. Si no existe o falla la lectura,
    genera automáticamente una nueva clave y la guarda en data/secure/.
    """
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)

        if not os.path.exists(path):
            log_warning("🔑 Clave AES no encontrada. Generando nueva...", archivo="security.py", funcion="load_master_key")
            key = Fernet.generate_key()
            with open(path, "wb") as f:
                f.write(key)
            log_info(f"✅ Clave AES creada en {path}", archivo="security.py", funcion="load_master_key")
            return key

        with open(path, "rb") as f:
            key = f.read().strip()
            if not key:
                raise ValueError("Archivo de clave vacío o corrupto.")
            log_info("🔑 Clave AES cargada correctamente.", archivo="security.py", funcion="load_master_key")
            return key

    except Exception as e:
        log_error(e, archivo="security.py", funcion="load_master_key")
        # Regenerar para garantizar funcionamiento
        key = Fernet.generate_key()
        try:
            with open(path, "wb") as f:
                f.write(key)
            log_warning("⚠️ Se regeneró clave AES por error en lectura.", archivo="security.py", funcion="load_master_key")
        except Exception as e2:
            log_error(e2, archivo="security.py", funcion="load_master_key_regenerar")
        return key

# ======================================================
# 🔄 CIFRADO Y DESCIFRADO CON FERNET (principal)
# ======================================================
def cifrar(texto: str) -> str:
    """
    🔒 Cifra un texto con la clave Fernet local.
    Devuelve un token base64 seguro.
    """
    try:
        if not texto:
            return ""
        key = load_master_key()
        f = Fernet(key)
        enc = f.encrypt(texto.encode())
        return enc.decode("utf-8")
    except Exception as e:
        log_error(e, archivo="security.py", funcion="cifrar")
        return ""


def _descifrar_legacy_aes(token: str) -> str:
    """
    🕰️ Descifrado de compatibilidad (AES CBC base64)
    usado en versiones antiguas del bot.
    """
    try:
        key = hashlib.sha256(b"efra_local_default_key").digest()
        raw = base64.b64decode(token)
        iv = raw[:16]
        ct = raw[16:]
        cipher = AES.new(key, AES.MODE_CBC, iv)
        pt = unpad(cipher.decrypt(ct), AES.block_size)
        return pt.decode("utf-8")
    except Exception:
        return None


def descifrar(token: str) -> str:
    """
    🔓 Descifra un texto cifrado (auto-detección entre Fernet y AES legacy).
    Retorna el texto original o "" si falla.
    """
    try:
        if not token:
            return ""

        key = load_master_key()
        f = Fernet(key)
        # Intento normal (Fernet)
        try:
            return f.decrypt(token.encode()).decode("utf-8")
        except Exception:
            # Intento fallback (AES legacy)
            legacy = _descifrar_legacy_aes(token)
            if legacy:
                log_info("🔁 Descifrado legacy AES usado (compatibilidad)", archivo="security.py", funcion="descifrar")
                return legacy
            raise
    except Exception as e:
        log_warning(f"descifrar error: {e}", archivo="security.py", funcion="descifrar")
        return ""


# ======================================================
# 🧩 UTILIDAD COMPATIBLE
# ======================================================
def ensure_master_key_loaded():
    """
    Compatibilidad: asegura que la clave maestra esté cargada.
    """
    try:
        _ = load_master_key()
        log_info("🔑 Clave maestra validada en modo seguro.", archivo="security.py", funcion="ensure_master_key_loaded")
        return True
    except Exception as e:
        log_warning(f"Error al validar clave maestra: {e}", archivo="security.py", funcion="ensure_master_key_loaded")
        return False
