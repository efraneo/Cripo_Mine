import copy

class StrategyOptimizer:

    def __init__(
        self,
        strategy_factory,
        backtest_engine_class,
        metrics_class
    ):

        self.strategy_factory = (
            strategy_factory
        )

        self.backtest_engine_class = (
            backtest_engine_class
        )

        self.metrics_class = (
            metrics_class
        )

    def optimize(
        self,
        base_config: dict,
        parameter_grid: dict,
        symbol: str,
        timeframe: str,
        dataframe
    ):

        results = []
        combinations = self._build_grid(
            parameter_grid
        )

        for params in combinations:
            config = copy.deepcopy(
                base_config
            )
            self._apply_params(
                config,
                params
            )
            strategy = (
                self.strategy_factory(
                    config
                )
            )
            engine = (
                self.backtest_engine_class(
                    strategy
                )
            )
            metrics_engine = (
                self.metrics_class()
            )
            output = engine.run(
                symbol,
                timeframe,
                dataframe
            )
            metrics = (
                metrics_engine
                .calculate(
                    output["trades"]
                )
            )
            results.append(
                {
                    "params": params,
                    "metrics": metrics
                }
            )

        results.sort(
            key=lambda x:
            x["metrics"].get(
                "profit_factor",
                0
            ),
            reverse=True
        )
        return results

    def _build_grid(
        self,
        grid
    ):

        keys = list(
            grid.keys()
        )

        result = [
            {}
        ]

        for key in keys:
            temp = []
            for partial in result:
                for value in grid[key]:
                    item = dict(
                        partial
                    )
                    item[key] = value
                    temp.append(
                        item
                    )
            result = temp
        return result

    def _apply_params(
        self,
        config,
        params
    ):

        for key, value in params.items():
            section, option = key.split(
                "."
            )
            config[section][
                option
            ] = value
