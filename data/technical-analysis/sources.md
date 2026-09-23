# 来源与论点核验

核验日期：2026-09-23。本文依据用户提供的[完整分享对话](https://chatgpt.com/share/6ab2c2f7-3120-83ee-a7ee-f5651a03d171)，涵盖价格行为、价格位置与波动、动量与背离、突破形态与多周期、投资决策五个阶段。[原分享](https://chatgpt.com/share/6aaa9542-6558-83e8-b519-d46b5874dd97)只包含前三阶段。阶段标题、继续提示及重复解释未进入教程。

来源用于定义和研究结论的核验，不复制外部图片、行情或长段原文。全部图表重新用教学数据计算。公开网页被读取不意味着其一般交易建议已被采用；本文只保留对应定义、机制及有明确样本边界的结果。

## 价格记录与交易机制

| 来源 | 核验位置与用途 | 解释边界 |
| --- | --- | --- |
| Cont、Kukanov、Stoikov，[The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402) | 摘要：50 只美国股票，短时间价格变化与订单流不平衡、深度的关系 | 不能只凭总量推出净流向或日线方向 |
| Osler，[Currency Orders and Exchange-Rate Dynamics](https://www.newyorkfed.org/research/staff_reports/sr125.html) | 纽约联储 Staff Report 125 摘要：一家大型外汇交易银行的止损、止盈订单及整数位聚集 | 支持可能的微观机制，不宣称所有品种和周期均有效 |
| Grinblatt、Han，[The Disposition Effect and Momentum](https://www.nber.org/papers/w8734) | 工作论文记录：持仓盈亏与后续行为、动量机制的研究 | 不能从一张图确认某类投资者仍持有什么仓位 |
| CME，[Chart Types: candlestick, line, bar](https://www.cmegroup.com/education/courses/technical-analysis/chart-types-candlestick-line-bar) | OHLC、实体和影线的基本定义 | 两条同 OHLC 路径由本教程自行构造 |
| CME，[Support and Resistance](https://www.cmegroup.com/education/courses/technical-analysis/support-and-resistance) | 支撑阻力、角色转换及区域而非精确单点的说明 | 触及或越过区域不保证后续结果 |

股票复权、合约换月、tick volume 等数据口径依据原对话中的数据平台解释整理，正文不涉及某个平台的当前默认设置。正文的拆股算例、波段关系与时间尺度说明是可直接核对的概念例子。

## 价格位置与指标定义

| 来源 | 核验位置与用途 | 本教程处理 |
| --- | --- | --- |
| TradingView，[Volume profile indicators: basic concepts](https://www.tradingview.com/support/solutions/43000502040-volume-profile-indicators-basic-concepts/) | Typical levels、Calculating value area：POC、价值区、参数和算法；Volume types：不同数据及方向分类 | 本例另行固定连续扩展算法，并列时优先低档，累计至少 70%；不声称逐项复制平台算法 |
| TradingView，[Average True Range](https://www.tradingview.com/support/solutions/43000501823-average-true-range-atr/) | TR 三项取最大、RMA 平滑、非方向性 | 首期 TR 及 Wilder 初始化规则在 README 中明确 |
| John Bollinger，[Bollinger Band Rules](https://www.bollingerbands.com/bollinger-band-rules) | 规则 4—8、11、14：同源指标、触轨、沿轨、默认窗口与概率解释 | 带宽使用价格标准差；不推导未来 95% 覆盖率 |
| CME，[Fibonacci Retracements and Extensions](https://www.cmegroup.com/education/courses/technical-analysis/fibonacci-retracements-and-extensions) | 回撤和延伸的基本概念及比例 | 不引入延伸目标；回撤价格由公式自行计算 |
| Fidelity，[MACD](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/macd) | Calculation、交易区间内 whipsaw 说明 | 12、26、9；只使用定义及局限，不照搬交易指令 |
| TradingView，[Relative Strength Index](https://www.tradingview.com/support/solutions/43000502338-relative-strength-index-rsi/) | Calculation 中 change、gain、loss、rma 的逐期计算 | 所有时期都参与；分母零时的处理由本教程明确 |
| Fidelity，[Relative Strength Index](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI) | 0—100、70／30、40—90 与 10—60 活动范围以及参数影响 | 活动范围仅作为经验描述，不当成固定边界 |
| TradingView，[Repainting](https://www.tradingview.com/pine-script-docs/concepts/repainting/) | 流动读数及向过去绘制 pivot 的信息时点问题 | 教程区分峰值所在期与信号确认期，不提供带未来信息的策略回测 |

SMA 滚动变化、EMA 线性趋势下的滞后、正柱收缩时 DIF 仍可上升、RSI 在平价期保留比值、收益率标准差与价格标准差的区别，属于公式推导。正文保留直观数值例，脚本与测试负责复算，不将它们归为某篇论文的实证结论。

## 经验研究

| 原始来源 | 已核对的结论及范围 | 正文中的用途 |
| --- | --- | --- |
| CFA Institute，[Market Efficiency](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/market-efficiency) | Summary：弱式、半强式、强式信息集，以及风险对应收益的含义 | 建立判断技术分析有效性的参照 |
| Moskowitz、Ooi、Pedersen，[Time Series Momentum](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum) | 作者机构介绍：58 个期货与远期合约，过去 12 个月超额收益的预测关系 | 支持研究价格延续性，不替日线指标背书 |
| Chong、Ng、Liew，[Revisiting the Performance of MACD and RSI Oscillators](https://mpra.ub.uni-muenchen.de/54149/) | 摘要：五个 OECD 国家市场；MACD(12,26,0)、RSI(21,50) 等规则的效果因市场而异 | 不把论文的零轴规则等同于教程全部 MACD 信号 |
| Lo、Mamaysky、Wang，[Foundations of Technical Analysis](https://web.mit.edu/wangj/www/pap/LoMamayskyWang00.pdf) | 作者托管论文摘要：美国股票、自动形态识别、部分指标对条件收益分布的增量信息 | 区分有增量信息与可实现的净收益；NBER PDF 本次 403，改读作者版本 |
| Tsinaslanidis、Guijarro、Voukelatos，[Automatic identification and evaluation of Fibonacci retracements](https://riunet.upv.es/server/api/core/bitstreams/07add8c4-4239-44e7-bf1f-93d66108918d/content) | 作者稿第 4—5、13 页：Fibonacci 区域与随机区域的反弹、收益对照 | 不能把比例的数学来源当成金融预测证据 |
| Gurrib 等，[Energy crypto currencies and leading U.S. energy stock prices: are Fibonacci retracements profitable?](https://link.springer.com/article/10.1186/s40854-021-00311-8) | 摘要与结论：2017-11 至 2020-01，能源股票和能源加密资产，比较买入持有 | 与随机区域基准回答不同问题；正文不引用具体收益率或推广到其他样本 |
| Sullivan、Timmermann、White，[Data-Snooping, Technical Trading Rule Performance, and the Bootstrap](https://eprints.lse.ac.uk/119144/1/dp303.pdf) | 作者工作论文摘要及第 1—3 页：将规则选择放回完整候选集合，检验数据窥探影响 | 说明多重尝试风险，不将论文误写为否定所有时期的全部技术规则 |

## 原对话内容映射

- 价格行为阶段 → 教程前两章；有效市场和经验证据统一收至“综合判断与证据”，避免前后重复。
- 位置与波动阶段 → 第三章；VWAP 为短补充，未扩写成交量策略。深回调例保留 100、116、110、140、122、126、114.8、116 关键路径，均线与 ATR 全部重算。
- 动量阶段 → “动量与背离”和“综合判断与证据”；A=120、B=125.5、最新=123.6 保留。新教学序列对应 DIF 4.52／2.14、RSI 95.7／64.0，末期 DIF 1.52、DEA 1.84、柱体 −0.33、RSI 55.0。
- 核验后的条件判断只用于虚构案例的结构解释，不写账户、持仓、真实交易价格或个人决策。
- 第四阶段 → “突破、形态与多周期结构”：越界与确认、ATR 标准化幅度、回踩与等待成本；双顶底、头肩、三角形、箱体、旗形、楔形及测量投影；OHLC 聚合、主周期分工、未完成周期和条件逐级变化。四张教学图重建为 Plotly，小时、日、周图来自同一 840 小时序列，保留当前 108、日线低点 103、周线 118—122 等关键结构。
- 第五阶段的 Stochastic 移入动量章；新增研究与回测细节并入证据章；基本面与估值、预期与消息、三类失效条件、止损执行、数量与压力损失、收益损失比、期望结果及完整案例集中在末章。
- 新增内容只使用原对话的虚构算例，不包含用户实际资产、账户、交易记录或具体证券的操作建议。

正文的研究结果按“机制是否合理、是否有预测信息、扣费并考虑风险后是否有用”组织，作者和完整出处保留在本文件。形态对照沿用正文数字：双顶补出跌至 110 的一条后续示例，上升三角形补出 113，上升楔形补出 110；头肩顶原路径的最后一步为 106。补出的节点用于显示越界与形成过程的区别，不来自实测，也不具有预测概率。

## 补充概念与研究核验

| 来源 | 本次核验位置与支持内容 | 使用边界 |
| --- | --- | --- |
| CME，[Technical Patterns: Reversals](https://www.cmegroup.com/education/courses/technical-analysis/technical-patterns-reversals) | 反转形态、颈线确认与形态可能演变 | 价格路径为对话教学例；名称不当作固定成功率 |
| CME，[Trend and Continuation Patterns](https://www.cmegroup.com/education/courses/technical-analysis/trend-and-continuation-patterns) | 三角形、矩形、旗形的边界关系 | 定义与传统方向解释分开；实际方向等待价格确认 |
| Fidelity，[Fast Stochastic](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/fast-stochastic) | 完整对话引用的快速随机指标定义；本次网页仅返回导航，公式另按区间位置定义核算 | %K 算例 90，%D 与平滑版本不混用；不依赖阈值交易建议 |
| CFA Institute，[Equity Valuation: Concepts and Basic Tools](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/equity-valuation-concepts-basic-tools) | 估值模型、现值与倍数方法 | 6×20 和 7.2×15 为虚构算术，不是预测或真实估值 |
| FINRA，[Stop Orders: Factors to Consider During Volatile Markets](https://www.finra.org/investors/insights/stop-orders-factors-consider-during-volatile-markets) | 触发价与成交价的区别、短暂波动触发、止损限价可能不成交 | 定义通用机制，不声称各市场产品触发规则完全相同 |
| CME，[Proper Position Size](https://www.cmegroup.com/education/courses/trade-and-risk-management/proper-position-size) | 风险预算与退出距离作为数量计算输入 | 正文使用无杠杆现货教学算例，不照搬期货乘数或固定账户风险比例 |
| CFA Institute，[Backtesting & Simulation](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation) | 滚动检验、前视和幸存者偏差、结构变化与尾部风险 | 本教程没有运行策略回测；示例只解释如何设计检验 |
| Osler，[Support for Resistance: Technical Analysis and Intraday Exchange Rates](https://www.newyorkfed.org/research/epr/00v06n2/0007osle.html) | 摘要：六家外汇机构的水平预测日内趋势中断，效果随汇率和机构变化 | 与原有 sr125 订单机制论文是不同研究；完整对话的一条 sr4 链接实际是另一篇头肩研究，本次改为匹配论点的原文 |
| Nagel，[Evaporating Liquidity](https://www.nber.org/system/files/working_papers/w17653/w17653.pdf) | NBER 原文检索摘要：短期反转收益与流动性供给、市场压力的关系；正文直接抓取失败 | 只使用摘要结论，不引用实证系数或推广为个股跌后必反弹 |
| Huang、Li、Wang、Zhou，[Time series momentum: Is it there?](https://scholars.hkbu.edu.hk/en/publications/time-series-momentum-is-it-there-2/) | 作者机构摘要：逐资产样本内外证据弱、策略与历史均值比较策略表现近似 | 不写成所有趋势策略都无效；与 Moskowitz 等的研究一起说明争议 |
| Marshall、Young、Cahan，[Are candlestick technical trading strategies profitable in the Japanese equity market?](https://link.springer.com/article/10.1007/s11156-007-0068-1) | 出版社摘要：日本股票 1975—2004 年测试策略未增加价值 | 未获取付费全文，不推导摘要以外的规则细节 |

多周期 OHLC、均线采样差异、突破 ATR 倍数、随机指标、估值与预期百分比、计划数量、跳空压力及期望结果均可直接由定义或教学数据复算。统计上“独立证据”的限制来自样本重叠与相关性，不为多个周期编造成功概率。
