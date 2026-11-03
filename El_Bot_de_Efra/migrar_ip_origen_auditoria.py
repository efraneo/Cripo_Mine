# migrar_ip_origen_auditoria.py
# ============================================================
# Corrige error "no such column: ip_origen" en auditoria_sesiones
# Base: data/secure/auditoria_sesiones.db
# ============================================================

import sqlite3
import os

# Ruta completa y robusta a la base de auditoría
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "secure", "auditoria_sesiones.db")

def agregar_columna_ip_origen():
    if not os.path.exists(DB_PATH):
        print(f"❌ No existe la base de datos esperada: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("PRAGMA table_info(auditoria_sesiones)")
        columnas = [r[1] for r in cur.fetchall()]

        if "ip_origen" not in columnas:
            print("➕ Añadiendo columna 'ip_origen' a auditoria_sesiones...")
            cur.execute("ALTER TABLE auditoria_sesiones ADD COLUMN ip_origen TEXT DEFAULT ''")
            conn.commit()
            print("✅ Columna 'ip_origen' añadida correctamente.")
        else:
            print("✅ La columna 'ip_origen' ya existe en auditoria_sesiones.")
    except Exception as e:
        print(f"❌ Error al migrar auditoria_sesiones: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    agregar_columna_ip_origen()
