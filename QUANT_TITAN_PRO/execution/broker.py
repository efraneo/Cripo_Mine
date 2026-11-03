from typing import Dict
from typing import List
from typing import Optional
import ccxt

class Broker:

    SUPPORTED_EXCHANGES = {
        "binance": ccxt.binance,
        "bybit": ccxt.bybit,
        "okx": ccxt.okx,
        "kraken": ccxt.kraken,
    }

    def __init__(self, config: dict):

        execution = config["execution"]
        exchange_config = config["exchange"]

        self.mode = execution.get(
            "mode",
            "paper"
        )

        exchange_name = exchange_config.get(
            "provider",
            "binance"
        )

        if exchange_name not in self.SUPPORTED_EXCHANGES:
            raise ValueError(
                f"Exchange no soportado: {exchange_name}"
            )
        exchange_class = self.SUPPORTED_EXCHANGES[
            exchange_name
        ]

        self.exchange = exchange_class(
            {
                "apiKey": exchange_config.get(
                    "api_key"
                ),
                "secret": exchange_config.get(
                    "api_secret"
                ),
                "enableRateLimit": exchange_config.get(
                    "enable_rate_limit",
                    True
                ),
                "timeout": exchange_config.get(
                    "timeout_seconds",
                    30
                ) * 1000,
            }
        )

        self.exchange.set_sandbox_mode(
            exchange_config.get(
                "sandbox",
                False
            )
        )

    def fetch_balance(self) -> Dict:

        if self.mode == "paper":
            return {
                "USDT": {
                    "free": 10000.0,
                    "used": 0.0,
                    "total": 10000.0
                }
            }
        return self.exchange.fetch_balance()

    def fetch_ticker(
        self,
        symbol: str
    ) -> Dict:

        return self.exchange.fetch_ticker(
            symbol
        )

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500
    ) -> List:

        return self.exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            limit=limit
        )

    def fetch_open_orders(
        self,
        symbol: Optional[str] = None
    ) -> List:

        if self.mode == "paper":
            return []
        return self.exchange.fetch_open_orders(
            symbol
        )

    def create_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float
    ) -> Dict:

        if self.mode == "paper":
            return {
                "id": "paper-order",
                "symbol": symbol,
                "side": side,
                "amount": quantity,
                "status": "filled"
            }

        return self.exchange.create_market_order(
            symbol,
            side.lower(),
            quantity
        )

    def create_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float
    ) -> Dict:

        if self.mode == "paper":
            return {
                "id": "paper-order",
                "symbol": symbol,
                "side": side,
                "amount": quantity,
                "price": price,
                "status": "open"
            }

        return self.exchange.create_limit_order(
            symbol,
            side.lower(),
            quantity,
            price
        )

    def cancel_order(
        self,
        order_id: str,
        symbol: str
    ) -> Dict:

        if self.mode == "paper":
            return {
                "id": order_id,
                "status": "cancelled"
            }

        return self.exchange.cancel_order(
            order_id,
            symbol
        )

    def markets(self) -> Dict:
        return self.exchange.load_markets()

    def current_mode(self) -> str:
        return self.mode
