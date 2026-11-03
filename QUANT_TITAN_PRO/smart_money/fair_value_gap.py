from datetime import datetime
import pandas as pd
from smart_money.smc_models import (
    FairValueGap
)

class FairValueGapDetector:

    def __init__(
        self,
        config: dict
    ):

        smc = config["smart_money"]

        self.min_gap_percent = smc.get(
            "fvg_min_gap_percent",
            0.20
        ) / 100

    def detect(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame
    ) -> list[FairValueGap]:

        gaps = []

        if len(df) < 3:
            return gaps

        for i in range(
            2,
            len(df)
        ):

            c1 = df.iloc[i - 2]
            c2 = df.iloc[i - 1]
            c3 = df.iloc[i]
            bullish_gap = (
                c1["high"]
                < c3["low"]
            )
            bearish_gap = (
                c1["low"]
                > c3["high"]
            )

            if bullish_gap:
                gap_size = (
                    c3["low"]
                    - c1["high"]
                )

                ratio = (
                    gap_size
                    / c1["high"]
                )

                if ratio >= self.min_gap_percent:

                    gaps.append(
                        FairValueGap(
                            symbol=symbol,
                            timeframe=timeframe,
                            side="BUY",
                            upper_price=c3["low"],
                            lower_price=c1["high"],
                            size_percent=round(
                                ratio * 100,
                                3
                            ),
                            filled=False,
                            created_at=datetime.utcnow()
                        )
                    )

            if bearish_gap:

                gap_size = (
                    c1["low"]
                    - c3["high"]
                )

                ratio = (
                    gap_size
                    / c1["low"]
                )

                if ratio >= self.min_gap_percent:

                    gaps.append(
                        FairValueGap(
                            symbol=symbol,
                            timeframe=timeframe,
                            side="SELL",
                            upper_price=c1["low"],
                            lower_price=c3["high"],
                            size_percent=round(
                                ratio * 100,
                                3
                            ),
                            filled=False,
                            created_at=datetime.utcnow()
                        )
                    )
        return gaps
