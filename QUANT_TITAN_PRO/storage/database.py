from pathlib import Path
from sqlite3 import Connection
from sqlite3 import Row
from sqlite3 import connect
from typing import Any
from typing import List
from typing import Optional

class Database:

    def __init__(self, config: dict):
        storage_config = config["storage"]
        self.engine = storage_config.get(
            "engine",
            "sqlite"
        )
        self.database_path = storage_config.get(
            "database_path",
            "data/quant_titan.db"
        )
        self.connection = self._create_connection()

    def _create_connection(
        self
    ) -> Connection:

        if self.engine != "sqlite":
            raise ValueError(
                f"Motor no soportado: {self.engine}"
            )

        path = Path(
            self.database_path
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        connection = connect(
            path
        )

        connection.row_factory = Row
        return connection

    def execute(
        self,
        query: str,
        params: tuple = ()
    ) -> None:

        cursor = self.connection.cursor()
        cursor.execute(
            query,
            params
        )
        self.connection.commit()

    def executemany(
        self,
        query: str,
        params: List[tuple]
    ) -> None:

        cursor = self.connection.cursor()
        cursor.executemany(
            query,
            params
        )
        self.connection.commit()

    def fetch_one(
        self,
        query: str,
        params: tuple = ()
    ) -> Optional[dict]:

        cursor = self.connection.cursor()
        cursor.execute(
            query,
            params
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return dict(
            row
        )

    def fetch_all(
        self,
        query: str,
        params: tuple = ()
    ) -> List[dict]:

        cursor = self.connection.cursor()
        cursor.execute(
            query,
            params
        )

        rows = cursor.fetchall()
        return [
            dict(row)
            for row in rows
        ]

    def transaction(
        self,
        queries: List[tuple]
    ) -> None:

        cursor = self.connection.cursor()
        try:
            for query, params in queries:
                cursor.execute(
                    query,
                    params
                )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def close(
        self
    ) -> None:
        self.connection.close()
