# vnpy_back

从 [VeighNa/vnpy](https://github.com/vnpy/vnpy) 剥离出来的**独立回测引擎**。不依赖 vnpy 框架本体，策略接口与 vnpy 的 `CtaTemplate` 完全对齐——写在 `strategies/` 里的策略文件，几乎零改动就能拿到实盘（VeighNa Station / 本项目 vnpy-domestic）上跑。

---

## 项目定位

这是把 vnpy 官方回测 demo（`vnpy_ctastrategy.backtesting`）单独剥离出来的精简版，只保留回测路径：

- **砍掉**：事件引擎（EventEngine）、网关（Gateway）、RPC、行情驱动等实盘链路
- **保留**：撮合引擎、逐日盯市、绩效统计、参数优化、策略模板
- **改动**：数据源从 vnpy 的 `database` 抽象改为 PostgreSQL 直连（bar）+ SQLite（tick）

目标只有一个：**回测结论能直接指导实盘**。所以回测的数据口径、合约处理、换月逻辑都要和实盘项目（vnpy-domestic）保持一致。

---

## 当前能力

| 能力 | 说明 |
| --- | --- |
| 数据回放 | 1min bar 逐根推送，支持 BAR / TICK 两种模式 |
| 撮合 | 限价单 + 本地条件单（stop order），含跳空保护、双触发检测、OCO |
| 绩效 | 逐日盯市 + 完整统计指标（收益/回撤/Sharpe/RGR 等）+ Plotly 4 子图 |
| 优化 | 网格搜索（BF）+ 遗传算法（GA，DEAP） |
| 策略 | 与 vnpy `CtaTemplate` 对齐，多周期合成（BarGenerator）、指标（ArrayManager，talib 优先） |

**当前是单合约回测**——指定一个 `vt_symbol`（如 `M2609.DCE`），回放该合约的数据。主力换月导致的跳空、跨合约的长期策略回测，见下方 Roadmap。

---

## 快速开始

```bash
python backtest.py     # 单次回测 + 输出 backtest_chart.html
python optimize.py     # BF 网格搜索 + GA 遗传算法参数优化
```

最小调用链（`backtest.py` 核心）：

```python
engine = BacktestingEngine()
engine.set_parameters(
    vt_symbol="M2609.DCE",        # 品种.交易所（标准 vnpy 格式）
    interval="1m",
    start=datetime(2025, 9, 15),
    end=datetime(2026, 8, 28),
    rate=0.00005,                 # 手续费率
    slippage=1,                   # 每手滑点
    size=10,                      # 合约乘数
    pricetick=1,                  # 最小变动价位
    capital=100_000,              # 初始资金
)
engine.add_strategy(DoubleMaStrategy, {})   # 第二参数可覆盖策略参数
engine.load_data()
engine.run_backtesting()
engine.calculate_result()
engine.calculate_statistics()
engine.show_chart().write_html("backtest_chart.html")
```

---

## 数据源与合约代码

bar 数据从 PostgreSQL 直连读取（`backtesting.py` 顶部 `PG_DSN`，本地库 `futures`，表 `kline_1min`）：

```sql
SELECT trade_time AT TIME ZONE 'Asia/Shanghai', open, high, low, close, vol, amount, oi
FROM kline_1min
WHERE contract_code = %s
  AND trade_time >= %s AND trade_time < %s
  AND open > 0 AND high > 0 AND low > 0 AND close > 0   -- 过滤无成交/脏数据
ORDER BY trade_time
```

**合约代码格式（重要坑）**：库里是「大写品种 + 映射后缀」，和标准 vnpy 格式不同：

| 你写的 `vt_symbol`（标准） | 库里实际 `contract_code` |
| --- | --- |
| `M2609.DCE` | `M2609.DCE` |
| `RB2701.SHFE` | `RB2701.SHF`（SHFE → SHF） |
| `C2701.DCE` | `C2701.DCE`（大写 C，不是小写 c） |
| `SR701.CZCE` | `SR701.ZCE`（CZCE → ZCE） |

引擎的 `EXCHANGE_SUFFIX` 映射会自动转换（`SHFE→SHF`、`CZCE→ZCE`、`CFFEX→CFX`、`INE→INE`、`GFEX→GFE`、`DCE→DCE`），所以你**直接写标准 vnpy 格式即可**，别手写成 `.SHF` 或小写品种。

加载按 30 天一批分批进行（带进度条），单批结果 `lru_cache` 缓存。

---

## 策略接口（对齐 vnpy CtaTemplate）

```python
from vnpy_core import CtaTemplate, BarData, BarGenerator, ArrayManager

class DoubleMaStrategy(CtaTemplate):
    fast_window: int = 10          # 参数（优化时可被 setting 覆盖）
    slow_window: int = 20

    parameters = ["fast_window", "slow_window"]
    variables = ["fast_ma0", "fast_ma1", "slow_ma0", "slow_ma1"]

    def on_init(self): ...         # 建 BarGenerator / ArrayManager，load_bar 预热
    def on_bar(self, bar): ...     # bar 回放模式主逻辑
    def on_tick(self, tick): ...   # tick 回放模式
```

下单方法（与 vnpy 一致）：`buy` / `sell` / `short` / `cover`，实际走 `send_order` → 限价单或条件单。

---

## Roadmap：连续复权拼合约

当前是单合约回测，**下一步**是支持主力连续合约 + 复权，实现长期策略在换月跳空下的正确回测：

1. **主力识别**：按持仓量/成交量确定每个时期的主力合约，口径对齐实盘 vnpy-domestic 的 `RolloverCtaEngine`（新浪主力识别）。
2. **换月拼接**：把不同时期的主力合约按时间无缝拼接成一条连续序列。
3. **复权处理**：对换月处的价格跳空做复权（前/后复权），消除跳空对技术指标（均线、通道）的干扰。
4. **与实盘换月一致**：回测的拼合约/复权规则要和实盘自动换月逻辑对齐，避免「回测一条线、实盘另一条线」。

---

## 数据一致性原则（回测 vs 实盘）

回测要有意义，必须和实盘共用同一套数据口径，否则回测再好看也是假的：

- **同源数据**：回测和实盘都读本地 PG `futures.kline_1min`，不各自造数。
- **代码一致**：合约代码、交易所后缀映射一致（见上表）。
- **时段一致**：交易时段过滤和实盘 `MyBarGenerator` 一致（非交易时段 tick 不合成 bar）。
- **换月一致**：复权拼合约的换月规则要和实盘 `RolloverCtaEngine` 的自动换月对齐。
- **脏数据一致**：无成交（close=0）、退市哨兵值等过滤规则两边一致。

做到这五点，回测统计（收益率、回撤、Sharpe）才是实盘的可信预期，而不是「回测一年翻倍、实盘一路亏」。

---

## 目录结构

```
vnpy_back/
├── backtesting.py        # 回测引擎核心（BacktestingEngine + DailyResult + 数据加载 + 优化）
├── vnpy_core.py          # vnpy.trader 自包含子集（常量/对象/工具/设置/数据库/优化/策略模板）
├── backtest.py           # 单次回测入口
├── optimize.py           # 参数优化入口（BF + GA）
├── strategies/
│   ├── __init__.py
│   └── double_ma_strategy.py   # 双均线示例策略（唯一提交的策略）
└── backtest_chart.html   # 回测结果图（生成产物，gitignore）
```

---

## 依赖

```
numpy  pandas  plotly  psycopg2  talib  tzlocal  deap  tqdm  vnpy_sqlite
```

- `talib`：指标计算（ArrayManager 优先 talib，缺失时 numpy fallback）
- `deap`：遗传算法优化
- `vnpy_sqlite`：tick 数据 SQLite 后端（bar 走 PG，不依赖它）
