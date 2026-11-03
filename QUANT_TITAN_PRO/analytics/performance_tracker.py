from collections import defaultdict

class PerformanceTracker:

    def __init__(self):
        self.trades = []

    def add_trade(
        self,
        trade
    ):

        self.trades.append(
            trade
        )

    def summary(
        self
    ) -> dict:

        if not self.trades:
            return {}
        wins = [
            trade
            for trade in self.trades
            if trade.pnl_percent > 0
        ]

        losses = [
            trade
            for trade in self.trades
            if trade.pnl_percent <= 0
        ]

        pnl = sum(
            trade.pnl_percent
            for trade in self.trades
        )

        return {
            "total_trades": len(
                self.trades
            ),
            "wins": len(
                wins
            ),
            "losses": len(
                losses
            ),
            "win_rate": round(
                len(wins)
                / len(self.trades)
                * 100,
                2
            ),
            "net_pnl": round(
                pnl,
                2
            ),
            "best_trade": self._best_trade(),
            "worst_trade": self._worst_trade(),
            "longest_win_streak":
                self._longest_streak(
                    positive=True
                ),
            "longest_loss_streak":
                self._longest_streak(
                    positive=False
                )
        }

    def by_symbol(
        self
    ) -> dict:

        data = defaultdict(
            list
        )

        for trade in self.trades:
            data[trade.symbol].append(
                trade.pnl_percent
            )
        return {
            symbol: {
                "trades": len(values),
                "average_pnl": round(
                    sum(values)
                    / len(values),
                    2
                )
            }

            for symbol, values
            in data.items()
        }

    def _best_trade(
        self
    ):

        return max(
            self.trades,
            key=lambda t:
            t.pnl_percent
        )

    def _worst_trade(
        self
    ):

        return min(
            self.trades,
            key=lambda t:
            t.pnl_percent
        )

    def _longest_streak(
        self,
        positive: bool
    ) -> int:

        current = 0
        best = 0
        for trade in self.trades:
            success = (
                trade.pnl_percent > 0
            )
            if success == positive:
                current += 1
                best = max(
                    best,
                    current
                )
            else:
                current = 0
        return best
