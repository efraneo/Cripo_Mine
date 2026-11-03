# config_loader.py
import os
from dotenv import load_dotenv
from utils.logger import logger, log_error

# =========================
# 📁 Directorio base
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# =========================
# 📄 Archivos .env a cargar
# =========================
env_files = ["telegram.env", "binance.env", "credenciales.env"]

for archivo in env_files:
    full_path = os.path.join(BASE_DIR, archivo)
    try:
        if os.path.exists(full_path):
            load_dotenv(dotenv_path=full_path, override=True)
            logger.debug(f"🔑 Variables de entorno cargadas desde {archivo}")
        else:
            logger.warning(f"⚠️ Archivo .env no encontrado: {archivo}")
    except Exception as e:
        log_error(e, archivo="config_loader.py", funcion=f"load_dotenv({archivo})")

# =========================
# 🔐 TELEGRAM
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =========================
# 🔑 BINANCE
# =========================
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

# =========================
# 🔒 Clave de autenticación
# =========================
CLAVE_SECRETA = os.getenv("CLAVE_SECRETA")

# =========================
# 📧 Email (opcional)
# =========================
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

# =========================
# 🗄️ Base de datos (si aplica)
# =========================
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")

# =========================
# 🧪 Modo DEMO activado
# =========================
MODO_DEMO = os.getenv("MODO_DEMO", "False").strip().lower() == "true"

# =========================
# 🧪 Validaciones
# =========================
if not TELEGRAM_BOT_TOKEN:
    logger.warning("⚠️ TELEGRAM_BOT_TOKEN no está definido.")
if not TELEGRAM_CHAT_ID:
    logger.warning("⚠️ TELEGRAM_CHAT_ID no está definido.")
if not API_KEY or not API_SECRET:
    logger.warning("⚠️ API_KEY o API_SECRET de Binance no están definidos.")
if not CLAVE_SECRETA:
    logger.warning("⚠️ CLAVE_SECRETA no está definida.")
