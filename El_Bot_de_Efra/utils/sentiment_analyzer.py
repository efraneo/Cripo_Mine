# utils/sentiment_analyzer.py

import requests
import os
from datetime import datetime

class SentimentAnalyzer:
    """
    Analiza el sentimiento del mercado usando múltiples fuentes reales.
    Fuentes:
    - Alternative.me (Fear & Greed Index)
    - CryptoPanic (noticias y sentimiento)
    - Binance (cambio porcentual BTC 24h)
    - AlphaVantage (reserva como último recurso para activos fuera de Binance/Yahoo)
    """

    def __init__(self, use_fear_greed=True, use_cryptopanic=True, use_binance=True):
        self.use_fear_greed = use_fear_greed
        self.use_cryptopanic = use_cryptopanic
        self.use_binance = use_binance
        self.cryptopanic_api_key = os.getenv("CRYPTOPANIC_API_KEY", None)
        self.alphavantage_api_key = os.getenv("ALPHAVANTAGE_API_KEY", None)

        self.fear_greed_api = "https://api.alternative.me/fng/"
        self.binance_ticker_api = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"

    # ==========================
    # 📊 Fear & Greed Index
    # ==========================
    def get_fear_greed_index(self):
        try:
            r = requests.get(self.fear_greed_api, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if "data" in data and len(data["data"]) > 0:
                    return {
                        "value": int(data["data"][0]["value"]),
                        "classification": data["data"][0]["value_classification"]
                    }
        except Exception as e:
            return {"error": f"Error obteniendo Fear & Greed Index: {e}"}
        return {"error": "Sin datos Fear & Greed"}

    # ==========================
    # 📰 CryptoPanic API
    # ==========================
    def get_cryptopanic_sentiment(self):
        if not self.cryptopanic_api_key:
            return {"error": "No se configuró CRYPTOPANIC_API_KEY"}

        try:
            url = f"https://cryptopanic.com/api/v1/posts/?auth_token={self.cryptopanic_api_key}&kind=news&filter=hot"
            r = requests.get(url, timeout=10)
            data = r.json()
            if "results" in data:
                positive, negative, neutral = 0, 0, 0
                for post in data["results"]:
                    if post.get("votes", {}).get("positive", 0) > post.get("votes", {}).get("negative", 0):
                        positive += 1
                    elif post.get("votes", {}).get("negative", 0) > post.get("votes", {}).get("positive", 0):
                        negative += 1
                    else:
                        neutral += 1
                return {
                    "positive": positive,
                    "negative": negative,
                    "neutral": neutral,
                    "total": len(data["results"])
                }
        except Exception as e:
            return {"error": f"Error obteniendo noticias CryptoPanic: {e}"}
        return {"error": "Sin datos CryptoPanic"}

    # ==========================
    # 📈 Binance BTC Sentiment
    # ==========================
    def get_binance_btc_sentiment(self):
        try:
            r = requests.get(self.binance_ticker_api, timeout=5)
            if r.status_code == 200:
                data = r.json()
                cambio_24h = float(data["priceChangePercent"])
                if cambio_24h > 2:
                    return "positivo"
                elif cambio_24h < -2:
                    return "negativo fuerte"
                elif cambio_24h < 0:
                    return "negativo"
                else:
                    return "neutral"
        except Exception as e:
            return f"Error Binance: {e}"
        return "neutral"

    # ==========================
    # 🔄 Fuente alternativa: AlphaVantage
    # ==========================
    def get_alpha_vantage_sentiment(self, symbol="BTCUSD"):
        """
        Última fuente gratuita para obtener tendencia real si no está en Binance o Yahoo.
        """
        if not self.alphavantage_api_key:
            return None

        try:
            url = f"https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol={symbol}&interval=60min&apikey={self.alphavantage_api_key}"
            r = requests.get(url, timeout=10)
            data = r.json()
            if "Time Series (60min)" in data:
                prices = list(data["Time Series (60min)"].values())
                if len(prices) >= 2:
                    close_now = float(prices[0]["4. close"])
                    close_prev = float(prices[1]["4. close"])
                    change_pct = ((close_now - close_prev) / close_prev) * 100
                    if change_pct > 1:
                        return "positivo"
                    elif change_pct < -1:
                        return "negativo"
                    else:
                        return "neutral"
        except Exception as e:
            return f"Error AlphaVantage: {e}"
        return None

    # ==========================
    # 🔍 Análisis combinado
    # ==========================
    def get_market_sentiment(self, fallback_symbol="BTCUSD"):
        """
        Combina todas las fuentes para dar una señal final real:
        - 'negativo fuerte' → Evitar operar
        - 'positivo fuerte' → Posible oportunidad alcista
        - 'neutral' → Sin cambios
        """
        fng_data = self.get_fear_greed_index() if self.use_fear_greed else {}
        cp_data = self.get_cryptopanic_sentiment() if self.use_cryptopanic else {}
        binance_sent = self.get_binance_btc_sentiment() if self.use_binance else "neutral"

        # Fuente alternativa si no hay datos de Binance ni Yahoo
        alpha_sent = None
        if binance_sent.startswith("Error") or binance_sent == "neutral":
            alpha_sent = self.get_alpha_vantage_sentiment(fallback_symbol)

        # === Evaluación combinada ===
        if fng_data.get("value", 50) < 20:
            return "negativo fuerte"
        if fng_data.get("value", 50) > 80:
            return "positivo fuerte"

        if cp_data and isinstance(cp_data, dict):
            neg = cp_data.get("negative", 0)
            pos = cp_data.get("positive", 0)
            if neg > pos * 1.5 and neg >= 3:
                return "negativo fuerte"

        # Si Binance y Alpha dicen lo mismo, usar eso
        if alpha_sent and alpha_sent == binance_sent:
            return alpha_sent

        # Si Alpha dice algo y Binance no tiene señal clara
        if alpha_sent and binance_sent == "neutral":
            return alpha_sent

        return binance_sent if binance_sent != "neutral" else "neutral"


# ==========================
# Ejemplo de uso
# ==========================
if __name__ == "__main__":
    sa = SentimentAnalyzer()
    sentimiento = sa.get_market_sentiment()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Sentimiento del mercado: {sentimiento}")
