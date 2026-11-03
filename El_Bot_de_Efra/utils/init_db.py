# utils/init_db.py
import os
from usuarios import crear_tabla_si_no_existe, seed_desde_csv, migrar_passwords_a_sha256, DB_PATH

def inicializar_db(csv_path: str = "claves.csv"):
    crear_tabla_si_no_existe()
    if not os.path.exists(csv_path):
        print(f"[WARN] No se encontró {csv_path}. Se crea DB vacía en: {DB_PATH}")
    else:
        n = seed_desde_csv(csv_path, forzar_hash=True)
        print(f"[OK] Cargadas/actualizadas {n} filas desde {csv_path}")
    migrar_passwords_a_sha256()
    print(f"[OK] DB lista en: {DB_PATH}")

if __name__ == "__main__":
    inicializar_db()
