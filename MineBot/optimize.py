# optimize.py

import numpy as np
from simulation import run_simulation

def optimize():
    best = None

    for ev in np.linspace(-0.5, 0.5, 21):
        for prob in np.linspace(0.4, 0.9, 11):
            win, ruin = run_simulation(
                games=5000,
                size=4,
                mines=3,
                ev_threshold=ev,
                prob_threshold=prob
            )

            roi = win - ruin * 10

            if best is None or roi > best["roi"]:
                best = {
                    "ev": ev,
                    "prob": prob,
                    "roi": roi,
                    "win": win,
                    "ruin": ruin
                }

    return best


if __name__ == "__main__":
    print(optimize())
