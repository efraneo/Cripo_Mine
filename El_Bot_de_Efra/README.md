# 🤖 El Bot de Efra — Inteligencia Artificial y Análisis Técnico para Trading

Bienvenido al **Bot de Efra**, un sistema modular de trading con inteligencia artificial, backtesting, estrategias técnicas, alertas automáticas y visualización interactiva. Diseñado para operar, aprender y escalar.

---

## 🚀 Características principales

- 🧠 Predicciones con Machine Learning (IA)
- 📚 Estrategias técnicas inteligentes (Cruce de medias, RSI, MACD, volatilidad)
- 🔄 Señales combinadas IA + Técnica vía `procesar_senal()`
- 📈 Gráficos de velas y señales con Plotly
- 🧪 Backtesting completo con métricas y curva de capital
- 📤 Alertas automáticas por Telegram y correo
- 🧾 Historial centralizado de decisiones del bot
- 🔐 Panel con login seguro vía `Streamlit` (usuarios, cambios de contraseña)
- 📲 Versión web y móvil: `app.py` (completo) y `app_lite.py` (lite)
- 🧩 Arquitectura modular y extensible

---

## 🧱 Estructura del proyecto

📁 El_Bot_de_Efra/
├── app.py # Interfaz principal completa con predicción, señales y backtesting
├── app_lite.py # Versión móvil ligera, ideal para uso desde el celular
├── el_bot_de_efra.py # Script principal: IA + estrategia técnica + envío de órdenes
├── trading_bot.py # Clase TradingBot: entrenamiento, predicción y ejecución
├── init_directorios.py # Crea carpetas necesarias (logs, data, modelos...)
│
├── backtesting/
│ ├── backtesting.py # Motor de backtesting y métricas
│ └── estrategias.py # Estrategias técnicas encapsuladas
│
├── utils/
│ ├── comun.py # Carga de datos, funciones generales
│ ├── modelo.py # Entrenamiento de modelos
│ ├── historial.py # Guardado y consulta de historial
│ ├── auth.py # Autenticación de usuarios y claves
│ ├── logger.py # Logging de errores centralizado
│
├── fibonacci.py # Detección de niveles de Fibonacci
├── telegram_alertas.py # Envío de mensajes por Telegram
├── notificador_email.py # Envío de emails automáticos
├── config_loader.py # Carga de .env y configuración segura
│
├── claves.csv # Lista de usuarios y contraseñas cifradas
├── activos.csv # Lista de activos a analizar
├── requirements.txt # Paquetes requeridos
├── telegram.env / binance.env # Claves API
└── logs/, data/, modelos/ # Carpeta de salidas y registros


---

## ⚙️ ¿Cómo funciona?

### 1. Predicción combinada IA + técnica

El archivo `el_bot_de_efra.py` centraliza la lógica:

```python
accion_ia, precision, señal_tec, señales = procesar_senal(activo)

-Usado en app.py y app_lite.py para mostrar señales combinadas y enviar alertas automáticas.

---

Nota importantes (Efring's Solutions)

- Interfaz principal (app.py)
Incluye:

Login y control de sesión

Predicción y señales por activo

Backtesting visual con métricas

Resumen y métricas del historial

- Versión móvil (app_lite.py)
Predicción rápida con alertas

Resumen histórico

Administración de cuenta

---

🧰 Requisitos
Python 3.9 o superior

Paquetes necesarios: pip install -r requirements.txt

Incluye:

streamlit, pandas, scikit-learn

yfinance, plotly, python-telegram-bot

python-dotenv, binance, bcrypt


---

✅ Ejecución
Modo completo (web)
-streamlit run app.py

Modo ligero (móvil o rápido)
-streamlit run app_lite.py

---

🛡 Seguridad
Contraseñas encriptadas (bcrypt)

Login obligatorio

Registro de accesos en logs/

📬 Notificaciones
Telegram: vía telegram_alertas.py (usa telegram.env)

Correo: configurado en notificador_email.py

🧠 Entrenamiento de IA
El módulo modelo.py entrena modelos ligeros de regresión para señales de compra/venta. Entrenamiento local y rápido.

