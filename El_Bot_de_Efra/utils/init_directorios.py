# utils/init_directorios.py

import os
from utils.logger import log_error

def crear_directorios_logs():
    """
    Crea las carpetas necesarias para logs, datos CSV y otros recursos.
    Se asegura de que existan antes de que el bot empiece a operar.
    """
    carpetas = ["logs", "csv", "charts", "graficos", "data/historial"]

    for carpeta in carpetas:
        try:
            os.makedirs(carpeta, exist_ok=True)
            print(f"✅ Carpeta creada o existente: {carpeta}")
        except Exception as e:
            print(f"❌ Error al crear carpeta '{carpeta}': {e}")
            log_error(e, archivo="init_directorios.py", funcion="crear_directorios_logs")


# Solo ejecuta si se lanza directamente
if __name__ == "__main__":
    crear_directorios_logs()
