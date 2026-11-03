from typing import Dict
from execution.broker import Broker
from strategies.models import TradeSignal

class OrderRouter:

    def __init__(
        self,
        broker: Broker,
        config: dict
    ):

        self.broker = broker
        self.execution_config = config["execution"]
        self.max_slippage = self.execution_config.get(
            "max_slippage_percent",
            0.10
        )

        self.order_type = self.execution_config.get(
            "order_type",
            "market"
        )

        self.partial_take_profit = (
            self.execution_config.get(
                "partial_take_profit",
                True
            )
        )

    def route(
        self,
        signal: TradeSignal,
        quantity: float
    ) -> Dict:

        market_data = self.broker.fetch_ticker(
            signal.symbol
        )

        if not self._slippage_ok(
            market_data
        ):
            return {
                "success": False,
                "reason": "Slippage excesivo"
            }

        if self.order_type == "limit":
            return self._route_limit(
                signal,
                quantity,
                market_data
            )

        return self._route_market(
            signal,
            quantity
        )

    def _route_market(
        self,
        signal: TradeSignal,
        quantity: float
    ) -> Dict:

        return self.broker.create_market_order(
            symbol=signal.symbol,
            side=signal.side,
            quantity=quantity
        )

    def _route_limit(
        self,
        signal: TradeSignal,
        quantity: float,
        market_data: Dict
    ) -> Dict:

        if signal.side == "BUY":
            price = market_data.get(
                "bid",
                signal.entry
            )
        else:
            price = market_data.get(
                "ask",
                signal.entry
            )
        return self.broker.create_limit_order(
            symbol=signal.symbol,
            side=signal.side,
            quantity=quantity,
            price=price
        )

    def _slippage_ok(
        self,
        market_data: Dict
    ) -> bool:

        bid = market_data.get(
            "bid",
            0
        )

        ask = market_data.get(
            "ask",
            0
        )

        if bid <= 0:
            return False

        if ask <= 0:
            return False

        spread = (
            (ask - bid)
            / bid
        ) * 100
        return spread <= self.max_slippage

    def execution_mode(self) -> str:
        return self.broker.current_mode()
