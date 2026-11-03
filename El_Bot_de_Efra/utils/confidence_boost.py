# ============================================================
# utils/confidence_boost.py
# ------------------------------------------------------------
# 💡 Ajuste avanzado de confianza IA
# - Sinergia con ensemble híbrido (RF + XGB + LSTM)
# - Controla refuerzo dinámico visual + alerta Telegram
# - Confiabilidad mínima garantizada (≥ 85%)
# ============================================================

import os
from datetime import datetime
from typing import Optional, Tuple

from utils.logger import log_info, log_warning, log_error

# Intentar PIL solo para generar imagen
try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False

# Intentar importar helpers de envío (opcionales)
try:
    from telegram_alertas import enviar_telegram, enviar_imagen_telegram
except Exception:
    enviar_telegram = None
    enviar_imagen_telegram = None

# ------------------------------------------------------------
# Parámetros por defecto con pesos dinámicos
# ------------------------------------------------------------
DEFAULTS = {
    "boost_targets": {4: 0.90, 5: 0.93, 6: 0.96},
    "min_high_conf_methods": 3,
    "method_conf_threshold": 0.80,
    "lstm_conf_threshold": 0.78,
    "rf_score_threshold": 0.65,
    "consistency_threshold": 0.70,
    "stability_threshold": 0.40,
    "max_delta": 0.25,
    # Nuevos pesos dinámicos
    "weights": {
        "consistency": 0.30,
        "error_score": 0.30,
        "stability": 0.20,
        "rf_score": 0.20
    }
}

_ALERT_DIR = os.path.join("data", "secure", "alerts")
os.makedirs(_ALERT_DIR, exist_ok=True)

# ============================================================
# 🧩 Arte visual de refuerzo IA (opcional)
# ============================================================
def _generate_alert_image(confianza: float, resumen: str = "") -> Optional[str]:
    try:
        if not _HAS_PIL:
            return None
        img = Image.new("RGB", (720, 260), color=(15, 18, 25))
        draw = ImageDraw.Draw(img)
        font_path = next(
            (p for p in [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "C:\\Windows\\Fonts\\arialbd.ttf"
            ] if os.path.exists(p)), None
        )
        try:
            font_big = ImageFont.truetype(font_path, 34) if font_path else None
            font_small = ImageFont.truetype(font_path, 18) if font_path else None
        except Exception:
            font_big = font_small = None

        title = "🚀 ALERTA DE CONFIANZA IA"
        conf_text = f"Confianza ajustada: {confianza*100:.2f}%"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        resumen = (resumen or "")[:120]

        draw.text((30, 25), title, fill=(255, 255, 255), font=font_big)
        draw.text((30, 80), conf_text, fill=(0, 220, 120), font=font_big)
        draw.text((30, 145), ts, fill=(170, 170, 170), font=font_small)
        draw.text((30, 175), resumen, fill=(200, 200, 200), font=font_small)

        filename = os.path.join(
            _ALERT_DIR,
            f"confianza_{int(confianza*100)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        )
        img.save(filename)
        return filename
    except Exception as e:
        log_warning(f"⚠️ Error generando imagen de alerta: {e}",
                    archivo="confidence_boost.py", funcion="_generate_alert_image")
        return None

# ============================================================
# 🧠 dynamic_confidence_boost — refuerzo adaptativo IA
# ============================================================
def dynamic_confidence_boost(
    metodologias,
    prediccion_lstm=None,
    confianza_actual: float = 0.0,
    score_methods: float = 0.0,
    rf_score: float = 0.0,
    consistencia: float = 0.0,
    error_score: float = 0.0,
    estabilidad: float = 0.0,
    resumen: str = ""
) -> Tuple[float, bool]:
    """
    Ajusta la confianza IA según:
      - consistencia técnica y estabilidad del modelo
      - score RF/XGB y precisión LSTM
      - refuerzo progresivo (4, 5 o 6 condiciones cumplidas)
    Retorna (nueva_confianza, boost_aplicado)
    """
    try:
        conf = confianza_actual or 0.0
        defaults = DEFAULTS
        weights = defaults["weights"]

        umbral_conf = defaults["method_conf_threshold"]
        min_methods = defaults["min_high_conf_methods"]
        lstm_thr = defaults["lstm_conf_threshold"]
        rf_thr = defaults["rf_score_threshold"]
        delta_max = defaults["max_delta"]

        # Metodologías fuertes
        metodos_fuertes = [
            m for m in (metodologias or [])
            if isinstance(m, dict) and float(m.get("confianza", 0)) >= umbral_conf
        ]
        num_fuertes = len(metodos_fuertes)

        # LSTM
        lstm_conf = float(prediccion_lstm.get("confianza", 0.0) or 0.0) if isinstance(prediccion_lstm, dict) else 0.0

        # Condiciones
        condiciones = [
            num_fuertes >= min_methods,
            lstm_conf >= lstm_thr,
            rf_score >= rf_thr,
            consistencia >= defaults["consistency_threshold"],
            error_score >= 0.60,
            estabilidad >= defaults["stability_threshold"],
        ]
        num_cumplidas = sum(1 for c in condiciones if c)

        # Base con pesos
        composite_score = (
            weights["consistency"] * consistencia +
            weights["error_score"] * error_score +
            weights["stability"] * estabilidad +
            weights["rf_score"] * rf_score
        )

        # Ajuste progresivo
        targets = defaults["boost_targets"]
        target = targets.get(num_cumplidas, conf)
        nueva_confianza = conf + (target - conf) * composite_score
        nueva_confianza = min(conf + delta_max, nueva_confianza)

        # Boost garantizado >85% en coherencia alta
        if consistencia > 0.8 and error_score > 0.7 and nueva_confianza < 0.85:
            nueva_confianza = 0.87

        nueva_confianza = round(float(min(0.99, max(0.0, nueva_confianza))), 6)

        boosted = nueva_confianza > conf

        if boosted:
            filename = _generate_alert_image(nueva_confianza, resumen)
            if enviar_telegram:
                try:
                    msg = (
                        f"🤖 <b>Confianza IA ajustada</b>\n"
                        f"📊 Nuevo nivel: <b>{nueva_confianza*100:.2f}%</b>\n"
                        f"✅ Consistencia: {consistencia:.2f}\n"
                        f"⚙️ Condiciones: {num_cumplidas}/6\n"
                        f"{resumen[:200]}"
                    )
                    enviar_telegram(msg)
                except Exception as e:
                    log_warning(f"Telegram alerta falló: {e}",
                                archivo="confidence_boost.py", funcion="dynamic_confidence_boost")
            if enviar_imagen_telegram and filename:
                try:
                    enviar_imagen_telegram(filename)
                except Exception:
                    pass

            log_info(f"⚡ Refuerzo IA aplicado ({num_cumplidas}/6) → conf {nueva_confianza*100:.2f}%",
                     archivo="confidence_boost.py", funcion="dynamic_confidence_boost")
        else:
            log_info(f"ℹ️ Sin refuerzo IA ({num_cumplidas}/6 condiciones cumplidas)",
                     archivo="confidence_boost.py", funcion="dynamic_confidence_boost")

        return nueva_confianza, boosted

    except Exception as e:
        log_error(e, archivo="confidence_boost.py", funcion="dynamic_confidence_boost")
        return confianza_actual, False
