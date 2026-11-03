from typing import Dict
from typing import List
from typing import Optional
from execution.order_router import OrderRouter
from risk.risk_engine import RiskEngine
from strategies.models import Position
from strategies.models import TradeSignal

class ExecutionEngine:

    def __init__(
        self,
        broker,
        order_router: OrderRouter,
        risk_engine: RiskEngine
    ):

        self.broker = broker
        self.order_router = order_router
        self.risk_engine = risk_engine

    def execute(
        self,
        signal: TradeSignal,
        open_positions: List[Position],
        daily_pnl: float,
        weekly_pnl: float
    ) -> Dict:

        balance = self._account_balance()
        risk_decision = self.risk_engine.evaluate(
            signal=signal,
            account_balance=balance,
            open_positions=open_positions,
            daily_pnl=daily_pnl,
            weekly_pnl=weekly_pnl
        )

        if not risk_decision.approved:
            return {
                "success": False,
                "stage": "risk",
                "reason": risk_decision.reason
            }

        quantity = self.risk_engine.position_size(
            account_balance=balance,
            signal=signal
        )

        if quantity <= 0:
            return {
                "success": False,
                "stage": "position_size",
                "reason": "Cantidad inválida"
            }

        order_result = self.order_router.route(
            signal,
            quantity
        )

        if not order_result.get(
            "id"
        ):
            return {
                "success": False,
                "stage": "execution",
                "reason": order_result.get(
                    "reason",
                    "Orden rechazada"
                )
            }

        return {
            "success": True,
            "stage": "completed",
            "order_id": order_result["id"],
            "symbol": signal.symbol,
            "side": signal.side,
            "quantity": quantity,
            "entry": signal.entry,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit
        }

    def _account_balance(
        self
    ) -> float:

        balance = self.broker.fetch_balance()
        usdt = balance.get(
            "USDT",
            {}
        )

        return float(
            usdt.get(
                "free",
                0
            )
        )

    def portfolio_status(
        self,
        open_positions: List[Position]
    ) -> Dict:

        balance = self._account_balance()
        snapshot = self.risk_engine.risk_snapshot(
            account_balance=balance,
            open_positions=open_positions
        )

        return {
            "mode": self.broker.current_mode(),
            **snapshot
        }

    def can_execute(
        self,
        signal: Optional[TradeSignal],
        open_positions: List[Position]
    ) -> bool:

        if signal is None:
            return False

        return len(
            open_positions
        ) < self.risk_engine.max_open_positions
