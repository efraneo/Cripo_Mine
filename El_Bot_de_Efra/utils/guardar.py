import pandas as pd
import json
import pickle
import os

from logger import logger

def guardar_csv(df, ruta, index=False):
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        df.to_csv(ruta, index=index)
        logger.info(f"✅ CSV guardado en {ruta}")
    except Exception as e:
        logger.error(f"❌ Error al guardar CSV en {ruta}: {e}")

def guardar_json(data, ruta):
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        logger.info(f"✅ JSON guardado en {ruta}")
    except Exception as e:
        logger.error(f"❌ Error al guardar JSON en {ruta}: {e}")

def guardar_pickle(objeto, ruta):
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "wb") as f:
            pickle.dump(objeto, f)
        logger.info(f"✅ Pickle guardado en {ruta}")
    except Exception as e:
        logger.error(f"❌ Error al guardar pickle en {ruta}: {e}")

def guardar_texto(texto, ruta):
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(texto)
        logger.info(f"📝 Texto guardado en {ruta}")
    except Exception as e:
        logger.error(f"❌ Error al guardar texto en {ruta}: {e}")

