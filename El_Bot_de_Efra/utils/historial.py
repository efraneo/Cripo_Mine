import pandas as pd
import os
from datetime import datetime, timedelta
from utils.logger import log_error, logger

# 📂 Ruta estándar del historial
RUTA_HISTORIAL = os.path.join("logs", "historial.csv")

# Columnas mínimas necesarias
COLUMNAS_BASE = [
    "fecha", "activo", "accion", "origen", "precision", "resultado"
]

# Columnas opcionales para datos técnicos
COLUMNAS_EXTRA = [
    "RSI", "MACD", "volumen", "tendencia", "duracion"
]


# ==========================
# 🔹 Cargar historial
# ==========================
def cargar_historial():
    """
    Carga el historial de logs tolerando columnas extra o faltantes.
    Siempre devuelve un DataFrame con columnas base + extra.
    """
    if not os.path.exists(RUTA_HISTORIAL):
        logger.warning("📂 El archivo historial.csv no existe.")
        return pd.DataFrame(columns=COLUMNAS_BASE + COLUMNAS_EXTRA)

    try:
        from utils.comun import leer_csv_seguro  # función de lectura segura
        df = leer_csv_seguro(RUTA_HISTORIAL, encoding="utf-8")

        # Crear columnas faltantes
        for col in COLUMNAS_BASE + COLUMNAS_EXTRA:
            if col not in df.columns:
                df[col] = None

        # Convertir fecha a datetime tolerante
        if "fecha" in df.columns:
            df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")

        # Ordenar por fecha descendente
        df.sort_values("fecha", ascending=False, inplace=True)

        return df

    except Exception as e:
        log_error(e, archivo="historial.py", funcion="cargar_historial")
        return pd.DataFrame(columns=COLUMNAS_BASE + COLUMNAS_EXTRA)


# ==========================
# 🔹 Guardar historial
# ==========================
def guardar_historial(
    fecha=None, activo=None, accion=None, origen="IA",
    precision=None, resultado=None, rsi=None, macd=None,
    volumen=None, tendencia=None, duracion=None
):
    """
    Guarda una nueva entrada en historial.csv con formato estándar.
    """
    try:
        # Crear nueva fila
        nuevo = {
            "fecha": fecha.strftime("%Y-%m-%d %H:%M:%S") if isinstance(fecha, datetime) else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "activo": activo if activo else "N/A",
            "accion": accion if accion else "N/A",
            "origen": origen if origen else "IA",
            "precision": round(float(precision), 4) if precision is not None else None,
            "resultado": resultado if resultado else None,
            "RSI": round(float(rsi), 2) if rsi is not None else None,
            "MACD": round(float(macd), 4) if macd is not None else None,
            "volumen": round(float(volumen), 4) if volumen is not None else None,
            "tendencia": tendencia if tendencia else None,
            "duracion": duracion if duracion else None,
        }

        # Crear archivo si no existe
        if not os.path.exists(RUTA_HISTORIAL):
            pd.DataFrame([nuevo]).to_csv(RUTA_HISTORIAL, index=False, encoding="utf-8")
        else:
            df_existente = pd.read_csv(RUTA_HISTORIAL, encoding="utf-8")
            df_nuevo = pd.concat([df_existente, pd.DataFrame([nuevo])], ignore_index=True)

            # Guardar con codificación flexible
            try:
                df_nuevo.to_csv(RUTA_HISTORIAL, index=False, encoding="utf-8")
            except UnicodeEncodeError:
                df_nuevo.to_csv(RUTA_HISTORIAL, index=False, encoding="latin-1")

        logger.info(f"📝 Historial actualizado para {nuevo['activo']}: {nuevo['accion']} ({nuevo['origen']})")

    except Exception as e:
        log_error(e, archivo="historial.py", funcion="guardar_historial")


# ==========================
# 🔹 Filtros y resúmenes
# ==========================
def filtrar_historial(df, activo=None, desde=None, hasta=None, origen=None):
    """Filtra el historial según activo, origen y rango de fechas."""
    if df.empty:
        return df
    if activo:
        df = df[df["activo"] == activo]
    if origen:
        df = df[df["origen"] == origen]
    if desde:
        df = df[df["fecha"] >= pd.to_datetime(desde)]
    if hasta:
        df = df[df["fecha"] <= pd.to_datetime(hasta)]
    return df


def resumen_semanal():
    """Resumen de señales de la última semana."""
    df = cargar_historial()
    if df.empty or "fecha" not in df.columns:
        return "No hay historial disponible."

    ultima_semana = datetime.now() - timedelta(days=7)
    df = df[df["fecha"] >= ultima_semana]

    if df.empty:
        return "No se registraron señales esta semana."

    resumen = df["accion"].value_counts().to_dict()
    resumen_str = "\n".join([f"• {accion}: {cantidad}" for accion, cantidad in resumen.items()])

    if "resultado" in df.columns:
        precision = df["resultado"].value_counts(normalize=True).get("✅", 0.0)
        resumen_str += f"\n🎯 Precisión: {precision:.2%}"
    else:
        resumen_str += "\nℹ️ No hay datos de precisión."

    return resumen_str


def resumen_metricas():
    """Métricas globales de historial."""
    df = cargar_historial()
    if df.empty:
        return {}
    total = len(df)
    acciones = df["accion"].value_counts().to_dict()
    precision = df["resultado"].value_counts(normalize=True).get("✅", 0.0) if "resultado" in df.columns else 0.0
    return {
        "total_señales": total,
        "acciones": acciones,
        "precision": round(precision * 100, 2)
    }
