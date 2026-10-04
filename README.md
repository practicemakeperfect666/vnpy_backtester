# vnpy_back

从 [VeighNa/vnpy](https://github.com/vnpy/vnpy) 剥离出来的**独立回测引擎**。不依赖 vnpy 框架本体，策略接口与 vnpy 的 `CtaTemplate` 完全对齐——写在 `strategies/` 里的策略文件，几乎零改动就能拿到实盘（VeighNa Station）上跑。

- 数据源：PostgreSQL `kline_1min` 表（psycopg2 直连），tick 模式走 SQLite
- 回放：1min bar 逐根推送，支持 BAR / TICK 两种回放模式
- 撮合：限价单 + 本地条件单（stop order），含跳空保护、双触发检测、OCO
- 绩效：逐日盯市（daily mark-to-market）+ 完整统计指标 + Plotly 图表
- 优化：网格搜索（BF）+ 遗传算法（GA，DEAP）

---

## 目录结构

```
vnpy_back/
├── backtesting.py        # 回测引擎核心（BacktestingEngine + DailyResult + 数据加载 + 优化入口）
├── vnpy_core.py          # vnpy.trader 自包含子集（常量/对象/工具/设置/数据库/优化/策略模板）
├── backtest.py           # 单次回测入口脚本
├── optimize.py           # 参数优化入口脚本（BF + GA）
├── strategies/           # vnpy 格式策略（复制到实盘项目即可用）
└── backtest_chart.html   # 最近一次回测的 Plotly 结果图（由 show_chart 生成）
```

---

## 文件说明

### vnpy_core.py（约 2900 行）

从 vnpy.trader 合并而来的自包含子集，来源模块用注释分段标注：

| 段 | 来源 | 内容 |
| --- | --- | --- |
| constant | `vnpy.trader.constant` | `Direction` `Offset` `Status` `Product` `OrderType` `OptionType` `Exchange` `Currency` `Interval` 等枚举 |
| object | `vnpy.trader.object` | `BaseData` + `TickData` `BarData` `OrderData` `TradeData` `PositionData` `AccountData` `ContractData` 等数据类，以及各类 `*Request` |
| utility | `vnpy.trader.utility` | `extract_vt_symbol` / `round_to` / `floor_to` / `ceil_to` / `get_digits`，以及 `BarGenerator`、`ArrayManager`、`virtual` |
| setting | `vnpy.trader.setting` | `SETTINGS` 全局设置（默认 `database.name = "sqlite"`） |
| database | `vnpy.trader.database` | `BaseDatabase` 抽象 + `BarOverview` / `TickOverview` + `get_database()` |
| optimize | `vnpy.trader.optimize` | `OptimizationSetting` + `run_bf_optimization` / `run_ga_optimization`（基于 DEAP） |
| base / template | `vnpy_ctastrategy` | `StopOrder`、`StopOrderStatus`、`BacktestingMode`、`EngineType`，以及 `CtaTemplate` / `CtaSignal` / `TargetPosTemplate` |

### backtesting.py（约 1400 行）

`BacktestingEngine` 回测引擎 + `DailyResult` 逐日结果 + 数据加载函数 + 优化评估函数。

### backtest.py / optimize.py

两个最小入口脚本，展示完整调用链，改 `vt_symbol` / 起止日期 / 策略类即可复用。

---

## 策略接口（对齐 vnpy CtaTemplate）

策略继承 `CtaTemplate`，用类属性声明参数和变量：

```python
from vnpy_core import (
    CtaTemplate, StopOrder, TickData, BarData, TradeData, OrderData,
    BarGenerator, ArrayManager,
)

class DoubleMaStrategy(CtaTemplate):
    author = "..."

    fast_window: int = 10          # 参数（可在优化时被 setting 覆盖）
    slow_window: int = 20

    fast_ma0: float = 0.0          # 变量（回测时会被记录）

    parameters = ["fast_window", "slow_window"]
    variables = ["fast_ma0", "fast_ma1", "slow_ma0", "slow_ma1"]

    def on_init(self): ...         # 初始化：建 BarGenerator / ArrayManager，load_bar 回看
    def on_start(self): ...        # 启动
    def on_stop(self): ...         # 停止
    def on_tick(self, tick): ...   # tick 回放模式回调
    def on_bar(self, bar): ...     # bar 回放模式回调（主要逻辑写这里）
    def on_trade(self, trade): ...
    def on_order(self, order): ...
    def on_stop_order(self, stop_order): ...
```

交易下单方法（与 vnpy 一致）：

```python
self.buy(price, volume)      # 买入开仓（多）
self.sell(price, volume)     # 卖出平仓（平多）
self.short(price, volume)    # 卖出开仓（空）
self.cover(price, volume)    # 买入平仓（平空）
# 实际都走 send_order -> send_limit_order / send_stop_order(stop=True)
```

回看历史数据（指标预热，多周期合成）：

```python
self.load_bar(days=10)       # 回看 N 天历史 bar 用于预热
self.load_tick(days=1)       # 回看 N 天 tick
```

### BarGenerator（多周期合成）

支持按分钟 / 小时 / 日三种窗口把 1min bar（或 tick）合成为更大周期，通过 `on_window_bar` 回调推给策略。`multi_timeframe_strategy.py` 就是典型用法（15min RSI 判方向 + 1min MA 找入场）。

### ArrayManager（滚动窗口指标，talib 优先）

`size=100` 默认滚动 100 根，`update_bar(bar)` 后即可调用。内置约 50 个指标，全部支持 `array=True` 返回 ndarray：

均线类 `sma / ema / kama / wma`；动量类 `mom / roc / rocr / rocp / trix / cmo`；波动类 `std / atr / natr / trange`；通道类 `boll / keltner / donchian / aroon`；趋势类 `adx / adxr / dx / plus_di / minus_di / plus_dm / minus_dm`；摆动类 `rsi / cci / willr / stoch / ultosc`；量能类 `obv / mfi / ad / adosc`；以及 `macd / apo / ppo / sar / bop / aroonosc`。

---

## 回测流程

```python
engine = BacktestingEngine()
engine.set_parameters(
    vt_symbol="M2609.DCE",        # 品种.交易所
    interval="1m",                # Interval("1m")
    start=datetime(2025, 9, 15),
    end=datetime(2026, 8, 28),
    rate=0.00005,                 # 手续费率
    slippage=1,                   # 每手滑点
    size=10,                      # 合约乘数
    pricetick=1,                  # 最小变动价位
    capital=100_000,              # 初始资金
)
engine.add_strategy(DoubleMaStrategy, {})   # 第二个参数可覆盖 parameters
engine.load_data()               # 从 PG 读数据
engine.run_backtesting()         # on_init -> on_start -> 逐 bar 回放 -> on_stop
engine.calculate_result()        # 逐日盯市
engine.calculate_statistics()    # 绩效指标

chart = engine.show_chart()      # Plotly 4 子图
chart.write_html("backtest_chart.html")
```

运行：

```bash
python backtest.py     # 单次回测 + 输出图表
python optimize.py     # 网格搜索 + 遗传算法参数优化
```

### 参数优化

```python
setting = OptimizationSetting()
setting.set_target("sharpe_ratio")
setting.add_parameter("fast_window", 5, 15, 5)    # (名称, 起始, 结束, 步长)
setting.add_parameter("slow_window", 20, 40, 10)

engine.run_bf_optimization(setting)   # 网格穷举，多进程
engine.run_ga_optimization(setting)   # 遗传算法（DEAP）
```

---

## 数据源

bar 数据从 PostgreSQL 直连读取（`backtesting.py` 顶部 `PG_DSN`，本地库 `futures`）：

```sql
SELECT trade_time AT TIME ZONE 'Asia/Shanghai', open, high, low, close, vol, amount, oi
FROM kline_1min
WHERE contract_code = %s
  AND trade_time >= %s AND trade_time < %s
  AND open > 0 AND high > 0 AND low > 0 AND close > 0   -- 过滤无成交/脏数据
ORDER BY trade_time
```

- 加载按 30 天一批分批进行，输出进度条，单批结果用 `lru_cache` 缓存
- 交易所后缀映射：`SHFE→SHF, CZCE→ZCE, CFFEX→CFX, INE→INE, GFEX→GFE, DCE→DCE`
- `contract_code = f"{symbol}.{pg_ex}"`，如 `M2609.DCE`
- `interval` 非 1min 时用 `resample_bars` 合成（当前只实现了小时级 HOUR，其余原样返回）
- tick 模式走 `get_database()` → `vnpy_sqlite`

---

## 撮合逻辑（关键细节）

**限价单 `cross_limit_order`（每根 bar 检查一次）**

- 多头成交价取 `min(委托价, bar.low)`，空头取 `max(委托价, bar.high)`
- **跳空保护**：开盘价已越过委托价（`bar.open >= order.price` 于多头）时**不成交**，保守处理开盘缺口

**条件单 `cross_stop_order`**

- 触发后直接以触发价全部成交（等价于市价），生成对应的 OrderData + TradeData
- 同样有跳空保护（开盘跳空不触发）

**双触发检测 `_check_double_trigger`**

- 同一根 bar 上止盈（限价）+ 止损（条件）同时被触发时，只统计不撮合，计入 `double_trigger_count`，防止乐观成交

**OCO 处理**

- 任意委托成交后若仓位归零（`pos == 0`），自动清掉剩余挂单，避免同 bar 二次触发

**逐日盯市 `DailyResult.calculate_pnl`**

- `holding_pnl` = 昨结仓 × (今收 - 昨收) × size（隔夜持仓盯市）
- `trading_pnl` = 当日逐笔 × (今收 - 成交价) × size
- `net_pnl` = 交易盈亏 + 持仓盈亏 - 手续费 - 滑点
- 先按日期把 trade 归入 `daily_results`，再按日迭代计算

---

## 绩效指标（calculate_statistics）

总收益、年化收益、最大回撤（金额 + 百分比 + 持续天数）、收益回撤比、Sharpe、EWM Sharpe（半衰期平滑）、RGR Ratio（自定义综合风险指标，含偏度/峰度/CVaR 惩罚）、盈亏交易日数、手续费/滑点/成交额合计与日均。

图表 `show_chart` 输出 4 子图：资金曲线 / 回撤 / 每日盈亏 / 盈亏分布直方图。

---

## 内置策略示例（strategies/）

| 文件 | 策略 | 说明 |
| --- | --- | --- |
| double_ma_strategy.py | 双均线 | 快慢均线金叉/死叉 |
| atr_rsi_strategy.py | ATR+RSI | RSI 超买超卖 + ATR 移动止损 |
| boll_channel_strategy.py | 布林通道 | 布林带 + CCI 过滤 + ATR 止损 |
| dual_thrust_strategy.py | 双推力 | 日内高低点突破 |
| king_keltner_strategy.py | Keltner 通道 | 通道突破 + 移动止损 |
| multi_signal_strategy.py | 多信号组合 | RSI/CCI/MA 三信号投票（`TargetPosTemplate`） |
| multi_timeframe_strategy.py | 多周期 | 15min RSI 方向 + 1min MA 入场（`BarGenerator`） |
| turtle_signal_strategy.py | 海龟 | 唐奇安通道突破 |
| test_strategy.py | 测试 | 引擎功能自测 |

---

## 依赖

```
numpy  pandas  plotly  psycopg2  talib  tzlocal  deap  tqdm  vnpy_sqlite
```

- `talib`：指标计算（ArrayManager 优先走 talib，缺失时用 numpy fallback）
- `deap`：遗传算法优化
- `vnpy_sqlite`：tick 数据 SQLite 后端（bar 走 PG，不依赖它）

---

## 与完整 vnpy 的差异

- 只保留回测路径所需的最小代码，砍掉了事件引擎（EventEngine）、网关（Gateway）、RPC 等
- 撮合在引擎内同步完成，无事件循环；`on_order` / `on_trade` 由引擎直接回调
- `send_notification` / `sync_strategy_data` / `put_strategy_event` 等方法为空实现（占位）
- 数据源从 vnpy 的 `database` 抽象改为 PG 直连（bar）+ SQLite（tick）混合
