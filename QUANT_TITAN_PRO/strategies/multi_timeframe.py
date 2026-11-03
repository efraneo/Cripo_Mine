class MultiTimeframeAnalyzer:

    def __init__(
        self,
        config: dict
    ):

        mtf = config.get(
            "multi_timeframe",
            {}
        )

        self.primary = mtf.get(
            "primary",
            "15m"
        )

        self.confirmation = mtf.get(
            "confirmation",
            [
                "1h",
                "4h"
            ]
        )

    def validate(
        self,
        signals: list
    ) -> bool:

        if not signals:
            return False
        sides = {
            signal.side
            for signal in signals
        }

        return len(
            sides
        ) == 1
