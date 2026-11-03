"""
utils/safe_import.py
--------------------
Helper ligero para importar atributos de módulos opcionales de manera segura.

Ejemplo:
    from utils.safe_import import _safe_import
    ejecutar_orden_market = _safe_import("utils.binance_client", "ejecutar_orden_market",
                                        default=lambda *a, **k: {"success": False})
"""
import importlib
import types
from typing import Any, Callable

def _safe_import(module_name: str, attr: str, default: Any = None) -> Any:
    """
    Intenta importar `attr` desde `module_name`. Si falla, devuelve `default`.
    - module_name: nombre del módulo (ej: "utils.telegram_client")
    - attr: nombre del atributo/función/variable en el módulo
    - default: valor a devolver en caso de fallo
    """
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, attr)
    except Exception:
        return default
