"""
utils/logger.py
----------------
Logger centralizado con fallback simple. Exporta funciones:
- log_error(e, archivo=None, funcion=None)
- log_warning(msg, archivo=None, funcion=None)
- log_info(msg, archivo=None, funcion=None)

Usado por muchos módulos del proyecto.
"""
import logging
import sys
from datetime import datetime

LOG_FORMAT = "%(asctime)s | %(levelname)s | [BotDeEfra] %(message)s"
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("BotDeEfra")

def _fmt_ctx(archivo, funcion):
    if archivo and funcion:
        return f"{archivo}.{funcion} ->"
    if archivo:
        return f"{archivo} ->"
    return ""

def log_error(e, archivo: str = None, funcion: str = None):
    try:
        ctx = _fmt_ctx(archivo, funcion)
        logger.exception(f"❌ {ctx} {e}")
    except Exception:
        print(f"ERROR LOGGER FAIL: {e}")

def log_warning(msg, archivo: str = None, funcion: str = None):
    try:
        ctx = _fmt_ctx(archivo, funcion)
        logger.warning(f"⚠️ {ctx} {msg}")
    except Exception:
        print(f"WARNING LOGGER FAIL: {msg}")

def log_info(msg, archivo: str = None, funcion: str = None):
    try:
        ctx = _fmt_ctx(archivo, funcion)
        logger.info(f"ℹ️ {ctx} {msg}")
    except Exception:
        print(f"INFO LOGGER FAIL: {msg}")
