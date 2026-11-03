from datetime import datetime
from typing import Dict
from typing import Optional
import pandas as pd
from strategies.candlestick_engine import CandlestickEngine
from strategies.context_filter import ContextFilter
from strategies.models import CandleSignal
from strategies.models import TradeSignal
from strategies.trend_engine import TrendEngine


class MetaStrategy:

    def __init__(
        self,
        config: dict,
        regime_detector
    ):
        self.config = config
        self.candlestick_engine = CandlestickEngine(
            config["strategy"]["candlestick"]
        )

        self.trend_engine = TrendEngine(
            config["strategy"]["trend"]
        )

        self.context_filter = ContextFilter(
            config
        )

        self.regime_detector = regime_detector

    def generate_signal(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
        btc_df: pd.DataFrame
    ) -> Optional[TradeSignal]:
        candle_signals = self.candlestick_engine.analyze(
            df
        )

        if not candle_signals:
            return None
        trend_data = self.trend_engine.detect(
            df
        )

        regime_data = self.regime_detector.detect(
            btc_df
        )

        best_signal = self._select_best_signal(
            candle_signals
        )

        if best_signal is None:
            return None

        approved = self.context_filter.validate(
            best_signal,
            trend_data,
            regime_data
        )

        if not approved:
            return None

        return self._build_trade_signal(
            symbol,
            timeframe,
            best_signal
        )

    def _select_best_signal(
        self,
        signals: list[CandleSignal]
    ) -> Optional[CandleSignal]:

        if not signals:
            return None

        return max(
            signals,
            key=lambda signal: signal.confidence
        )

    def _build_trade_signal(
        self,
        symbol: str,
        timeframe: str,
        signal: CandleSignal
    ) -> TradeSignal:

        risk = abs(
            signal.entry
            - signal.stop_loss
        )

        reward = abs(
            signal.take_profit
            - signal.entry
        )

        rr = 0.0

        if risk > 0:
            rr = reward / risk

        return TradeSignal(
            symbol=symbol,
            timeframe=timeframe,
            strategy="META_STRATEGY",
            side=signal.side,
            confidence=signal.confidence,
            entry=signal.entry,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,

            risk_reward=round(
                rr,
                2
            ),
            created_at=datetime.utcnow()
        )
