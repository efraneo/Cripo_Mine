from datetime import datetime

class StateManager:

    def __init__(self):
        self.reset()

    def reset(self):
        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.last_cycle = None
        self.market_regime = "UNKNOWN"
        self.started_at = datetime.utcnow()

    def register_trade(
        self,
        pnl: float
    ):

        self.total_trades += 1
        self.daily_pnl += pnl
        self.weekly_pnl += pnl
        self.last_cycle = datetime.utcnow()

        if pnl >= 0:
            self.wins += 1
        else:
            self.losses += 1

    def update_market_regime(
        self,
        regime: str
    ):
        self.market_regime = regime

    def snapshot(self):
        win_rate = 0.0

        if self.total_trades > 0:
            win_rate = (
                self.wins
                / self.total_trades
            ) * 100

        return {
            "daily_pnl": round(
                self.daily_pnl,
                2
            ),
            "weekly_pnl": round(
                self.weekly_pnl,
                2
            ),
            "wins": self.wins,
            "losses": self.losses,
            "total_trades": self.total_trades,
            "win_rate": round(
                win_rate,
                2
            ),
            "market_regime": self.market_regime,
            "started_at": self.started_at,
            "last_cycle": self.last_cycle
        }
