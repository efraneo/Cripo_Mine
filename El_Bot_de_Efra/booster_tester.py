# ============================================================
# 🚀 booster_tester.py
# ------------------------------------------------------------
# Prueba local del sistema "Confidence Boost" y combinación
# sin ejecutar la app Streamlit completa.
# 🔹 Genera varias simulaciones con colores y alertas visuales
# 🔹 Permite verificar que la confianza IA supere 90%
# ============================================================

import json
import random
import time
import colorama
from colorama import Fore, Style

from utils.confidence_boost import boost_confidence_and_alert
from utils.metodologias import aplicar_metodologias
from utils.prediccion import combinar_senales

colorama.init(autoreset=True)

import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="apscheduler")
warnings.filterwarnings("ignore", category=UserWarning, module="telegram.utils.request")

# ============================================================
# 🔧 Generadores de datos sintéticos
# ============================================================
def generar_metodos_prueba():
    """Simula varias metodologías técnicas."""
    return [
        {"metodo": "RSI", "senal": random.choice(["BUY", "SELL"]), "confianza": round(random.uniform(0.75, 0.95), 2)},
        {"metodo": "MACD", "senal": random.choice(["BUY", "SELL"]), "confianza": round(random.uniform(0.7, 0.95), 2)},
        {"metodo": "Bollinger", "senal": random.choice(["BUY", "SELL"]), "confianza": round(random.uniform(0.7, 0.9), 2)},
        {"metodo": "MA Crossover", "senal": random.choice(["BUY", "SELL"]), "confianza": round(random.uniform(0.7, 0.95), 2)},
        {"metodo": "Volumen", "senal": random.choice(["BUY", "SELL"]), "confianza": round(random.uniform(0.65, 0.9), 2)},
    ]


def generar_prediccion_lstm():
    """Predicción IA simulada."""
    return {
        "tendencia": random.choice(["BUY", "SELL"]),
        "confianza": round(random.uniform(0.75, 0.95), 2)
    }


# ============================================================
# 🧩 Función principal de test
# ============================================================
def ejecutar_prueba(iteraciones=8):
    print(Fore.CYAN + "\n🔮 === Simulación de combinación + Boost IA ===\n" + Style.RESET_ALL)

    exitosos = 0
    for i in range(iteraciones):
        print(Fore.YELLOW + f"\n🧠 Iteración {i + 1}/{iteraciones}" + Style.RESET_ALL)
        metodos = generar_metodos_prueba()
        pred_lstm = generar_prediccion_lstm()

        resultado = combinar_senales(
            metodos,
            prediccion_lstm=pred_lstm,
            peso_lstm=0.55,
            verbose=True
        )

        confianza_actual = resultado.get("confianza", 0.0)
        score_methods = resultado.get("score", 0.0)

        conf_boost, forzado = boost_confidence_and_alert(
            metodologias=metodos,
            prediccion_lstm=pred_lstm,
            confianza_actual=confianza_actual,
            score_methods=score_methods,
            rf_score=random.uniform(0.6, 0.9),
            consistencia=random.uniform(0.65, 0.95),
            error_score=random.uniform(0.5, 0.9),
            estabilidad=random.uniform(0.6, 0.95),
            resumen="Simulación avanzada booster_tester"
        )

        senal = resultado.get("senal", "HOLD")
        print(f"📊 Señal final: {Fore.GREEN if senal=='BUY' else Fore.RED if senal=='SELL' else Fore.WHITE}{senal}{Style.RESET_ALL}")
        print(f"🤖 Confianza inicial: {confianza_actual*100:.2f}%")
        print(f"⚡ Confianza ajustada: {conf_boost*100:.2f}%  {'🟢 (Boost aplicado)' if forzado else '⚪ (sin refuerzo)'}")

        if conf_boost >= 0.9:
            exitosos += 1
            print(Fore.GREEN + "✅ Confianza IA reforzada por encima del 90% 🚀" + Style.RESET_ALL)
        elif conf_boost >= 0.75:
            print(Fore.YELLOW + "⚠️ Confianza IA aceptable (revisión manual recomendada)" + Style.RESET_ALL)
        else:
            print(Fore.RED + "❌ Confianza IA baja — faltan señales fuertes" + Style.RESET_ALL)

        print("-" * 65)
        time.sleep(0.8)

    print(Fore.CYAN + f"\n📈 Resultados totales: {exitosos}/{iteraciones} con Confianza > 90%" + Style.RESET_ALL)
    if exitosos >= iteraciones // 2:
        print(Fore.GREEN + "🎯 Rendimiento IA óptimo — Boost funcional y consistente" + Style.RESET_ALL)
    else:
        print(Fore.RED + "⚠️ Boost IA inconsistente — revisa ponderaciones o señales LSTM" + Style.RESET_ALL)


# ============================================================
# 🚀 Ejecución directa
# ============================================================
if __name__ == "__main__":
    try:
        ejecutar_prueba(iteraciones=10)
    except Exception as e:
        print(Fore.RED + f"❌ Error en prueba: {e}" + Style.RESET_ALL)
