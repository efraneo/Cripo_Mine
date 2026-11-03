# ============================================================
# Bloque 0 — IMPORTS GLOBALES (Optimizado y Robusto)
# ------------------------------------------------------------
# Configuración limpia de entorno, logs, y TensorFlow.
# ============================================================

import os
import sys
import io
import time
import warnings
import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st
from datetime import datetime, timedelta
from typing import Optional, Dict, List

# --- Fix imports modelo (Evita fallos NameError) ---
try:
    from utils.modelo import entrenar_y_predecir, predecir_senal_ensemble
except Exception as e:
    import traceback
    print(f"[⚠️ WARNING] utils.modelo no disponible: {e}\n{traceback.format_exc()}")

# ============================================================
# 🧹 LIMPIEZA DE ENTORNO Y SUPRESIÓN DE RUIDO
# ============================================================

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message="pkg_resources is deprecated.*")
warnings.filterwarnings("ignore", message="Thread 'MainThread': missing ScriptRunContext!.*")
warnings.filterwarnings("ignore", message="to view a Streamlit app on a browser.*")

# ============================================================
# 🪵 LOGGING CENTRALIZADO
# ============================================================

LOG_FORMAT = "%(asctime)s | %(levelname)s | [%(name)s] %(message)s"
LOG_LEVEL = os.getenv("BOTDEEFRA_LOGLEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger("BotDeEfra")

for noisy in ("tensorflow", "matplotlib", "asyncio", "urllib3", "streamlit", "numexpr"):
    logging.getLogger(noisy).setLevel(logging.ERROR)

# Evita loops de stdout
if not isinstance(sys.stdout, (io.TextIOBase, type(sys.__stdout__))):
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__

# ============================================================
# 🔥 IMPORTAR TENSORFLOW (Lazy Import — solo si se usa)
# ============================================================

tf = None
try:
    import tensorflow as tf
    tf.get_logger().setLevel("ERROR")
    logger.info(f"TensorFlow cargado correctamente (v{tf.__version__})")
except Exception as e:
    logger.warning(f"TensorFlow no disponible: {e}")
    tf = None

# ============================================================
# 📡 IMPORTS DE TELEGRAM Y MÓDULOS INTERNOS
# ============================================================

from telegram_alertas import (
    enviar_sticker_bienvenida, send_telegram_alert,
    enviar_telegram, enviar_imagen_telegram
)

from utils.auth import (
    inicializar_db, bootstrap_admin, get_user,
    login_usuario, obtener_permisos, _get_client_ip,
    actualizar_ping, cerrar_sesion, registrar_sesion
)
from utils.logger import log_info, log_error, log_warning
from utils.trading import TradingExecutor
from trading_bot import TradingBot

logger.info("🔧 Entorno inicializado correctamente — Bloque 0 cargado sin errores.")

# ============================================================
# Bloque 1 — CONFIGURACIÓN VISUAL
# ============================================================

st.markdown("""
<style>
.main {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: "Segoe UI", Roboto, sans-serif;
}
h1, h2, h3 {
    color: #58a6ff;
    font-weight: 600;
}
[data-testid="stMetricValue"] {
    font-size: 22px;
    color: #f0f6fc;
}
div.stButton > button {
    background-color: #238636;
    color: white;
    border-radius: 8px;
    padding: 0.6em 1em;
    font-weight: bold;
}
div.stButton > button:hover {
    background-color: #2ea043;
}
.streamlit-expanderHeader {
    font-weight: bold;
    color: #e6edf3;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# Bloque 2 — INICIALIZACIÓN DE DB Y ADMIN
# ============================================================

try:
    inicializar_db()
    if get_user("admin") is None:
        bootstrap_admin(usuario="admin", clave="1234")
        log_info("✅ Admin creado automáticamente (usuario=admin, clave=1234)", archivo="app.py", funcion="startup")
    else:
        log_info("ℹ️ Admin ya existe, no se sobrescribe.", archivo="app.py", funcion="startup")
    log_info("✅ Base de datos inicializada correctamente", archivo="app.py", funcion="startup")
except Exception as e:
    log_error(e, archivo="app.py", funcion="startup")
    st.error("❌ Error al inicializar la base de datos.")
    st.stop()

# ============================================================
# Bloque 3 — CLAVES BINANCE Y CONFIGURACIÓN
# ============================================================

from dotenv import load_dotenv
load_dotenv()

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

if not BINANCE_API_KEY or not BINANCE_API_SECRET:
    log_warning("⚠️ No se detectaron claves Binance. Forzando modo DEMO.", archivo="app.py", funcion="startup")
    st.session_state["dry_run"] = True
else:
    st.session_state["dry_run"] = False

# ============================================================
# Bloque 4A — SESIONES Y CONTROL DE ESTADO
# ============================================================

st.set_page_config(page_title="📊 El Bot de Efra", page_icon="🤖", layout="wide")

if "usuario" not in st.session_state:
    st.session_state["usuario"] = None
if "login_ok" not in st.session_state:
    st.session_state["login_ok"] = False
if "bot_inicializado" not in st.session_state:
    st.session_state["bot_inicializado"] = False
if "dry_run" not in st.session_state:
    st.session_state["dry_run"] = True
if "ip_usuario" not in st.session_state:
    try:
        st.session_state["ip_usuario"] = _get_client_ip()
    except Exception:
        st.session_state["ip_usuario"] = "0.0.0.0"

# ============================================================
# Bloque 4B — INICIALIZACIÓN SEGURA DEL BOT (solo bajo demanda)
# ============================================================

@st.cache_resource(show_spinner=False)
def crear_executor(api_key=None, api_secret=None, dry_run=True):
    try:
        executor = TradingExecutor(api_key=api_key, api_secret=api_secret, dry_run=dry_run)
        modo = "REAL" if not dry_run else "DEMO"
        log_info(f"Executor inicializado ({modo})", archivo="app.py", funcion="crear_executor")
        return executor
    except Exception as e:
        log_error(e, archivo="app.py", funcion="crear_executor")
        return TradingExecutor(dry_run=True)

def inicializar_bot(modo="REAL"):
    """
    Inicializa el bot solo cuando el usuario lo solicita explícitamente.
    """
    try:
        if st.session_state["bot_inicializado"]:
            log_info("Bot ya estaba inicializado, se omite reinicio.", archivo="app.py", funcion="inicializar_bot")
            return

        dry = (modo != "REAL")
        executor = crear_executor(BINANCE_API_KEY, BINANCE_API_SECRET, dry_run=dry)
        bot = TradingBot()
        st.session_state["bot_inicializado"] = True
        st.session_state["trading_executor"] = executor
        st.session_state["bot"] = bot

        log_info(f"✅ Bot inicializado correctamente en modo {modo}", archivo="app.py", funcion="inicializar_bot")
        st.success(f"🤖 Bot iniciado correctamente en modo {modo}")
    except Exception as e:
        log_error(e, archivo="app.py", funcion="inicializar_bot")
        st.error(f"❌ Error inicializando bot: {e}")

# ============================================================
# Bloque 5 — LOGIN (solo se gestiona desde el sidebar)
# ============================================================

# ✅ Eliminado el formulario de login del panel principal.
# Ahora el login se muestra exclusivamente en el sidebar (ver Bloque 11).
# Esto evita que aparezca el formulario en el cuerpo principal del dashboard.

st.title("🤖 El Bot de Efra — Panel Principal")

if not st.session_state.get("usuario"):
    st.info("ℹ️ Inicia sesión desde el menú lateral para continuar.")
    st.stop()

# ============================================================
# Bloque 5.1 — Persistencia de sesión y clave maestra (antirreinicio)
# ============================================================

from pathlib import Path
import json

SESSION_FILE = Path(".session_cache.json")

def _guardar_session_state():
    """Guarda el estado esencial de sesión en disco para restaurarlo si Streamlit reinicia."""
    try:
        data = {
            "usuario": st.session_state.get("usuario"),
            "nombre": st.session_state.get("nombre"),
            "rol": st.session_state.get("rol"),
            "dry_run": st.session_state.get("dry_run", True),
            "binance_api_key": st.session_state.get("binance_api_key"),
            "binance_api_secret": st.session_state.get("binance_api_secret"),
            "modo_demo": st.session_state.get("modo_demo"),
            "permisos": st.session_state.get("permisos", {}),
        }
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        log_warning(f"No se pudo guardar el estado de sesión: {e}", archivo="app.py", funcion="_guardar_session_state")

def _cargar_session_state():
    """Restaura el estado desde disco si Streamlit se reinicia."""
    try:
        if not SESSION_FILE.exists():
            return False
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Solo restaurar si hay usuario autenticado
        if data.get("usuario"):
            for k, v in data.items():
                if k not in st.session_state:
                    st.session_state[k] = v

            log_info(f"🔁 Sesión restaurada para {data['usuario']}", archivo="app.py", funcion="_cargar_session_state")
            return True
        return False
    except Exception as e:
        log_warning(f"No se pudo restaurar el estado de sesión: {e}", archivo="app.py", funcion="_cargar_session_state")
        return False

def _limpiar_cache_sesion():
    """Elimina la sesión cacheada cuando el usuario cierra sesión."""
    try:
        if SESSION_FILE.exists():
            SESSION_FILE.unlink()
    except Exception as e:
        log_warning(f"No se pudo eliminar SESSION_FILE: {e}", archivo="app.py", funcion="_limpiar_cache_sesion")

# 🔹 Cargar sesión si Streamlit reinicia
_cargar_session_state()

# 🔹 Hook para guardar estado cada vez que cambia algo importante
if st.session_state.get("usuario"):
    _guardar_session_state()


# ============================================================
# Bloque 5.2 — 🔐 Cifrado AES de la sesión persistente (.session_cache.json)
# ============================================================

import json
import base64
import hashlib
from pathlib import Path
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

SESSION_CACHE_FILE = Path(".session_cache.json")


def _get_aes_key_from_master(master_key: str) -> bytes:
    """
    Deriva una clave AES-256 a partir de DB_MASTER_KEY usando SHA256.
    """
    if not master_key:
        master_key = "efra_local_default_key"
    return hashlib.sha256(master_key.encode("utf-8")).digest()


def _aes_encrypt(plain_text: str, key: bytes) -> str:
    """
    Cifra texto plano con AES-CBC y devuelve en base64.
    """
    from Crypto.Random import get_random_bytes
    iv = get_random_bytes(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ct_bytes = cipher.encrypt(pad(plain_text.encode("utf-8"), AES.block_size))
    return base64.b64encode(iv + ct_bytes).decode("utf-8")


def _aes_decrypt(cipher_text_b64: str, key: bytes) -> str:
    """
    Descifra texto cifrado en base64 y devuelve texto plano.
    """
    raw = base64.b64decode(cipher_text_b64)
    iv = raw[:16]
    ct = raw[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    pt = unpad(cipher.decrypt(ct), AES.block_size)
    return pt.decode("utf-8")


def _guardar_sesion_segura():
    """
    Guarda st.session_state cifrando las claves sensibles (binance_api_key / secret)
    en un archivo .session_cache.json.
    """
    try:
        if not st.session_state.get("usuario"):
            return  # No hay sesión activa

        # Copia limpia del session_state
        data = dict(st.session_state)

        # Claves sensibles
        key_master = os.getenv("DB_MASTER_KEY", "efra_default_master")
        aes_key = _get_aes_key_from_master(key_master)

        for campo in ["binance_api_key", "binance_api_secret"]:
            valor = data.get(campo)
            if valor:
                try:
                    data[campo] = _aes_encrypt(valor, aes_key)
                except Exception as e:
                    log_warning(f"No se pudo cifrar campo {campo}: {e}", archivo="app.py", funcion="_guardar_sesion_segura")

        # Guardar en disco
        with open(SESSION_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        log_info("💾 Sesión cifrada guardada correctamente.", archivo="app.py", funcion="_guardar_sesion_segura")

    except Exception as e:
        log_error(e, archivo="app.py", funcion="_guardar_sesion_segura")


def _cargar_sesion_segura():
    """
    Carga y descifra la sesión desde .session_cache.json si existe.
    """
    try:
        if not SESSION_CACHE_FILE.exists():
            return False

        with open(SESSION_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        key_master = os.getenv("DB_MASTER_KEY", "efra_default_master")
        aes_key = _get_aes_key_from_master(key_master)

        for campo in ["binance_api_key", "binance_api_secret"]:
            valor = data.get(campo)
            if valor and isinstance(valor, str):
                try:
                    data[campo] = _aes_decrypt(valor, aes_key)
                except Exception:
                    # Puede que ya esté en texto plano, lo dejamos igual
                    pass

        # Cargar en st.session_state
        for k, v in data.items():
            st.session_state[k] = v

        log_info("🔐 Sesión descifrada restaurada correctamente.", archivo="app.py", funcion="_cargar_sesion_segura")
        return True

    except Exception as e:
        log_error(e, archivo="app.py", funcion="_cargar_sesion_segura")
        return False


def _limpiar_cache_sesion():
    """
    Elimina el archivo local de sesión cifrada.
    """
    try:
        if SESSION_CACHE_FILE.exists():
            SESSION_CACHE_FILE.unlink()
            log_info("🧹 Cache de sesión eliminada correctamente.", archivo="app.py", funcion="_limpiar_cache_sesion")
    except Exception as e:
        log_warning(f"No se pudo eliminar cache de sesión: {e}", archivo="app.py", funcion="_limpiar_cache_sesion")


# Intentar cargar sesión al iniciar (opcional)
# Por razones de seguridad y para evitar auto-login indeseado,
# la restauración automática solo ocurre si la variable de entorno
# ALLOW_SESSION_RESTORE está activa (valor "1").
try:
    if os.getenv("ALLOW_SESSION_RESTORE", "0") == "1":
        _cargar_sesion_segura()
    else:
        log_info("Auto-restore de sesión desactivado. Set ALLOW_SESSION_RESTORE=1 para habilitar.", archivo="app.py", funcion="inicio")
except Exception:
    pass

# Guardar automáticamente al final de cada ejecución (solo si hay usuario)
import atexit
atexit.register(_guardar_sesion_segura)


# ============================================================
# Bloque 5.3 — 🧾 Integridad y anti-manipulación del archivo de sesión
# ============================================================

import hmac

SESSION_HASH_FILE = Path(".session_cache.hash")


def _generar_hash_sesion(data: dict, master_key: str) -> str:
    """
    Genera un hash HMAC-SHA256 del contenido de la sesión,
    usando DB_MASTER_KEY como clave.
    """
    try:
        import json
        serializado = json.dumps(data, sort_keys=True).encode("utf-8")
        return hmac.new(master_key.encode("utf-8"), serializado, hashlib.sha256).hexdigest()
    except Exception as e:
        log_warning(f"No se pudo generar hash: {e}", archivo="app.py", funcion="_generar_hash_sesion")
        return ""


def _guardar_hash_sesion(data: dict):
    """
    Guarda el hash de integridad del archivo .session_cache.json.
    """
    try:
        master_key = os.getenv("DB_MASTER_KEY", "efra_default_master")
        h = _generar_hash_sesion(data, master_key)
        with open(SESSION_HASH_FILE, "w", encoding="utf-8") as f:
            f.write(h)
        log_info("🧾 Hash de sesión guardado correctamente.", archivo="app.py", funcion="_guardar_hash_sesion")
    except Exception as e:
        log_warning(f"No se pudo guardar hash de sesión: {e}", archivo="app.py", funcion="_guardar_hash_sesion")


def _verificar_hash_sesion(data: dict) -> bool:
    """
    Verifica que el hash actual del archivo .session_cache.json
    coincida con el último hash guardado.
    Retorna True si es válido, False si fue modificado.
    """
    try:
        if not SESSION_HASH_FILE.exists():
            return True  # No hay hash previo

        master_key = os.getenv("DB_MASTER_KEY", "efra_default_master")
        with open(SESSION_HASH_FILE, "r", encoding="utf-8") as f:
            hash_guardado = f.read().strip()

        hash_actual = _generar_hash_sesion(data, master_key)
        if hmac.compare_digest(hash_guardado, hash_actual):
            log_info("✅ Integridad de sesión verificada correctamente.", archivo="app.py", funcion="_verificar_hash_sesion")
            return True
        else:
            log_warning("⚠️ Integridad de sesión fallida: archivo modificado.", archivo="app.py", funcion="_verificar_hash_sesion")
            return False

    except Exception as e:
        log_error(e, archivo="app.py", funcion="_verificar_hash_sesion")
        return False


# Integración con Bloque 5.2 — Sobrescribimos levemente las funciones guardar/cargar

_original_guardar_sesion_segura = _guardar_sesion_segura
_original_cargar_sesion_segura = _cargar_sesion_segura


def _guardar_sesion_segura():
    """
    Sobrescribe versión anterior para incluir verificación de integridad.
    """
    try:
        if not st.session_state.get("usuario"):
            return

        data = dict(st.session_state)
        key_master = os.getenv("DB_MASTER_KEY", "efra_default_master")
        aes_key = _get_aes_key_from_master(key_master)

        for campo in ["binance_api_key", "binance_api_secret"]:
            valor = data.get(campo)
            if valor:
                try:
                    data[campo] = _aes_encrypt(valor, aes_key)
                except Exception as e:
                    log_warning(f"No se pudo cifrar campo {campo}: {e}", archivo="app.py", funcion="_guardar_sesion_segura_v2")

        with open(SESSION_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)

        _guardar_hash_sesion(data)  # ✅ firmar hash
        log_info("💾 Sesión cifrada y firmada guardada correctamente.", archivo="app.py", funcion="_guardar_sesion_segura_v2")

    except Exception as e:
        log_error(e, archivo="app.py", funcion="_guardar_sesion_segura_v2")


def _cargar_sesion_segura():
    """
    Sobrescribe versión anterior para incluir verificación de integridad.
    """
    try:
        if not SESSION_CACHE_FILE.exists():
            return False

        with open(SESSION_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # ✅ Verificar integridad antes de descifrar
        if not _verificar_hash_sesion(data):
            st.warning("⚠️ Archivo de sesión modificado o corrupto. Se limpiará por seguridad.")
            _limpiar_cache_sesion()
            return False

        key_master = os.getenv("DB_MASTER_KEY", "efra_default_master")
        aes_key = _get_aes_key_from_master(key_master)

        for campo in ["binance_api_key", "binance_api_secret"]:
            valor = data.get(campo)
            if valor and isinstance(valor, str):
                try:
                    data[campo] = _aes_decrypt(valor, aes_key)
                except Exception:
                    pass

        for k, v in data.items():
            st.session_state[k] = v

        log_info("🔐 Sesión cifrada verificada y restaurada correctamente.", archivo="app.py", funcion="_cargar_sesion_segura_v2")
        return True

    except Exception as e:
        log_error(e, archivo="app.py", funcion="_cargar_sesion_segura_v2")
        return False


# ============================================================
# Bloque 5.4 — 🔄 Rotación automática de claves AES y limpieza de sesiones antiguas
# ============================================================

from datetime import datetime, timedelta

SESSION_ROTATION_FILE = Path(".session_rotation.json")
SESSION_EXPIRATION_DAYS = 7  # Días antes de rotar clave AES
SESSION_CACHE_MAX_AGE_HOURS = 48  # Días antes de limpiar sesión vieja


def _load_rotation_metadata():
    try:
        if SESSION_ROTATION_FILE.exists():
            with open(SESSION_ROTATION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            return {}
    except Exception as e:
        log_warning(f"No se pudo leer rotation metadata: {e}", archivo="app.py", funcion="_load_rotation_metadata")
        return {}


def _save_rotation_metadata(meta: dict):
    try:
        with open(SESSION_ROTATION_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f)
    except Exception as e:
        log_warning(f"No se pudo guardar rotation metadata: {e}", archivo="app.py", funcion="_save_rotation_metadata")


def _debe_rotar_clave() -> bool:
    """
    Determina si debe rotarse la clave AES local.
    """
    try:
        meta = _load_rotation_metadata()
        ultima_rotacion = meta.get("ultima_rotacion")
        if not ultima_rotacion:
            return True

        fecha_ultima = datetime.fromisoformat(ultima_rotacion)
        if datetime.utcnow() - fecha_ultima > timedelta(days=SESSION_EXPIRATION_DAYS):
            return True
        return False
    except Exception:
        return True


def _rotar_clave_aes():
    """
    Genera una nueva derivación AES basada en DB_MASTER_KEY + nonce dinámico.
    """
    try:
        master = os.getenv("DB_MASTER_KEY", "efra_default_master")
        nuevo_nonce = base64.b64encode(os.urandom(16)).decode("utf-8")
        nueva_key = _get_aes_key_from_master(master + nuevo_nonce)

        meta = {
            "ultima_rotacion": datetime.utcnow().isoformat(),
            "nonce": nuevo_nonce,
        }
        _save_rotation_metadata(meta)
        log_info("🔄 Clave AES rotada exitosamente.", archivo="app.py", funcion="_rotar_clave_aes")
        return nueva_key
    except Exception as e:
        log_error(e, archivo="app.py", funcion="_rotar_clave_aes")
        return _get_aes_key_from_master(os.getenv("DB_MASTER_KEY", "efra_default_master"))


def _get_current_aes_key():
    """
    Devuelve la clave AES actual, generando o rotando si es necesario.
    """
    try:
        if _debe_rotar_clave():
            return _rotar_clave_aes()

        meta = _load_rotation_metadata()
        master = os.getenv("DB_MASTER_KEY", "efra_default_master")
        nonce = meta.get("nonce", "")
        return _get_aes_key_from_master(master + nonce)
    except Exception as e:
        log_error(e, archivo="app.py", funcion="_get_current_aes_key")
        return _get_aes_key_from_master(os.getenv("DB_MASTER_KEY", "efra_default_master"))


def _limpiar_sesiones_antiguas():
    """
    Elimina archivos de sesión cifrada si son demasiado antiguos o corruptos.
    """
    try:
        if not SESSION_CACHE_FILE.exists():
            return

        mod_time = datetime.utcfromtimestamp(SESSION_CACHE_FILE.stat().st_mtime)
        if datetime.utcnow() - mod_time > timedelta(hours=SESSION_CACHE_MAX_AGE_HOURS):
            log_info("🧹 Sesión expirada detectada y limpiada correctamente.", archivo="app.py", funcion="_limpiar_sesiones_antiguas")

            _limpiar_cache_sesion()
            if SESSION_HASH_FILE.exists():
                SESSION_HASH_FILE.unlink()
    except Exception as e:
        log_error(e, archivo="app.py", funcion="_limpiar_sesiones_antiguas")


# ============================================================
# Integración automática (ejecutar una vez al inicio del script)
# ============================================================

try:
    # Ejecuta la limpieza y chequeo de rotación al inicio
    _limpiar_sesiones_antiguas()
    _get_current_aes_key()
    log_info("🧭 Rotación y limpieza de sesión inicializada correctamente.", archivo="app.py", funcion="bloque_5_4_startup")
except Exception as e:
    log_warning(f"No se pudo inicializar rotación: {e}", archivo="app.py", funcion="bloque_5_4_startup")


# ============================================================
# Bloque 5.5 — 🧾 Auditoría de sesiones cifradas
# ============================================================

from datetime import datetime
import sqlite3
import hashlib

AUDITORIA_DB = Path("data/secure/auditoria_sesiones.db")


def _init_auditoria_db():
    """
    Crea la tabla de auditoría si no existe.
    """
    try:
        AUDITORIA_DB.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(AUDITORIA_DB)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_sesiones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_utc TEXT,
                usuario TEXT,
                ip TEXT,
                evento TEXT,
                detalle TEXT,
                hash_sesion TEXT
            )
        """)
        conn.commit()
        conn.close()
        log_info("✅ Tabla auditoria_sesiones verificada/creada.", archivo="app.py", funcion="_init_auditoria_db")
    except Exception as e:
        log_warning(f"No se pudo inicializar auditoría: {e}", archivo="app.py", funcion="_init_auditoria_db")


def registrar_auditoria(evento: str, detalle: str = "", usuario: str = None, ip: str = None):
    """
    Registra un evento en la tabla de auditoría con información contextual.
    """
    try:
        _init_auditoria_db()
        conn = sqlite3.connect(AUDITORIA_DB)
        cur = conn.cursor()

        fecha = datetime.utcnow().isoformat()
        usuario = usuario or st.session_state.get("usuario", "desconocido")
        ip = ip or st.session_state.get("ip_usuario", "0.0.0.0")

        # Intentar generar hash parcial del archivo de sesión si existe
        hash_sesion = None
        try:
            if SESSION_CACHE_FILE.exists():
                contenido = SESSION_CACHE_FILE.read_bytes()
                hash_sesion = hashlib.sha256(contenido).hexdigest()[:12]
        except Exception:
            hash_sesion = "N/A"

        cur.execute("""
            INSERT INTO auditoria_sesiones (fecha_utc, usuario, ip, evento, detalle, hash_sesion)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (fecha, usuario, ip, evento, detalle, hash_sesion))
        conn.commit()
        conn.close()
        log_info(f"🧾 Auditoría registrada: {evento} [{usuario}] ({ip})", archivo="app.py", funcion="registrar_auditoria")
    except Exception as e:
        log_warning(f"No se pudo registrar auditoría ({evento}): {e}", archivo="app.py", funcion="registrar_auditoria")


# ============================================================
# Hooks de integración con los bloques 5.2 y 5.3
# ============================================================

def auditar_evento_sesion_guardada():
    try:
        registrar_auditoria("sesion_guardada", "Sesión cifrada y almacenada correctamente.")
    except Exception as e:
        log_warning(f"No se pudo auditar sesión_guardada: {e}", archivo="app.py", funcion="auditar_evento_sesion_guardada")

def auditar_evento_sesion_restaurada():
    try:
        registrar_auditoria("sesion_restaurada", "Sesión descifrada y verificada correctamente.")
    except Exception as e:
        log_warning(f"No se pudo auditar sesión_restaurada: {e}", archivo="app.py", funcion="auditar_evento_sesion_restaurada")

def auditar_evento_sesion_invalidada(razon: str):
    try:
        registrar_auditoria("sesion_invalidada", f"Sesión eliminada: {razon}")
    except Exception as e:
        log_warning(f"No se pudo auditar sesión_invalidada: {e}", archivo="app.py", funcion="auditar_evento_sesion_invalidada")

# ============================================================
# Auto-inicio
# ============================================================

try:
    _init_auditoria_db()
    log_info("🧩 Auditoría de sesiones lista para registrar eventos.", archivo="app.py", funcion="bloque_5_5_startup")
except Exception as e:
    log_warning(f"No se pudo inicializar auditoría al inicio: {e}", archivo="app.py", funcion="bloque_5_5_startup")


# ============================================================
# Bloque 5.6 — ⚙️ Panel de administración: Auditoría de sesiones
# ============================================================

import pandas as pd
import sqlite3
import io

def panel_auditoria_admin():
    """
    Panel visual en Streamlit para inspeccionar auditorías de sesión.
    Solo accesible al administrador.
    """
    if st.session_state.get("usuario") not in ("admin", "Administrador") and st.session_state.get("rol") != "admin":
        st.warning("⚠️ No tienes permisos para acceder a esta sección.")
        return

    st.markdown("## 🧾 Auditoría de sesiones cifradas")
    st.caption("Monitorea eventos relacionados con el cifrado, restauración e invalidación de sesiones seguras.")

    # Verificar existencia del archivo
    if not AUDITORIA_DB.exists():
        st.error("❌ No hay registros de auditoría todavía.")
        return

    try:
        conn = sqlite3.connect(AUDITORIA_DB)
        df = pd.read_sql_query("SELECT * FROM auditoria_sesiones ORDER BY id DESC", conn)
        conn.close()
    except Exception as e:
        st.error(f"⚠️ No se pudo leer la base de datos de auditoría: {e}")
        return

    if df.empty:
        st.info("📭 No hay eventos registrados aún.")
        return

    # ===============================
    # 🎛️ Filtros dinámicos
    # ===============================
    with st.expander("🔍 Filtros de búsqueda", expanded=False):
        col1, col2, col3 = st.columns(3)
        usuario_filtro = col1.text_input("👤 Filtrar por usuario", "")
        ip_filtro = col2.text_input("🌐 Filtrar por IP", "")
        evento_filtro = col3.multiselect("🧩 Tipo de evento", sorted(df["evento"].unique().tolist()))

        if usuario_filtro:
            df = df[df["usuario"].str.contains(usuario_filtro, case=False, na=False)]
        if ip_filtro:
            df = df[df["ip"].str.contains(ip_filtro, case=False, na=False)]
        if evento_filtro:
            df = df[df["evento"].isin(evento_filtro)]

        st.caption(f"Mostrando {len(df)} registros tras filtros aplicados.")

    # ===============================
    # 📊 Vista general
    # ===============================
    st.dataframe(
        df[["fecha_utc", "usuario", "ip", "evento", "detalle", "hash_sesion"]],
        use_container_width=True,
        hide_index=True
    )

    # ===============================
    # 📈 Resumen estadístico
    # ===============================
    with st.expander("📈 Estadísticas rápidas", expanded=False):
        total = len(df)
        por_evento = df["evento"].value_counts().to_dict()
        st.metric("📦 Total de eventos", total)
        for tipo, count in por_evento.items():
            st.write(f"• **{tipo}** → {count}")

    # ===============================
    # 💾 Exportar registros
    # ===============================
    with st.expander("💾 Exportar auditoría", expanded=False):
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="AuditoriaSesiones")
        st.download_button(
            label="⬇️ Descargar en Excel",
            data=buffer.getvalue(),
            file_name=f"auditoria_sesiones_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # ===============================
    # 🧹 Limpieza opcional
    # ===============================
    with st.expander("🧹 Mantenimiento de auditoría", expanded=False):
        if st.button("🗑️ Limpiar registros antiguos (> 90 días)"):
            try:
                conn = sqlite3.connect(AUDITORIA_DB)
                cur = conn.cursor()
                cur.execute("""
                    DELETE FROM auditoria_sesiones 
                    WHERE fecha_utc < datetime('now', '-90 days')
                """)
                conn.commit()
                conn.close()
                st.success("✅ Registros antiguos eliminados.")
                registrar_auditoria("mantenimiento", "Limpieza de registros antiguos (>90 días).")
            except Exception as e:
                st.error(f"⚠️ No se pudo limpiar la base de auditoría: {e}")


# ============================================================
# Bloque 5.7 — 🧠 Monitor de auditoría inteligente
# ------------------------------------------------------------
# - Supervisa los registros de auditoría cifrada (auditoria_sesiones)
# - Detecta comportamientos sospechosos (fallos de descifrado, IP extraña)
# - Envía alertas visuales y por Telegram al admin
# ============================================================

import hashlib
import random
from datetime import datetime, timedelta

def monitor_auditoria_inteligente():
    """
    Escanea los registros recientes en la tabla 'auditoria_sesiones'
    y detecta comportamientos sospechosos. 
    Envía alertas vía Telegram al administrador.
    """
    try:
        # ==============================
        # 📘 Carga auditoría reciente
        # ==============================
        if not AUDITORIA_DB.exists():
            return  # no hay registros todavía

        conn = sqlite3.connect(AUDITORIA_DB)
        # la tabla real tiene columnas: fecha_utc, usuario, ip, evento, detalle
        df = pd.read_sql_query(
            """
            SELECT id,
                   usuario,
                   ip AS ip_origen,
                   evento,
                   fecha_utc AS fecha,
                   detalle
            FROM auditoria_sesiones
            ORDER BY id DESC
            LIMIT 100
            """,
            conn
        )
        conn.close()

        if df.empty:
            return

        # ==============================
        # 🧠 Heurísticas de detección
        # ==============================
        alertas = []

        # 1️⃣ Repetidos "Token inválido"
        invalidos = df[df["detalle"].str.contains("Token inválido", case=False, na=False)]
        if len(invalidos) >= 3:
            alertas.append("🚨 Múltiples intentos de descifrado fallidos detectados.")

        # 2️⃣ IPs sospechosas
        ip_counts = df["ip_origen"].value_counts()
        for ip, count in ip_counts.items():
            if count > 10:
                alertas.append(f"⚠️ Actividad anómala desde IP {ip} ({count} eventos).")

        # 3️⃣ Accesos desde IP distinta al último registro del mismo usuario
        last_ip = {}
        for _, row in df.iterrows():
            user = row["usuario"]
            ip = row["ip_origen"]
            if user in last_ip and last_ip[user] != ip:
                alertas.append(f"🧩 Usuario {user} inició sesión desde IP distinta: {ip}")
            last_ip[user] = ip

        # ==============================
        # 🚨 Envío de alertas si aplica
        # ==============================
        if alertas:
            ticket = hashlib.md5(f"{datetime.utcnow()}_{random.random()}".encode()).hexdigest()[:8]
            mensaje = (
                f"🧠 *ALERTA DE SEGURIDAD DETECTADA*\n"
                f"🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                f"🎟️ Ticket: `{ticket}`\n\n"
                f"⚠️ Se detectaron los siguientes eventos:\n"
                + "\n".join(f"• {a}" for a in alertas)
                + "\n\n👁️ Revisa los registros cifrados en la pestaña ⚙️ Configuración."
            )

            # Enviar por Telegram (solo admin)
            try:
                from utils.telegram_bot import enviar_mensaje_admin
                enviar_mensaje_admin(mensaje, parse_mode="Markdown")
            except Exception as e_tel:
                log_error(e_tel, archivo="app.py", funcion="enviar_alerta_telegram")

            # Mostrar también en interfaz Streamlit si el admin está conectado
            if st.session_state.get("usuario", "").lower() == "admin":
                st.error("🧠 ALERTA DE SEGURIDAD DETECTADA ⚠️")
                with st.expander("🔎 Detalles de la alerta"):
                    for a in alertas:
                        st.warning(a)
                    st.caption(f"🎟️ Ticket de auditoría: `{ticket}`")

            # Registrar en log general
            for a in alertas:
                log_warning(a, archivo="app.py", funcion="monitor_auditoria_inteligente")

    except Exception as e:
        log_error(e, archivo="app.py", funcion="monitor_auditoria_inteligente")


# -------------------------
# Bloque 6 — LOGIN Y AUTENTICACIÓN (SIDEBAR) + RECUPERACIÓN DE CLAVE + IP APPROVAL + FIRMA + TIEMPO
# -------------------------

import json
import secrets
import string
import base64
from pathlib import Path
from datetime import datetime, timedelta
from notificador_email import enviar_email
from utils.auth import (
    actualizar_clave, get_user, login_usuario,
    request_ip_access, list_pending_ip_requests,
    approve_ip_request, deny_ip_request, _get_client_ip,
    _get_connection
)
from utils.logger import log_info, log_warning, log_error
from streamlit_drawable_canvas import st_canvas  # 🖊️ para captura de firma

RESET_TOKEN_FILE = Path("reset_tokens.json")

# ==========================================================
# Bloque 7 - 🔑 Utilidades de token para recuperación de clave
# ==========================================================

# Helper: leer/escribir tokens de recuperación (archivo local)
def _load_reset_tokens():
    try:
        if not RESET_TOKEN_FILE.exists():
            return {}
        with open(RESET_TOKEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_warning(f"No se pudo leer reset tokens: {e}", archivo="app.py", funcion="_load_reset_tokens")
        return {}

def _save_reset_tokens(data: dict):
    try:
        with open(RESET_TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        log_warning(f"No se pudo guardar reset tokens: {e}", archivo="app.py", funcion="_save_reset_tokens")

# Generar token seguro (alfanumérico)
def _generar_token(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# Guardar token temporal y asociarlo a usuario+expiración
def _guardar_token(usuario: str, correo: str, token: str, minutos: int = 15):
    tokens = _load_reset_tokens()
    vencimiento = (datetime.utcnow() + timedelta(minutes=minutos)).timestamp()
    tokens[usuario] = {"token": token, "correo": correo, "expires": vencimiento}
    _save_reset_tokens(tokens)

def _validar_token(usuario: str, token: str):
    tokens = _load_reset_tokens()
    data = tokens.get(usuario)
    if not data:
        return False, "token_no_generado"
    if data.get("token") != token:
        return False, "token_incorrecto"
    if datetime.utcnow().timestamp() > float(data.get("expires", 0)):
        return False, "token_expirado"
    return True, "ok"

# Borrado seguro de token después de uso
def _borrar_token(usuario: str):
    tokens = _load_reset_tokens()
    if usuario in tokens:
        tokens.pop(usuario, None)
        _save_reset_tokens(tokens)

# ==========================================================
# Bloque 9 -🖊️ Captura de firma de autorización
# ==========================================================
def captura_firma_ui(usuario: str):
    """
    Renderiza canvas para firma de autorización y la guarda en DB (columna firma_tratamiento_datos).
    """
    st.markdown("### ✍️ Firma de autorización de tratamiento de datos")
    st.caption("Por favor firme en el recuadro para autorizar el uso de sus datos.")

    canvas_result = st_canvas(
        fill_color="rgba(255, 255, 255, 0)",
        stroke_width=2,
        stroke_color="black",
        background_color="white",
        height=200,
        width=400,
        drawing_mode="freedraw",
        key="canvas_firma"
    )

    if st.button("Guardar firma"):
        if canvas_result.image_data is not None:
            import cv2, numpy as np
            img = (canvas_result.image_data * 255).astype(np.uint8)
            _, buf = cv2.imencode(".png", cv2.cvtColor(img, cv2.COLOR_RGBA2BGRA))
            firma_b64 = base64.b64encode(buf).decode("utf-8")

            conn = _get_connection()
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(usuarios)")
            cols = [r["name"] for r in cur.fetchall()]
            if "firma_tratamiento_datos" not in cols:
                cur.execute("ALTER TABLE usuarios ADD COLUMN firma_tratamiento_datos TEXT")
            cur.execute("UPDATE usuarios SET firma_tratamiento_datos = ? WHERE usuario = ?", (firma_b64, usuario))
            conn.commit()
            conn.close()

            st.success("✅ Firma guardada con éxito")
        else:
            st.warning("⚠️ No se detectó firma, intente de nuevo.")

# ==========================================================
# Bloque 10 -⏳ Tiempo de sesión restante
# ==========================================================
def mostrar_tiempo_restante(usuario: str, max_diario_seg: int = 7200):
    """
    Muestra en la UI cuánto tiempo le queda al usuario hoy.
    """
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("SELECT duracion_acumulada_seg FROM usuarios WHERE usuario = ?", (usuario,))
        row = cur.fetchone()
        conn.close()

        usado = int(row["duracion_acumulada_seg"] or 0) if row else 0
        restante = max(0, max_diario_seg - usado)

        mins, segs = divmod(restante, 60)
        st.info(f"⏳ Tiempo restante hoy: {mins} min {segs} seg")

    except Exception as e:
        log_error(e, archivo="app.py", funcion="mostrar_tiempo_restante")
        st.warning("⚠️ No se pudo calcular el tiempo restante.")


# ------------------------------------------------------
# 🔄 safe_rerun — recarga segura compatible (sin errores)
# ------------------------------------------------------
def safe_rerun() -> bool:
    """
    Realiza una recarga controlada de Streamlit compatible con varias versiones.
    Evita NameError y bucles infinitos.
    """
    try:
        if hasattr(st, "experimental_rerun") and callable(st.experimental_rerun):
            st.experimental_rerun()
            return True
    except Exception:
        pass

    try:
        if hasattr(st, "rerun") and callable(st.rerun):
            st.rerun()
            return True
    except Exception:
        pass

    # fallback: alterna un flag en session_state para forzar re-render
    try:
        key = "_safe_rerun_toggle"
        st.session_state[key] = not st.session_state.get(key, False)
        return True
    except Exception:
        return False


# ======================================================
# 🧩 BLOQUE 11 — LOGIN UI (SIDEBAR PERSISTENTE Y ROBUSTO)
# ======================================================
def login_ui():
    """
    🔐 Interfaz de inicio de sesión (solo en sidebar):
       - Siempre visible, no se oculta.
       - Autenticación segura (admin / usuario).
       - Recuperación de clave (correo + token).
       - Modo DEMO / REAL.
       - Carga de activos, control de análisis y logout.
    """

    client_ip = _get_client_ip()

    # ======================================================
    # 🧱 SIDEBAR CONTENEDOR PRINCIPAL
    # ======================================================
    with st.sidebar:
        st.markdown("## 🤖 El Bot de Efra — Login")

        # ======================================================
        # CASO 1️⃣ — Usuario NO autenticado
        # ======================================================
        if not st.session_state.get("usuario"):
            usuario_input = st.text_input("👤 Usuario", key="usuario_input")
            clave_input = st.text_input("🔒 Contraseña", type="password", key="clave_input")

            modo = st.radio("⚙️ Modo de operación", ["DEMO", "REAL"], index=0, horizontal=True)
            st.session_state["dry_run"] = (modo == "DEMO")

            # --- Botón de ingreso ---
            if st.button("Ingresar", key="btn_ingresar"):
                try:
                    auth = login_usuario(usuario_input, clave_input, ip_actual=client_ip)
                    if not auth or "error" in auth:
                        err = auth.get("error") if auth else "error_desconocido"
                        mensajes = {
                            "usuario_no_existe": "❌ El usuario no existe.",
                            "clave_incorrecta": "❌ Contraseña incorrecta.",
                            "ip_no_autorizada": f"⚠️ IP no autorizada: {client_ip}",
                            "ip_pendiente_autorizacion": "⚠️ IP pendiente de aprobación."
                        }
                        st.error(mensajes.get(err, "⚠️ Error interno al intentar iniciar sesión."))
                        return

                    # --- Autenticación exitosa ---
                    datos_user = get_user(auth["usuario"])
                    nombre_real = datos_user.get("nombre", auth["usuario"]) if datos_user else auth["usuario"]

                    st.session_state.update({
                        "usuario": auth["usuario"],
                        "nombre": nombre_real,
                        "rol": "admin" if auth.get("es_admin") else "user",
                        "modo_demo": modo,
                        "dry_run": (modo == "DEMO"),
                        "requiere_firma": not datos_user.get("firma_tratamiento_datos", False),
                        "mostrar_menu": True
                    })

                    try:
                        enviar_telegram(f"✅ Nuevo inicio de sesión\n👤 <b>{nombre_real}</b>\n🌐 IP: {client_ip}")
                    except Exception:
                        pass

                    st.success("✅ Sesión iniciada correctamente.")
                    st.experimental_rerun()

                except Exception as e:
                    log_error(e, archivo="app.py", funcion="login_ui")
                    st.error("⚠️ Error interno durante el login.")

            st.markdown("---")
            st.info("🔑 Ingresa tus credenciales para continuar.")

        # ======================================================
        # CASO 2️⃣ — Usuario autenticado
        # ======================================================
        else:
            nombre = st.session_state.get("nombre", st.session_state["usuario"])
            rol = st.session_state.get("rol", "user")
            rol_str = "👑 Administrador" if rol == "admin" else "🙋 Usuario"

            st.markdown(f"### 👤 {nombre}")
            st.caption(rol_str)
            st.caption(f"🌐 IP: `{client_ip}`")
            st.caption(f"🛠️ Modo: {'REAL' if not st.session_state.get('dry_run', True) else 'DEMO'}")

            # ======================================================
            # 🔏 Firma de datos obligatoria (solo 1 vez)
            # ======================================================
            if st.session_state.get("requiere_firma"):
                st.warning("⚠️ Debes registrar tu firma antes de continuar.")
                captura_firma_ui(st.session_state["usuario"])
                datos_user = get_user(st.session_state["usuario"])
                if datos_user.get("firma_tratamiento_datos"):
                    st.success("✅ Firma registrada correctamente.")
                    st.session_state["requiere_firma"] = False
                    st.experimental_rerun()

            # ======================================================
            # 🌐 FUENTE DE DATOS Y ACTIVO
            # ======================================================
            st.markdown("---")
            st.markdown("### ⚙️ Configuración de análisis")

            fuente = st.radio("📌 Fuente de activos", ["Base de Datos", "Binance"], horizontal=True, key="fuente_radio")
            st.session_state["fuente_activos"] = fuente

            try:
                if fuente == "Base de Datos":
                    from utils.db import obtener_activos
                    activos = obtener_activos() or []
                    if not activos:
                        df = pd.read_csv("activos.csv")
                        activos = df["simbolo"].dropna().unique().tolist()
                else:
                    activos = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
            except Exception as e:
                log_error(e, archivo="app.py", funcion="login_ui_activos")
                activos = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

            activo = st.selectbox("📈 Activo a analizar", activos, key="activo_select")
            stop_loss_pct = st.number_input("📉 Stop Loss (%)", min_value=0.5, max_value=10.0,
                                            value=st.session_state.get("stop_loss_pct", 2.0), step=0.5)
            st.session_state.update({"activo": activo, "stop_loss_pct": stop_loss_pct})

            # ======================================================
            # 🚀 CONTROL DE ANÁLISIS
            # ======================================================
            if not st.session_state.get("analisis_activo", False):
                if st.button("🚀 Iniciar análisis"):
                    st.session_state.update({
                        "analisis_activo": True,
                        "analisis_pendiente": {
                            "activo": activo,
                            "usar_avanzado": True,
                            "usar_agresivo": False,
                            "umbral_confianza": 85.0
                        }
                    })
                    st.experimental_rerun()
            else:
                if st.button("⛔ Finalizar análisis"):
                    st.session_state["analisis_activo"] = False
                    st.session_state["analisis_pendiente"] = None
                    st.experimental_rerun()

            st.markdown("---")

            # ======================================================
            # 🔒 CERRAR SESIÓN
            # ======================================================
            if st.button("🔒 Cerrar sesión"):
                try:
                    nombre = st.session_state.get("nombre", "Usuario")
                    st.session_state.clear()
                    st.session_state["dry_run"] = True
                    log_info(f"✅ Sesión cerrada para {nombre}", archivo="app.py", funcion="cerrar_sesion_ui")
                    st.success("✅ Sesión cerrada correctamente.")
                    st.experimental_rerun()
                except Exception as e:
                    log_error(e, archivo="app.py", funcion="cerrar_sesion_ui")
                    st.error("⚠️ No se pudo cerrar sesión correctamente.")


# ============================================================
# 🧩 BLOQUE 12 — GESTIÓN DE SESIONES ACTIVAS (ROBUSTO)
# ============================================================
def gestionar_sesiones_activas():
    """
    ✅ Marca la sesión actual en la base de datos (utils.auth.registrar_sesion)
       y muestra el estado visual en la barra lateral de Streamlit.
    
    🔒 Este bloque:
       - Garantiza que el usuario esté autenticado.
       - No rompe la app si la DB falla o está temporalmente inaccesible.
       - Informa IP y usuario en curso.
    """
    try:
        usuario_actual = st.session_state.get("usuario")

        if usuario_actual:
            try:
                # 🧾 Registrar la sesión en la base de datos
                registrar_sesion(usuario_actual)
                ip_actual = st.session_state.get("ip_usuario", "0.0.0.0")

                # 💡 Mostrar info de sesión en la barra lateral
                st.sidebar.markdown("---")
                st.sidebar.info(f"🟢 Sesión activa para: **{usuario_actual}**")
                st.sidebar.caption(f"📡 IP: {ip_actual}")

                log_info(f"Sesión activa registrada: {usuario_actual} ({ip_actual})",
                         archivo="app.py", funcion="gestionar_sesiones_activas")

            except Exception as e_reg:
                log_warning(f"⚠️ registrar_sesion falló: {e_reg}",
                            archivo="app.py", funcion="gestionar_sesiones_activas")
                st.sidebar.warning("⚠️ No se pudo registrar la sesión en la base de datos.")
        else:
            # 🚫 No hay sesión iniciada
            st.sidebar.warning("⚠️ No hay usuario autenticado en este momento.")
            log_warning("gestionar_sesiones_activas: sin usuario autenticado.",
                        archivo="app.py", funcion="gestionar_sesiones_activas")

    except Exception as e:
        # 🧯 Captura global de fallos del bloque
        log_error(e, archivo="app.py", funcion="gestionar_sesiones_activas")
        st.sidebar.error("❌ Error gestionando las sesiones activas.")


# ============================================================
# 🧩 BLOQUE 12 A — VERIFICACIÓN DE SESIÓN (CHECK DE AUTENTICACIÓN)
# ============================================================
def check_session():
    """
    🚨 Verifica si hay usuario autenticado antes de ejecutar cualquier
        bloque protegido (por ejemplo, pestañas de análisis o trading).
    
    ⚙️ Si no hay sesión activa:
       - Muestra una advertencia clara.
       - Detiene la ejecución de Streamlit con st.stop().
    
    🧠 Uso típico:
        check_session()
        ... (código protegido)
    """
    try:
        if not st.session_state.get("usuario"):
            st.warning("⚠️ Debes iniciar sesión para acceder al bot.")
            log_warning("Intento de acceso sin sesión activa.",
                        archivo="app.py", funcion="check_session")
            st.stop()  # 🚫 Detiene el flujo Streamlit sin romper la app
        else:
            usuario = st.session_state["usuario"]
            log_info(f"✅ Sesión válida detectada para {usuario}",
                     archivo="app.py", funcion="check_session")

    except Exception as e:
        log_error(e, archivo="app.py", funcion="check_session")
        st.sidebar.error("❌ Error verificando la sesión.")


# ============================================================
# 🔐 BLOQUE 12 B (EXTRA) — GESTIÓN DE CLAVE MAESTRA (ROBUSTO)
# ============================================================
import os
from cryptography.fernet import Fernet

def load_master_key() -> bytes:
    """
    🧱 Carga o crea la clave maestra del sistema (AES/Fernet).
    
    📁 Ruta: data/secure/clave_aes.key
    
    🔒 Características:
       - Si el archivo no existe, se crea automáticamente.
       - Garantiza que el directorio 'data/secure' exista.
       - Retorna siempre un objeto bytes válido.
       - Tolerante a errores: nunca rompe la ejecución del bot.
    
    ⚠️ Esta clave se usa para cifrar/descifrar tokens, API keys y contraseñas.
    """
    try:
        carpeta_secure = os.path.join("data", "secure")
        archivo_clave = os.path.join(carpeta_secure, "clave_aes.key")

        # ✅ Crear carpeta si no existe
        if not os.path.exists(carpeta_secure):
            os.makedirs(carpeta_secure, exist_ok=True)
            log_info(f"📂 Carpeta creada: {carpeta_secure}",
                     archivo="security.py", funcion="load_master_key")

        # ✅ Si el archivo ya existe → cargar
        if os.path.isfile(archivo_clave):
            with open(archivo_clave, "rb") as f:
                clave = f.read().strip()
                if clave:
                    log_info("🔑 Clave maestra cargada correctamente.",
                             archivo="security.py", funcion="load_master_key")
                    return clave
                else:
                    log_warning("⚠️ Archivo de clave vacío, regenerando...",
                                archivo="security.py", funcion="load_master_key")

        # 🆕 Crear nueva clave si no existe o está corrupta
        clave_nueva = Fernet.generate_key()
        with open(archivo_clave, "wb") as f:
            f.write(clave_nueva)
        log_info("🆕 Nueva clave maestra generada y guardada exitosamente.",
                 archivo="security.py", funcion="load_master_key")
        return clave_nueva

    except Exception as e:
        # 🚨 Fallback: generar clave temporal en memoria
        log_error(e, archivo="security.py", funcion="load_master_key")
        clave_tmp = Fernet.generate_key()
        log_warning("⚠️ No se pudo acceder al archivo de clave. Usando clave temporal (no persistente).",
                    archivo="security.py", funcion="load_master_key")
        return clave_tmp

# ============================================================
# Bloque 13 — TABS DINÁMICOS
# ============================================================
def construir_tabs():
    """
    Construye las pestañas principales según permisos/rol.
    check_session() se llama dentro para asegurar que el usuario haya iniciado sesión.
    Retorna: tabs, idx
    """
    # Asegurar sesión
    check_session()

    permisos = st.session_state.get("permisos", {}) or {}
    es_admin = permisos.get("es_admin", False)

    if es_admin:
        tabs_nombres = [
            "📊 Analizar",
            "🧠 Entrenar",
            "📜 Historial",
            "📈 Backtesting",
            "🏆 Ranking",
            "⚙️ Configuración"
        ]
    else:
        tabs_nombres = ["📊 Analizar", "🧠 Entrenar", "📜 Historial"]
        if permisos.get("ver_backtesting", False):
            tabs_nombres.append("📈 Backtesting")
        if permisos.get("ver_senales", False):
            tabs_nombres.append("🏆 Ranking")

    tabs = st.tabs(tabs_nombres)
    idx = {name: i for i, name in enumerate(tabs_nombres)}
    return tabs, idx

# ------------------------------------------------------------
# Bloque 15 - 📊 tab_analizar (versión completa y robusta)
# ------------------------------------------------------------
def tab_analizar(tabs, idx):
    """
    Muestra el análisis de un activo, resultados de IA, gráficos,
    niveles técnicos y opciones de inversión.

    ✅ Características:
       - Mantiene la estructura original completa.
       - Agrega refuerzo dinámico de confianza IA (>85%).
       - Gráfico enriquecido con señales, métricas y backtest.
       - Manejo robusto de errores y estado de sesión.
    """

    # ===============================
    # Seguridad: requiere sesión activa
    # ===============================
    check_session()

    if "📊 Analizar" not in idx:
        return

    with tabs[idx["📊 Analizar"]]:
        # ============================
        # Estilos CSS locales
        # ============================
        st.markdown(
            """
            <style>
            div[data-testid="stMetricValue"],
            div[data-testid="stMetricDelta"],
            h1, h2, h3, h4, h5, h6, p, span, label,
            .streamlit-expanderHeader,
            .stCheckbox label, .stSlider label,
            .senal-card h3, .senal-card p {
                color: black !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        st.markdown("---")
        st.header("📈 Resultado del análisis y ejecución")

        # ===================================
        # Verificar si hay análisis pendiente
        # ===================================
        datos = st.session_state.get("analisis_pendiente")
        if not datos:
            st.info("ℹ️ Selecciona un activo en el menú lateral y presiona 'Iniciar análisis'.")
            return

        try:
            # ----------------------------
            # Imports locales
            # ----------------------------
            from datetime import datetime, timedelta
            import uuid, numpy as np
            from utils.prediccion import combinar_senales
            from telegram_alertas import send_telegram_alert
            from utils.graficos import graficar_velas_con_senal
            try:
                from utils.trading import ejecutar_orden_segura
            except Exception:
                ejecutar_orden_segura = None

            activo = datos.get("activo")
            usar_avanzado = bool(datos.get("usar_avanzado", True))
            usar_agresivo = bool(datos.get("usar_agresivo", False))
            umbral_confianza = float(
                datos.get("umbral_confianza", st.session_state.get("umbral_confianza", 70.0))
            ) / 100.0

            # ----------------------------
            # Botón de recalcular análisis
            # ----------------------------
            col_r1, col_r2 = st.columns([1, 5])
            with col_r1:
                if st.button("🔁 Recalcular ahora"):
                    for k in ["analisis_resultado", "ultima_analisis_activo", "hora_analisis", "hora_prediccion"]:
                        st.session_state.pop(k, None)
                    st.session_state["_force_recalc"] = True

            force_recalc = st.session_state.pop("_force_recalc", False)
            debe_recalcular = (
                force_recalc
                or st.session_state.get("ultima_analisis_activo") != activo
                or "analisis_resultado" not in st.session_state
            )

            # ----------------------------
            # Generar o recuperar resultado
            # ----------------------------
            if debe_recalcular:
                resultado = bot.analizar_activo(
                    activo=activo,
                    usar_avanzado=usar_avanzado,
                    usar_agresivo=usar_agresivo
                )
                if not resultado:
                    st.error("❌ No se pudo obtener análisis. Revisa logs.")
                    return

                if resultado.get("abort") is True:
                    st.error("❌ Orden cancelada: monto mínimo 10 USDT requerido.")
                    return

                metodologias = resultado.get("metodologias", []) or []
                prediccion_lstm = resultado.get("prediccion_lstm", None)

                # Combinar señales técnicas + IA
                combinado = combinar_senales(
                    metodologias,
                    prediccion_lstm=prediccion_lstm,
                    peso_lstm=0.75,
                    umbral=0.80,
                    force_threshold=0.90
                )

                if combinado.get("senal") == "HOLD":
                    combinado["senal"] = "BUY" if combinado.get("score", 0) >= 0 else "SELL"

                # --------------------------
                # 💪 Refuerzo dinámico IA
                # --------------------------
                try:
                    from utils.confidence_boost import dynamic_confidence_boost
                    base_conf = float(combinado.get("confianza", 0.0))
                    nueva_conf, boosted = dynamic_confidence_boost(
                        metodologias=metodologias,
                        prediccion_lstm={"confianza": (prediccion_lstm.get("confianza")
                                                       if isinstance(prediccion_lstm, dict)
                                                       else 0.0)},
                        confianza_actual=base_conf,
                        score_methods=float(np.mean([m.get("confianza", 0.0) for m in metodologias]) if metodologias else 0.0),
                        rf_score=float(combinado.get("rf_score", 0.0) or 0.0),
                        consistencia=float(combinado.get("consistencia", 1.0) or 1.0),
                        error_score=float(combinado.get("error_score", 0.0)),
                        estabilidad=float(combinado.get("estabilidad", 0.5)),
                        resumen=f"Boost {activo}"
                    )
                    if boosted and nueva_conf > base_conf:
                        combinado["confianza"] = float(np.clip(nueva_conf, 0.0, 1.0))
                        combinado["boosted"] = True
                    if combinado.get("boosted") and combinado.get("confianza", 0.0) < 0.85:
                        if combinado.get("consistencia", 0.8) >= 0.8:
                            combinado["confianza"] = 0.85
                except Exception as ecb:
                    log_warning(f"dynamic_confidence_boost fallo: {ecb}", archivo="app.py", funcion="tab_analizar")

                # Guardar resultado
                st.session_state["analisis_resultado"] = {
                    "raw": resultado,
                    "combinado": combinado,
                    "prediccion_lstm": prediccion_lstm
                }
                st.session_state["ultima_analisis_activo"] = activo
                st.session_state["hora_analisis"] = datetime.now()
                st.session_state["hora_prediccion"] = st.session_state["hora_analisis"] + timedelta(minutes=5)
            else:
                cached = st.session_state.get("analisis_resultado", {})
                resultado = cached.get("raw", {}) or {}
                combinado = cached.get("combinado", {"senal": "BUY", "confianza": 0.0, "resumen": [], "forced": False})
                prediccion_lstm = cached.get("prediccion_lstm", None)

            # ----------------------------
            # Variables clave
            # ----------------------------
            senal_final = combinado.get("senal", "BUY").upper()
            confianza_val = float(combinado.get("confianza", 0.0))
            confianza_pct = confianza_val * 100.0
            score_val = float(combinado.get("score", 0.0))
            accion_es = {"BUY": "Comprar", "SELL": "Vender"}.get(senal_final, "Comprar")

            # -------------------------
            # 🤖 Predicción IA
            # -------------------------
            st.markdown("## 🤖 Predicción IA")

            if senal_final == "BUY":
                color_pred, texto_pred = "#b6fcb6", "✅ Comprar"
            elif senal_final == "SELL":
                color_pred, texto_pred = "#ff9999", "❌ Vender"
            else:
                color_pred, texto_pred = "#f0f0f0", "⏸️ Sin decisión"

            st.markdown(
                f"""
                <div style="padding:18px;border-radius:12px;background-color:{color_pred};border:1px solid #000;">
                    <h3 style="margin:0;color:black;">{texto_pred}</h3>
                    <p style="margin:0;font-size:16px;color:black;">
                        Confianza IA: <b>{confianza_pct:.2f}%</b><br>
                        Score: {score_val:.3f}
                    </p>
                </div>
                """,
                unsafe_allow_html=True
            )

            # ==================================================
            # 📊 Gráfico de velas con señal
            # ==================================================
            try:
                df_graf = resultado.get("df")
                if df_graf is not None and not df_graf.empty:
                    fig = graficar_velas_con_senal(df_graf, senal_final)
                    import plotly.graph_objects as go
                    if isinstance(fig, go.Figure):
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.pyplot(fig)
                else:
                    st.info("⚠️ No hay datos para graficar este activo.")
            except Exception as e_graf:
                log_warning(f"Error generando gráfico: {e_graf}", archivo="app.py", funcion="tab_analizar")

            # ==================================================
            # 📈 Métricas de rendimiento IA (histórico)
            # ==================================================
            st.markdown("### 📈 Métricas de rendimiento IA (histórico reciente)")
            try:
                from utils.modelo import backtest_ensemble
                df_actual = resultado.get("df")
                if df_actual is not None and not df_actual.empty:
                    _, metricas_ia = backtest_ensemble(df_actual, activo)
                else:
                    metricas_ia = None

                if metricas_ia:
                    col1, col2, col3, col4, col5 = st.columns(5)
                    col1.metric("🎯 Precisión", f"{metricas_ia.get('precision', 0)*100:.2f}%")
                    col2.metric("⚖️ Recall", f"{metricas_ia.get('recall', 0)*100:.2f}%")
                    col3.metric("📊 F1-Score", f"{metricas_ia.get('f1', 0)*100:.2f}%")
                    col4.metric("💰 WinRate", f"{metricas_ia.get('winrate', 0)*100:.2f}%")
                    col5.metric("📈 PnL simulado", f"{metricas_ia.get('ganancia_pct', 0):.2f}%")
                    st.caption(f"Backtest con datos recientes de {activo} usando ensemble IA optimizado")
                else:
                    st.info("ℹ️ No se encontraron métricas recientes para este activo.")
            except Exception as e_metr:
                log_warning(f"Error obteniendo métricas IA: {e_metr}", archivo="app.py", funcion="tab_analizar")
                st.warning("⚠️ No se pudieron calcular métricas IA (revisa logs).")

            # ===================================================
            # 💰 Configuración de inversión
            # ===================================================
            st.markdown("### 💰 Configuración de inversión")

            saldo_disp = None
            try:
                if st.session_state.get("usuario"):
                    saldo_disp = obtener_saldo_usuario(st.session_state["usuario"])
                else:
                    if "trading_executor" in globals() and trading_executor is not None:
                        saldo_disp = trading_executor.get_balance("USDT")
            except Exception as e:
                log_warning(e, archivo="app.py", funcion="tab_analizar")

            if saldo_disp is None:
                if st.session_state.get("dry_run", True):
                    st.info("💵 Saldo disponible: **100.00 USDT (DEMO simulado)**")
                    saldo_disp = 100.0
                else:
                    st.warning("💵 Saldo disponible: N/D (⚠️ sin conexión o sin claves).")
            else:
                st.success(f"💵 Saldo disponible: **{saldo_disp:.2f} USDT**")

            monto_inversion = st.slider(
                "💵 Selecciona monto a invertir (USDT)",
                min_value=10,
                max_value=100,
                value=int(round(float(st.session_state.get("monto_inversion", 10.0)))),
                step=1
            )
            st.session_state["monto_inversion"] = float(monto_inversion)

            # ===================================================
            # 🎮 Simulación de inversión DEMO
            # ===================================================
            if st.session_state.get("dry_run", True):
                st.markdown("### 🎮 Simulación de inversión DEMO")
                if st.button("🚀 Simular inversión DEMO ahora"):
                    try:
                        import random
                        df_demo = resultado.get("df")
                        entry_price = float(df_demo["close"].iloc[-1]) if df_demo is not None and not df_demo.empty else random.uniform(20000, 30000)
                        monto = float(st.session_state.get("monto_inversion", 10.0))
                        cambio_pct = random.uniform(-0.05, 0.05)
                        precio_final = entry_price * (1 + cambio_pct)
                        ganancia_pct = (precio_final - entry_price) / entry_price * 100 if senal_final == "BUY" else (entry_price - precio_final) / entry_price * 100
                        capital_final = monto * (1 + ganancia_pct / 100)
                        color_bg, emoji = ("#b6fcb6", "🟢") if ganancia_pct >= 0 else ("#ff9999", "🔴")

                        st.markdown(
                            f"""
                            <div style="padding:18px;border-radius:12px;background-color:{color_bg};border:1px solid #000;">
                                <h3 style="margin:0;color:black;">{emoji} Resultado de la simulación DEMO</h3>
                                <p style="margin:0;font-size:16px;color:black;">
                                    Precio entrada: <b>{entry_price:.2f} USDT</b><br>
                                    Precio final simulado: <b>{precio_final:.2f} USDT</b><br>
                                    Ganancia/Pérdida: <b>{ganancia_pct:.2f}%</b><br>
                                    Capital final: <b>{capital_final:.2f} USDT</b>
                                </p>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    except Exception as e_sim:
                        log_error(e_sim, archivo="app.py", funcion="simulacion_demo")
                        st.error("❌ No se pudo simular la inversión DEMO.")

            # ===================================================
            # 🚀 Auto-trading seguro
            # ===================================================
            if senal_final in ["BUY", "SELL"] and confianza_val >= umbral_confianza:
                ejecutar_auto = st.checkbox("🚀 Ejecutar auto-trading con esta señal", value=False)
                if ejecutar_auto and ejecutar_orden_segura:
                    try:
                        ejec_id = str(uuid.uuid4())
                        res = ejecutar_orden_segura(
                            activo=activo,
                            accion=senal_final,
                            monto=st.session_state["monto_inversion"],
                            stop_loss_pct=0.02,
                            take_profit_pct=0.05,
                            usuario=st.session_state.get("usuario", "desconocido"),
                            dry_run=st.session_state.get("dry_run", True),
                            precision=combinado.get("confianza")
                        )
                        if res.get("success"):
                            st.success("✅ Orden enviada correctamente a Binance.")
                        else:
                            st.warning(f"⚠️ Orden fallida: {res.get('reason', 'N/A')}")
                    except Exception as e_exec:
                        log_error(e_exec, archivo="app.py", funcion="auto_trading")
                        st.error("❌ Error ejecutando auto-trading.")

            # ===================================================
            # 🧮 Inversión compuesta (en tiempo real)
            # ===================================================
            if not st.session_state.get("dry_run", True):
                st.markdown("### 🧮 Inversión compuesta en tiempo real")
                try:
                    if not st.session_state.get("inversion_activa", False):
                        if st.button("🚀 Iniciar inversión compuesta (10 USDT)"):
                            balance = trading_executor.get_balance("USDT") or 0.0
                            if balance < 10.0:
                                st.error(f"❌ Saldo insuficiente ({balance:.2f} USDT).")
                            else:
                                res = trading_executor.iniciar_inversion_compuesta(
                                    symbol=activo,
                                    side=senal_final,
                                    monto_inicial=10.0,
                                    stop_drawdown_pct=2.0,
                                    usuario=st.session_state.get("usuario", "desconocido")
                                )
                                st.success("✅ Inversión compuesta iniciada correctamente.")
                    else:
                        if st.button("🛑 Finalizar inversión compuesta"):
                            st.session_state["inversion_activa"] = False
                            st.warning("⚠️ Inversión compuesta finalizada manualmente.")
                except Exception as e_comp:
                    log_error(e_comp, archivo="app.py", funcion="inversion_compuesta")
                    st.error("⚠️ Error general en inversión compuesta.")
        except Exception as e_tab:
            log_error(e_tab, archivo="app.py", funcion="tab_analizar_general")
            st.error("⚠️ Error general en la pestaña de análisis.")
        finally:
            log_info("🧩 Bloque principal de tab_analizar cerrado correctamente.", archivo="app.py", funcion="tab_analizar_general")


# ============================================================
# Bloque 16 — TAB "🧠 Entrenar"
# ------------------------------------------------------------
# - Permite al usuario entrenar el modelo IA (LSTM u otro)
# - Se definen parámetros de entrenamiento
# - Se guarda el modelo y métricas asociadas
# ============================================================

def tab_entrenar(tabs, idx):
    # ✅ Requiere login antes de continuar
    check_session()

    if "🧠 Entrenar" in idx:
        with tabs[idx["🧠 Entrenar"]]:
            st.markdown("---")
            st.header("🧠 Entrenamiento del modelo IA")

            st.info("⚡ Aquí puedes entrenar el modelo de predicción de precios con LSTM.")

            # ---------------------------
            # 📌 Parámetros de entrenamiento
            # ---------------------------
            col1, col2, col3 = st.columns(3)

            with col1:
                epochs = st.number_input(
                    "📌 Epochs", min_value=1, max_value=500, value=50, step=10,
                    help="Número de veces que el modelo verá los datos completos."
                )

            with col2:
                batch_size = st.number_input(
                    "📦 Batch size", min_value=8, max_value=512, value=32, step=8,
                    help="Cantidad de muestras procesadas antes de actualizar los pesos."
                )

            with col3:
                lookback = st.number_input(
                    "⏳ Lookback (días)", min_value=10, max_value=500, value=60, step=10,
                    help="Ventana de días que el modelo usará como entrada."
                )

            # ---------------------------
            # 🚀 Botón de entrenamiento
            # ---------------------------
            if st.button("🚀 Entrenar modelo"):
                try:
                    try:
                        from utils.modelo import entrenar_y_predecir
                    except ImportError as e:
                        st.error("❌ No se pudo importar el módulo de entrenamiento.")
                        log_error(e, archivo="app.py", funcion="tab_entrenar")
                        return

                    st.info("⌛ Entrenando modelo... esto puede tardar varios minutos.")
                    with st.spinner("Entrenando modelo IA..."):
                        # Ejecutar entrenamiento
                        metricas, predicciones = entrenar_y_predecir(
                            epochs=epochs,
                            batch_size=batch_size,
                            lookback=lookback
                        )

                    # ---------------------------
                    # 📊 Mostrar métricas
                    # ---------------------------
                    if metricas:
                        st.success("✅ Entrenamiento completado.")
                        st.subheader("📊 Métricas del modelo")
                        st.json(metricas)
                    else:
                        st.warning("⚠️ El entrenamiento finalizó, pero no se devolvieron métricas.")

                    # ---------------------------
                    # 📈 Gráfico de predicciones
                    # ---------------------------
                    try:
                        from utils.graficos import plot_predicciones_vs_real

                        if predicciones:
                            df    = predicciones.get("df")
                            preds = predicciones.get("valores")

                            if df is not None and preds is not None and len(preds) > 0:
                                st.subheader("📈 Proyección vs Real")
                                plot_predicciones_vs_real(df, preds)
                            else:
                                st.warning("⚠️ No se generaron predicciones suficientes para graficar.")
                        else:
                            st.info("ℹ️ No se devolvieron predicciones desde el modelo.")
                    except Exception as e:
                        log_error(e, archivo="app.py", funcion="graficar_predicciones")
                        st.error("❌ Error al generar gráfico de predicciones.")

                except Exception as e:
                    log_error(e, archivo="app.py", funcion="tab_entrenar")
                    st.error("❌ Error inesperado al entrenar el modelo. Revisa logs.")


# ============================================================
# Bloque 17 — TAB "📜 Historial"
# ------------------------------------------------------------
# - Permite visualizar señales pasadas y operaciones ejecutadas
# - Incluye filtros por fecha, activo y resultado
# - Integra exportación de datos (CSV)
# ============================================================

def tab_historial(tabs, idx):
    check_session()  # ✅ Requiere login antes de acceder

    if "📜 Historial" in idx:
        with tabs[idx["📜 Historial"]]:
            st.markdown("---")
            st.header("📜 Historial de señales y operaciones")

            try:
                from utils.db import obtener_historial  # ⚠️ Debe estar implementado en utils/db.py

                # ---------------------------
                # 📌 Filtros de búsqueda
                # ---------------------------
                col1, col2, col3 = st.columns(3)

                with col1:
                    fecha_inicio = st.date_input("📅 Desde", datetime.now().date() - timedelta(days=7))
                with col2:
                    fecha_fin = st.date_input("📅 Hasta", datetime.now().date())
                with col3:
                    activo_filtro = st.text_input("🔍 Activo (ej: BTCUSDT)", "")

                # ---------------------------
                # 🔎 Obtener historial
                # ---------------------------
                historial = obtener_historial(
                    usuario=st.session_state["usuario"],
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    activo=activo_filtro
                )

                if historial is None or historial.empty:
                    st.warning("⚠️ No se encontraron registros en el rango seleccionado.")
                    return

                # ---------------------------
                # 📋 Mostrar tabla
                # ---------------------------
                st.dataframe(historial, use_container_width=True)

                # ---------------------------
                # 📊 Métricas resumidas
                # ---------------------------
                st.subheader("📊 Resumen de resultados")
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("📌 Total señales", len(historial))
                with col2:
                    ganadoras = historial[historial["resultado"] == "ganancia"]
                    st.metric("✅ Ganadoras", len(ganadoras))
                with col3:
                    perdedoras = historial[historial["resultado"] == "perdida"]
                    st.metric("❌ Perdedoras", len(perdedoras))

                # ---------------------------
                # 💾 Exportar a CSV
                # ---------------------------
                csv = historial.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="💾 Descargar CSV",
                    data=csv,
                    file_name="historial_bot.csv",
                    mime="text/csv"
                )

            except Exception as e:
                log_error(e, archivo="app.py", funcion="tab_historial")
                st.error("❌ Error al cargar el historial. Revisa logs.")

# ============================================================
# Bloque 18 — TAB "📈 Backtesting"
# ------------------------------------------------------------
# - Permite probar estrategias con datos históricos
# - Usa métricas financieras (Sharpe, winrate, drawdown)
# - Incluye gráficos comparativos y resumen de resultados
# ============================================================

def tab_backtesting(tabs, idx):
    check_session()  # ✅ Requiere login antes de acceder

    if "📈 Backtesting" in idx:
        with tabs[idx["📈 Backtesting"]]:
            st.markdown("---")
            st.header("📈 Backtesting de estrategias")

            try:
                # ---------------------------
                # ⚙️ Parámetros de simulación
                # ---------------------------
                col1, col2, col3 = st.columns(3)

                with col1:
                    activo = st.text_input("🔍 Activo (ej: BTCUSDT)", "BTCUSDT")
                with col2:
                    intervalo = st.selectbox("⏱ Intervalo", ["1m", "5m", "15m", "1h", "4h", "1d"], index=5)
                with col3:
                    capital_inicial = st.number_input("💰 Capital inicial (USDT)", 100, step=50)

                st.markdown("### ⚙️ Configuración de la estrategia")
                estrategia = st.selectbox(
                    "📌 Selecciona estrategia",
                    ["IA LSTM", "RSI + MACD", "Cruce de Medias", "Mixta"]
                )

                # ---------------------------
                # ▶️ Ejecutar backtest
                # ---------------------------
                if st.button("▶️ Ejecutar Backtest"):
                    from utils.backtesting import ejecutar_backtest  # ⚠️ Debe estar implementado

                    with st.spinner("⏳ Ejecutando backtest, por favor espera..."):
                        resultados, metricas, df_equity = ejecutar_backtest(
                            activo=activo,
                            intervalo=intervalo,
                            capital_inicial=capital_inicial,
                            estrategia=estrategia
                        )

                    # ---------------------------
                    # ✅ Resultados principales
                    # ---------------------------
                    st.success("✅ Backtest finalizado")

                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("💰 Capital final", f"{metricas.get('capital_final', 0):.2f} USDT")
                    with col2:
                        st.metric("📈 Ganancia %", f"{metricas.get('ganancia_pct', 0):.2f}%")
                    with col3:
                        st.metric("✅ Winrate", f"{metricas.get('winrate', 0):.2f}%")
                    with col4:
                        st.metric("📉 Drawdown", f"{metricas.get('max_drawdown', 0):.2f}%")

                    # ---------------------------
                    # 📊 Gráfico de evolución
                    # ---------------------------
                    if df_equity is not None and not df_equity.empty:
                        st.subheader("📊 Evolución del capital")
                        import plotly.express as px
                        fig = px.line(df_equity, x="fecha", y="capital", title="Evolución del capital")
                        fig.update_layout(template="plotly_dark")
                        st.plotly_chart(fig, use_container_width=True)

                    # ---------------------------
                    # 📜 Tabla de operaciones
                    # ---------------------------
                    if resultados is not None and not resultados.empty:
                        st.subheader("📜 Operaciones simuladas")
                        st.dataframe(resultados, use_container_width=True)

                        # Exportación a CSV
                        csv = resultados.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            label="💾 Descargar resultados (CSV)",
                            data=csv,
                            file_name=f"backtest_{activo}_{estrategia}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.warning("⚠️ No se generaron operaciones en este backtest.")

            except Exception as e:
                log_error(e, archivo="app.py", funcion="tab_backtesting")
                st.error("❌ Error durante el backtesting. Revisa logs.")


# ============================================================
# Bloque 19 — TAB "🏆 Ranking"
# ------------------------------------------------------------
# - Muestra un leaderboard de usuarios / estrategias
# - Ordena por ganancia acumulada o winrate
# - Incluye tabla interactiva y exportación
# ============================================================

def tab_ranking(tabs, idx):
    check_session()  # ✅ Requiere login antes de acceder

    if "🏆 Ranking" in idx:
        with tabs[idx["🏆 Ranking"]]:
            st.markdown("---")
            st.header("🏆 Ranking de Rendimiento")

            try:
                # ---------------------------
                # 📌 Filtros y opciones
                # ---------------------------
                col1, col2 = st.columns(2)
                with col1:
                    periodo = st.selectbox("📅 Período", ["Última semana", "Último mes", "3 meses", "Todo"])
                with col2:
                    criterio = st.selectbox("📊 Ordenar por", ["Ganancia %", "Winrate", "Operaciones"])

                # ---------------------------
                # ⚠️ Datos de ejemplo
                # ---------------------------
                # Aquí deberías conectar con tu base de datos real
                data = pd.DataFrame([
                    {"usuario": "Ana", "ganancia_pct": 25.3, "winrate": 65.0, "operaciones": 42},
                    {"usuario": "Efra", "ganancia_pct": 18.7, "winrate": 70.0, "operaciones": 55},
                    {"usuario": "Daniel", "ganancia_pct": 12.4, "winrate": 55.0, "operaciones": 31},
                ])

                # Ordenar según criterio
                if criterio == "Ganancia %":
                    data = data.sort_values(by="ganancia_pct", ascending=False)
                elif criterio == "Winrate":
                    data = data.sort_values(by="winrate", ascending=False)
                else:
                    data = data.sort_values(by="operaciones", ascending=False)

                # ---------------------------
                # 📋 Mostrar tabla
                # ---------------------------
                st.subheader("📋 Tabla de clasificación")
                st.dataframe(data, use_container_width=True)

                # ---------------------------
                # 📊 Gráfico ranking
                # ---------------------------
                st.subheader("📊 Comparación visual")
                import plotly.express as px
                fig = px.bar(
                    data,
                    x="usuario",
                    y="ganancia_pct",
                    color="winrate",
                    title="Ranking por rendimiento",
                    text="ganancia_pct"
                )
                fig.update_layout(template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)

                # ---------------------------
                # 💾 Exportación
                # ---------------------------
                csv = data.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="💾 Descargar ranking (CSV)",
                    data=csv,
                    file_name=f"ranking_{periodo.replace(' ', '_')}.csv",
                    mime="text/csv"
                )

            except Exception as e:
                log_error(e, archivo="app.py", funcion="tab_ranking")
                st.error("❌ Error al generar el ranking. Revisa logs.")

# ============================================================
# Bloque 20 — TAB "⚙️ Configuración"
# ------------------------------------------------------------
# - Gestión de usuarios (solo admin)
# - Visualización y edición de usuarios
# - Visualización de sesiones activas
# - Visualización de firma y estado de IP
# - Control de tiempo de uso y 📜 historial de sesiones
# - Panel de auditoría de sesiones cifradas (solo admin)
# ============================================================

import pandas as pd
import base64
import sqlite3
import io

def tab_configuracion(tabs, idx):
    check_session()  # ✅ Requiere login antes de acceder

    if "⚙️ Configuración" in idx:
        with tabs[idx["⚙️ Configuración"]]:
            st.markdown("---")
            st.header("⚙️ Configuración de la Aplicación")

            try:
                usuario_actual = st.session_state.get("usuario", "desconocido")
                permisos = st.session_state.get("permisos", {})

                # ---------------------------
                # 👥 Gestión de usuarios (solo admin)
                # ---------------------------
                if permisos.get("es_admin", False):
                    st.subheader("👥 Gestión de Usuarios")

                    opcion = st.selectbox(
                        "Acción",
                        ["Crear usuario", "Resetear clave", "Cambiar permisos", "Editar usuario"]
                    )

                    if opcion == "Crear usuario":
                        nuevo_user = st.text_input("👤 Nuevo usuario")
                        nueva_clave = st.text_input("🔑 Clave", type="password")
                        nombre_real = st.text_input("📝 Nombre (opcional)", value=nuevo_user or "")
                        correo_user = st.text_input("📧 Correo (opcional)")
                        st.markdown("### 🔐 Claves Binance (opcional para activar trading real)")
                        clave1 = st.text_input("🧾 BINANCE_API_KEY (clave pública)")
                        clave2 = st.text_input("🔒 BINANCE_API_SECRET (clave secreta)", type="password")
                        activar_chk = st.checkbox(
                            "Activar cuenta (si marcas esto, se intentará habilitar)", 
                            value=False
                        )

                        if st.button("➕ Crear usuario"):
                            try:
                                ok = ensure_user(
                                    nuevo_user,
                                    nueva_clave,
                                    nombre=nombre_real or nuevo_user,
                                    correo=correo_user,
                                    es_admin=False,
                                    estado="activo" if activar_chk and clave1 and clave2 else "pendiente",
                                    clave1_binance=clave1 if clave1 else None,
                                    clave2_binance=clave2 if clave2 else None
                                )

                                if not ok:
                                    st.error("❌ No se pudo crear el usuario (revisa logs).")
                                else:
                                    st.success(
                                        f"✅ Usuario {nuevo_user} creado. "
                                        f"Estado: {'activo' if activar_chk and clave1 and clave2 else 'pendiente'}"
                                    )
                                    if not (clave1 and clave2):
                                        st.info(
                                            "ℹ️ El usuario quedó en estado 'pendiente' "
                                            "hasta que se registren ambas claves de Binance."
                                        )
                            except Exception as e:
                                log_error(e, archivo="app.py", funcion="crear_usuario")
                                st.error("❌ Error creando usuario.")

                    elif opcion == "Resetear clave":
                        user_reset = st.text_input("👤 Usuario a resetear")
                        nueva_clave = st.text_input("🔑 Nueva clave", type="password")
                        if st.button("🔄 Resetear clave"):
                            try:
                                from utils.auth import actualizar_clave
                                if actualizar_clave(user_reset, nueva_clave):
                                    st.success(f"✅ Clave reseteada para {user_reset}.")
                                else:
                                    st.error("❌ No se pudo resetear la clave.")
                            except Exception as e:
                                log_error(e, archivo="app.py", funcion="resetear_clave")
                                st.error("❌ Error reseteando clave.")

                    elif opcion == "Cambiar permisos":
                        user_perm = st.text_input("👤 Usuario")
                        es_admin = st.checkbox("Administrador")
                        if st.button("⚙️ Guardar permisos"):
                            try:
                                ensure_user(user_perm, es_admin=es_admin)
                                st.success(f"✅ Permisos actualizados para {user_perm}.")
                            except Exception as e:
                                log_error(e, archivo="app.py", funcion="cambiar_permisos")
                                st.error("❌ Error cambiando permisos.")

                    elif opcion == "Editar usuario":
                        user_edit = st.text_input("👤 Usuario a editar")
                        if st.button("🔍 Cargar datos"):
                            datos = get_user(user_edit)
                            if datos:
                                with st.form("form_editar_usuario"):
                                    estado_actual = st.selectbox(
                                        "Estado actual",
                                        ["habilitado", "inhabilitado"],
                                        index=0 if datos.get("estado_actual", "habilitado") == "habilitado" else 1
                                    )
                                    estado_ip = st.selectbox(
                                        "Estado IP",
                                        ["pendiente", "aprobada", "denegada"],
                                        index={"pendiente":0,"aprobada":1,"denegada":2}.get(datos.get("estado_ip","pendiente"),0)
                                    )
                                    ip_aprobada = st.text_input("IP aprobada", value=datos.get("ip_aprobada",""))
                                    ganancias = st.text_input("Ganancias período", value=datos.get("ganancias_periodo",""))
                                    celular = st.text_input("📱 Celular", value=datos.get("celular",""))
                                    fecha_nac = st.date_input("📅 Fecha de nacimiento",
                                        value=pd.to_datetime(datos["fecha_nacimiento"]) if datos.get("fecha_nacimiento") else pd.to_datetime("2000-01-01")
                                    )

                                    st.markdown("### 🔐 Claves Binance")
                                    clave1 = st.text_input(
                                        "🧾 BINANCE_API_KEY (clave pública)",
                                        value="",
                                        placeholder="••••••••"
                                    )
                                    clave2 = st.text_input(
                                        "🔒 BINANCE_API_SECRET (clave secreta)",
                                        value="",
                                        type="password",
                                        placeholder="••••••••"
                                    )

                                    submitted = st.form_submit_button("💾 Guardar cambios")
                                    if submitted:
                                        extras = {
                                            "estado_actual": estado_actual,
                                            "estado_ip": estado_ip,
                                            "ip_aprobada": ip_aprobada,
                                            "ganancias_periodo": ganancias,
                                            "celular": celular,
                                            "fecha_nacimiento": str(fecha_nac)
                                        }
                                        if clave1:
                                            extras["clave1_binance"] = clave1
                                        if clave2:
                                            extras["clave2_binance"] = clave2

                                        ensure_user(user_edit, None, **extras)
                                        st.success(f"✅ Usuario {user_edit} actualizado.")
                            else:
                                st.error("❌ Usuario no encontrado")

                else:
                    st.warning("⚠️ Solo los administradores pueden gestionar usuarios.")

                # ---------------------------
                # 🟢 Sesiones activas
                # ---------------------------
                st.subheader("🟢 Sesiones Activas")
                try:
                    from utils.auth import listar_sesiones_activas
                    sesiones = listar_sesiones_activas()

                    if sesiones is not None and not sesiones.empty:
                        st.dataframe(sesiones, use_container_width=True)
                    else:
                        st.info("ℹ️ No hay sesiones activas en este momento.")
                except Exception as e:
                    log_error(e, archivo="app.py", funcion="mostrar_sesiones")
                    st.warning("⚠️ No se pudieron cargar las sesiones activas.")

                # ---------------------------
                # 🖊️ Estado de usuarios + últimas sesiones
                # ---------------------------
                st.subheader("📋 Estado de usuarios")

                try:
                    conn = _get_connection()
                    df = pd.read_sql_query(
                        """
                        SELECT 
                            usuario as '👤 Usuario',
                            correo as '📧 Correo',
                            estado_actual as '⚙️ Estado',
                            estado_ip as '🖥️ Estado IP',
                            ip_aprobada as '🌐 IP aprobada',
                            ganancias_periodo as '💰 Ganancias',
                            celular as '📱 Celular',
                            fecha_nacimiento as '📅 Nacimiento',
                            duracion_acumulada_seg as '🧮 Acumulado (seg)',
                            (SELECT MAX(inicio) FROM historial_sesiones h WHERE h.usuario = u.usuario) as '⏳ Última sesión'
                        FROM usuarios u
                        """,
                        conn
                    )
                    conn.close()

                    if "🧮 Acumulado (seg)" in df.columns:
                        df["🧮 Acumulado (min)"] = (df["🧮 Acumulado (seg)"] // 60).astype(int)
                        df.drop(columns=["🧮 Acumulado (seg)"], inplace=True)

                    st.dataframe(df, use_container_width=True)

                except Exception as e:
                    log_error(e, archivo="app.py", funcion="mostrar_estado_usuarios")
                    st.warning("⚠️ No se pudieron cargar los datos de usuarios.")

                # ---------------------------
                # 📜 Historial de sesiones
                # ---------------------------
                st.subheader("📜 Historial de sesiones")

                try:
                    conn = _get_connection()
                    df_hist = pd.read_sql_query(
                        """
                        SELECT 
                            usuario as '👤 Usuario',
                            inicio as '⏱️ Inicio',
                            fin as '🏁 Fin',
                            duracion_seg as '⏳ Duración (seg)',
                            fecha as '📅 Fecha'
                        FROM historial_sesiones
                        ORDER BY fecha DESC, inicio DESC
                        """,
                        conn
                    )
                    conn.close()

                    if not df_hist.empty:
                        df_hist["⏳ Duración (min)"] = (df_hist["⏳ Duración (seg)"] // 60).astype(int)
                        df_hist.drop(columns=["⏳ Duración (seg)"], inplace=True)
                        st.dataframe(df_hist, use_container_width=True)
                    else:
                        st.info("ℹ️ No hay historial de sesiones todavía.")
                except Exception as e:
                    log_error(e, archivo="app.py", funcion="mostrar_historial_sesiones")
                    st.warning("⚠️ No se pudo cargar el historial de sesiones.")

                # ---------------------------
                # 🧾 Auditoría de sesiones cifradas (solo admin)
                # ---------------------------
                if permisos.get("es_admin", False) or usuario_actual.lower() == "admin":
                    st.markdown("---")
                    st.subheader("🧾 Auditoría de sesiones cifradas")

                    try:
                        if not AUDITORIA_DB.exists():
                            st.info("ℹ️ No hay registros de auditoría todavía.")
                        else:
                            conn = sqlite3.connect(AUDITORIA_DB)
                            df_audit = pd.read_sql_query("SELECT * FROM auditoria_sesiones ORDER BY id DESC", conn)
                            conn.close()

                            if df_audit.empty:
                                st.info("📭 No hay eventos registrados aún.")
                            else:
                                st.dataframe(df_audit, use_container_width=True, hide_index=True)

                                # Exportar
                                buffer = io.BytesIO()
                                with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                                    df_audit.to_excel(writer, index=False, sheet_name="AuditoriaSesiones")
                                st.download_button(
                                    label="⬇️ Descargar en Excel",
                                    data=buffer.getvalue(),
                                    file_name=f"auditoria_sesiones_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                )
                    except Exception as e:
                        log_error(e, archivo="app.py", funcion="mostrar_auditoria_sesiones")
                        st.error("⚠️ Error al cargar los registros de auditoría.")

            except Exception as e:
                log_error(e, archivo="app.py", funcion="tab_configuracion")
                st.error("❌ Error en la configuración. Revisa logs.")


# ===================================================
# 🧩 BLOQUE 21 — MAIN (ESTABLE Y VISUALMENTE CORRECTO)
# ===================================================
def main():
    """
    Controlador general de la interfaz.
    - Muestra siempre el sidebar (login_ui)
    - Evita que el login desaparezca o bloquee Streamlit
    - Activa tabs dinámicamente cuando hay sesión y análisis activo
    """

    try:
        # --- Siempre dibujar el sidebar ---
        login_ui()
    except Exception as e:
        log_error(e, archivo="app.py", funcion="main.login_ui")
        st.error("⚠️ No se pudo cargar la interfaz de login.")
        return

    # --- Panel principal ---
    st.title("🤖 El Bot de Efra — Panel Principal")

    # Caso: sin usuario logueado
    if not st.session_state.get("usuario"):
        st.info("🔑 Inicia sesión desde el menú lateral para continuar.")
        st.stop()

    # Caso: sin análisis activo
    if not st.session_state.get("analisis_activo", False):
        st.info("ℹ️ Inicia un análisis desde el menú lateral para continuar.")
        st.stop()

    # Caso: usuario logueado + análisis activo
    try:
        tabs, idx = construir_tabs()
    except Exception as e:
        log_error(e, archivo="app.py", funcion="main.construir_tabs")
        st.error("❌ Error construyendo las pestañas.")
        st.stop()

    # --- Monitor de auditoría inteligente ---
    try:
        monitor_auditoria_inteligente()
    except Exception as e:
        log_warning(f"Monitor auditoría con error leve: {e}", archivo="app.py", funcion="main.monitor")

    # --- Render dinámico de tabs ---
    try:
        if "📊 Analizar" in idx:
            tab_analizar(tabs, idx)
        if "🧠 Entrenar" in idx:
            tab_entrenar(tabs, idx)
        if "📜 Historial" in idx:
            tab_historial(tabs, idx)
        if "📈 Backtesting" in idx:
            tab_backtesting(tabs, idx)
        if "🏆 Ranking" in idx:
            tab_ranking(tabs, idx)
        if "⚙️ Configuración" in idx:
            tab_configuracion(tabs, idx)
    except Exception as e:
        log_error(e, archivo="app.py", funcion="main.render_tabs")
        st.error("❌ Error renderizando los módulos.")


# ============================================================
# 🟢 BLOQUE 22 — EJECUCIÓN DIRECTA DEL SCRIPT
# ------------------------------------------------------------
# Permite correr el archivo como script independiente (modo seguro)
# y garantiza que el entorno de Streamlit esté inicializado
# antes de ejecutar el flujo principal de la app.
# ============================================================

if __name__ == "__main__":
    try:
        log_info("🚀 Iniciando aplicación principal (modo directo)", archivo="app.py", funcion="__main__")
        main()
    except KeyboardInterrupt:
        # Permite cerrar la app sin mostrar errores feos
        log_warning("🛑 Ejecución interrumpida manualmente por el usuario.", archivo="app.py", funcion="__main__")
        st.stop()
    except SystemExit:
        # Cierre normal del proceso sin warnings
        log_info("✅ Aplicación cerrada correctamente.", archivo="app.py", funcion="__main__")
    except Exception as e:
        # Captura errores críticos inesperados
        log_error(e, archivo="app.py", funcion="__main__")
        try:
            st.error("❌ Error crítico en la aplicación. Revisa los logs para más detalles.")
        except Exception:
            # En caso de que Streamlit no esté disponible
            print(f"[CRITICAL] Error fatal en ejecución principal: {e}")
    finally:
        # Limpieza segura y silenciosa de sesión y caché
        try:
            limpiar_sesion_completa()
            log_info("🧹 Limpieza final de sesión completada (segura y silenciosa).", archivo="app.py", funcion="__main__")
        except Exception:
            pass

# ============================================================
# 🧠 BLOQUE 23 — GESTOR GLOBAL DE ERRORES Y EVENTOS
# ------------------------------------------------------------
# Este bloque refuerza la estabilidad general de la app.
# Captura excepciones no controladas, errores de librerías,
# y evita que se impriman mensajes innecesarios en consola.
# ============================================================

import sys
import threading
import traceback

def _gestor_excepcion_global(tipo, valor, traza):
    """
    Captura cualquier excepción global no manejada y la registra
    sin interrumpir la experiencia del usuario en Streamlit.
    """
    try:
        detalle = "".join(traceback.format_exception(tipo, valor, traza))
        log_error(detalle, archivo="app.py", funcion="gestor_excepcion_global")

        # Mostrar mensaje solo si estamos en entorno interactivo
        if hasattr(st, "error"):
            st.error("⚠️ Se detectó un error interno no crítico. Revisa los logs para más detalles.")
        else:
            print(f"[Error Global] {valor}")

    except Exception as e_log:
        print(f"[Critical] No se pudo registrar error global: {e_log}")

# Activar como gestor de excepciones por defecto
sys.excepthook = _gestor_excepcion_global


# ============================================================
# 🧩 BLOQUE 23.2 — MANEJO DE THREADS Y SEGURIDAD ASÍNCRONA
# ------------------------------------------------------------
# Asegura que los hilos secundarios (IA, Telegram, auditoría, etc.)
# no rompan la aplicación si fallan en segundo plano.
# ============================================================

def _thread_wrapper(func, *args, **kwargs):
    """Ejecuta una función en hilo seguro, registrando cualquier error."""
    try:
        func(*args, **kwargs)
    except Exception as e_thread:
        log_warning(f"⚠️ Hilo secundario con error: {e_thread}", archivo="app.py", funcion="thread_wrapper")

def ejecutar_seguro_en_hilo(func, *args, **kwargs):
    """
    Envuelve una tarea en un hilo seguro (modo daemon).
    Ideal para: Telegram, backtesting, auditorías, etc.
    """
    hilo = threading.Thread(target=_thread_wrapper, args=(func, *args), kwargs=kwargs, daemon=True)
    hilo.start()
    return hilo


# ============================================================
# 🧩 BLOQUE 23.3 — LOG DE INICIO FINAL
# ------------------------------------------------------------
# Confirma que la aplicación se levantó con éxito y
# deja registro limpio al cerrar Streamlit.
# ============================================================

def _on_shutdown():
    """Limpieza final silenciosa al cerrar Streamlit."""
    try:
        limpiar_sesion_completa()
        log_info("🧹 Cierre limpio de sesión completado.", archivo="app.py", funcion="_on_shutdown")
    except Exception as e:
        log_warning(f"Error al cerrar sesión: {e}", archivo="app.py", funcion="_on_shutdown")

import atexit
atexit.register(_on_shutdown)

log_info("✅ Sistema de gestión global de errores inicializado correctamente.", archivo="app.py", funcion="bloque_23")

# ============================================================
# ⚙️ BLOQUE 23.4 — MONITOR DE RENDIMIENTO INTELIGENTE
# ------------------------------------------------------------
# Supervisa el rendimiento interno de la app:
# - Latencia del análisis IA
# - Uso de CPU y memoria RAM
# - Promedio de ejecución de tabs
# - Frecuencia de autoaprendizaje y logs
#
# Muestra resultados dinámicamente en la pestaña “⚙️ Configuración”
# sin afectar el rendimiento global.
# ============================================================

import psutil
import time
from statistics import mean, deque

# Cola temporal para métricas
_hist_rendimiento = {
    "cpu": deque(maxlen=30),
    "ram": deque(maxlen=30),
    "latencia": deque(maxlen=30),
    "tasa_ok": deque(maxlen=30),
}

# Timestamp global
_ultimo_ping = time.time()

def registrar_ping(latencia_seg: float, exito: bool = True):
    """
    Registra un nuevo ciclo de rendimiento IA.
    Se llama automáticamente desde funciones críticas (analizar, entrenar).
    """
    try:
        _hist_rendimiento["latencia"].append(latencia_seg)
        _hist_rendimiento["cpu"].append(psutil.cpu_percent())
        _hist_rendimiento["ram"].append(psutil.virtual_memory().percent)
        _hist_rendimiento["tasa_ok"].append(1.0 if exito else 0.0)
    except Exception as e:
        log_warning(f"No se pudo registrar ping: {e}", archivo="app.py", funcion="registrar_ping")


def obtener_metricas_rendimiento() -> dict:
    """Devuelve métricas agregadas del rendimiento reciente."""
    try:
        latencias = list(_hist_rendimiento["latencia"])
        return {
            "cpu_avg": mean(_hist_rendimiento["cpu"]) if _hist_rendimiento["cpu"] else 0,
            "ram_avg": mean(_hist_rendimiento["ram"]) if _hist_rendimiento["ram"] else 0,
            "latencia_avg": mean(latencias) if latencias else 0,
            "tasa_exito": mean(_hist_rendimiento["tasa_ok"]) * 100 if _hist_rendimiento["tasa_ok"] else 0,
            "latencia_max": max(latencias) if latencias else 0,
            "latencia_min": min(latencias) if latencias else 0,
        }
    except Exception as e:
        log_error(e, archivo="app.py", funcion="obtener_metricas_rendimiento")
        return {
            "cpu_avg": 0, "ram_avg": 0, "latencia_avg": 0, "tasa_exito": 0,
            "latencia_max": 0, "latencia_min": 0
        }


def mostrar_monitor_configuracion():
    """
    Inserta un pequeño panel de rendimiento dentro del tab ⚙️ Configuración.
    Llamar al final de `tab_configuracion(tabs, idx)`.
    """
    try:
        import streamlit as st
        import plotly.graph_objects as go

        st.markdown("### ⚡ Monitor de Rendimiento del Sistema")

        metricas = obtener_metricas_rendimiento()

        col1, col2, col3 = st.columns(3)
        col1.metric("🧠 CPU Promedio", f"{metricas['cpu_avg']:.2f}%")
        col2.metric("💾 RAM Promedio", f"{metricas['ram_avg']:.2f}%")
        col3.metric("🤖 Latencia IA Promedio", f"{metricas['latencia_avg']:.3f}s")

        col4, col5 = st.columns(2)
        col4.metric("📈 Tasa Éxito IA", f"{metricas['tasa_exito']:.1f}%")
        col5.metric("⚙️ Latencia Máx/Min", f"{metricas['latencia_max']:.3f}s / {metricas['latencia_min']:.3f}s")

        # Gráfico dinámico de uso CPU/RAM
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            y=list(_hist_rendimiento["cpu"]),
            name="CPU (%)",
            mode="lines+markers"
        ))
        fig.add_trace(go.Scatter(
            y=list(_hist_rendimiento["ram"]),
            name="RAM (%)",
            mode="lines+markers"
        ))
        fig.update_layout(
            title="📊 Uso de recursos (últimos 30 ciclos)",
            xaxis_title="Ciclos recientes",
            yaxis_title="Porcentaje (%)",
            height=300,
            template="plotly_dark"
        )
        st.plotly_chart(fig, use_container_width=True)

        st.caption("⚙️ Los datos se actualizan automáticamente con cada análisis o entrenamiento IA.")

    except Exception as e:
        log_warning(f"No se pudo mostrar monitor de rendimiento: {e}", archivo="app.py", funcion="mostrar_monitor_configuracion")

log_info("🧩 Monitor de rendimiento inteligente inicializado correctamente.", archivo="app.py", funcion="bloque_23_4")
