# ============================================================
# 📦 utils/db.py — Gestión de datos y lectura segura de activos
# ============================================================

import os
import pandas as pd
from datetime import datetime
from utils.logger import log_info, log_warning, log_error
import sqlite3
from typing import Tuple, Dict, List, Any

# intento importar logger del proyecto si existe (no obligatorio)
try:
    from utils.logger import log_info, log_warning, log_error
except Exception:
    def log_info(*args, **kwargs): pass
    def log_warning(*args, **kwargs): pass
    def log_error(*args, **kwargs): pass

# === Ruta segura para el archivo de activos ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACTIVOS_CSV = os.path.join(BASE_DIR, "activos.csv")
DB_PATH = os.path.join(BASE_DIR, "data.db")  # ajusta si usas otra ruta
ACTIVOS_FILE = os.path.join(BASE_DIR, "..", "activos.csv")

def _get_conn():
    # intenta conectar a la DB si existe, si no usamos fallback CSV
    if os.path.exists(ACTIVOS_CSV):
        try:
            conn = sqlite3.connect(ACTIVOS_CSV)
            return conn
        except Exception as e:
            log_warning(f"No se pudo conectar a DB en {_get_conn}: {e}")
            return None
    return None

# ============================================================
# 🧱 obtener_activos_por_categoria (simulada)
# ============================================================

def leer_activos_por_categoria() -> Tuple[Dict[str, List[str]], List[str]]:
    """
    Devuelve (categorias_dict, lista_activos)
    - categorias_dict: {"Criptos": ["BTCUSDT","ETHUSDT"], "Metales": [...]}
    - lista_activos: lista plana con todos los símbolos
    Siempre devuelve tuplas vacías o con datos válidos; no lanza excepciones.
    """
    categorias = {}
    lista_activos = []

    # 1) Preferir DB si existe tabla 'activos'
    try:
        conn = _get_conn()
        if conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT categoria, simbolo FROM activos WHERE simbolo IS NOT NULL ORDER BY categoria"
            )
            rows = cur.fetchall()
            for cat, sym in rows:
                if not cat:
                    cat = "SinCategoria"
                categorias.setdefault(cat, []).append(sym)
                lista_activos.append(sym)
            conn.close()

            if lista_activos:
                log_info(f"leer_activos_por_categoria: cargados {len(lista_activos)} desde DB")
                return categorias, lista_activos
    except Exception as e:
        log_warning(f"leer_activos_por_categoria (DB) falló: {e}")

    # 2) Fallback CSV
    try:
        if os.path.exists(ACTIVOS_CSV):
            df = pd.read_csv(ACTIVOS_CSV)
            if "categoria" in df.columns and "simbolo" in df.columns:
                for _, row in df.dropna(subset=["simbolo"]).iterrows():
                    cat = row.get("categoria") or "SinCategoria"
                    sym = str(row.get("simbolo")).strip()
                    categorias.setdefault(cat, []).append(sym)
                    lista_activos.append(sym)
                if lista_activos:
                    log_info(f"leer_activos_por_categoria: cargados {len(lista_activos)} desde activos.csv")
                    return categorias, lista_activos
    except Exception as e:
        log_warning(f"leer_activos_por_categoria (CSV) falló: {e}")

    # 3) Fallback hardcoded mínimo
    fallback = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    categorias = {"Top": fallback}
    lista_activos = fallback.copy()
    log_warning("leer_activos_por_categoria: usando fallback mínimo.")
    return categorias, lista_activos

# ============================================================
# 🧩 obtener_historial — Simulación segura de historial de usuario
# ============================================================
def obtener_historial(usuario: str, fecha_inicio: datetime, fecha_fin: datetime, activo: str = ""):
    """
    ⚠️ Simulación de historial de operaciones.
    En producción, reemplázala con la consulta real a tu DB.
    """
    try:
        data = [
            {"fecha": "2025-09-10", "activo": "BTCUSDT", "accion": "compra", "resultado": "ganancia"},
            {"fecha": "2025-09-11", "activo": "ETHUSDT", "accion": "venta", "resultado": "perdida"},
        ]
        df = pd.DataFrame(data)
        df["fecha"] = pd.to_datetime(df["fecha"])

        # 🔍 Filtrado por rango de fechas y activo
        mask = (df["fecha"] >= pd.to_datetime(fecha_inicio)) & (df["fecha"] <= pd.to_datetime(fecha_fin))
        if activo:
            mask &= df["activo"] == activo

        return df[mask]

    except Exception as e:
        log_error(e, archivo="db.py", funcion="obtener_historial")
        return pd.DataFrame(columns=["fecha", "activo", "accion", "resultado"])


# ============================================================
# 📊 obtener_activos — Lista general de activos
# ============================================================
def obtener_activos():
    """
    🔹 Intenta leer activos desde base de datos simulada o archivo CSV.
    Retorna siempre una lista válida (sin romper el flujo).
    """
    try:
        # 1️⃣ Simulación de lista de activos (puedes conectar DB real aquí)
        activos = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT"]

        # 2️⃣ Si hay CSV de respaldo, usarlo
        if os.path.exists("activos.csv"):
            df = pd.read_csv("activos.csv")
            if "simbolo" in df.columns:
                activos = df["simbolo"].dropna().unique().tolist()

        # Validación final
        if not activos:
            activos = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

        return activos

    except Exception as e:
        log_warning(f"⚠️ obtener_activos falló: {e}", archivo="db.py", funcion="obtener_activos")
        return ["BTCUSDT", "ETHUSDT", "BNBUSDT"]


# ============================================================
# 🧠 leer_activos_por_categoria — Bloque robusto y flexible
# ============================================================
def leer_activos_por_categoria():
    """
    Lee los activos agrupados por categoría desde la base de datos.
    Retorna:
        tuple(dict, list): (categorías, lista_activos)
        - categorias: dict con las categorías y sus activos
        - lista_activos: lista plana con todos los activos
    """
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()

        cursor.execute("SELECT categoria, simbolo FROM activos ORDER BY categoria")
        resultados = cursor.fetchall()

        categorias = {}
        lista_activos = []

        for categoria, simbolo in resultados:
            if categoria not in categorias:
                categorias[categoria] = []
            categorias[categoria].append(simbolo)
            lista_activos.append(simbolo)

        return categorias, lista_activos

    except Exception as e:
        print(f"[⚠️ leer_activos_por_categoria] Error: {e}")
        return {}, []

    finally:
        if 'conexion' in locals():
            conexion.close()
