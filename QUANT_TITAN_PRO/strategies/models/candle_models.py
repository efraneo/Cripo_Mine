from dataclasses import dataclass

@dataclass
class CandleSignal:
    pattern: str
    side: str
    confidence: float
    entry: float
    stop_loss: float
    take_profit: float
    volume_score: float
    rejection_score: float
    trend_score: float
