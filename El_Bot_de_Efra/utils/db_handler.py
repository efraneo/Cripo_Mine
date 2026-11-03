# ==========================================================
# utils/db_handler.py
# ==========================================================
# Manejo de la base de datos SQLite para historial, usuarios y operaciones
# ==========================================================

import sqlite3
from datetime import datetime
from utils.logger import log_error

DB_NAME = "resultados_bot.db"


# ==========================================================
# 📌 Inicializar Tablas
# ==========================================================
def crear_tabla_si_no_existe():
    """
    Crea la tabla principal 'historial' con las mismas columnas que el CSV de operaciones.
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            usuario TEXT,
            activo TEXT,
            accion TEXT,
            precio_entrada REAL,
            monto REAL,
            tipo TEXT,
            precision REAL,
            conclusion TEXT,
            tp1 REAL,
            tp2 REAL,
            tp3 REAL,
            tp4 REAL,
            sl REAL,
            duracion INTEGER,
            rsi REAL,
            macd REAL,
            macd_signal REAL,
            tendencia TEXT,
            soporte REAL,
            resistencia REAL,
            volumen_fuerte INTEGER
        )''')
        conn.commit()
        conn.close()
    except Exception as e:
        log_error(e, archivo="db_handler.py", funcion="crear_tabla_si_no_existe")


def inicializar_db():
    """
    Inicializa todas las tablas necesarias (historial + usuarios).
    """
    try:
        crear_tabla_si_no_existe()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Usuarios
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                creado_en TEXT
            )
        """)

        conn.commit()
        conn.close()
    except Exception as e:
        log_error(e, archivo="db_handler.py", funcion="inicializar_db")


# ==========================================================
# 📌 Guardar Datos
# ==========================================================
def guardar_en_base_datos(data):
    """
    Guarda un registro en la tabla 'historial'.
    La estructura es la misma que logs/operaciones.csv
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO historial (
            fecha, usuario, activo, accion, precio_entrada, monto, tipo,
            precision, conclusion, tp1, tp2, tp3, tp4, sl, duracion,
            rsi, macd, macd_signal, tendencia, soporte, resistencia, volumen_fuerte
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            data.get("fecha"),
            data.get("usuario"),
            data.get("activo"),
            data.get("accion"),
            data.get("precio_entrada"),
            data.get("monto"),
            data.get("tipo"),
            data.get("precision"),
            data.get("conclusion"),
            data.get("tp1"),
            data.get("tp2"),
            data.get("tp3"),
            data.get("tp4"),
            data.get("sl"),
            data.get("duracion"),
            data.get("rsi"),
            data.get("macd"),
            data.get("macd_signal"),
            data.get("tendencia"),
            data.get("soporte"),
            data.get("resistencia"),
            int(data.get("volumen_fuerte", False))
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        log_error(e, archivo="db_handler.py", funcion="guardar_en_base_datos")


def guardar_generico(tabla, datos: dict):
    """
    Inserta datos en cualquier tabla (flexible).
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        columnas = ", ".join(datos.keys())
        placeholders = ", ".join(["?"] * len(datos))
        valores = list(datos.values())

        query = f"INSERT INTO {tabla} ({columnas}) VALUES ({placeholders})"
        cursor.execute(query, valores)

        conn.commit()
        conn.close()
    except Exception as e:
        log_error(e, archivo="db_handler.py", funcion="guardar_generico")


# ==========================================================
# 📌 Consultar Datos
# ==========================================================
def consultar(tabla, condiciones=None):
    """
    Consulta registros de una tabla.
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        query = f"SELECT * FROM {tabla}"
        if condiciones:
            query += f" WHERE {condiciones}"

        cursor.execute(query)
        rows = cursor.fetchall()

        conn.close()
        return rows
    except Exception as e:
        log_error(e, archivo="db_handler.py", funcion="consultar")
        return []
