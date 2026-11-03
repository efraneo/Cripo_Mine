# autoplay_engine.py

class AutoPlayEngine:

    @staticmethod
    def execute(solver, hidden, safe_moves):

        if not safe_moves:
            return None

        best_move = safe_moves[0][0]

        is_diamond = hidden[best_move] == 1

        solver.register_click(is_diamond, index=best_move)

        return best_move