# migrar_usuarios.py
import sqlite3
from datetime import datetime

DB = "usuarios.db"

def migrar_usuarios():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # columnas a añadir
    nuevas = {
        "estado_actual": "TEXT DEFAULT 'habilitado'",
        "ganancias_periodo": "TEXT DEFAULT ''",
        "ip_autorizada": "TEXT DEFAULT ''",
        "clave1_binance": "TEXT DEFAULT ''",
        "clave2_binance": "TEXT DEFAULT ''",
        "cambio_clave": "INTEGER DEFAULT 0",
        "celular": "TEXT DEFAULT ''",
        "fecha_nacimiento": "TEXT DEFAULT ''",
        "firma_tratamiento_datos": "BLOB"
    }

    cur.execute("PRAGMA table_info(usuarios);")
    cols = [c[1] for c in cur.fetchall()]

    for col, typ in nuevas.items():
        if col not in cols:
            print(f"➕ Añadiendo columna {col}...")
            try:
                cur.execute(f"ALTER TABLE usuarios ADD COLUMN {col} {typ};")
            except Exception as e:
                print(f"❌ Error añadiendo {col}: {e}")
        else:
            print(f"✅ La columna {col} ya existe.")

    # Crear tablas auxiliares si no existen (ip_requests, ip_autorizadas, sesiones)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ip_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            ip TEXT NOT NULL,
            ts TEXT,
            estado TEXT DEFAULT 'pendiente',
            admin TEXT DEFAULT '',
            nota TEXT DEFAULT ''
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ip_autorizadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            ip TEXT NOT NULL,
            aprobado_por TEXT,
            ts TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sesiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            ip TEXT,
            inicio TEXT,
            ultimo_ping TEXT,
            activo INTEGER DEFAULT 1,
            duracion_acumulada_seg INTEGER DEFAULT 0,
            fecha_acumulada TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()
    print("🎉 Migración completa.")

if __name__ == "__main__":
    migrar_usuarios()
