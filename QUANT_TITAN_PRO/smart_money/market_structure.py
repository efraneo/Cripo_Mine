from typing import Any
import pandas as pd
from smart_money.bos_detector import BOSDetector
from smart_money.choch_detector import CHOCHDetector
from smart_money.fair_value_gap import (
    FairValueGapDetector
)
from smart_money.liquidity_zones import (
    LiquidityZones
)
from smart_money.order_blocks import (
    OrderBlocks
)

class MarketStructure:

    def __init__(
        self,
        config: dict
    ):

        self.liquidity_detector = (
            LiquidityZones(
                config
            )
        )

        self.bos_detector = (
            BOSDetector(
                config
            )
        )

        self.choch_detector = (
            CHOCHDetector(
                config
            )
        )

        self.order_block_detector = (
            OrderBlocks(
                config
            )
        )

        self.fvg_detector = (
            FairValueGapDetector(
                config
            )
        )

    def analyze(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame
    ) -> dict[str, Any]:

        liquidity = (
            self.liquidity_detector
            .detect(
                symbol,
                timeframe,
                df
            )
        )

        bos = (
            self.bos_detector
            .detect(
                symbol,
                timeframe,
                df
            )
        )

        choch = (
            self.choch_detector
            .detect(
                symbol,
                timeframe,
                df
            )
        )

        order_blocks = (
            self.order_block_detector
            .detect(
                symbol,
                timeframe,
                df
            )
        )

        fvgs = (
            self.fvg_detector
            .detect(
                symbol,
                timeframe,
                df
            )
        )

        return {
            "liquidity": liquidity,
            "bos": bos,
            "choch": choch,
            "order_blocks": order_blocks,
            "fair_value_gaps": fvgs
        }
