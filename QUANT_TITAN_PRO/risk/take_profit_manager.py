from dataclasses import dataclass

@dataclass
class TakeProfitLevels:
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    take_profit_4: float
    expected_rr: float

class TakeProfitManager:

    def __init__(
        self,
        config: dict
    ):

        indicators = config.get(
            "indicators",
            {}
        )

        self.sl_multiplier = indicators.get(
            "atr_stop_multiplier",
            1.5
        )

        self.tp1_multiplier = indicators.get(
            "atr_tp1_multiplier",
            1.5
        )

        self.tp2_multiplier = indicators.get(
            "atr_tp2_multiplier",
            3.0
        )

    def build(
        self,
        side: str,
        entry: float,
        atr: float,
        liquidity_target: float | None = None,
        order_block_target: float | None = None
    ) -> TakeProfitLevels:

        if side == "BUY":
            stop_loss = (
                entry
                - atr * self.sl_multiplier
            )

            tp1 = (
                entry
                + atr * self.tp1_multiplier
            )

            tp2 = (
                entry
                + atr * self.tp2_multiplier
            )

        else:

            stop_loss = (
                entry
                + atr * self.sl_multiplier
            )

            tp1 = (
                entry
                - atr * self.tp1_multiplier
            )

            tp2 = (
                entry
                - atr * self.tp2_multiplier
            )

        tp3 = (
            liquidity_target
            if liquidity_target
            is not None
            else tp2
        )

        tp4 = (
            order_block_target
            if order_block_target
            is not None
            else tp3
        )

        risk = abs(
            entry - stop_loss
        )

        reward = abs(
            tp2 - entry
        )

        rr = round(
            reward / risk,
            2
        )

        return TakeProfitLevels(
            stop_loss=round(
                stop_loss,
                8
            ),

            take_profit_1=round(
                tp1,
                8
            ),

            take_profit_2=round(
                tp2,
                8
            ),

            take_profit_3=round(
                tp3,
                8
            ),

            take_profit_4=round(
                tp4,
                8
            ),

            expected_rr=rr
        )
