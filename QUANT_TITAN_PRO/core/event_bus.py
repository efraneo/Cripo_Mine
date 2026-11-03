from collections import defaultdict
from typing import Callable
from typing import Dict
from typing import List

class EventBus:

    def __init__(self):
        self.subscribers = defaultdict(
            list
        )

    def subscribe(
        self,
        event_name: str,
        callback: Callable
    ):

        self.subscribers[
            event_name
        ].append(
            callback
        )

    def publish(
        self,
        event_name: str,
        payload: Dict
    ):

        listeners = self.subscribers.get(
            event_name,
            []
        )

        for callback in listeners:
            try:
                callback(
                    payload
                )

            except Exception as error:
                print(
                    f"[EVENT BUS] "
                    f"{event_name}: "
                    f"{error}"
                )
