from typing import Dict
from typing import List

import numpy as np
import pandas as pd

class CorrelationFilter:

    def __init__(self, config: dict):
        self.max_correlation = config.get(
            "max_correlation",
            0.70
        )

        self.max_positions = config.get(
            "max_open_positions",
            3
        )

    def filter_candidates(
        self,
        candidates: List[Dict],
        price_history: Dict[str, pd.DataFrame]
    ) -> List[Dict]:

        if not candidates:
            return []
        selected = []

        for candidate in candidates:
            symbol = candidate["symbol"]

            if not selected:
                selected.append(candidate)
                continue

            if self._is_diversified(
                symbol,
                selected,
                price_history
            ):
                selected.append(candidate)

            if len(selected) >= self.max_positions:
                break
        return selected

    def correlation_matrix(
        self,
        price_history: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        data = {}

        for symbol, df in price_history.items():
            data[symbol] = (
                df["close"]
                .pct_change()
            )

        frame = pd.DataFrame(data)
        return frame.corr()

    def _is_diversified(
        self,
        symbol: str,
        selected: List[Dict],
        price_history: Dict[str, pd.DataFrame]
    ) -> bool:

        if symbol not in price_history:
            return False
        current_returns = (
            price_history[symbol]
            ["close"]
            .pct_change()
            .dropna()
        )

        for asset in selected:
            selected_symbol = asset["symbol"]

            if selected_symbol not in price_history:
                continue
            selected_returns = (
                price_history[selected_symbol]
                ["close"]
                .pct_change()
                .dropna()
            )

            correlation = self._safe_correlation(
                current_returns,
                selected_returns
            )

            if abs(correlation) > self.max_correlation:
                return False
        return True

    def _safe_correlation(
        self,
        series_a: pd.Series,
        series_b: pd.Series
    ) -> float:

        size = min(
            len(series_a),
            len(series_b)
        )

        if size < 30:
            return 0.0
        a = series_a.tail(size)
        b = series_b.tail(size)

        correlation = np.corrcoef(
            a,
            b
        )[0][1]

        if np.isnan(correlation):
            return 0.0
        return float(correlation)
