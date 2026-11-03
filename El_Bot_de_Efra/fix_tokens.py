# fix_tokens.py
# ============================================================
# Limpieza segura de tokens cifrados inválidos en usuarios.db
# Ejecutar desde el directorio raíz del proyecto
# ============================================================

import os
import sqlite3
import sys

# Agregar carpeta 'utils' al path para importar correctamente
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UTILS_DIR = os.path.join(BASE_DIR, "utils")
if UTILS_DIR not in sys.path:
    sys.path.insert(0, UTILS_DIR)

from security import descifrar, cifrar  # ✅ importación correcta

DB_PATH = os.path.join(BASE_DIR, "usuarios.db")


def limpiar_tokens_invalidos():
    if not os.path.exists(DB_PATH):
        print("❌ No se encontró usuarios.db en el directorio raíz.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Campos potencialmente cifrados que pueden causar el error
    campos_cifrados = [
        "clave1_binance",
        "clave2_binance",
        "ip_autorizada",
        "ip_aprobada"
    ]

    print("🔍 Escaneando registros en usuarios.db ...")

    try:
        # Obtener columnas actuales de la tabla usuarios
        cur.execute("PRAGMA table_info(usuarios)")
        cols = [r[1] for r in cur.fetchall()]
        campos_validos = [c for c in campos_cifrados if c in cols]

        if not campos_validos:
            print("✅ No hay campos cifrados que limpiar.")
            return

        cur.execute(f"SELECT id, usuario, {', '.join(campos_validos)} FROM usuarios")
        filas = cur.fetchall()

        fixed = 0
        for fila in filas:
            id_user = fila[0]
            usuario = fila[1]
            updates = {}
            for i, campo in enumerate(campos_validos, start=2):
                val = fila[i]
                if not val:
                    continue
                texto = descifrar(val)
                if texto is None:
                    updates[campo] = None
                    print(f"⚠️ Token inválido eliminado ({campo}) -> usuario {usuario}")
            if updates:
                sets = ", ".join([f"{c}=NULL" for c in updates])
                cur.execute(f"UPDATE usuarios SET {sets} WHERE id=?", (id_user,))
                fixed += 1

        conn.commit()
        print(f"🎯 Limpieza completada. {fixed} usuario(s) reparado(s).")

    except Exception as e:
        print(f"❌ Error limpiando tokens: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    limpiar_tokens_invalidos()
