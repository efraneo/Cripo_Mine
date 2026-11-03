import pandas as pd

class VolatilityIndicator:

    def __init__(
        self,
        period: int = 20
    ):
        self.period = period

    def calculate(
        self,
        df: pd.DataFrame
    ) -> float:

        returns = (
            df["close"]
            .pct_change()
        )

        volatility = (
            returns
            .rolling(
                self.period
            )
            .std()
        )
        latest = volatility.iloc[-1]

        return round(
            float(latest),
            5
        )

    def regime(
        self,
        value: float
    ) -> str:

        if value < 0.005:
            return "LOW"

        if value < 0.015:
            return "NORMAL"

        if value < 0.03:
            return "HIGH"

        return "EXTREME"
