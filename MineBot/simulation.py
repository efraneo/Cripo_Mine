# simulation.py

import random
from solver import DiamondSolver

def run_simulation(
    games=10_000,
    size=4,
    mines=3
):
    wins = 0
    ruins = 0

    for _ in range(games):
        solver = DiamondSolver(size, mines)
        cells = [-1]*mines + [1]*(size*size-mines)
        random.shuffle(cells)

        for cell in cells:
            if not solver.should_continue():
                break

            solver.register_click(cell == 1)
            if cell == -1:
                ruins += 1
                break

        if solver.diamonds >= solver.target:
            wins += 1

    return wins/games, ruins/games


if __name__ == "__main__":
    win_rate, ruin_rate = run_simulation()
    print(f"Win rate: {win_rate:.2%}")
    print(f"Ruin rate: {ruin_rate:.2%}")
