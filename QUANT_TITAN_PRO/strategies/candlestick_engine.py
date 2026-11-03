from typing import List
import pandas as pd
from strategies.models import CandleSignal

class CandlestickEngine:

    def __init__(self, config: dict):
        self.min_confidence = config.get(
            "min_confidence",
            0.80
        )

    def analyze(
        self,
        df: pd.DataFrame
    ) -> List[CandleSignal]:
        signals = []
        detectors = [
            self.detect_hammer,
            self.detect_shooting_star,
            self.detect_bullish_engulfing,
            self.detect_bearish_engulfing,
            self.detect_doji,
        ]

        for detector in detectors:
            signals.extend(
                detector(df)
            )
        return signals

    def detect_hammer(
        self,
        df: pd.DataFrame
    ) -> List[CandleSignal]:
        candle = df.iloc[-1]
        body = abs(
            candle["close"]
            - candle["open"]
        )

        lower_wick = min(
            candle["open"],
            candle["close"]
        ) - candle["low"]

        upper_wick = candle["high"] - max(
            candle["open"],
            candle["close"]
        )

        if (
            lower_wick >= body * 2.5
            and upper_wick <= body * 0.5
            and candle["close"] > candle["open"]
        ):
            return [
                CandleSignal(
                    pattern="HAMMER",
                    side="BUY",
                    confidence=0.65,
                    entry=candle["close"],
                    stop_loss=candle["low"],
                    take_profit=0.0,
                    volume_score=0.0,
                    rejection_score=0.85,
                    trend_score=0.0,
                )
            ]
        return []

    def detect_shooting_star(
        self,
        df: pd.DataFrame
    ) -> List[CandleSignal]:
        candle = df.iloc[-1]
        body = abs(
            candle["close"]
            - candle["open"]
        )

        upper_wick = candle["high"] - max(
            candle["open"],
            candle["close"]
        )

        lower_wick = min(
            candle["open"],
            candle["close"]
        ) - candle["low"]

        if (
            upper_wick >= body * 2.5
            and lower_wick <= body * 0.5
        ):
            return [
                CandleSignal(
                    pattern="SHOOTING_STAR",
                    side="SELL",
                    confidence=0.65,
                    entry=candle["close"],
                    stop_loss=candle["high"],
                    take_profit=0.0,
                    volume_score=0.0,
                    rejection_score=0.85,
                    trend_score=0.0,
                )
            ]
        return []

    def detect_bullish_engulfing(
        self,
        df: pd.DataFrame
    ) -> List[CandleSignal]:
        previous = df.iloc[-2]
        current = df.iloc[-1]
        condition = (
            previous["close"]
            < previous["open"]
            and current["close"]
            > current["open"]
            and current["open"]
            < previous["close"]
            and current["close"]
            > previous["open"]
        )

        if condition:
            return [
                CandleSignal(
                    pattern="BULLISH_ENGULFING",
                    side="BUY",
                    confidence=0.70,
                    entry=current["close"],
                    stop_loss=min(
                        previous["low"],
                        current["low"]
                    ),
                    take_profit=0.0,
                    volume_score=0.0,
                    rejection_score=0.70,
                    trend_score=0.0,
                )
            ]
        return []

    def detect_bearish_engulfing(
        self,
        df: pd.DataFrame
    ) -> List[CandleSignal]:
        previous = df.iloc[-2]
        current = df.iloc[-1]
        condition = (
            previous["close"]
            > previous["open"]
            and current["close"]
            < current["open"]
            and current["open"]
            > previous["close"]
            and current["close"]
            < previous["open"]
        )

        if condition:
            return [
                CandleSignal(
                    pattern="BEARISH_ENGULFING",
                    side="SELL",
                    confidence=0.70,
                    entry=current["close"],
                    stop_loss=max(
                        previous["high"],
                        current["high"]
                    ),
                    take_profit=0.0,
                    volume_score=0.0,
                    rejection_score=0.70,
                    trend_score=0.0,
                )
            ]
        return []

    def detect_doji(
        self,
        df: pd.DataFrame
    ) -> List[CandleSignal]:
        candle = df.iloc[-1]
        body = abs(
            candle["close"]
            - candle["open"]
        )

        total_range = (
            candle["high"]
            - candle["low"]
        )

        if total_range == 0:
            return []
        ratio = body / total_range

        if ratio <= 0.10:
            return [
                CandleSignal(
                    pattern="DOJI",
                    side="NEUTRAL",
                    confidence=0.50,
                    entry=candle["close"],
                    stop_loss=candle["low"],
                    take_profit=0.0,
                    volume_score=0.0,
                    rejection_score=0.50,
                    trend_score=0.0,
                )
            ]
        return []from typing import List

import pandas as pd
from strategies.models import CandleSignal

class CandlestickEngine:

    def __init__(self, config: dict):
        self.min_confidence = config.get(
            "min_confidence",
            0.80
        )

    def analyze(
        self,
        df: pd.DataFrame
    ) -> List[CandleSignal]:
        signals = []
        detectors = [
            self.detect_hammer,
            self.detect_shooting_star,
            self.detect_bullish_engulfing,
            self.detect_bearish_engulfing,
            self.detect_doji,
        ]

        for detector in detectors:
            signals.extend(
                detector(df)
            )
        return signals

    def detect_hammer(
        self,
        df: pd.DataFrame
    ) -> List[CandleSignal]:
        candle = df.iloc[-1]
        body = abs(
            candle["close"]
            - candle["open"]
        )

        lower_wick = min(
            candle["open"],
            candle["close"]
        ) - candle["low"]

        upper_wick = candle["high"] - max(
            candle["open"],
            candle["close"]
        )

        if (
            lower_wick >= body * 2.5
            and upper_wick <= body * 0.5
            and candle["close"] > candle["open"]
        ):

            return [
                CandleSignal(
                    pattern="HAMMER",
                    side="BUY",
                    confidence=0.65,
                    entry=candle["close"],
                    stop_loss=candle["low"],
                    take_profit=0.0,
                    volume_score=0.0,
                    rejection_score=0.85,
                    trend_score=0.0,
                )
            ]
        return []

    def detect_shooting_star(
        self,
        df: pd.DataFrame
    ) -> List[CandleSignal]:
        candle = df.iloc[-1]
        body = abs(
            candle["close"]
            - candle["open"]
        )

        upper_wick = candle["high"] - max(
            candle["open"],
            candle["close"]
        )

        lower_wick = min(
            candle["open"],
            candle["close"]
        ) - candle["low"]

        if (
            upper_wick >= body * 2.5
            and lower_wick <= body * 0.5
        ):

            return [
                CandleSignal(
                    pattern="SHOOTING_STAR",
                    side="SELL",
                    confidence=0.65,
                    entry=candle["close"],
                    stop_loss=candle["high"],
                    take_profit=0.0,
                    volume_score=0.0,
                    rejection_score=0.85,
                    trend_score=0.0,
                )
            ]
        return []

    def detect_bullish_engulfing(
        self,
        df: pd.DataFrame
    ) -> List[CandleSignal]:
        previous = df.iloc[-2]
        current = df.iloc[-1]
        condition = (
            previous["close"]
            < previous["open"]
            and current["close"]
            > current["open"]
            and current["open"]
            < previous["close"]
            and current["close"]
            > previous["open"]
        )

        if condition:
            return [
                CandleSignal(
                    pattern="BULLISH_ENGULFING",
                    side="BUY",
                    confidence=0.70,
                    entry=current["close"],
                    stop_loss=min(
                        previous["low"],
                        current["low"]
                    ),
                    take_profit=0.0,
                    volume_score=0.0,
                    rejection_score=0.70,
                    trend_score=0.0,
                )
            ]
        return []

    def detect_bearish_engulfing(
        self,
        df: pd.DataFrame
    ) -> List[CandleSignal]:
        previous = df.iloc[-2]
        current = df.iloc[-1]
        condition = (
            previous["close"]
            > previous["open"]
            and current["close"]
            < current["open"]
            and current["open"]
            > previous["close"]
            and current["close"]
            < previous["open"]
        )

        if condition:
            return [
                CandleSignal(
                    pattern="BEARISH_ENGULFING",
                    side="SELL",
                    confidence=0.70,
                    entry=current["close"],
                    stop_loss=max(
                        previous["high"],
                        current["high"]
                    ),
                    take_profit=0.0,
                    volume_score=0.0,
                    rejection_score=0.70,
                    trend_score=0.0,
                )
            ]
        return []

    def detect_doji(
        self,
        df: pd.DataFrame
    ) -> List[CandleSignal]:
        candle = df.iloc[-1]
        body = abs(
            candle["close"]
            - candle["open"]
        )

        total_range = (
            candle["high"]
            - candle["low"]
        )

        if total_range == 0:
            return []
        ratio = body / total_range

        if ratio <= 0.10:
            return [
                CandleSignal(
                    pattern="DOJI",
                    side="NEUTRAL",
                    confidence=0.50,
                    entry=candle["close"],
                    stop_loss=candle["low"],
                    take_profit=0.0,
                    volume_score=0.0,
                    rejection_score=0.50,
                    trend_score=0.0,
                )
            ]
        return []
