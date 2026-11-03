from typing import Dict
from typing import List

class SymbolRanker:

    def __init__(self, config: dict):
        self.top_n = config.get(
            "top_opportunities",
            10
        )
        self.weights = {
            "trend": 0.30,
            "momentum": 0.25,
            "volume": 0.20,
            "volatility": 0.15,
            "liquidity": 0.10,
        }

    def rank(
        self,
        opportunities: List[Dict]
    ) -> List[Dict]:
        ranked = []
        for opportunity in opportunities:
            score = self._calculate_score(
                opportunity
            )
            opportunity[
                "institutional_score"
            ] = round(
                score,
                3
            )
            ranked.append(
                opportunity
            )
        ranked.sort(
            key=lambda x: x[
                "institutional_score"
            ],
            reverse=True
        )
        return ranked[
            : self.top_n
        ]

    def _calculate_score(
        self,
        data: Dict
    ) -> float:
        trend_score = data.get(
            "trend_score",
            0
        )

        momentum_score = data.get(
            "momentum_score",
            0
        )

        volume_score = data.get(
            "volume_score",
            0
        )

        volatility_score = data.get(
            "volatility_score",
            0
        )

        liquidity_score = data.get(
            "liquidity_score",
            0.8
        )

        score = (
            trend_score *
            self.weights["trend"]
            +
            momentum_score *
            self.weights["momentum"]
            +
            volume_score *
            self.weights["volume"]
            +
            volatility_score *
            self.weights["volatility"]
            +
            liquidity_score *
            self.weights["liquidity"]
        )
        return score

    def get_best_symbol(
        self,
        opportunities: List[Dict]
    ) -> Dict:

        ranked = self.rank(
            opportunities
        )

        if not ranked:
            return {}
        return ranked[0]
