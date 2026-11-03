from typing import List
from storage.database import Database
from strategies.models import TradeSignal

class SignalRepository:

    def __init__(self, database: Database):
        self.database = database
        self._create_table()

    def _create_table(self) -> None:
        query = """
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            strategy TEXT NOT NULL,
            side TEXT NOT NULL,
            confidence REAL NOT NULL,
            entry_price REAL NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit REAL NOT NULL,
            risk_reward REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
        self.database.execute(
            query
        )

    def save(
        self,
        signal: TradeSignal,
        status: str
    ) -> None:

        query = """
        INSERT INTO signals (
            symbol,
            timeframe,
            strategy,
            side,
            confidence,
            entry_price,
            stop_loss,
            take_profit,
            risk_reward,
            status,
            created_at
        )

        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """
        self.database.execute(
            query,
            (
                signal.symbol,
                signal.timeframe,
                signal.strategy,
                signal.side,
                signal.confidence,
                signal.entry,
                signal.stop_loss,
                signal.take_profit,
                signal.risk_reward,
                status,
                signal.created_at.isoformat()
            )
        )

    def latest(
        self,
        limit: int = 100
    ) -> List[dict]:

        query = """
        SELECT *
        FROM signals
        ORDER BY created_at DESC
        LIMIT ?
        """
        return self.database.fetch_all(
            query,
            (limit,)
        )
