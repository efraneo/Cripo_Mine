from market.asset_ranker import (
    AssetRanker
)
from market.liquidity_filter import (
    LiquidityFilter
)

class UniverseManager:

    def __init__(
        self,
        config: dict
    ):

        self.ranker = AssetRanker(
            config
        )

        self.filter = LiquidityFilter(
            config
        )

        market = config.get(
            "market",
            {}
        )

        self.max_assets = market.get(
            "max_assets",
            25
        )

    def build(
        self,
        tickers: list
    ) -> list:

        assets = []

        for ticker in tickers:
            if not self.filter.validate(
                ticker
            ):
                continue
            symbol = ticker[
                "symbol"
            ]
            score = (
                self.ranker.rank(
                    symbol
                )
            )
            assets.append(
                {
                    "symbol": symbol,
                    "tier": self.ranker.tier(
                        symbol
                    ),
                    "rank": score,
                    "volume": float(
                        ticker.get(
                            "quoteVolume",
                            0
                        )
                    )
                }
            )
        assets.sort(
            key=lambda x: (
                x["rank"],
                x["volume"]
            ),
            reverse=True
        )
        return assets[
            :self.max_assets
        ]
