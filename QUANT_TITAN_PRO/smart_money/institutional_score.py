from datetime import datetime
from smart_money.smc_models import (
    InstitutionalScore
)

class InstitutionalScoreEngine:

    def __init__(
        self,
        config: dict
    ):

        smc = config["smart_money"]
        self.min_score = smc.get(
            "institutional_min_score",
            0.70
        )

    def calculate(
        self,
        symbol: str,
        timeframe: str,
        structure: dict,
        trend_score: float
    ) -> InstitutionalScore:

        liquidity_score = self._score_liquidity(
            structure["liquidity"]
        )

        bos_score = self._score_bos(
            structure["bos"]
        )

        choch_score = self._score_choch(
            structure["choch"]
        )

        order_block_score = (
            self._score_order_blocks(
                structure["order_blocks"]
            )
        )

        fvg_score = self._score_fvg(
            structure["fair_value_gaps"]
        )

        total = round(
            (
                liquidity_score * 0.15 +
                bos_score * 0.20 +
                choch_score * 0.20 +
                order_block_score * 0.20 +
                fvg_score * 0.10 +
                trend_score * 0.15
            ),
            3
        )

        return InstitutionalScore(
            symbol=symbol,
            timeframe=timeframe,
            liquidity_score=liquidity_score,
            bos_score=bos_score,
            choch_score=choch_score,
            order_block_score=order_block_score,
            fvg_score=fvg_score,
            trend_score=trend_score,
            total_score=total,
            created_at=datetime.utcnow()
        )

    def approved(
        self,
        score: InstitutionalScore
    ) -> bool:

        return (
            score.total_score
            >= self.min_score
        )

    def _score_liquidity(
        self,
        zones
    ) -> float:

        if not zones:
            return 0.0

        return round(
            min(
                1.0,
                len(zones) / 5
            ),
            3
        )

    def _score_bos(
        self,
        bos
    ) -> float:

        if bos is None:
            return 0.0
        return bos.strength

    def _score_choch(
        self,
        choch
    ) -> float:

        if choch is None:
            return 0.0
        return choch.confidence

    def _score_order_blocks(
        self,
        blocks
    ) -> float:

        if not blocks:
            return 0.0
        values = [
            block.strength
            for block in blocks
        ]
        return round(
            sum(values)
            / len(values),
            3
        )

    def _score_fvg(
        self,
        gaps
    ) -> float:

        if not gaps:
            return 0.0
        return round(

            min(
                1.0,
                len(gaps) / 4
            ),
            3
        )
