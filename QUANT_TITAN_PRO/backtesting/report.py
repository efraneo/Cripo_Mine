import math

class BacktestReport:
    def build(
        self,
        initial_balance: float,
        final_balance: float,
        trades
    ) -> dict:

        equity_curve = self._equity_curve(
            initial_balance,
            trades
        )

        return {
            "initial_balance": initial_balance,
            "final_balance": final_balance,
            "total_return": round(
                (
                    final_balance
                    - initial_balance
                )
                / initial_balance
                * 100,
                2
            ),
            "max_drawdown": self._max_drawdown(
                equity_curve
            ),
            "sharpe_ratio": self._sharpe(
                trades
            ),
            "equity_curve": equity_curve
        }

    def _equity_curve(
        self,
        initial_balance,
        trades
    ):

        curve = [
            initial_balance
        ]
        balance = initial_balance

        for trade in trades:
            balance *= (
                1 +
                trade.pnl_percent
                / 100
            )
            curve.append(
                round(
                    balance,
                    2
                )
            )
        return curve

    def _max_drawdown(
        self,
        curve
    ) -> float:

        peak = curve[0]
        max_dd = 0

        for value in curve:
            if value > peak:
                peak = value
            drawdown = (
                peak - value
            ) / peak
            max_dd = max(
                max_dd,
                drawdown
            )
        return round(
            max_dd * 100,
            2
        )

    def _sharpe(
        self,
        trades
    ) -> float:

        if len(trades) < 2:
            return 0.0

        returns = [
            trade.pnl_percent
            for trade in trades
        ]

        avg = (
            sum(returns)
            / len(returns)
        )

        variance = sum(
            (
                x - avg
            ) ** 2
            for x in returns
        ) / len(returns)
        std = math.sqrt(
            variance
        )

        if std == 0:
            return 0.0
        return round(
            avg / std,
            3
        )
