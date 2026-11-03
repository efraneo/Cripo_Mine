from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class ExecutionReport:
    order_id: Optional[str]
    symbol: str
    status: str
    executed_price: float
    executed_quantity: float
    slippage: float
    timestamp: datetime
