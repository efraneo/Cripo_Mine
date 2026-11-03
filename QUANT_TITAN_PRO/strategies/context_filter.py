from typing import Dict
from typing import Optional
from strategies.models import CandleSignal

class ContextFilter:

    def __init__(self, config: dict):

        strategy = config["strategy"]
        self.min_confidence = strategy.get(
            "min_confidence",
            0.85
        )

        self.minimum_rr = strategy.get(
            "minimum_rr",
            2.0
        )

        self.allow_long = strategy.get(
            "allow_long",
            True
        )

        self.allow_short = strategy.get(
            "allow_short",
            True
        )

    def validate(
        self,
        signal: CandleSignal,
        trend_data: Dict,
        regime_data: Dict
    ) -> bool:

        if not self._validate_regime(
            regime_data
        ):
            return False

        if not self._validate_direction(
            signal
        ):
            return False

        if not self._validate_confidence(
            signal
        ):
            return False

        if not self._validate_trend(
            signal,
            trend_data
        ):
            return False

        if not self._validate_rr(
            signal
        ):
            return False
        return True

    def rejection_reason(
        self,
        signal: CandleSignal,
        trend_data: Dict,
        regime_data: Dict
    ) -> Optional[str]:
        checks = [
            (
                self._validate_regime(
                    regime_data
                ),
                "Régimen inválido"
            ),
            (
                self._validate_direction(
                    signal
                ),
                "Dirección deshabilitada"
            ),
            (
                self._validate_confidence(
                    signal
                ),
                "Confianza insuficiente"
            ),
            (
                self._validate_trend(
                    signal,
                    trend_data
                ),
                "Tendencia incompatible"
            ),
            (
                self._validate_rr(
                    signal
                ),
                "Risk / Reward insuficiente"
            )
        ]

        for passed, reason in checks:

            if not passed:
                return reason
        return None

    def _validate_regime(
        self,
        regime_data: Dict
    ) -> bool:
        return regime_data.get(
            "can_trade",
            False
        )

    def _validate_direction(
        self,
        signal: CandleSignal
    ) -> bool:

        if (
            signal.side == "BUY"
            and not self.allow_long
        ):
            return False

        if (
            signal.side == "SELL"
            and not self.allow_short
        ):
            return False
        return True

    def _validate_confidence(
        self,
        signal: CandleSignal
    ) -> bool:
        return (
            signal.confidence
            >=
            self.min_confidence
        )

    def _validate_trend(
        self,
        signal: CandleSignal,
        trend_data: Dict
    ) -> bool:
        trend = trend_data.get(
            "trend",
            "RANGE"
        )

        if signal.side == "BUY":
            return trend in [
                "BULL",
                "STRONG_BULL"
            ]

        if signal.side == "SELL":
            return trend in [
                "BEAR",
                "STRONG_BEAR"
            ]
        return False

    def _validate_rr(
        self,
        signal: CandleSignal
    ) -> bool:

        if signal.take_profit <= 0:
            return False

        risk = abs(
            signal.entry
            - signal.stop_loss
        )

        reward = abs(
            signal.take_profit
            - signal.entry
        )

        if risk == 0:
            return False
        rr = reward / risk
        return rr >= self.minimum_rr
