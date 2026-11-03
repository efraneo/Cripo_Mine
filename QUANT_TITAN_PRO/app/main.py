import sys
import traceback
from app.bootstrap import bootstrap
from app.scheduler import Scheduler

def main():

    try:
        container = bootstrap()
        config = container["broker"].exchange.options
        config = bootstrap()["config"]
        scheduler_interval = (
            config["application"]
            .get(
                "scheduler_interval_seconds",
                60
            )
        )

        scheduler = Scheduler(
            orchestrator=container[
                "orchestrator"
            ],
            broker=container[
                "broker"
            ],
            interval_seconds=scheduler_interval
        )

        scheduler.start()

    except KeyboardInterrupt:

        print(
            "\n"
            "[SYSTEM] Bot detenido."
        )
        sys.exit(0)

    except Exception:

        print(
            "\n"
            "[FATAL ERROR]\n"
        )
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
