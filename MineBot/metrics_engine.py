# metrics_engine.py
import numpy as np

class MetricsEngine:

    @staticmethod
    def sharpe_ratio(equity_curve):
        returns = np.diff(equity_curve) / equity_curve[:-1]
        if len(returns) < 2:
            return 0.0
        if returns.std() == 0:
            return 0.0
        return returns.mean() / returns.std()

    @staticmethod
    def risk_of_ruin(equity_curve):
        return np.mean(np.array(equity_curve) <= 0)

    @staticmethod
    def volatility(equity_curve):
        returns = np.diff(equity_curve) / equity_curve[:-1]
        if len(returns) == 0:
            return 0.0
        return np.std(returns)