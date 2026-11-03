from datetime import datetime
from typing import Optional
import pandas as pd
from smart_money.market_structure import (
    MarketStructure
)
from smart_money.institutional_score import (
    InstitutionalScoreEngine
)
from strategies.models import (
    CandleSignal,
    TradeSignal
)

class InstitutionalStrategy:
    def __init__(
        self,
        config: dict,
        candlestick_engine,
        trend_engine
    ):

        self.config = config

        self.candlestick_engine = (
            candlestick_engine
        )

        self.trend_engine = (
            trend_engine
        )

        self.market_structure = (
            MarketStructure(
                config
            )
        )

        self.score_engine = (
            InstitutionalScoreEngine(
                config
            )
        )

    def generate_signal(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
        market_context=None
    ) -> Optional[TradeSignal]:

        candle_signal = (
            self.candlestick_engine
            .analyze(
                df
            )
        )

        if candle_signal is None:
            return None
        trend = (
            self.trend_engine
            .detect(
                df
            )
        )

        structure = (
            self.market_structure
            .analyze(
                symbol,
                timeframe,
                df
            )
        )

        institutional_score = (
            self.score_engine
            .calculate(
                symbol=symbol,
                timeframe=timeframe,
                structure=structure,
                trend_score=trend.score
            )
        )

        if not self.score_engine.approved(
            institutional_score
        ):
            return None

        return self._build_trade_signal(
            symbol,
            timeframe,
            candle_signal,
            institutional_score
        )

    def _build_trade_signal(
        self,
        symbol: str,
        timeframe: str,
        candle_signal: CandleSignal,
        score
    ) -> TradeSignal:

        confidence = round(
            (
                candle_signal.confidence * 0.40 +
                score.total_score * 0.60
            ),
            3
        )

        risk_reward = round(
            abs(
                candle_signal.take_profit
                -
                candle_signal.entry
            )
            /
            abs(
                candle_signal.entry
                -
                candle_signal.stop_loss
            ),
            2
        )

        return TradeSignal(
            symbol=symbol,
            timeframe=timeframe,
            strategy="INSTITUTIONAL_STRATEGY",
            side=candle_signal.side,
            confidence=confidence,
            entry=candle_signal.entry,
            stop_loss=candle_signal.stop_loss,
            take_profit=candle_signal.take_profit,
            risk_reward=risk_reward,
            institutional_score=score.total_score,
            liquidity_score=score.liquidity_score,
            volume_score=candle_signal.volume_score,
            trend_score=score.trend_score,
            regime="UNKNOWN",
            created_at=datetime.utcnow()
        )
