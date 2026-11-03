from dataclasses import dataclass
import pandas as pd

@dataclass
class OrderBlock:
    side: str
    high: float
    low: float
    volume: float
    strength: float
    candle_index: int

class OrderBlockDetector:

    def __init__(
        self,
        window: int = 15,
        volume_factor: float = 1.5
    ):
        self.window = window
        self.volume_factor = volume_factor

    def detect(
        self,
        df: pd.DataFrame
    ) -> list[OrderBlock]:
        blocks = []

        if len(df) < self.window:
            return blocks
        average_volume = (
            df["volume"]
            .tail(self.window)
            .mean()
        )

        candles = df.tail(self.window)

        for idx, (_, candle) in enumerate(
            candles.iterrows()
        ):

            if candle["volume"] < (
                average_volume
                * self.volume_factor
            ):
                continue
            bullish = (
                candle["close"]
                > candle["open"]
            )
            side = (
                "BUY"
                if bullish
                else "SELL"
            )
            strength = min(
                candle["volume"]
                / average_volume,
                5.0
            )
            blocks.append(
                OrderBlock(
                    side=side,
                    high=float(
                        candle["high"]
                    ),
                    low=float(
                        candle["low"]
                    ),
                    volume=float(
                        candle["volume"]
                    ),
                    strength=round(
                        strength,
                        2
                    ),
                    candle_index=idx
                )
            )
        return sorted(
            blocks,
            key=lambda x:
            x.strength,
            reverse=True
        )
