import pandas as pd
import numpy as np
from utils.prediccion import combinar_senales
from fibonacci import detectar_niveles_fibonacci

# ================================
# 🔹 Crear DataFrame de velas simulado
# ================================
idx = pd.date_range("2025-01-01", periods=120, freq="1min")
df = pd.DataFrame({
    "open": np.random.rand(120) * 100 + 100,
    "high": np.random.rand(120) * 100 + 105,
    "low": np.random.rand(120) * 100 + 95,
    "close": np.random.rand(120) * 100 + 100,
    "volume": np.random.rand(120) * 1000
}, index=idx)

# ================================
# 🔹 Simulación de señales de metodologías
# ================================
met = [
    {"metodo": "RSI", "senal": "BUY", "confianza": 0.72},
    {"metodo": "MACD", "senal": "BUY", "confianza": 0.80},
    {"metodo": "MA Crossover", "senal": "BUY", "confianza": 0.65},
    {"metodo": "Volumen", "senal": "BUY", "confianza": 0.60},
    {"metodo": "Bollinger", "senal": "BUY", "confianza": 0.70},
    {"metodo": "ATR Breakout", "senal": "BUY", "confianza": 0.68},
    {"metodo": "Stochastic", "senal": "BUY", "confianza": 0.74},
    {"metodo": "ADX", "senal": "BUY", "confianza": 0.55},
    {"metodo": "Patrones", "senal": "BUY", "confianza": 0.80},
]

# Fibonacci real
niveles_fib = detectar_niveles_fibonacci(df)
if niveles_fib:
    met.append({"metodo": "Fibonacci", "senal": "BUY", "confianza": 0.75})

# ================================
# 🔹 LSTM simulado
# ================================
lstm = {"tendencia": "BUY", "confianza": 0.82}

# ================================
# 🔹 Combinar señales
# ================================
comb = combinar_senales(met, prediccion_lstm=lstm, peso_lstm=0.55, verbose=True)

print("\nMETODOLOGIAS (detalles):")
for m in met:
    print(" ", m)

print("\nCOMBINADO:")
print(comb)
