from dataclasses import dataclass
from datetime import datetime
import pandas as pd
from strategies.models import TradeSignal

@dataclass
class BacktestTrade:
    symbol: str
    side: str
    entry: float
    exit_price: float
    pnl_percent: float
    opened_at: datetime
    closed_at: datetime

class BacktestEngine:

    def __init__(
        self,
        strategy,
        initial_balance: float = 10000
    ):

        self.strategy = strategy
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.trades = []

    def run(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame
    ) -> dict:

        for index in range(
            250,
            len(df)
        ):

            chunk = df.iloc[:index]
            signal = (
                self.strategy
                .generate_signal(
                    symbol,
                    timeframe,
                    chunk
                )
            )

            if signal is None:
                continue

            trade = self._simulate_trade(
                signal,
                df,
                index
            )

            if trade:

                self.trades.append(
                    trade
                )

        return {
            "initial_balance": self.initial_balance,
            "final_balance": self.balance,
            "trades": self.trades
        }

    def _simulate_trade(
        self,
        signal: TradeSignal,
        df: pd.DataFrame,
        index: int
    ):

        future = df.iloc[
            index:index + 50
        ]

        for _, candle in future.iterrows():
            if signal.side == "BUY":
                if candle["low"] <= signal.stop_loss:
                    return self._close_trade(
                        signal,
                        signal.stop_loss
                    )
                if candle["high"] >= signal.take_profit:
                    return self._close_trade(
                        signal,
                        signal.take_profit
                    )
            else:
                if candle["high"] >= signal.stop_loss:
                    return self._close_trade(
                        signal,
                        signal.stop_loss
                    )
                if candle["low"] <= signal.take_profit:
                    return self._close_trade(
                        signal,
                        signal.take_profit
                    )
        return None

    def _close_trade(
        self,
        signal,
        exit_price
    ):

        pnl = (
            (exit_price - signal.entry)
            / signal.entry
        )

        if signal.side == "SELL":
            pnl *= -1
        self.balance *= (
            1 + pnl
        )
        return BacktestTrade(
            symbol=signal.symbol,
            side=signal.side,
            entry=signal.entry,
            exit_price=exit_price,
            pnl_percent=round(
                pnl * 100,
                2
            ),
            opened_at=signal.created_at,
            closed_at=datetime.utcnow()
        )
