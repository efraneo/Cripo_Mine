from dataclasses import dataclass

@dataclass
class RiskDecision:
    approved: bool
    reason: str
    risk_percent: float
