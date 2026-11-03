import numpy as np
import logging

logger = logging.getLogger("btc-miner-studio")

# RUTA FORZADA PARA GANANCIA INMEDIATA
FORCED_ROUTE = {
    "id": "unmineable_easy",
    "nombre": "unMineable - MODO FACIL (Max Shares)",
    "url": "rx.unmineable.com:3333",
    "usuario": "BTC:dirección_sustituida_por_config",
    "nota": "Ruta forzada para asegurar la aceptacion de shares."
}

def decidir(cfg, on_event=None):
    """Fuerza la ruta mas facil para asegurar ganancias inmediatas."""
    decision = {
        "ruta": "unmineable_easy",
        "rentabilidad": 1.0,
        "reevaluar": False
    }
    
    if on_event:
        on_event(f"FORZANDO RUTA: {FORCED_ROUTE['nombre']} para asegurar shares OK", "ok")
    
    return decision

def ruta_por_id(route_id):
    """Devuelve la ruta forzada independientemente del id solicitado."""
    return FORCED_ROUTE

def registrar_saldo_zpool(cfg, on_event=None):
    pass

def imprimir_tabla(cfg):
    return "MODO FORZADO: Minando en la ruta mas facil para asegurar ganancias."
