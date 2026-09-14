# 数据字典 SOURCES

> 本文件由 `inv.sources.generate()` 自动生成，请勿手工编辑。
> 最后生成：2026-09-11 11:57
> 新增数据序列请在 `src/inv/config.py` 中登记，然后运行 `make update`。

行数/起止日期反映 `data/raw/` 下的实际落盘状态。

## FRED（圣路易斯联储）

来源：<https://fred.stlouisfed.org>　需免费 API Key（配置于 `.env`）

落盘位置：`data/raw/fred/<字段名>.csv`
最早可证 vintage：`data/raw/fred_first_release/<字段名>.csv`，保留观测期、该 vintage 的值与可用日。

| 字段名 | FRED ID | 说明 | 单位 | 原频率 | 行数 | 起始 | 最新 |
|---|---|---|---|---|---:|---|---|
| `ffr_effective` | [DFF](https://fred.stlouisfed.org/series/DFF) | 有效联邦基金利率 | % | 日 | 13388 | 1990-01-01 | 2026-08-27 |
| `ffr_target_upper` | [DFEDTARU](https://fred.stlouisfed.org/series/DFEDTARU) | 联邦基金目标区间上限 | % | 日 | 6465 | 2008-12-16 | 2026-08-28 |
| `ffr_target_lower` | [DFEDTARL](https://fred.stlouisfed.org/series/DFEDTARL) | 联邦基金目标区间下限 | % | 日 | 6465 | 2008-12-16 | 2026-08-28 |
| `iorb` | [IORB](https://fred.stlouisfed.org/series/IORB) | 准备金余额利率 | % | 日 | 1860 | 2021-07-29 | 2026-08-31 |
| `on_rrp` | [RRPONTSYD](https://fred.stlouisfed.org/series/RRPONTSYD) | 隔夜逆回购用量 | 十亿美元 | 日 | 3315 | 2003-02-07 | 2026-08-28 |
| `fed_assets` | [WALCL](https://fred.stlouisfed.org/series/WALCL) | 美联储总资产 | 百万美元 | 周 | 1237 | 2002-12-18 | 2026-08-26 |
| `ust2y` | [DGS2](https://fred.stlouisfed.org/series/DGS2) | 2年期国债收益率 | % | 日 | 9170 | 1990-01-02 | 2026-08-27 |
| `ust10y` | [DGS10](https://fred.stlouisfed.org/series/DGS10) | 10年期国债收益率 | % | 日 | 9170 | 1990-01-02 | 2026-08-27 |
| `ust30y` | [DGS30](https://fred.stlouisfed.org/series/DGS30) | 30年期国债收益率 | % | 日 | 9170 | 1990-01-02 | 2026-08-27 |
| `curve_10y2y` | [T10Y2Y](https://fred.stlouisfed.org/series/T10Y2Y) | 10Y-2Y 期限利差 | % | 日 | 9171 | 1990-01-02 | 2026-08-28 |
| `curve_10y3m` | [T10Y3M](https://fred.stlouisfed.org/series/T10Y3M) | 10Y-3M 期限利差 | % | 日 | 9171 | 1990-01-02 | 2026-08-28 |
| `real10y` | [DFII10](https://fred.stlouisfed.org/series/DFII10) | 10年期 TIPS 实际利率 | % | 日 | 5918 | 2003-01-02 | 2026-08-27 |
| `real5y` | [DFII5](https://fred.stlouisfed.org/series/DFII5) | 5年期 TIPS 实际利率 | % | 日 | 5918 | 2003-01-02 | 2026-08-27 |
| `breakeven10y` | [T10YIE](https://fred.stlouisfed.org/series/T10YIE) | 10年盈亏平衡通胀预期 | % | 日 | 5919 | 2003-01-02 | 2026-08-28 |
| `fwd5y5y` | [T5YIFR](https://fred.stlouisfed.org/series/T5YIFR) | 5年后5年远期通胀预期 | % | 日 | 5919 | 2003-01-02 | 2026-08-28 |
| `usd_broad` | [DTWEXBGS](https://fred.stlouisfed.org/series/DTWEXBGS) | 广义贸易加权美元指数 | 指数 | 日 | 5174 | 2006-01-02 | 2026-08-21 |
| `usd_afe` | [DTWEXAFEGS](https://fred.stlouisfed.org/series/DTWEXAFEGS) | 发达经济体美元指数 | 指数 | 日 | 5174 | 2006-01-02 | 2026-08-21 |
| `cpi` | [CPIAUCSL](https://fred.stlouisfed.org/series/CPIAUCSL) | CPI 城市消费者（季调） | 指数 | 月 | 438 | 1990-01-01 | 2026-07-01 |
| `cpi_core` | [CPILFESL](https://fred.stlouisfed.org/series/CPILFESL) | 核心 CPI（季调） | 指数 | 月 | 438 | 1990-01-01 | 2026-07-01 |
| `pce_core` | [PCEPILFE](https://fred.stlouisfed.org/series/PCEPILFE) | 核心 PCE 物价指数 | 指数 | 月 | 439 | 1990-01-01 | 2026-07-01 |
| `unemployment` | [UNRATE](https://fred.stlouisfed.org/series/UNRATE) | 失业率 | % | 月 | 438 | 1990-01-01 | 2026-07-01 |
| `nonfarm_payroll` | [PAYEMS](https://fred.stlouisfed.org/series/PAYEMS) | 非农就业人数 | 千人 | 月 | 439 | 1990-01-01 | 2026-07-01 |
| `initial_claims` | [ICSA](https://fred.stlouisfed.org/series/ICSA) | 初次失业申请（季调） | 人 | 周 | 1912 | 1990-01-06 | 2026-08-22 |
| `gdp_real` | [GDPC1](https://fred.stlouisfed.org/series/GDPC1) | 实际 GDP | 十亿美元(2017) | 季 | 146 | 1990-01-01 | 2026-04-01 |
| `hy_spread` | [BAMLH0A0HYM2](https://fred.stlouisfed.org/series/BAMLH0A0HYM2) | 美国高收益债信用利差 | % | 日 | 803 | 2023-08-07 | 2026-08-27 |
| `nfci` | [NFCI](https://fred.stlouisfed.org/series/NFCI) | 芝加哥联储全国金融状况指数 | 指数 | 周 | 1912 | 1990-01-05 | 2026-08-21 |
| `wti` | [DCOILWTICO](https://fred.stlouisfed.org/series/DCOILWTICO) | WTI 原油现货价 | 美元/桶 | 日 | 9212 | 1990-01-02 | 2026-08-25 |
| `usdcny` | [DEXCHUS](https://fred.stlouisfed.org/series/DEXCHUS) | 美元兑人民币 | CNY/USD | 日 | 9134 | 1990-01-02 | 2026-08-21 |

## Yahoo Finance

来源：`yfinance` 库（非官方接口，已实现重试与失败保护）

落盘位置：`data/raw/market/<字段名>.csv`，保留 OHLCV 全字段；
派生数据集默认取 `adj_close`（无则取 `close`）。

| 字段名 | Ticker | 说明 | 资产类别 | 行数 | 起始 | 最新 |
|---|---|---|---|---:|---|---|
| `gold` | `GC=F` | COMEX 黄金连续期货 | metal | 6508 | 2000-08-30 | 2026-08-07 |
| `silver` | `SI=F` | COMEX 白银连续期货 | metal | 6510 | 2000-08-30 | 2026-08-07 |
| `gld` | `GLD` | SPDR 黄金 ETF | metal | 5462 | 2004-11-18 | 2026-08-06 |
| `dxy` | `DX-Y.NYB` | 美元指数 DXY | fx | 9326 | 1990-01-01 | 2026-08-07 |
| `eurusd` | `EURUSD=X` | 欧元兑美元 | fx | 5886 | 2003-12-01 | 2026-08-07 |
| `usdjpy` | `USDJPY=X` | 美元兑日元 | fx | 7720 | 1996-10-30 | 2026-08-07 |
| `usdcny_yf` | `USDCNY=X` | 美元兑人民币(离岸参考) | fx | 6288 | 2001-06-25 | 2026-08-07 |
| `tlt` | `TLT` | 20年+ 美国国债 ETF | bond | 6044 | 2002-07-30 | 2026-08-06 |
| `ief` | `IEF` | 7-10年 美国国债 ETF | bond | 6044 | 2002-07-30 | 2026-08-06 |
| `tip` | `TIP` | 通胀保值债券 ETF | bond | 5702 | 2003-12-05 | 2026-08-06 |
| `lqd` | `LQD` | 投资级公司债 ETF | bond | 6044 | 2002-07-30 | 2026-08-06 |
| `hyg` | `HYG` | 高收益债 ETF | bond | 4862 | 2007-04-11 | 2026-08-06 |
| `spx` | `^GSPC` | 标普500指数 | equity_us | 9216 | 1990-01-02 | 2026-08-06 |
| `ndx` | `^NDX` | 纳斯达克100指数 | equity_us | 9216 | 1990-01-02 | 2026-08-06 |
| `dji` | `^DJI` | 道琼斯工业指数 | equity_us | 8710 | 1992-01-02 | 2026-08-06 |
| `rut` | `^RUT` | 罗素2000指数 | equity_us | 9216 | 1990-01-02 | 2026-08-06 |
| `vix` | `^VIX` | VIX 波动率指数 | equity_us | 9218 | 1990-01-02 | 2026-08-07 |
| `spy` | `SPY` | 标普500 ETF | equity_us | 8437 | 1993-01-29 | 2026-08-06 |
| `qqq` | `QQQ` | 纳斯达克100 ETF | equity_us | 6895 | 1999-03-10 | 2026-08-06 |
| `wti_yf` | `CL=F` | WTI 原油期货 | commodity | 6517 | 2000-08-23 | 2026-08-07 |
| `copper` | `HG=F` | COMEX 铜期货 | commodity | 6513 | 2000-08-30 | 2026-08-07 |
| `sse_yf` | `000001.SS` | 上证指数(yf备用) | equity_cn | 7050 | 1997-07-02 | 2026-08-07 |
| `csi300_yf` | `000300.SS` | 沪深300(yf备用) | equity_cn | 1299 | 2021-03-11 | 2026-08-07 |
| `hsi` | `^HSI` | 恒生指数 | equity_cn | 9031 | 1990-01-02 | 2026-08-07 |

## A股指数

主通道：AkShare（`stock_zh_index_daily`，无需 Key）
备通道：yfinance（主通道失败时自动降级）

落盘位置：`data/raw/cn/<字段名>.csv`

| 字段名 | 代码 | 说明 | 行数 | 起始 | 最新 |
|---|---|---|---:|---|---|
| `sse` | `sh000001` | 上证指数 | 8699 | 1990-12-19 | 2026-08-07 |
| `csi300` | `sh000300` | 沪深300 | 5966 | 2002-01-04 | 2026-08-07 |
| `csi500` | `sh000905` | 中证500 | 5245 | 2005-01-04 | 2026-08-07 |
| `chinext` | `sz399006` | 创业板指 | 3930 | 2010-06-01 | 2026-08-06 |
| `star50` | `sh000688` | 科创50 | 1599 | 2020-01-02 | 2026-08-07 |

## 派生字段命名约定

由 `inv.dataset.add_derived()` 生成，存于 `data/processed/`（不进版本库，可随时重建）。
默认视图按最早可证可用日对齐；`observation` 文件仅用于明确的描述性观测期分析。

| 前缀/模式 | 含义 | 计算方式 | 示例 |
|---|---|---|---|
| `ret_<x>` | 对数收益率 | `ln(x_t / x_{t-1})` | `ret_gold` |
| `d_<x>` | 一阶差分 | `x_t - x_{t-1}`，单位=百分点 | `d_real10y` |
| `ratio_<a>_<b>` | 比价 | `a / b` | `ratio_gold_silver` |
| `<x>_implied` | 推算值 | 见 `dataset.py` 注释 | `real10y_implied` |

**为什么价格用对数收益、利率用差分**：

- 价格的变化幅度应以比例衡量，且对数收益可跨期相加，便于重采样。
- 利率本身已是百分比，从 2% 到 3% 是「上升 1 个百分点」，而非「上涨 50%」，
  因此用绝对差分才有经济含义。

## 派生数据集

| 文件 | 频率 | 重采样规则 |
|---|---|---|
| `processed/macro_daily.csv` | SPX 实际交易日 | 最早可证可用日后的下一交易时段生效，按频率限制有效期 |
| `processed/macro_weekly.csv` | 周（周五） | `ret_*`/`d_*` 累加，其余取区间末值 |
| `processed/macro_monthly.csv` | 月末 | 同上 |
| `processed/macro_observation_*.csv` | 日/周/月 | 按观测期对齐的描述性最新修订值，不用于回测 |

**时点口径**：FRED 的观测日期不是发布时间。默认数据集使用 ALFRED 留存的最早可证 vintage 日，
并在缺少日内时间时从下一 SPX 交易时段保守生效；它不声称等于档案覆盖前的真实历史首发时刻。市场价格不前向填充，
宏观值按日/周/月/季分别在 7/21/62/140 个自然日后失效。

## 黄金研究固定快照

`scripts/update_gold.py` 显式抓取或读取缓存，按信息截止时间保存独立快照；不更新以上共享原始数据。
来源在 `config.GOLD_RESEARCH_FRED_IDS` 与 `config.GOLD_RESEARCH_CANDIDATES` 中登记。
已确认采用 `gold`（COMEX 黄金期货，`GC=F`）作为主研究对象；`xauusd` 留作补充参照。
`--futures-review` 复用市场下载器，在忽略缓存保存定时行情快照；公开目录保存覆盖、哈希和口径缺口。

`--intraday` 通过 Yahoo/yfinance 定向取得五分钟 OHLCV，配置见 `config.GOLD_RESEARCH_INTRADAY`。
Phase 1 日内图使用 `GCZ26.CMX` 十二月合约，长历史仍为 `GC=F` 日线；两者分别计算、不拼接。
Yahoo 时间标签按柱起点处理，图中使用五分钟后的区间结束时刻（纽约时间）；不当作交易所结算价。
原始响应、清洗后行情与哈希保存在忽略缓存；公开核验记录为 `reviews/intraday-<UTC截止时间>.json`。
当前选定日内输入见 `phase1/intraday-input.json`；缺口不填补，节假日的缺失与休市分开核验。

`--drivers` 固定 Phase 2 的 DXY、WTI期货、FedWatch分会议概率与GLD持金量；
只有 `--drivers --refresh` 联网更新 `config.GOLD_RESEARCH_DRIVER_MARKETS` 中的两个Yahoo品种，
FedWatch与GLD读取已取得的导出缓存。完整商业数据保留在忽略缓存，选定哈希与覆盖见 `phase2/inputs.json`。
驱动分析按共同观测日计算，明确缩短后的截止日；CFTC按公布时间过滤，ETF与持仓保持原频率。
WGC月报等后补证据及公开时间限制见 `phase2/evidence.json`；统计和图表均可离线重算。

- `data/raw/gold-outlook/snapshots/<UTC截止时间>/coverage.csv`：实际覆盖、缺口和来源。
- 同目录 `manifest.json`：输入版本、抓取时间、公开文件哈希与阶段状态。
- FRED 使用研究截止时间之前最后一个完整芝加哥日的 vintage；`known_by_at` 只给可知上界。
- CFTC 使用下载时的年度档案；已核验的公布时间单独记录，未知时间留空，不冒充历史初版。
- 候选商业数据的公开权限未确认时，只保存核验记录，不发布完整数值。
- 本研究不使用 SPX 日历裁剪黄金日期，普通站点构建不联网更新快照。

