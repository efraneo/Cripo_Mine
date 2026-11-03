from dataclasses import dataclass

@dataclass
class OpportunityScore:
    symbol: str
    total_score: float
    volume_score: float
    volatility_score: float
    liquidity_score: float
    institutional_score: float
    timeframe_score: float

class OpportunityScorer:

    def __init__(
        self,
        config: dict
    ):
        self.config = config

    def calculate(
        self,
        symbol: str,
        relative_volume: float,
        volatility: float,
        liquidity_score: float,
        institutional_score: float,
        timeframe_alignment: float
    ) -> OpportunityScore:

        volume_score = min(
            relative_volume / 2,
            1.0
        )
        volatility_score = min(
            volatility * 50,
            1.0
        )
        total = (
            volume_score * 0.20 +
            volatility_score * 0.15 +
            liquidity_score * 0.20 +
            institutional_score * 0.30 +
            timeframe_alignment * 0.15
        )
        return OpportunityScore(
            symbol=symbol,
            total_score=round(
                total,
                4
            ),
            volume_score=round(
                volume_score,
                4
            ),
            volatility_score=round(
                volatility_score,
                4
            ),
            liquidity_score=round(
                liquidity_score,
                4
            ),
            institutional_score=round(
                institutional_score,
                4
            ),
            timeframe_score=round(
                timeframe_alignment,
                4
            )
        )
