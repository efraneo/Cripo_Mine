# solver.py
import numpy as np
from risk_engine import RiskEngine
from montecarlo_engine import MonteCarloEngine
from metrics_engine import MetricsEngine
from safezone_engine import SafeZoneEngine
from hedge_engine import HedgeEngine

class DiamondSolver:

    def __init__(self, size, mines, capital=100.0, target=8):
        self.size = size
        self.mines = mines
        self.cells = size * size
        self.target = target

        self.revealed = np.zeros(self.cells, dtype=int)
        self.diamonds = 0

        self.initial_capital = capital
        self.capital = capital
        self.equity_curve = [capital]
        self.peak = capital
        self.max_drawdown = 0.0

        self.last_ev = 0.0
        self.last_kelly = 0.0

    # ==========================
    # ESTADO
    # ==========================
    def remaining_cells(self):
        return self.cells - np.count_nonzero(self.revealed)

    def remaining_mines(self):
        return self.mines - np.count_nonzero(self.revealed == -1)

    def base_mine_probability(self):
        remaining = self.remaining_cells()
        if remaining <= 0:
            return 1.0
        return self.remaining_mines() / remaining

    def current_multiplier(self):
        return 1.18

    def roi(self):
        return (self.capital - self.initial_capital) / self.initial_capital

    # ==========================
    # CLICK
    # ==========================
    def register_click(self, is_diamond, index=None):

        if self.capital <= 0:
            return

        if index is not None:
            self.revealed[index] = 1 if is_diamond else -1

        p_mine = self.base_mine_probability()
        payout = self.current_multiplier()

        ev = RiskEngine.expected_value(p_mine, payout)
        kelly = RiskEngine.kelly_fraction(p_mine, payout)

        self.last_ev = ev
        self.last_kelly = kelly

        if ev <= 0:
            return

        vol = MetricsEngine.volatility(self.equity_curve)
        vol_adjust = RiskEngine.volatility_target(vol)

        stake = self.capital * kelly * vol_adjust

        if is_diamond:
            self.diamonds += 1
            self.capital += stake * payout
        else:
            self.capital -= stake

        self.equity_curve.append(self.capital)
        self._update_drawdown()

    # ==========================
    # MONTE CARLO
    # ==========================
    def monte_carlo(self, trials=5000):
        p_mine = self.base_mine_probability()
        payout = self.current_multiplier()
        steps = max(0, self.target - self.diamonds)

        return MonteCarloEngine.trajectory(
            self.capital, p_mine, payout, steps, trials
        )

    def monte_carlo_heatmap(self, trials=3000):
        return MonteCarloEngine.heatmap(
            self.revealed,
            self.size,
            self.remaining_mines(),
            trials
        )

    def monte_carlo_cell_risk(self, index, trials=2000):
        heat = self.monte_carlo_heatmap(trials)
        return heat[index // self.size][index % self.size]

    # ==========================
    # RIESGO
    # ==========================
    def _update_drawdown(self):
        self.peak = max(self.peak, self.capital)
        dd = (self.peak - self.capital) / self.peak
        self.max_drawdown = max(self.max_drawdown, dd)

    def sharpe(self):
        return MetricsEngine.sharpe_ratio(self.equity_curve)

    # ==========================
    # SAFE ZONE WRAPPER
    # ==========================
    def safest_cells_pro(self, trials=2000, top_n=7):
        return SafeZoneEngine.safest_cells_pro(self, trials, top_n)

    # ==========================
    # HEDGE WRAPPER
    # ==========================
    def hedge_state(self):
        return HedgeEngine.institutional_state(self)

    # ==========================
    # DECISION
    # ==========================
    def should_continue(self, profile="PRO"):

        if self.capital <= 0:
            return False

        dd_limits = {
            "SAFE": 0.10,
            "PRO": 0.20,
            "INST": 0.35
        }

        if self.max_drawdown > dd_limits.get(profile, 0.20):
            return False

        p_mine = self.base_mine_probability()
        ev = RiskEngine.expected_value(p_mine, self.current_multiplier())

        return ev > 0

    def should_stop_now(self):
        if self.capital <= 0:
            return True

        p_mine = self.base_mine_probability()
        ev = RiskEngine.expected_value(p_mine, self.current_multiplier())

        return ev <= 0