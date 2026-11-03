from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class LiquidityZone:

    symbol: str
    timeframe: str
    zone_type: str
    price: float
    strength: float
    touches: int
    created_at: datetime

@dataclass
class BreakOfStructure:
    symbol: str
    timeframe: str
    direction: str
    level: float
    strength: float
    candle_index: int
    created_at: datetime

@dataclass
class ChangeOfCharacter:
    symbol: str
    timeframe: str
    direction: str
    level: float
    confidence: float
    candle_index: int
    created_at: datetime

@dataclass
class OrderBlock:
    symbol: str
    timeframe: str
    side: str
    high: float
    low: float
    strength: float
    volume_score: float
    created_at: datetime

@dataclass
class FairValueGap:
    symbol: str
    timeframe: str
    side: str
    upper_price: float
    lower_price: float
    size_percent: float
    filled: bool
    created_at: datetime

@dataclass
class InstitutionalScore:
    symbol: str
    timeframe: str
    liquidity_score: float
    bos_score: float
    choch_score: float
    order_block_score: float
    fvg_score: float
    trend_score: float
    total_score: float
    created_at: datetime
