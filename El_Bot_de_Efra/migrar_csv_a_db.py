# ========================================================== 
# migrar_csv_a_db.py
# ==========================================================
# Script para regenerar usuarios.db a partir de claves.csv
# Incluye:
#   - Tabla usuarios (con permisos y estado)
#   - Tabla sesiones (para login + IP + actividad)
#   - Inserción de usuarios desde CSV con bcrypt
# ==========================================================

import os
import sqlite3
import bcrypt
import pandas as pd
from datetime import datetime

DB_NAME = "usuarios.db"
CSV_PATH = "claves.csv"

print("🚀 Reiniciando usuarios.db ...")

# ==========================================================
# Helper para normalizar flags
# ==========================================================
def normalize_bool(value, default=0):
    """
    Convierte valores a enteros 0/1.
    Reconoce: 1, "1", "true", "yes", "si", "sí", "admin" → 1
               0, "0", "false", "no", "" → 0
    """
    if value is None:
        return int(default)
    if isinstance(value, (int, float)):
        return int(value != 0)
    val = str(value).strip().lower()
    if val in ("1", "true", "t", "yes", "y", "si", "sí", "admin"):
        return 1
    return 0

# ==========================================================
# 1. Respaldar DB anterior
# ==========================================================
if os.path.exists(DB_NAME):
    backup = DB_NAME.replace(".db", f"_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
    os.rename(DB_NAME, backup)
    print(f"📦 Backup creado: {backup}")

# ==========================================================
# 2. Crear tablas
# ==========================================================
try:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Tabla de usuarios
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT UNIQUE NOT NULL,
        clave TEXT NOT NULL,
        nombre TEXT,
        correo TEXT,
        es_admin INTEGER DEFAULT 0,
        ver_senales INTEGER DEFAULT 1,
        usar_ia INTEGER DEFAULT 1,
        ver_historial INTEGER DEFAULT 1,
        ver_backtesting INTEGER DEFAULT 0,
        estado TEXT DEFAULT 'activo',
        creado_en TEXT
    )
    """)

    # Tabla de sesiones activas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sesiones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT NOT NULL,
        ip TEXT,
        inicio TEXT,
        ultimo_ping TEXT,
        activo INTEGER DEFAULT 1,
        FOREIGN KEY(usuario) REFERENCES usuarios(usuario) ON DELETE CASCADE
    )
    """)

    conn.commit()
    print("✅ Tablas usuarios y sesiones creadas con esquema correcto.")
except Exception as e:
    print(f"❌ Error creando tablas: {e}")
    exit()

# ==========================================================
# 3. Cargar CSV original
# ==========================================================
if not os.path.exists(CSV_PATH):
    print(f"⚠️ No se encontró {CSV_PATH}, no hay nada para migrar.")
    conn.close()
    exit()

try:
    df = pd.read_csv(CSV_PATH, encoding="utf-8", on_bad_lines="skip")
    print(f"📊 CSV cargado con {len(df)} usuarios.")
except Exception as e:
    print(f"❌ Error leyendo CSV: {e}")
    conn.close()
    exit()

# Normalizar nombres de columnas
df.columns = [c.strip().lower() for c in df.columns]

# ==========================================================
# 4. Insertar usuarios con bcrypt
# ==========================================================
insertados = 0
for _, row in df.iterrows():
    try:
        usuario = str(row.get("usuario")).strip()
        clave_plana = str(row.get("clave")).strip()
        if not usuario or not clave_plana:
            print(f"⚠️ Fila inválida, se omite: {row}")
            continue

        hashed = bcrypt.hashpw(clave_plana.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        cursor.execute("""
        INSERT INTO usuarios (
            usuario, clave, nombre, correo, es_admin,
            ver_senales, usar_ia, ver_historial, ver_backtesting,
            estado, creado_en
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            usuario,
            hashed,
            row.get("nombre"),
            row.get("correo"),
            normalize_bool(row.get("es_admin"), 0),
            normalize_bool(row.get("ver_senales"), 1),
            normalize_bool(row.get("usar_ia"), 1),
            normalize_bool(row.get("ver_historial"), 1),
            normalize_bool(row.get("ver_backtesting"), 0),
            str(row.get("estado", "activo")).strip().lower(),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        insertados += 1
    except Exception as e:
        print(f"❌ Error insertando usuario {row.get('usuario')}: {e}")

conn.commit()
conn.close()

print(f"✅ Migración completada. {insertados} usuarios insertados en {DB_NAME}.")
