# hedge_engine.py

class HedgeEngine:

    @staticmethod
    def institutional_state(solver):

        if solver.capital <= 0:
            return "STOP"

        if solver.max_drawdown > 0.30:
            return "HARD_STOP"

        if solver.max_drawdown > 0.20:
            return "REDUCE"

        if solver.roi() > 0.50:
            return "TAKE_PROFIT"

        return "CONTINUE"