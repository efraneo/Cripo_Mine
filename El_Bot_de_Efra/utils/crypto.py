# utils/crypto.py
"""
Compatibilidad: provee encrypt/decrypt usando utils.security
para evitar errores de importación (app.py.login_ui).
"""

from typing import Optional
from utils.logger import log_error
from utils.security import cifrar, descifrar

def encrypt(plain: str) -> Optional[str]:
    try:
        return cifrar(plain)
    except Exception as e:
        log_error(f"encrypt error: {e}", archivo="crypto.py", funcion="encrypt")
        return None

def decrypt(cipher: str) -> Optional[str]:
    try:
        return descifrar(cipher)
    except Exception as e:
        log_error(f"decrypt error: {e}", archivo="crypto.py", funcion="decrypt")
        return None
