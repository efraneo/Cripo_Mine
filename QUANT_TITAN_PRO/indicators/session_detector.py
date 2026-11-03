from datetime import datetime, timezone

class SessionDetector:

    def __init__(self):
        self.sessions = {
            "ASIA": (0, 8),
            "LONDON": (7, 16),
            "NEW_YORK": (13, 22)
        }

    def current_session(
        self,
        timestamp: datetime | None = None
    ) -> str:

        if timestamp is None:
            timestamp = datetime.now(
                timezone.utc
            )
        hour = timestamp.hour
        active = []

        for name, (
            start,
            end
        ) in self.sessions.items():

            if start <= hour < end:
                active.append(
                    name
                )

        if len(active) == 0:
            return "CLOSED"

        if len(active) == 1:
            return active[0]

        return "_".join(
            active
        )

    def is_high_liquidity(
        self,
        timestamp: datetime | None = None
    ) -> bool:

        session = self.current_session(
            timestamp
        )

        return session in {
            "LONDON",
            "NEW_YORK",
            "LONDON_NEW_YORK"
        }
