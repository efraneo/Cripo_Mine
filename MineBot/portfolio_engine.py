# portfolio_engine.py

import numpy as np
from solver import DiamondSolver
from montecarlo_engine import MonteCarloEngine


class PortfolioEngine:

    def __init__(
        self,
        n_boards=3,
        size=4,
        mines=3,
        capital=300.0,
        kelly_fraction=0.5,
        max_drawdown_limit=0.30
    ):

        self.n_boards = n_boards
        self.size = size
        self.mines = mines
        self.initial_capital = capital
        self.kelly_fraction = kelly_fraction
        self.max_drawdown_limit = max_drawdown_limit

        self.solvers = []
        self.total_equity_curve = []
        self.peak_capital = capital

        allocation = capital / n_boards

        for _ in range(n_boards):
            self.solvers.append(
                DiamondSolver(size, mines, allocation)
            )

        self.total_equity_curve.append(capital)

    # ==========================================================
    # CORE METRICS
    # ==========================================================
    def total_capital(self):
        return sum(s.capital for s in self.solvers)

    def roi(self):
        return (
            self.total_capital() - self.initial_capital
        ) / self.initial_capital

    def sharpe(self):
        if len(self.total_equity_curve) < 2:
            return 0.0

        returns = np.diff(self.total_equity_curve)
        if returns.std() == 0:
            return 0.0

        return returns.mean() / returns.std()

    def max_drawdown(self):
        curve = np.array(self.total_equity_curve)
        peak = np.maximum.accumulate(curve)
        dd = (curve - peak) / peak
        return dd.min()

    def should_stop(self):
        return abs(self.max_drawdown()) >= self.max_drawdown_limit

    # ==========================================================
    # KELLY ALLOCATION
    # ==========================================================
    def _compute_weights(self):

        weights = []

        for solver in self.solvers:
            k = solver.last_kelly if solver.last_kelly > 0 else 0.05
            k *= self.kelly_fraction
            weights.append(max(k, 0.01))

        weights = np.array(weights)

        if weights.sum() == 0:
            weights = np.ones(len(weights))

        weights /= weights.sum()

        return weights

    # ==========================================================
    # STEP PORTFOLIO
    # ==========================================================
    def step(self, hidden_states):

        if self.should_stop():
            return

        weights = self._compute_weights()
        total_cap = self.total_capital()

        for i, solver in enumerate(self.solvers):

            alloc = total_cap * weights[i]
            solver.capital = alloc

            hidden = hidden_states[i]

            # elegir mejor celda según solver
            safe_moves = solver.safest_cells_pro()

            if not safe_moves:
                continue

            best_idx = safe_moves[0][0]

            is_diamond = hidden[best_idx] == 1

            solver.register_click(is_diamond)

        total_now = self.total_capital()

        self.peak_capital = max(self.peak_capital, total_now)
        self.total_equity_curve.append(total_now)

    # ==========================================================
    # MONTE CARLO PORTFOLIO
    # ==========================================================
    def monte_carlo(self, trials=10000):

        weights = self._compute_weights()
        total_cap = self.total_capital()

        results = []

        for solver, w in zip(self.solvers, weights):

            alloc = total_cap * w
            p_mine = solver.base_mine_probability()
            payout = solver.current_multiplier()

            mc = MonteCarloEngine.trajectory(
                capital=alloc,
                p_mine=p_mine,
                payout=payout,
                steps=1,
                trials=trials
            )

            results.append(mc["EV"])

        portfolio_ev = np.sum(results)

        return portfolio_ev