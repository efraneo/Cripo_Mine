# utils/security.py
# ==========================================================
# Helpers de cifrado simétrico para claves sensibles.
# Usa Fernet (PBKDF2) con DB_MASTER_KEY o crea automáticamente
# una clave persistente en data/secure/clave_aes.key
# ==========================================================

import os
import logging
from base64 import urlsafe_b64encode
from typing import Optional
from hashlib import pbkdf2_hmac

# ----------------------------------------------------------
# Configuración de logging segura
# ----------------------------------------------------------
_logger = logging.getLogger("utils.security")
if not _logger.handlers:
    import sys
    h = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | [security] %(message)s")
    h.setFormatter(fmt)
    _logger.addHandler(h)
    _logger.setLevel(logging.INFO)

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:
    _logger.error("❌ cryptography no está instalada. Ejecuta: pip install cryptography")
    raise

# ----------------------------------------------------------
# Configuración de claves y rutas
# ----------------------------------------------------------
_SALT = b"botdefra_fixed_salt_v1"
_KEY_FILE = os.path.join("data", "secure", "clave_aes.key")

# Crear carpeta si no existe
os.makedirs(os.path.dirname(_KEY_FILE), exist_ok=True)


# 🔧 Sincronización automática de auditoría
AUDIT_DB = os.path.join("data", "secure", "auditoria_sesiones.db")
LEGACY_AUDIT_DB = os.path.join("data", "auditoria_sesiones.db")

# Si existe en data/ pero no en secure/, moverlo
try:
    if os.path.exists(LEGACY_AUDIT_DB) and not os.path.exists(AUDIT_DB):
        os.replace(LEGACY_AUDIT_DB, AUDIT_DB)
        _logger.info("🧩 Base auditoría movida a ubicación segura (data/secure/).")
    elif os.path.exists(LEGACY_AUDIT_DB) and os.path.exists(AUDIT_DB):
        _logger.warning("⚠️ Duplicado auditoría detectado, usa solo data/secure/")
except Exception as e:
    _logger.error(f"No se pudo sincronizar auditoría: {e}")


# ==========================================================
# 🔐 Clave maestra: lectura, generación y persistencia
# ==========================================================
def _derive_fernet_key_from_password(password: str) -> bytes:
    """Deriva una clave Fernet (urlsafe base64, 32 bytes) desde un password."""
    key_bytes = pbkdf2_hmac("sha256", password.encode("utf-8"), _SALT, 200_000, dklen=32)
    return urlsafe_b64encode(key_bytes)


def _read_binance_env(path: str = "binance.env") -> Optional[dict]:
    """Lee archivo estilo KEY=VAL y devuelve un dict simple."""
    if not os.path.exists(path):
        return None
    data = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
        return data
    except Exception as e:
        _logger.warning(f"No se pudo leer {path}: {e}")
        return None


def _read_or_create_keyfile() -> str:
    """Lee la clave desde data/secure/clave_aes.key o la crea si no existe."""
    try:
        if os.path.exists(_KEY_FILE):
            with open(_KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
                if key:
                    return key

        # Crear nueva clave Fernet
        new_key = Fernet.generate_key().decode("utf-8")
        with open(_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(new_key)
        _logger.info(f"🔐 Nueva clave AES generada en {_KEY_FILE}")
        return new_key
    except Exception as e:
        _logger.error(f"❌ Error leyendo/creando {_KEY_FILE}: {e}")
        raise


def load_master_key() -> Optional[str]:
    """Carga DB_MASTER_KEY desde entorno, binance.env o archivo persistente."""
    k = os.environ.get("DB_MASTER_KEY")
    if k:
        return k

    env = _read_binance_env("binance.env")
    if env and "DB_MASTER_KEY" in env:
        return env["DB_MASTER_KEY"]

    # Si no hay, usar archivo persistente (auto crea)
    return _read_or_create_keyfile()


# ==========================================================
# 🧩 Fernet utils
# ==========================================================
def _get_fernet() -> Optional[Fernet]:
    """Obtiene un objeto Fernet seguro a partir de la clave maestra."""
    master = load_master_key()
    if not master:
        _logger.error("❌ No se pudo crear Fernet: falta DB_MASTER_KEY o archivo de clave.")
        return None
    try:
        # Si ya tiene formato de clave Fernet (44 chars base64)
        if len(master) >= 44 and all(c.isalnum() or c in "-_" for c in master):
            return Fernet(master.encode("utf-8"))
        key = _derive_fernet_key_from_password(master)
        return Fernet(key)
    except Exception as e:
        _logger.error(f"❌ Error derivando Fernet key: {e}")
        return None


# ==========================================================
# 🔒 Cifrado / Descifrado
# ==========================================================
def cifrar(plaintext: str) -> Optional[str]:
    """Cifra texto plano y devuelve token en UTF-8."""
    if plaintext is None:
        return None
    f = _get_fernet()
    if f is None:
        _logger.error("No se pudo cifrar: falta clave maestra.")
        return None
    try:
        tok = f.encrypt(plaintext.encode("utf-8"))
        return tok.decode("utf-8")
    except Exception as e:
        _logger.error(f"❌ cifrar error: {type(e).__name__}: {e}")
        return None


def descifrar(token: str) -> Optional[str]:
    """Descifra un token cifrado con Fernet y devuelve texto plano."""
    if not token:
        return None
    f = _get_fernet()
    if f is None:
        _logger.error("No se pudo descifrar: falta clave maestra.")
        return None
    try:
        pt = f.decrypt(token.encode("utf-8"))
        return pt.decode("utf-8")
    except InvalidToken:
        _logger.error("❌ descifrar error: Token inválido (clave maestra incorrecta o dato corrupto)")
        return None
    except Exception as e:
        _logger.error(f"❌ descifrar error: {type(e).__name__}: {e}")
        return None
