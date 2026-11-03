from scanner.opportunity_score import (
    OpportunityScorer
)

class MarketScanner:

    def __init__(
        self,
        config: dict,
        universe_manager,
        strategy,
        indicators
    ):

        self.config = config
        self.universe_manager = (
            universe_manager
        )
        self.strategy = strategy
        self.indicators = indicators
        self.scorer = OpportunityScorer(
            config
        )

    def scan(
        self,
        tickers,
        market_data
    ):

        ranked = []
        assets = (
            self.universe_manager
            .build(
                tickers
            )
        )

        for asset in assets:
            symbol = asset[
                "symbol"
            ]

            if symbol not in market_data:
                continue
            data = market_data[
                symbol
            ]
            signal = (
                self.strategy
                .generate_signal(
                    symbol,
                    "15m",
                    data
                )
            )

            if signal is None:
                continue
            relative_volume = (
                self.indicators[
                    "relative_volume"
                ]
                .calculate(
                    data
                )
            )
            volatility = (
                self.indicators[
                    "volatility"
                ]
                .calculate(
                    data
                )
            )
            score = (
                self.scorer
                .calculate(
                    symbol=symbol,
                    relative_volume=relative_volume,
                    volatility=volatility,
                    liquidity_score=0.80,
                    institutional_score=signal.confidence,
                    timeframe_alignment=0.75
                )
            )
            ranked.append(
                {
                    "symbol": symbol,
                    "signal": signal,
                    "score": score
                }
            )
        ranked.sort(
            key=lambda x:
            x["score"]
            .total_score,
            reverse=True
        )
        return ranked
