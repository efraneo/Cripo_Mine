# regime_engine.py
class RegimeEngine:

    @staticmethod
    def classify(p_mine):

        if p_mine < 0.15:
            return "LOW_RISK"

        elif p_mine < 0.25:
            return "MEDIUM_RISK"

        elif p_mine < 0.35:
            return "HIGH_RISK"

        else:
            return "CRITICAL"

    @staticmethod
    def adjust_kelly(regime, base_fraction):

        modifiers = {
            "LOW_RISK": 1.0,
            "MEDIUM_RISK": 0.8,
            "HIGH_RISK": 0.5,
            "CRITICAL": 0.2
        }

        return base_fraction * modifiers.get(regime, 1.0)