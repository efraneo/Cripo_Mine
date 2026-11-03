class PortfolioManager:

    def __init__(
        self,
        config: dict
    ):

        portfolio = config.get(
            "portfolio",
            {}
        )
        self.max_positions = portfolio.get(
            "max_positions",
            5
        )
        self.max_symbol_exposure = (
            portfolio.get(
                "max_symbol_exposure",
                0.30
            )
        )

    def can_open(
        self,
        open_positions,
        symbol
    ) -> bool:

        if len(
            open_positions
        ) >= self.max_positions:
            return False
        symbol_positions = [
            p
            for p in open_positions
            if p.symbol == symbol
        ]
        return (
            len(
                symbol_positions
            )
            <
            self.max_symbol_exposure
            *
            self.max_positions
        )

    def exposure(
        self,
        open_positions
    ) -> dict:

        total = len(
            open_positions
        )

        if total == 0:
            return {}
        exposure = {}

        for position in open_positions:
            exposure[
                position.symbol
            ] = exposure.get(
                position.symbol,
                0
            ) + 1
        return {
            symbol:
            round(
                count / total,
                2
            )
            for symbol,
            count
            in exposure.items()
        }
