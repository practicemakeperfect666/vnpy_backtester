from datetime import datetime

from vnpy_core import OptimizationSetting
from backtesting import BacktestingEngine
from strategies.double_ma_strategy import DoubleMaStrategy


def main():
    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol="M2609.DCE",
        interval="1m",
        start=datetime(2025, 9, 15),
        end=datetime(2026, 8, 28),
        rate=0.00005,
        slippage=1,
        size=10,
        pricetick=1,
        capital=100_000,
    )
    engine.add_strategy(DoubleMaStrategy, {})

    setting = OptimizationSetting()
    setting.set_target("sharpe_ratio")
    setting.add_parameter("fast_window", 5, 15, 5)
    setting.add_parameter("slow_window", 20, 40, 10)

    engine.run_ga_optimization(setting)
    engine.run_bf_optimization(setting)


if __name__ == "__main__":
    main()
