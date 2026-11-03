import pandas as pd

class LiquidityZones:

    def __init__(
        self,
        lookback: int = 80,
        threshold: float = 0.003
    ):
        self.lookback = lookback
        self.threshold = threshold

    def detect(
        self,
        df: pd.DataFrame
    ) -> dict:

        window = df.tail(
            self.lookback
        )

        swing_high = (
            window["high"]
            .max()
        )

        swing_low = (
            window["low"]
            .min()
        )

        current_price = (
            df["close"]
            .iloc[-1]
        )

        distance_high = abs(
            swing_high
            - current_price
        ) / current_price
        distance_low = abs(
            current_price
            - swing_low
        ) / current_price
        return {
            "high_liquidity":
                swing_high,
            "low_liquidity":
                swing_low,
            "near_high":
                distance_high
                <= self.threshold,
            "near_low":
                distance_low
                <= self.threshold
        }
