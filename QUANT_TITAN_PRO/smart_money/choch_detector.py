import pandas as pd

class CHOCHDetector:

    def __init__(
        self,
        window: int = 10
    ):
        self.window = window

    def detect(
        self,
        df: pd.DataFrame,
        trend: str
    ) -> str | None:

        recent_high = (
            df["high"]
            .tail(
                self.window
            )
            .max()
        )

        recent_low = (
            df["low"]
            .tail(
                self.window
            )
            .min()
        )

        current = (
            df["close"]
            .iloc[-1]
        )

        if (
            trend == "BULLISH"
            and
            current < recent_low
        ):
            return "BEARISH_CHOCH"

        if (
            trend == "BEARISH"
            and
            current > recent_high
        ):
            return "BULLISH_CHOCH"
        return None
