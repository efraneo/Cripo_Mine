class AssetRanker:

    def __init__(
        self,
        config: dict
    ):

        market = config.get(
            "market",
            {}
        )

        self.tier_1 = set(
            market.get(
                "tier_1",
                [
                    "BTCUSDT",
                    "ETHUSDT"
                ]
            )
        )

        self.tier_2 = set(
            market.get(
                "tier_2",
                [
                    "SOLUSDT",
                    "BNBUSDT"
                ]
            )
        )

        self.tier_3 = set(
            market.get(
                "tier_3",
                [
                    "XRPUSDT",
                    "ADAUSDT",
                    "DOGEUSDT"
                ]
            )
        )

    def rank(
        self,
        symbol: str
    ) -> int:

        if symbol in self.tier_1:
            return 100

        if symbol in self.tier_2:
            return 80

        if symbol in self.tier_3:
            return 60
        return 30

    def tier(
        self,
        symbol: str
    ) -> str:

        if symbol in self.tier_1:
            return "TIER_1"

        if symbol in self.tier_2:
            return "TIER_2"

        if symbol in self.tier_3:
            return "TIER_3"
        return "MICROCAP"
