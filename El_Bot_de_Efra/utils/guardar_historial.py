import pandas as pd
from datetime import datetime
import os

from logger import logger

def guardar_historial(fecha, activo, accion, precision=None, origen="IA", orden=None, capital=None):
    """
    Guarda una señal o predicción en el archivo historial.csv
    """
    try:
        archivo = "logs/historial.csv"

        nueva_fila = {
            "fecha": fecha,
            "activo": activo,
            "accion": accion,
            "precision": precision,
            "origen": origen,
            "orden": orden,
            "capital": capital
        }

        # Si ya existe, lo cargamos
        if os.path.exists(archivo):
            df = pd.read_csv(archivo)
            df = pd.concat([df, pd.DataFrame([nueva_fila])], ignore_index=True)
        else:
            df = pd.DataFrame([nueva_fila])

        # Formatear fecha
        df['fecha'] = pd.to_datetime(df['fecha'])
        df.drop_duplicates(subset=["fecha", "activo", "origen"], keep="last", inplace=True)
        df.sort_values("fecha", ascending=False, inplace=True)

        df.to_csv(archivo, index=False)
        logger.info(f"📝 Historial actualizado: {activo} - {accion} ({origen})")

    except Exception as e:
        logger.error(f"❌ Error al guardar historial: {e}")

