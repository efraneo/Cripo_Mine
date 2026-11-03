# safezone_engine.py
import numpy as np

class SafeZoneEngine:

    @staticmethod
    def safest_cells_pro(solver, trials=2000, top_n=7):

        heat = solver.monte_carlo_heatmap(trials)

        risks = []

        for i in range(solver.cells):
            if solver.revealed[i] == 0:
                r = heat[i // solver.size][i % solver.size]
                risks.append((i, r))

        risks.sort(key=lambda x: x[1])

        # Threshold dinámico según drawdown
        if solver.max_drawdown < 0.10:
            threshold = 0.35
        elif solver.max_drawdown < 0.20:
            threshold = 0.25
        else:
            threshold = 0.15

        filtered = [x for x in risks if x[1] <= threshold]

        return filtered[:top_n]