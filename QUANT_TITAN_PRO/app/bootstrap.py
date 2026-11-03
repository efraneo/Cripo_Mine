import yaml
from app.dependency_container import (
    DependencyContainer
)

def load_config(
    path: str = "config/settings.yaml"
) -> dict:

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:
        return yaml.safe_load(
            file
        )


def register_events(
    container: dict
):

    event_bus = container[
        "event_bus"
    ]

    event_bus.subscribe(
        "signal_detected",
        _on_signal_detected
    )

    event_bus.subscribe(
        "execution_result",
        _on_execution_result
    )

def bootstrap():
    config = load_config()
    container = DependencyContainer(
        config
    ).build()

    register_events(
        container
    )
    return container

def _on_signal_detected(
    payload: dict
):

    print(
        "[SIGNAL]",
        payload
    )

def _on_execution_result(
    payload: dict
):

    print(
        "[EXECUTION]",
        payload
    )
