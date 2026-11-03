import pandas as pd

class RelativeVolume:

    def __init__(
        self,
        period: int = 20
    ):
        self.period = period

    def calculate(
        self,
        df: pd.DataFrame
    ) -> float:

        average_volume = (
            df["volume"]
            .rolling(
                self.period
            )
            .mean()
        )

        current_volume = (
            df["volume"]
            .iloc[-1]
        )

        reference_volume = (
            average_volume
            .iloc[-1]
        )

        if reference_volume <= 0:

            return 0.0
        relative_volume = (
            current_volume
            / reference_volume
        )

        return round(
            relative_volume,
            3
        )

    def classify(
        self,
        value: float
    ) -> str:

        if value < 0.8:
            return "LOW"

        if value < 1.2:
            return "NORMAL"

        if value < 2.0:
            return "HIGH"
        return "EXTREME"import pandas as pd

class RelativeVolume:

    def __init__(
        self,
        period: int = 20
    ):
        self.period = period

    def calculate(
        self,
        df: pd.DataFrame
    ) -> float:

        average_volume = (
            df["volume"]
            .rolling(
                self.period
            )
            .mean()
        )

        current_volume = (
            df["volume"]
            .iloc[-1]
        )

        reference_volume = (
            average_volume
            .iloc[-1]
        )

        if reference_volume <= 0:

            return 0.0
        relative_volume = (
            current_volume
            / reference_volume
        )

        return round(
            relative_volume,
            3
        )

    def classify(
        self,
        value: float
    ) -> str:

        if value < 0.8:
            return "LOW"

        if value < 1.2:
            return "NORMAL"

        if value < 2.0:
            return "HIGH"
        return "EXTREME"
