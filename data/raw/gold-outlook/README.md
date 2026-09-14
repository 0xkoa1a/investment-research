# 黄金研究数据

本目录保存黄金研究的公开来源记录和固定输入快照。正文位于 `content/research/gold-outlook.md`。

## 基准快照

- 信息截止：2026-09-09 11:59:46 UTC，即北京时间 19:59:46。
- 目录：`snapshots/20260909T115946Z/`。
- 已取得：16 条 FRED 序列和 CFTC 黄金分项期货持仓。
- 主研究对象已确认改为 COMEX 黄金期货 `gold`（`GC=F`）；`xauusd` 作为补充。原宏观快照没有价格文件。
- 期货补充快照位于忽略缓存 `.cache/gold-outlook/comex/snapshots/`；公开核验记录位于 `reviews/`。已取得行情，接续与 Close 时刻仍待核验。
- 阶段：用户已确认推进至Phase 5；整合与审查已完成，等待最终审阅。
- Phase 1主价格为明确交割月份的`GCZ26.CMX`五分钟Close；长期背景仍用`GC=F`日线，互不拼接。
- Phase 2输入选择见`phase2/inputs.json`；基准FRED/CFTC不变，DXY、CL=F、FedWatch与GLD为后补历史记录。

`source-review.json` 保存本阶段的获取结果、官方发布核验、替代建议与缺口。每次生成快照会复制这一记录，避免之后修改来源说明时改变旧快照的信息边界。

## 使用入口

以下命令在仓库根目录运行。`--refresh` 才会联网；省略时只读取缓存。研究截止时间必须带时区，已有同名快照不能覆盖。

```bash
.venv/bin/python scripts/update_gold.py --cutoff <带时区的ISO时间> --refresh
.venv/bin/python scripts/update_gold.py --cutoff <带时区的ISO时间> --futures-review --refresh
.venv/bin/python scripts/update_gold.py --drivers --cutoff 2026-09-09T11:59:46Z
.venv/bin/python scripts/update_gold.py --verify data/raw/gold-outlook/snapshots/20260909T115946Z
```

抓取只写黄金研究专用目录和忽略缓存，不刷新共享 raw 文件、不构建 SPX 宏观数据集，也不改报告正文。源码复用现有 FRED 序列清单与密钥配置；为指定 vintage 和保持共享数据边界，采用独立读取入口。

`--imports <目录>` 接受已登记且允许公开保存的 CSV。未确认权限的候选会被拒绝；同一系列不能用导入文件静默覆盖在线结果。后续新增现货来源，需要先在配置中登记已核验的来源和许可，再启用相应导入。

## 字段与时间

| 字段 | 含义 |
|---|---|
| `observation_date` | 统计所属日期或价格观察日期，YYYY-MM-DD |
| `value` | 原单位数值；缺失值保留为空 |
| `available_at` | 已核验的公布时间；未知时为空 |
| `known_by_at` | 已知信息可用的保守上界；不是第一次公布时间 |
| `vintage_date` | FRED 查询使用的历史版本日期 |
| `session_close_at` | 导入价格必须提供的、带时区的日终时间；用于过滤未完成交易日 |

FRED 取研究截止时间之前最后一个完整芝加哥日的版本。本次为 2026-09-08，`known_by_at` 为芝加哥次日零点，即 2026-09-09 05:00 UTC。各观测的首次发布时间仍为空；不能把这个统一上界用于发布日事件分析。

CFTC 的 `value` 为 Managed Money 多头减空头，并同时保存多头、空头、跨期头寸和总未平仓量。重点样本公布时间依据官方发布日历，早期历史逐周发布时间未核验，留空。年度档案可能包含后来修订，因此不作为每周发布初版使用。

`coverage.csv` 的 `rows` 包含缺失值行，`valid_rows` 是非空观测数，`focus_rows` 按观测日期计数。月度 CPI 的 `focus_rows=0` 不表示八月没有通胀信息：七月 CPI 于八月发布。`source_*` 字段记录外部文件已检查的覆盖，不能当作快照已保存的行数。

## 复核与公开边界

`manifest.json` 保存截止时间、抓取时间、来源版本、输入及输出哈希。原始网络响应在忽略缓存中，公开 CSV 已规整列名，但没有插值、补齐市场价格或改变原始频率。

FRED 政府来源数据按原机构及 FRED 要求署名；CFTC 数据依据其公开政策注明来源。SPDR 原始工作簿和其他许可未确认的商业序列不在本目录中。

- [FRED 使用条款](https://fred.stlouisfed.org/legal/terms/)
- [CFTC 公开政策](https://www.cftc.gov/WebPolicy/index.htm)
- [CFTC 发布日历](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm)

Phase 0 快照保持原状。`scripts/research/gold-outlook.py` 仅读取所选本地输入，先核对输入哈希，再输出Phase 1的两幅行情图、Phase 2的三幅驱动图，Phase 3的一幅双面板事件图，以及各阶段的`statistics.json`。运行 `make analyze REPORT=gold-outlook` 可重算；不联网、不改报告文字。

`--drivers`默认读取已取得的导出缓存；加`--refresh`只重新下载DXY和CL=F。归档目录每次新建，信息基准固定、获取时间另记；`phase2/inputs.json`选择所用版本。FedWatch保留所有原概率区间，末端空区间不补值，已填概率之和须在舍入误差内等于1；图中高于当前目标区间的概率由对应区间相加。GLD的`US Holiday`保留缺失，不生成日资金流。利率末日为9月4日、WTI现货为9月1日，统计按实际共同末日计算，不能视为9月8日观测。

`phase2/evidence.json`记录政策、风险与WGC月报证据。WGC八月月报的9月9日公布时刻未知，只作为后补证据；月频不插值。CFTC使用9月4日已公布的9月1日持仓，排除9月8日尚未发布的持仓；保留多、空、净额及总未平仓量。

`phase1/events.json` 保留原发布证据及空的一致预期字段；`phase1/execution.json` 记录阶段授权与图表用途。含完整价格数值的 `content/_assets/plots/gold-outlook/` 当前被精确 Git 忽略，供本地页面审阅；原始行情仍在忽略缓存。公开干净检出暂不包含这组图，发布前必须解决数据权限并使该页与快照一起通过构建。

`phase3/inputs.json`固定此前输入选择及事件证据的哈希。`phase3/evidence.json`区分事前报道、当次发布、后续修订及事后观点，并保存CME交易日历依据。`phase3/statistics.json`保留三个案例前一日与当日、后1/3/5交易日的实际日期、原始端点价格、累计涨跌和跨市场变化。日终缺价留空，不移动窗口；9月7日按交易所安排不另计常规交易日。分钟反应以前一根完整柱为基准，08:00—17:00图中两个窗口均无缺柱；周日首两根缺柱不推造开盘价。


## Phase 4更新快照

- 新信息截止：`2026-09-11T10:28:05Z`，北京时间18:28:05；黄金最后完整端点为纽约9月10日17:00。
- `phase4/inputs.json`固定基准选择、新宏观与商业快照及事件证据的哈希。公开FRED版本为9月10日，保守可用上界为9月11日05:00 UTC；商业导出在截止后获取，只纳入更早的完整日期，不声称这是当时的初版档案。
- `phase4/snapshots/20260911T102805Z/`保存政府来源CSV；`.cache/gold-outlook/phase4/snapshots/`保存黄金、DXY、WTI期货与GLD，继续保持本地边界。
- `phase4/statistics.json`区分旧观测修订和新增日期变化，保存新旧值及各自日期；`no_new_observation`表示没有新数据，不能解读为新一天没有变化。
- `phase4/evidence.json`记录PPI初值与前值修订、已可用的WGC八月摘要、Reuters的近似FedWatch快照，以及带时区的未来日历。9月11日CPI和9月8日CFTC持仓公布均在截止后。十年通胀补偿最新日期与名义/实际收益率不同，不跨日期相减。
- 官方FedWatch新导出为HTML错误页，按无效输入记录；不拼入旧概率序列。新闻引用约70%只供判断，不计算与旧CSV的精确差值。
- 报告新增一张变化表、三种情景及未来日历；原六张图与前三阶段统计不延长。报告级`data_as_of`更新为9月10日，每幅历史图的标题/注释保留自身截止。

更新入口为显式导入，复用已登记的来源，不联网修改共享数据：

```bash
.venv/bin/python scripts/update_gold.py --outlook \
  --cutoff 2026-09-11T10:28:05Z --sample-end 2026-09-10 \
  --imports .cache/gold-outlook/phase4/downloads/20260911T102805Z
make analyze REPORT=gold-outlook
```

导入目录使用`fred_snapshot`保存的`<FRED_ID>-<vintage>.json`原响应；Yahoo `gold-raw.csv`为GCZ26.CMX的Datetime/OHLCV五分钟数据，`dxy-raw.csv`、`wti_futures-raw.csv`为带日期的日度OHLCV。各Yahoo文件配套`<name>-retrieval.json`记录获取时间、source_id、interval及vendor的symbol/currency/instrumentType/dataGranularity。GLD使用发行人的`spdr-archive.xlsx`与`gld_holdings-retrieval.json`。可选的`fedwatch_<YYYYMMDD>-raw.csv`为官方导出，含Date及利率区间概率，缺失或错误时记录缺口。商业导出入口见`inputs.json`中的官方来源链接；会话参数不进入公开文件。

快照和已有Phase 4选择拒绝覆盖；以后更新须另建信息截止并明确修订输入选择，保留原目录。执行`--verify`可分别检查新宏观和本地商业快照。普通构建不运行数据更新。


## Phase 5整合与审查

正文以当前判断开篇，再给行情、驱动与事件证据，最后列修订条件、日历和未解决问题。`phase5/inputs.json`固定前四阶段的输入及统计版本；`audit.json`记录数字、日期与图表契约检查，`source-review.json`记录原始发布和因果表述复核，`execution.json`记录本阶段授权、图表用途及浏览器验收。

信息截止沿用Phase 4；历史图与事件窗口仍截止9月8日，更新表截止9月10日。六幅图继续用于不同的问题，持仓图只改善悬停符号与千位分隔；各阶段统计值不变，Phase 2统计中的该图哈希随显示格式更新。方法中的复现边界与商业数据许可限制仍有效。本地审阅稿完成不代表公开发布或最终用户确认。
