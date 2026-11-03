class SignalRouter:

    def __init__(
        self,
        portfolio_manager,
        risk_manager
    ):

        self.portfolio_manager = (
            portfolio_manager
        )

        self.risk_manager = (
            risk_manager
        )

    def route(
        self,
        ranked_signals,
        open_positions
    ):

        accepted = []

        for item in ranked_signals:
            signal = item[
                "signal"
            ]
            symbol = signal.symbol

            allowed = (
                self.portfolio_manager
                .can_open(
                    open_positions,
                    symbol
                )
            )

            if not allowed:
                continue

            decision = (
                self.risk_manager
                .evaluate(
                    signal
                )
            )

            if not decision.approved:
                continue

            accepted.append(
                signal
            )
        return accepted
