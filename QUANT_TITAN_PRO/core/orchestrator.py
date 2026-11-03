from core.event_bus import EventBus
from core.state_manager import StateManager

class Orchestrator:

    def __init__(
        self,
        market_scanner,
        meta_strategy,
        execution_engine,
        position_manager,
        signal_repository,
        state_manager: StateManager,
        event_bus: EventBus
    ):

        self.market_scanner = market_scanner
        self.meta_strategy = meta_strategy
        self.execution_engine = execution_engine
        self.position_manager = position_manager
        self.signal_repository = signal_repository
        self.state_manager = state_manager
        self.event_bus = event_bus

    def cycle(
        self,
        btc_df
    ):

        symbols = self.market_scanner.scan()

        open_positions = (
            self.position_manager
            .get_open_positions()
        )

        for asset in symbols:
            symbol = asset.symbol
            timeframe = asset.timeframe
            candles = asset.data

            signal = (
                self.meta_strategy
                .generate_signal(
                    symbol=symbol,
                    timeframe=timeframe,
                    df=candles,
                    btc_df=btc_df
                )
            )

            if signal is None:
                continue

            self.signal_repository.save(
                signal,
                status="DETECTED"
            )

            self.event_bus.publish(
                "signal_detected",
                {
                    "symbol": symbol,
                    "confidence":
                    signal.confidence
                }
            )

            result = (
                self.execution_engine
                .execute(
                    signal,
                    open_positions,
                    self.state_manager.daily_pnl,
                    self.state_manager.weekly_pnl
                )
            )

            status = (
                "EXECUTED"

                if result["success"]

                else "REJECTED"

            )

            self.signal_repository.save(
                signal,
                status=status
            )

            self.event_bus.publish(
                "execution_result",
                result
            )
