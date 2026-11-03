# parallel_montecarlo_engine.py

import numpy as np
import multiprocessing as mp


class ParallelMonteCarloEngine:

    @staticmethod
    def _simulate_chunk(args):
        capital, p_mine, payout, steps, trials = args

        # Vectorización total
        rand_matrix = np.random.rand(trials, steps)

        # Mina si random < p_mine
        mine_hits = rand_matrix < p_mine

        results = np.full(trials, capital, dtype=np.float64)

        for step in range(steps):
            wins = ~mine_hits[:, step]

            stake = results * 0.02  # stake fijo institucional 2%
            results[wins] += stake[wins] * payout
            results[~wins] -= stake[~wins]

        return results

    @staticmethod
    def trajectory(capital, p_mine, payout, steps, trials):

        if steps == 0:
            return capital, 1.0, capital

        cores = mp.cpu_count()
        chunk = trials // cores

        args = [
            (capital, p_mine, payout, steps, chunk)
            for _ in range(cores)
        ]

        with mp.Pool(cores) as pool:
            results = pool.map(
                ParallelMonteCarloEngine._simulate_chunk,
                args
            )

        final = np.concatenate(results)

        ev = np.mean(final)
        prob = np.mean(final > capital)
        cvar = np.percentile(final, 5)

        return ev, prob, cvar