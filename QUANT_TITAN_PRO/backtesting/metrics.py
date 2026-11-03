class MetricsCalculator:

    def calculate(
        self,
        trades
    ) -> dict:

        if not trades:
            return {}

        wins = [
            trade
            for trade in trades
            if trade.pnl_percent > 0
        ]

        losses = [
            trade
            for trade in trades
            if trade.pnl_percent <= 0
        ]

        total = len(
            trades
        )

        win_rate = round(
            len(wins)
            / total * 100,
            2
        )

        gross_profit = sum(
            trade.pnl_percent
            for trade in wins
        )

        gross_loss = abs(
            sum(
                trade.pnl_percent
                for trade in losses
            )
        )

        profit_factor = (
            gross_profit
            / gross_loss
            if gross_loss > 0
            else 999
        )

        expectancy = round(
            (
                gross_profit
                -
                gross_loss
            )
            / total,
            2
        )

        return {
            "trades": total,
            "wins": len(
                wins
            ),
            "losses": len(
                losses
            ),
            "win_rate": win_rate,
            "profit_factor": round(
                profit_factor,
                2
            ),
            "expectancy": expectancy
        }
