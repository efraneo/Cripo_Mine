# risk_engine.py
import numpy as np

class RiskEngine:

    @staticmethod
    def expected_value(p_mine, payout):
        p_win = 1 - p_mine
        return p_win * payout - p_mine

    @staticmethod
    def kelly_fraction(p_mine, payout, fraction=0.25):
        p = 1 - p_mine
        b = payout
        q = 1 - p

        if b <= 0:
            return 0.0

        f_star = (b * p - q) / b
        f_star = max(0.0, f_star)

        return fraction * f_star

    @staticmethod
    def volatility_target(current_vol, target_vol=0.20):
        if current_vol == 0:
            return 1.0
        return min(1.0, target_vol / current_vol)