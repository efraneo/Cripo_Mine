# migrar_db.py 
# ============================================================
# Script de migración unificado
# - Valida/crea tablas (historial, usuarios, sesiones, ip_requests, ip_autorizadas, historial_sesiones, auditoria_sesiones)
# - Añade automáticamente columnas nuevas si no existen
# ============================================================

import sqlite3
import os

# Ruta a tu base principal (ajústala si no está aquí)
DB_PATH = os.path.join(os.path.dirname(__file__), "usuarios.db")

def migrar_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ==========================
    # 🔄 Migración tabla historial
    # ==========================
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT,
                simbolo TEXT,
                resultado REAL,
                usuario TEXT
            )
        """)
        print("✅ Tabla 'historial' lista.")

        cursor.execute("PRAGMA table_info(historial);")
        cols = [c[1] for c in cursor.fetchall()]

        if "usuario" not in cols:
            print("➕ Añadiendo columna 'usuario' a historial...")
            cursor.execute("ALTER TABLE historial ADD COLUMN usuario TEXT;")
            conn.commit()
        else:
            print("✅ La columna 'usuario' ya existe en historial.")
    except Exception as e:
        print(f"⚠️ Error migrando historial: {e}")

    # ==========================
    # 🔄 Migración tabla usuarios
    # ==========================
    try:
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

        cursor.execute("PRAGMA table_info(usuarios);")
        cols = [c[1] for c in cursor.fetchall()]

        nuevos_campos = {
            "estado_actual": "TEXT DEFAULT 'habilitado'",
            "estado_ip": "TEXT DEFAULT 'pendiente'",
            "ip_aprobada": "TEXT DEFAULT ''",
            "ganancias_periodo": "TEXT DEFAULT ''",
            "ip_autorizada": "TEXT DEFAULT ''",
            "clave1_binance": "TEXT",
            "clave2_binance": "TEXT",
            "cambio_clave": "INTEGER DEFAULT 0",
            "celular": "TEXT",
            "fecha_nacimiento": "TEXT",
            "firma_tratamiento_datos": "BLOB",
            "duracion_acumulada_seg": "INTEGER DEFAULT 0",
            "fecha_acumulada": "TEXT DEFAULT ''"
        }

        for campo, tipo in nuevos_campos.items():
            if campo not in cols:
                try:
                    print(f"➕ Añadiendo columna '{campo}' a usuarios...")
                    cursor.execute(f"ALTER TABLE usuarios ADD COLUMN {campo} {tipo};")
                    conn.commit()
                except Exception as e:
                    print(f"⚠️ No se pudo añadir columna {campo}: {e}")
            else:
                print(f"✅ La columna '{campo}' ya existe en usuarios.")
    except Exception as e:
        print(f"⚠️ Error migrando usuarios: {e}")

    # ==========================
    # 🔄 Migración tabla sesiones
    # ==========================
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sesiones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL,
                ip TEXT,
                inicio TEXT,
                ultimo_ping TEXT,
                activo INTEGER DEFAULT 1,
                duracion_acumulada_seg INTEGER DEFAULT 0,
                fecha_acumulada TEXT DEFAULT '',
                FOREIGN KEY(usuario) REFERENCES usuarios(usuario) ON DELETE CASCADE
            )
        """)
        print("✅ Tabla 'sesiones' lista.")
    except Exception as e:
        print(f"⚠️ Error migrando sesiones: {e}")

    # ==========================
    # 🔄 Migración tabla ip_requests
    # ==========================
    try:
        cursor.execute("""
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
        print("✅ Tabla 'ip_requests' lista.")
    except Exception as e:
        print(f"⚠️ Error migrando ip_requests: {e}")

    # ==========================
    # 🔄 Migración tabla ip_autorizadas
    # ==========================
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ip_autorizadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL,
                ip TEXT NOT NULL,
                aprobado_por TEXT,
                ts TEXT
            )
        """)
        print("✅ Tabla 'ip_autorizadas' lista.")
    except Exception as e:
        print(f"⚠️ Error migrando ip_autorizadas: {e}")

    # ==========================
    # 🔄 Migración tabla historial_sesiones
    # ==========================
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historial_sesiones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL,
                inicio TEXT NOT NULL,
                fin TEXT NOT NULL,
                duracion_seg INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                ip_origen TEXT DEFAULT '',
                evento TEXT DEFAULT '',
                detalle TEXT DEFAULT '',
                FOREIGN KEY(usuario) REFERENCES usuarios(usuario) ON DELETE CASCADE
            )
        """)
        print("✅ Tabla 'historial_sesiones' lista.")

        # --- Añadir columnas si faltan ---
        cursor.execute("PRAGMA table_info(historial_sesiones);")
        cols = [c[1] for c in cursor.fetchall()]
        nuevas_cols = {
            "ip_origen": "TEXT DEFAULT ''",
            "evento": "TEXT DEFAULT ''",
            "detalle": "TEXT DEFAULT ''"
        }
        for col, tipo in nuevas_cols.items():
            if col not in cols:
                print(f"➕ Añadiendo columna '{col}' a historial_sesiones...")
                cursor.execute(f"ALTER TABLE historial_sesiones ADD COLUMN {col} {tipo};")
                conn.commit()
    except Exception as e:
        print(f"⚠️ Error migrando historial_sesiones: {e}")

    # ==========================
    # 🔄 Migración tabla auditoria_sesiones
    # ==========================
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auditoria_sesiones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL,
                evento TEXT NOT NULL,
                fecha TEXT NOT NULL,
                detalle TEXT DEFAULT ''
            )
        """)
        print("✅ Tabla 'auditoria_sesiones' lista.")

        # Verificar columnas existentes
        cursor.execute("PRAGMA table_info(auditoria_sesiones);")
        cols = [c[1] for c in cursor.fetchall()]

        if "ip_origen" not in cols:
            print("➕ Añadiendo columna 'ip_origen' a auditoria_sesiones...")
            cursor.execute("ALTER TABLE auditoria_sesiones ADD COLUMN ip_origen TEXT DEFAULT '';")
            conn.commit()
        else:
            print("✅ La columna 'ip_origen' ya existe en auditoria_sesiones.")
    except Exception as e:
        print(f"⚠️ Error migrando auditoria_sesiones: {e}")

    # 🔚 Cerrar conexión al final
    conn.close()
    print("🎯 Migración finalizada correctamente.")


if __name__ == "__main__":
    migrar_db()
