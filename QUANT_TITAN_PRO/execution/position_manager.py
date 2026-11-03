from datetime import datetime
from typing import Dict
from typing import List
from typing import Optional
from strategies.models import Position

class PositionManager:

    def __init__(self):
        self.positions: Dict[str, Position] = {}

    def add_position(
        self,
        position: Position
    ) -> None:
        self.positions[position.symbol] = position

    def remove_position(
        self,
        symbol: str
    ) -> None:
        self.positions.pop(
            symbol,
            None
        )

    def get_position(
        self,
        symbol: str
    ) -> Optional[Position]:
        return self.positions.get(
            symbol
        )

    def get_open_positions(
        self
    ) -> List[Position]:
        return list(
            self.positions.values()
        )

    def update_market_price(
        self,
        symbol: str,
        current_price: float
    ) -> None:
        position = self.get_position(
            symbol
        )

        if position is None:
            return

        position.current_price = current_price
        position.updated_at = datetime.utcnow()
        position.unrealized_pnl = self.calculate_pnl(
            position
        )

    def calculate_pnl(
        self,
        position: Position
    ) -> float:

        if position.side == "BUY":
            pnl = (
                position.current_price
                - position.entry_price
            )

        else:

            pnl = (
                position.entry_price
                - position.current_price
            )

        pnl *= position.quantity
        return round(
            pnl,
            4
        )

    def check_stop_loss(
        self,
        symbol: str
    ) -> bool:

        position = self.get_position(
            symbol
        )

        if position is None:
            return False

        if position.side == "BUY":
            return (
                position.current_price
                <=
                position.stop_loss
            )
        return (
            position.current_price
            >=
            position.stop_loss
        )

    def check_take_profit(
        self,
        symbol: str
    ) -> bool:

        position = self.get_position(
            symbol
        )

        if position is None:
            return False

        if position.side == "BUY":
            return (
                position.current_price
                >=
                position.take_profit
            )
        return (
            position.current_price
            <=
            position.take_profit
        )

    def close_position(
        self,
        symbol: str
    ) -> Optional[Position]:

        position = self.get_position(
            symbol
        )

        if position is None:
            return None

        position.realized_pnl = self.calculate_pnl(
            position
        )

        position.closed_at = datetime.utcnow()
        self.remove_position(
            symbol
        )
        return position

    def total_unrealized_pnl(
        self
    ) -> float:

        total = 0.0

        for position in self.positions.values():
            total += position.unrealized_pnl
        return round(
            total,
            4
        )

    def exposure(
        self
    ) -> float:

        exposure = 0.0

        for position in self.positions.values():
            exposure += (
                position.quantity
                * position.current_price
            )

        return round(
            exposure,
            2
        )

    def portfolio_summary(
        self
    ) -> Dict:

        return {
            "positions": len(
                self.positions
            ),
            "exposure": self.exposure(),
            "unrealized_pnl": self.total_unrealized_pnl()
        }
