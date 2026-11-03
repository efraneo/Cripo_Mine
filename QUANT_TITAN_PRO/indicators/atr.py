import pandas as pd

class ATRIndicator:
    def __init__(
        self,
        period: int = 14
    ):
        self.period = period

    def calculate(
        self,
        df: pd.DataFrame
    ) -> float:

        high = df["high"]
        low = df["low"]
        close = df["close"]
        previous_close = close.shift(1)
        tr_1 = high - low

        tr_2 = (
            high
            - previous_close
        ).abs()

        tr_3 = (
            low
            - previous_close
        ).abs()

        true_range = pd.concat(
            [
                tr_1,
                tr_2,
                tr_3
            ],

            axis=1
        ).max(
            axis=1
        )

        atr = (
            true_range
            .rolling(
                self.period
            )
            .mean()
        )

        return float(
            atr.iloc[-1]
        )
