import pandas as pd

class BOSDetector:

    def __init__(
        self,
        window: int = 10
    ):
        self.window = window

    def detect(
        self,
        df: pd.DataFrame
    ) -> str | None:

        highs = (
            df["high"]
            .tail(
                self.window
            )
        )

        lows = (
            df["low"]
            .tail(
                self.window
            )
        )

        current_close = (
            df["close"]
            .iloc[-1]
        )

        previous_high = (
            highs.iloc[:-1]
            .max()
        )

        previous_low = (
            lows.iloc[:-1]
            .min()
        )

        if current_close > previous_high:
            return "BULLISH_BOS"

        if current_close < previous_low:
            return "BEARISH_BOS"
        return None
