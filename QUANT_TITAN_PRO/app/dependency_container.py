from ai.regime_detector import RegimeDetector
from core.event_bus import EventBus
from core.orchestrator import Orchestrator
from core.state_manager import StateManager
from execution.broker import Broker
from execution.execution_engine import ExecutionEngine
from execution.order_router import OrderRouter
from execution.position_manager import PositionManager
from market.market_scanner import MarketScanner
from risk.risk_engine import RiskEngine
from storage.database import Database
from storage.repositories.position_repository import (
    PositionRepository
)
from storage.repositories.signal_repository import (
    SignalRepository
)
from storage.repositories.trade_repository import (
    TradeRepository
)
from strategies.meta_strategy import MetaStrategy

class DependencyContainer:

    def __init__(
        self,
        config: dict
    ):
        self.config = config

    def build(self):
        broker = Broker(
            self.config
        )

        database = Database(
            self.config
        )
        event_bus = EventBus()
        state_manager = StateManager()
        regime_detector = RegimeDetector(
            self.config
        )

        market_scanner = MarketScanner(
            broker,
            self.config
        )

        risk_engine = RiskEngine(
            self.config
        )

        order_router = OrderRouter(
            broker,
            self.config
        )

        execution_engine = ExecutionEngine(
            broker,
            order_router,
            risk_engine
        )

        position_manager = PositionManager()

        signal_repository = SignalRepository(
            database
        )

        trade_repository = TradeRepository(
            database
        )

        position_repository = PositionRepository(
            database
        )

        meta_strategy = MetaStrategy(
            self.config,
            regime_detector
        )

        orchestrator = Orchestrator(
            market_scanner=market_scanner,
            meta_strategy=meta_strategy,
            execution_engine=execution_engine,
            position_manager=position_manager,
            signal_repository=signal_repository,
            state_manager=state_manager,
            event_bus=event_bus
        )

        return {
            "broker": broker,
            "database": database,
            "event_bus": event_bus,
            "state_manager": state_manager,
            "risk_engine": risk_engine,
            "market_scanner": market_scanner,
            "position_manager": position_manager,
            "signal_repository": signal_repository,
            "trade_repository": trade_repository,
            "position_repository": position_repository,
            "execution_engine": execution_engine,
            "orchestrator": orchestrator
        }
