from datetime import datetime
from typing import List
from strategies.models import Position
from strategies.models import RiskDecision
from strategies.models import TradeSignal

class RiskEngine:

    def __init__(self, config: dict):
        risk_config = config["risk"]

        self.initial_capital = risk_config.get(
            "initial_capital",
            10_000
        )

        self.risk_per_trade = (
            risk_config.get(
                "risk_per_trade_percent",
                0.5
            )
            / 100
        )

        self.max_open_positions = risk_config.get(
            "max_open_positions",
            3
        )

        self.max_daily_loss = (
            risk_config.get(
                "max_daily_loss_percent",
                2.0
            )
            / 100
        )

        self.max_weekly_loss = (
            risk_config.get(
                "max_weekly_loss_percent",
                5.0
            )
            / 100
        )

        self.max_drawdown = (
            risk_config.get(
                "max_drawdown_percent",
                10.0
            )
            / 100
        )

    def evaluate(
        self,
        signal: TradeSignal,
        account_balance: float,
        open_positions: List[Position],
        daily_pnl: float,
        weekly_pnl: float
    ) -> RiskDecision:

        if len(open_positions) >= self.max_open_positions:
            return RiskDecision(
                approved=False,
                reason="Máximo de posiciones abiertas",
                risk_percent=0.0
            )

        if not self._daily_loss_ok(
            daily_pnl,
            account_balance
        ):
            return RiskDecision(
                approved=False,
                reason="Límite diario alcanzado",
                risk_percent=0.0
            )

        if not self._weekly_loss_ok(
            weekly_pnl,
            account_balance
        ):
            return RiskDecision(
                approved=False,
                reason="Límite semanal alcanzado",
                risk_percent=0.0
            )

        if not self._drawdown_ok(
            account_balance
        ):
            return RiskDecision(
                approved=False,
                reason="Drawdown máximo alcanzado",
                risk_percent=0.0
            )

        return RiskDecision(
            approved=True,
            reason="Operación aprobada",
            risk_percent=round(
                self.risk_per_trade * 100,
                2
            )
        )

    def position_size(
        self,
        account_balance: float,
        signal: TradeSignal
    ) -> float:

        risk_amount = (
            account_balance
            * self.risk_per_trade
        )

        stop_distance = abs(
            signal.entry
            - signal.stop_loss
        )

        if stop_distance <= 0:
            return 0.0

        size = (
            risk_amount
            / stop_distance
        )

        return round(
            size,
            8
        )

    def _daily_loss_ok(
        self,
        daily_pnl: float,
        account_balance: float
    ) -> bool:

        limit = (
            account_balance
            * self.max_daily_loss
        )
        return daily_pnl > -limit

    def _weekly_loss_ok(
        self,
        weekly_pnl: float,
        account_balance: float
    ) -> bool:

        limit = (
            account_balance
            * self.max_weekly_loss
        )
        return weekly_pnl > -limit

    def _drawdown_ok(
        self,
        account_balance: float
    ) -> bool:

        minimum_balance = (
            self.initial_capital
            * (1 - self.max_drawdown)
        )
        return account_balance >= minimum_balance

    def risk_snapshot(
        self,
        account_balance: float,
        open_positions: List[Position]
    ) -> dict:

        exposure = 0.0

        for position in open_positions:
            exposure += (
                position.quantity
                * position.current_price
            )

        return {
            "timestamp": datetime.utcnow(),
            "balance": account_balance,
            "positions": len(
                open_positions
            ),
            "exposure": round(
                exposure,
                2
            ),
            "available_balance": round(
                account_balance
                - exposure,
                2
            )
        }
