# backtester.py
import numpy as np
from solver import DiamondSolver

class Backtester:

    @staticmethod
    def run_sessions(
        size,
        mines,
        sessions=500,
        capital=100,
        target=8
    ):
        final_capitals = []
        drawdowns = []
        sharpes = []

        for _ in range(sessions):
            solver = DiamondSolver(size, mines, capital, target)

            while solver.should_continue("INST"):
                p_mine = solver.base_mine_probability()
                is_diamond = np.random.rand() > p_mine
                solver.register_click(is_diamond)

                if solver.capital <= 0:
                    break

            final_capitals.append(solver.capital)
            drawdowns.append(solver.max_drawdown)
            sharpes.append(solver.sharpe())

        results = {
            "mean_final": np.mean(final_capitals),
            "median_final": np.median(final_capitals),
            "cagr_proxy": np.mean(final_capitals) / capital - 1,
            "mean_dd": np.mean(drawdowns),
            "mean_sharpe": np.mean(sharpes),
            "risk_of_ruin": np.mean(np.array(final_capitals) <= 1)
        }

        return results