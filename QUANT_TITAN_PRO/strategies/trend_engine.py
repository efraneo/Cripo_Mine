from typing import Dict
import pandas as pd

class TrendEngine:

    def __init__(self, config: dict):
        self.fast_ema = config.get(
            "fast_ema",
            20
        )

        self.medium_ema = config.get(
            "medium_ema",
            50
        )

        self.slow_ema = config.get(
            "slow_ema",
            200
        )

    def detect(
        self,
        df: pd.DataFrame
    ) -> Dict:
        data = df.copy()
        data["ema_fast"] = self._ema(
            data,
            self.fast_ema
        )

        data["ema_medium"] = self._ema(
            data,
            self.medium_ema
        )

        data["ema_slow"] = self._ema(
            data,
            self.slow_ema
        )

        price = data["close"].iloc[-1]
        fast = data["ema_fast"].iloc[-1]
        medium = data["ema_medium"].iloc[-1]
        slow = data["ema_slow"].iloc[-1]
        trend = self._classify_trend(
            price,
            fast,
            medium,
            slow
        )

        strength = self._trend_strength(
            price,
            fast,
            medium,
            slow
        )

        momentum = self._momentum(
            data
        )

        return {
            "trend": trend,
            "strength": round(
                strength,
                3
            ),
            "momentum": round(
                momentum,
                3
            ),
            "ema_fast": round(
                fast,
                4
            ),
            "ema_medium": round(
                medium,
                4
            ),
            "ema_slow": round(
                slow,
                4
            )
        }

    def _ema(
        self,
        df: pd.DataFrame,
        period: int
    ) -> pd.Series:

        return (
            df["close"]
            .ewm(
                span=period,
                adjust=False
            )
            .mean()
        )

    def _classify_trend(
        self,
        price: float,
        fast: float,
        medium: float,
        slow: float
    ) -> str:

        if price > fast > medium > slow:
            return "STRONG_BULL"

        if price > medium > slow:
            return "BULL"

        if price < fast < medium < slow:
            return "STRONG_BEAR"

        if price < medium < slow:
            return "BEAR"
        return "RANGE"

    def _trend_strength(
        self,
        price: float,
        fast: float,
        medium: float,
        slow: float
    ) -> float:

        distance_fast = abs(
            price - fast
        ) / price

        distance_medium = abs(
            price - medium
        ) / price

        distance_slow = abs(
            price - slow
        ) / price

        score = (
            distance_fast * 0.30 +
            distance_medium * 0.30 +
            distance_slow * 0.40
        )

        return min(
            score * 20,
            1.0
        )

    def _momentum(
        self,
        df: pd.DataFrame
    ) -> float:
        current = df["close"].iloc[-1]
        past = df["close"].iloc[-20]
        change = (
            current - past
        ) / past
        return abs(change)from typing import Dict

import pandas as pd

class TrendEngine:

    def __init__(self, config: dict):
        self.fast_ema = config.get(
            "fast_ema",
            20
        )

        self.medium_ema = config.get(
            "medium_ema",
            50
        )

        self.slow_ema = config.get(
            "slow_ema",
            200
        )

    def detect(
        self,
        df: pd.DataFrame
    ) -> Dict:
        data = df.copy()
        data["ema_fast"] = self._ema(
            data,
            self.fast_ema
        )

        data["ema_medium"] = self._ema(
            data,
            self.medium_ema
        )

        data["ema_slow"] = self._ema(
            data,
            self.slow_ema
        )

        price = data["close"].iloc[-1]
        fast = data["ema_fast"].iloc[-1]
        medium = data["ema_medium"].iloc[-1]
        slow = data["ema_slow"].iloc[-1]
        trend = self._classify_trend(
            price,
            fast,
            medium,
            slow
        )

        strength = self._trend_strength(
            price,
            fast,
            medium,
            slow
        )

        momentum = self._momentum(
            data
        )

        return {
            "trend": trend,
            "strength": round(
                strength,
                3
            ),
            "momentum": round(
                momentum,
                3
            ),
            "ema_fast": round(
                fast,
                4
            ),
            "ema_medium": round(
                medium,
                4
            ),
            "ema_slow": round(
                slow,
                4
            )
        }

    def _ema(
        self,
        df: pd.DataFrame,
        period: int
    ) -> pd.Series:

        return (
            df["close"]
            .ewm(
                span=period,
                adjust=False
            )
            .mean()
        )

    def _classify_trend(
        self,
        price: float,
        fast: float,
        medium: float,
        slow: float
    ) -> str:

        if price > fast > medium > slow:
            return "STRONG_BULL"

        if price > medium > slow:
            return "BULL"

        if price < fast < medium < slow:
            return "STRONG_BEAR"

        if price < medium < slow:
            return "BEAR"
        return "RANGE"

    def _trend_strength(
        self,
        price: float,
        fast: float,
        medium: float,
        slow: float
    ) -> float:

        distance_fast = abs(
            price - fast
        ) / price

        distance_medium = abs(
            price - medium
        ) / price

        distance_slow = abs(
            price - slow
        ) / price

        score = (
            distance_fast * 0.30 +
            distance_medium * 0.30 +
            distance_slow * 0.40
        )

        return min(
            score * 20,
            1.0
        )

    def _momentum(
        self,
        df: pd.DataFrame
    ) -> float:

        current = df["close"].iloc[-1]
        past = df["close"].iloc[-20]
        change = (
            current - past
        ) / past
        return abs(change)
