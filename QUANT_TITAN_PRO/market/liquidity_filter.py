class LiquidityFilter:

    def __init__(
        self,
        config: dict
    ):

        market = config.get(
            "market",
            {}
        )

        self.min_volume = market.get(
            "min_volume_usdt",
            50_000_000
        )

        self.max_spread = market.get(
            "max_spread_percent",
            0.20
        )

    def validate(
        self,
        ticker: dict
    ) -> bool:

        volume = float(
            ticker.get(
                "quoteVolume",
                0
            )
        )

        bid = float(
            ticker.get(
                "bidPrice",
                0
            )
        )

        ask = float(
            ticker.get(
                "askPrice",
                0
            )
        )

        if bid <= 0:
            return False
        spread = (
            ask - bid
        ) / bid * 100
        return (
            volume >= self.min_volume
            and
            spread <= self.max_spread
        )
