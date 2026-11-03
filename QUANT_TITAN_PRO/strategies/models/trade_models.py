from dataclasses import dataclass
from datetime import datetime

@dataclass
class TradeSignal:
    symbol: str
    timeframe: str
    strategy: str
    side: str
    confidence: float
    entry: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    institutional_score: float
    liquidity_score: float
    volume_score: float
    trend_score: float
    regime: str
    created_at: datetime

@dataclass
class Position:
    id: str
    symbol: str
    timeframe: str
    strategy: str
    side: str
    quantity: float
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    realized_pnl: float
    unrealized_pnl: float
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None
