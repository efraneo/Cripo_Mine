import time
from datetime import datetime

class Scheduler:

    def __init__(
        self,
        orchestrator,
        broker,
        interval_seconds: int
    ):

        self.orchestrator = orchestrator
        self.broker = broker
        self.interval_seconds = (
            interval_seconds
        )

    def start(
        self
    ):

        print(
            "\n"
            "=================================\n"
            " QUANT TITAN PRO INICIADO\n"
            "=================================\n"
        )

        while True:
            try:
                start = datetime.utcnow()
                btc_df = self.broker.fetch_ohlcv(
                    "BTC/USDT",
                    timeframe="1h",
                    limit=500
                )

                self.orchestrator.cycle(
                    btc_df
                )

                elapsed = (
                    datetime.utcnow()
                    - start
                )

                print(
                    f"[CYCLE] "
                    f"{elapsed}"
                )

            except Exception as error:

                print(
                    "[ERROR]",
                    error
                )

            time.sleep(
                self.interval_seconds
            )
