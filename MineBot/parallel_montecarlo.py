# parallel_montecarlo.py
import numpy as np

class ParallelMonteCarlo:

    @staticmethod
    def run(capital, p_mine, payout, steps, trials=20000):

        p_win = 1 - p_mine

        random_matrix = np.random.rand(trials, steps)

        wins = random_matrix < p_win

        capital_paths = np.full(trials, capital)

        for step in range(steps):
            active = capital_paths > 0
            capital_paths[active & wins[:, step]] *= payout
            capital_paths[active & ~wins[:, step]] *= (1 - p_mine)

        ev = capital_paths.mean()
        prob_success = np.mean(capital_paths > capital)
        cvar_95 = capital_paths[capital_paths <= np.percentile(capital_paths, 5)].mean()

        return ev, prob_success, cvar_95