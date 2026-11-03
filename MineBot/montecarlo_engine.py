# montecarlo_engine.py
import numpy as np
import multiprocessing as mp


class MonteCarloEngine:

    # ==========================================================
    # CORE VECTORIZED TRAJECTORY
    # ==========================================================
    @staticmethod
    def _vectorized_simulation(capital, p_mine, payout, steps, trials):
        """
        Simulación completamente vectorizada sin loops internos.
        """

        # Matriz de eventos (True = diamond, False = mine)
        rand = np.random.rand(trials, steps)
        wins = rand > p_mine

        # Detectar primer fallo por fila
        first_mine_index = np.argmax(~wins, axis=1)

        # Si nunca pierde, argmax devuelve 0 → corregimos
        no_mine_mask = wins.all(axis=1)
        first_mine_index[no_mine_mask] = steps

        # Número de wins antes del fallo
        win_counts = first_mine_index

        # Capital final vectorizado
        results = capital * (payout ** win_counts)

        return results

    # ==========================================================
    # PARALLEL WORKER
    # ==========================================================
    @staticmethod
    def _worker(args):
        capital, p_mine, payout, steps, trials = args
        return MonteCarloEngine._vectorized_simulation(
            capital, p_mine, payout, steps, trials
        )

    # ==========================================================
    # PUBLIC TRAJECTORY (PARALLEL)
    # ==========================================================
    @staticmethod
    def trajectory(
        capital,
        p_mine,
        payout,
        steps,
        trials=20000,
        n_jobs=None
    ):
        """
        Monte Carlo paralelo tipo hedge fund.
        """

        if n_jobs is None:
            n_jobs = mp.cpu_count()

        trials_per_worker = trials // n_jobs
        remainder = trials % n_jobs

        args = [
            (capital, p_mine, payout, steps, trials_per_worker)
            for _ in range(n_jobs)
        ]

        if remainder > 0:
            args.append((capital, p_mine, payout, steps, remainder))

        with mp.Pool(n_jobs) as pool:
            results = pool.map(MonteCarloEngine._worker, args)

        results = np.concatenate(results)

        # ============================
        # MÉTRICAS HEDGE FUND
        # ============================

        ev = results.mean()
        median = np.median(results)
        std = results.std()

        p5 = np.percentile(results, 5)
        p1 = np.percentile(results, 1)

        cvar_95 = results[results <= p5].mean()
        prob_success = np.mean(results > capital)
        prob_ruin = np.mean(results <= capital * 0.5)

        return {
            "EV": ev,
            "median": median,
            "std": std,
            "p5": p5,
            "p1": p1,
            "cvar_95": cvar_95,
            "prob_success": prob_success,
            "prob_ruin_50pct": prob_ruin,
        }

    # ==========================================================
    # VECTORIZED HEATMAP
    # ==========================================================
    @staticmethod
    def heatmap(revealed, size, remaining_mines, trials=10000):
        """
        Heatmap Monte Carlo vectorizado sin loops Python.
        """

        cells = size * size
        heat = np.zeros(cells)

        hidden = np.where(revealed == 0)[0]

        if len(hidden) == 0:
            return heat.reshape(size, size)

        # Simulaciones vectorizadas
        draws = np.array([
            np.random.choice(hidden, remaining_mines, replace=False)
            for _ in range(trials)
        ])

        # Conteo eficiente
        flat_draws = draws.flatten()
        counts = np.bincount(flat_draws, minlength=cells)

        heat = counts / trials

        # Ajustes por estado conocido
        heat[revealed == -1] = 1.0
        heat[revealed == 1] = 0.0

        return heat.reshape(size, size)