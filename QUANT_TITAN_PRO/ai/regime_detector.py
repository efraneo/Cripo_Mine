from typing import Dict

import pandas as pd

class RegimeDetector:

    def __init__(self, config: dict):
        self.config = config

    def detect(self, btc_df: pd.DataFrame) -> Dict:
        ema_50 = self._ema(btc_df, 50)
        ema_200 = self._ema(btc_df, 200)
        volatility = self._volatility(btc_df)
        current_price = btc_df["close"].iloc[-1]
        trend = self._trend(
            current_price,
            ema_50,
            ema_200
        )

        risk = self._risk_level(
            volatility
        )

        regime = self._regime_label(
            trend,
            risk
        )

        return {
            "regime": regime,
            "trend": trend,
            "volatility": round(
                volatility,
                4
            ),
            "risk": risk,
            "can_trade": regime not in [
                "DANGER",
                "CHAOS"
            ]
        }

    def _ema(
        self,
        df: pd.DataFrame,
        period: int
    ) -> float:
        return (
            df["close"]
            .ewm(
                span=period,
                adjust=False
            )
            .mean()
            .iloc[-1]
        )

    def _volatility(
        self,
        df: pd.DataFrame
    ) -> float:
        returns = (
            df["close"]
            .pct_change()
        )
        return (
            returns.std()
            * 100
        )

    def _trend(
        self,
        price: float,
        ema_50: float,
        ema_200: float
    ) -> str:

        if price > ema_50 > ema_200:
            return "BULL"

        if price < ema_50 < ema_200:
            return "BEAR"
        return "RANGE"

    def _risk_level(
        self,
        volatility: float
    ) -> str:

        if volatility < 1:
            return "LOW"

        if volatility < 2:
            return "MEDIUM"

        if volatility < 4:
            return "HIGH"
        return "EXTREME"

    def _regime_label(
        self,
        trend: str,
        risk: str
    ) -> str:

        if trend == "BULL" and risk in [
            "LOW",
            "MEDIUM"
        ]:
            return "BULL_MARKET"

        if trend == "BEAR" and risk in [
            "HIGH",
            "EXTREME"
        ]:
            return "BEAR_MARKET"

        if risk == "EXTREME":
            return "CHAOS"

        if trend == "RANGE":
            return "SIDEWAYS"
        return "DANGER"
