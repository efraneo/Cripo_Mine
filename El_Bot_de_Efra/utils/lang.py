# ==========================================================
# utils/lang.py
# ==========================================================
# Módulo para gestión multilenguaje del bot.
# Permite:
#   - Traducciones dinámicas
#   - Idioma por defecto configurable
#   - Fallback seguro si falta una traducción
# ==========================================================

import logging
from typing import Dict

# Idioma por defecto
DEFAULT_LANG = "es"

# ==========================================================
# 🌍 Diccionario de traducciones
# ==========================================================
# Las claves son identificadores lógicos (ej: "buy", "sell").
# Los valores son dicts con traducción en cada idioma soportado.
# ==========================================================

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "buy": {
        "es": "Comprar",
        "en": "Buy",
        "pt": "Comprar",
    },
    "sell": {
        "es": "Vender",
        "en": "Sell",
        "pt": "Vender",
    },
    "hold": {
        "es": "Mantener",
        "en": "Hold",
        "pt": "Segurar",
    },
    "signal": {
        "es": "Señal detectada",
        "en": "Signal detected",
        "pt": "Sinal detectado",
    },
    "trend_up": {
        "es": "Tendencia alcista",
        "en": "Uptrend",
        "pt": "Tendência de alta",
    },
    "trend_down": {
        "es": "Tendencia bajista",
        "en": "Downtrend",
        "pt": "Tendência de baixa",
    },
    "trend_side": {
        "es": "Tendencia lateral",
        "en": "Sideways trend",
        "pt": "Tendência lateral",
    },
}

# ==========================================================
# 🔄 Función de traducción
# ==========================================================
def translate(key: str, lang: str = DEFAULT_LANG) -> str:
    """
    Traduce una clave dada al idioma especificado.
    Si no existe traducción, retorna la clave misma.

    Args:
        key (str): identificador de la palabra/expresión.
        lang (str): idioma destino ("es", "en", "pt").

    Returns:
        str: traducción correspondiente o clave fallback.
    """
    try:
        if key not in TRANSLATIONS:
            logging.warning(f"⚠️ Clave no encontrada en TRANSLATIONS: {key}")
            return key

        if lang not in TRANSLATIONS[key]:
            logging.warning(f"⚠️ Traducción no encontrada para {key} en {lang}")
            return TRANSLATIONS[key].get(DEFAULT_LANG, key)

        return TRANSLATIONS[key][lang]
    except Exception as e:
        logging.error(f"❌ Error en translate: {e}")
        return key

# ==========================================================
# ⚙️ Funciones de gestión dinámica
# ==========================================================
def add_translation(key: str, lang: str, text: str) -> None:
    """
    Agrega o actualiza una traducción en tiempo real.
    """
    try:
        if key not in TRANSLATIONS:
            TRANSLATIONS[key] = {}
        TRANSLATIONS[key][lang] = text
        logging.info(f"✅ Traducción añadida: {key}[{lang}] = {text}")
    except Exception as e:
        logging.error(f"❌ Error en add_translation: {e}")


def available_languages() -> Dict[str, int]:
    """
    Retorna los idiomas disponibles y cuántas claves soportan.
    """
    langs = {}
    try:
        for values in TRANSLATIONS.values():
            for lang in values.keys():
                langs[lang] = langs.get(lang, 0) + 1
    except Exception as e:
        logging.error(f"❌ Error en available_languages: {e}")
    return langs

# ==========================================================
# 🌍 Traducción de texto (stub con fallback)
# ==========================================================
try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

def traducir_texto(texto: str, destino: str = "es") -> str:
    """
    Traduce texto usando GoogleTranslator si está disponible.
    Si falla, retorna el mismo texto.
    
    Args:
        texto (str): Texto a traducir
        destino (str): Idioma destino (default: 'es')
    
    Returns:
        str: Texto traducido o original si no se puede traducir.
    """
    try:
        if GoogleTranslator:
            return GoogleTranslator(source="auto", target=destino).translate(texto)
        return texto
    except Exception:
        return texto
