from typing import Dict, List

import ccxt
import pandas as pd

class MarketScanner:
    def __init__(
        self,
        exchange: ccxt.Exchange,
        config: dict
    ):
        self.exchange = exchange
        self.timeframe = config["timeframes"][0]
        self.candle_limit = config.get(
            "history_limit",
            200
        )

    def scan(
        self,
        symbols: List[str]
    ) -> List[dict]:
        opportunities = []

        for symbol in symbols:
            try:
                analysis = self._analyze_symbol(
                    symbol
                )
                opportunities.append(
                    analysis
                )
            except Exception:
                continue
        return opportunities

    def _analyze_symbol(
        self,
        symbol: str
    ) -> Dict:
        df = self._load_dataframe(
            symbol
        )
        trend_score = self._trend_score(
            df
        )
        momentum_score = self._momentum_score(
            df
        )
        volatility_score = self._volatility_score(
            df
        )
        volume_score = self._volume_score(
            df
        )
        total_score = (
            trend_score * 0.30 +
            momentum_score * 0.30 +
            volatility_score * 0.20 +
            volume_score * 0.20
        )
        return {
            "symbol": symbol,
            "price": round(
                df["close"].iloc[-1],
                4
            ),
            "trend_score": round(
                trend_score,
                3
            ),
            "momentum_score": round(
                momentum_score,
                3
            ),
            "volatility_score": round(
                volatility_score,
                3
            ),
            "volume_score": round(
                volume_score,
                3
            ),
            "market_score": round(
                total_score,
                3
            )
        }

    def _load_dataframe(
        self,
        symbol: str
    ) -> pd.DataFrame:
        candles = self.exchange.fetch_ohlcv(
            symbol,
            timeframe=self.timeframe,
            limit=self.candle_limit
        )

        df = pd.DataFrame(
            candles,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume"
            ]
        )

        df["ema_20"] = (
            df["close"]
            .ewm(
                span=20,
                adjust=False
            )
            .mean()
        )

        df["ema_50"] = (
            df["close"]
            .ewm(
                span=50,
                adjust=False
            )
            .mean()
        )
        return df

    def _trend_score(
        self,
        df: pd.DataFrame
    ) -> float:
        price = df["close"].iloc[-1]
        ema_20 = df["ema_20"].iloc[-1]
        ema_50 = df["ema_50"].iloc[-1]

        if price > ema_20 > ema_50:
            return 1.0
        if price < ema_20 < ema_50:
            return 0.7
        return 0.4

    def _momentum_score(
        self,
        df: pd.DataFrame
    ) -> float:
        current = df["close"].iloc[-1]
        previous = df["close"].iloc[-20]
        change = (
            (current - previous)
            / previous
        ) * 100

        if change >= 10:
            return 1.0
        if change >= 5:
            return 0.8
        if change >= 2:
            return 0.6
        return 0.3

    def _volatility_score(
        self,
        df: pd.DataFrame
    ) -> float:
        volatility = (
            df["close"]
            .pct_change()
            .std()
        ) * 100

        if volatility >= 3:
            return 1.0
        if volatility >= 2:
            return 0.8
        if volatility >= 1:
            return 0.6
        return 0.3

    def _volume_score(
        self,
        df: pd.DataFrame
    ) -> float:
        current_volume = (
            df["volume"]
            .iloc[-1]
        )
        average_volume = (
            df["volume"]
            .tail(50)
            .mean()
        )
        ratio = (
            current_volume /
            average_volume
        )

        if ratio >= 2:
            return 1.0
        if ratio >= 1.5:
            return 0.8
        if ratio >= 1.2:
            return 0.6
        return 0.3
