# migrar_env_a_db.py
import os
import sqlite3
from dotenv import load_dotenv

# 🔐 Importar funciones de seguridad (cifrado con DB_MASTER_KEY)
from utils.security import cifrar

# Cargar archivo .env
load_dotenv("binance.env")
api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")

if not api_key or not api_secret:
    raise ValueError("❌ No se encontraron claves en binance.env")

# 🔐 Cifrar antes de guardar
api_key_enc = cifrar(api_key)
api_secret_enc = cifrar(api_secret)

# Conectar a SQLite
conn = sqlite3.connect("usuarios.db")
cur = conn.cursor()

# Actualizar al usuario administrador con id '8642239'
cur.execute("""
    UPDATE usuarios
    SET clave1_binance = ?, clave2_binance = ?
    WHERE usuario = ?
""", (api_key_enc, api_secret_enc, "8642239"))

conn.commit()
conn.close()

print("✅ Claves migradas y cifradas para usuario 8642239 en usuarios.db")
