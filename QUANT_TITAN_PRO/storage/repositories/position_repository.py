from typing import List
from typing import Optional
from storage.database import Database
from strategies.models import Position

class PositionRepository:

    def __init__(self, database: Database):
        self.database = database
        self._create_table()

    def _create_table(self) -> None:
        query = """
        CREATE TABLE IF NOT EXISTS positions (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            strategy TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity REAL NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit REAL NOT NULL,
            realized_pnl REAL NOT NULL,
            unrealized_pnl REAL NOT NULL,
            opened_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            closed_at TEXT
        )
        """
        self.database.execute(query)

    def save(
        self,
        position: Position
    ) -> None:

        query = """
        INSERT OR REPLACE INTO positions (
            id,
            symbol,
            timeframe,
            strategy,
            side,
            quantity,
            entry_price,
            current_price,
            stop_loss,
            take_profit,
            realized_pnl,
            unrealized_pnl,
            opened_at,
            updated_at,
            closed_at
        )

        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                position.unrealized_pnl,
                position.opened_at.isoformat(),
                position.updated_at.isoformat(),
                position.closed_at.isoformat()

                if position.closed_at
                else None
            )
        )

    def get(
        self,
        symbol: str
    ) -> Optional[dict]:

        query = """
        SELECT *
        FROM positions
        WHERE symbol = ?
        LIMIT 1
        """

        return self.database.fetch_one(
            query,
            (symbol,)
        )

    def get_open_positions(
        self
    ) -> List[dict]:

        query = """
        SELECT *
        FROM positions
        WHERE closed_at IS NULL
        """

        return self.database.fetch_all(
            query
        )

    def delete(
        self,
        symbol: str
    ) -> None:

        query = """
        DELETE FROM positions
        WHERE symbol = ?
        """

        self.database.execute(
            query,
            (symbol,)
        )

    def update_price(
        self,
        symbol: str,
        current_price: float,
        unrealized_pnl: float,
        updated_at: str
    ) -> None:

        query = """
        UPDATE positions

        SET
            current_price = ?,
            unrealized_pnl = ?,
            updated_at = ?

        WHERE symbol = ?
        """

        self.database.execute(
            query,
            (
                current_price,
                unrealized_pnl,
                updated_at,
                symbol
            )
        )
