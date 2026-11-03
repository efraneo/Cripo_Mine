from dataclasses import dataclass

@dataclass
class MarketContext:
    trend: str
    volatility: float
    volume_ratio: float
    liquidity_score: float
    session: str
    regime: str
