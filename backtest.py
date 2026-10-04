from datetime import datetime

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

    engine.load_data()
    engine.run_backtesting()
    engine.calculate_result()
    engine.calculate_statistics()

    chart = engine.show_chart()
    if chart is not None:
        chart.write_html("backtest_chart.html")


if __name__ == "__main__":
    main()
