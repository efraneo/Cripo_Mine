from typing import List
from typing import Optional
from storage.database import Database
from strategies.models import Position

class TradeRepository:

    def __init__(self, database: Database):
        self.database = database
        self._create_table()

    def _create_table(self) -> None:
        query = """
        CREATE TABLE IF NOT EXISTS trades (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            strategy TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity REAL NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit REAL NOT NULL,
            realized_pnl REAL NOT NULL,
            fees REAL DEFAULT 0,
            opened_at TEXT NOT NULL,
            closed_at TEXT NOT NULL
        )
        """
        self.database.execute(query)

    def save(
        self,
        position: Position
    ) -> None:

        query = """
        INSERT INTO trades (
            id,
            symbol,
            timeframe,
            strategy,
            side,
            quantity,
            entry_price,
            exit_price,
            stop_loss,
            take_profit,
            realized_pnl,
            fees,
            opened_at,
            closed_at
        )

        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """
        self.database.execute(

            query,
            (
                position.id,
                position.symbol,
                position.timeframe,
                position.strategy,
                position.side,
                position.quantity,
                position.entry_price,
                position.current_price,
                position.stop_loss,
                position.take_profit,
                position.realized_pnl,

                getattr(
                    position,
                    "fees",
                    0.0
                ),
                position.opened_at.isoformat(),
                position.closed_at.isoformat()
            )
        )

    def get_all(
        self
    ) -> List[dict]:

        query = """
        SELECT *
        FROM trades
        ORDER BY closed_at DESC
        """

        return self.database.fetch_all(
            query
        )

    def get_by_symbol(
        self,
        symbol: str
    ) -> List[dict]:

        query = """
        SELECT *
        FROM trades
        WHERE symbol = ?
        ORDER BY closed_at DESC
        """

        return self.database.fetch_all(
            query,
            (symbol,)
        )

    def count(
        self
    ) -> int:

        row = self.database.fetch_one(
            """
            SELECT COUNT(*) AS total
            FROM trades
            """
        )

        return int(
            row["total"]
        )
