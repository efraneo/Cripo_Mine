from typing import List

import ccxt

class MarketUniverse:
    EXCLUDED_SYMBOLS = {
        "BUSD/USDT",
        "TUSD/USDT",
        "FDUSD/USDT",
        "USDC/USDT",
        "USDP/USDT",
        "DAI/USDT",
    }

    EXCLUDED_KEYWORDS = {
        "UP/",
        "DOWN/",
        "BULL/",
        "BEAR/",
        "1000",
    }

    def __init__(self, exchange_config: dict):
        self.exchange = ccxt.binance(
            {
                "apiKey": exchange_config["api_key"],
                "secret": exchange_config["api_secret"],
                "enableRateLimit": exchange_config[
                    "enable_rate_limit"
                ],
            }
        )
        self.exchange.set_sandbox_mode(
            exchange_config["sandbox"]
        )

    def get_symbols(self) -> List[str]:
        markets = self.exchange.load_markets()
        symbols = []
        for symbol, market in markets.items():
            if not self._is_valid_market(
                symbol,
                market
            ):
                continue
            symbols.append(symbol)
        return sorted(symbols)

    def _is_valid_market(
        self,
        symbol: str,
        market: dict
    ) -> bool:

        if not market.get("spot", False):
            return False

        if not symbol.endswith("/USDT"):
            return False

        if symbol in self.EXCLUDED_SYMBOLS:
            return False

        for keyword in self.EXCLUDED_KEYWORDS:
            if keyword in symbol:
                return False

        return True