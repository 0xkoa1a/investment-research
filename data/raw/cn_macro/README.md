# 中国挖掘机与宏观年度图表数据

`excavator_macro_annual.csv` 由 `scripts/build_cn_excavator_macro.py` 生成，
覆盖 2006—2025。报告渲染只读取该快照，不在渲染时联网。

`excavator_macro_monthly.csv` 由 `scripts/build_cn_excavator_monthly.py` 生成，
用于“挖掘机产量、PMI 与克强指数”月度图。`li_keqiang_index_cme_digitized.csv`
是该脚本读取的版本化克强指数近似数字化快照。

`excavator_demand_monthly.csv` 是“挖掘机销量与宏观经济指标背离的原因”图
使用的版本化月度快照，覆盖 2014-01—2025-12。销量数据截至 2025-08，
其余三项截至 2025-12；报告渲染不联网。

## 主要来源

- 挖掘机产量：国家统计局年度累计口径；年度表由[中商产业研究院数据库](https://s.askci.com/data/MonthDetail/Index?CityCode=&EndTime=&StartTime=&isYear=1&type=2&zbId=a02091u)转录，2007—2009 由[国家统计局月度当月值镜像](https://chinadata.live/data/china-excavator-production/)加总交叉核对。
- 制造业 PMI：[China Data Portal 的国家统计局镜像](https://chinadata.live/data/china-pmi/)，月度值取年度平均。
- 月度对比图的挖掘机产量和制造业 PMI：同一国家统计局镜像；挖掘机自 2013 年起通常不单列 1 月、2 月当月值，滚动 12 个月计算使用[中商产业研究院表中的 1—2 月累计值](https://s.askci.com/data/industry/a02091u/)，不拆分或插值单月数据。
- 月度对比图的克强指数：从 [CME Group 2024 年 3 月演示材料](https://acoc.memberclicks.net/assets/Spring_2024_Economic%20Outlook_Erik%20Norland.pdf)第 15 页（图中来源标注 Bloomberg Professional `CLKQINDX`）近似数字化复原。数字化过程从 PDF 中提取蓝色曲线路径，按月度横轴位置采样并用右侧数轴校准，保留两位小数；按图中时间轴近似映射覆盖 2005-01—2024-03。该 CSV 不是 Bloomberg 原始数据，不与其他机构的克强指数拼接。
- 克强指数构成：AkShare 的全社会用电量、交通运输量和新增人民币贷款接口；权重为用电 40%、铁路货运 20%、人民币贷款 40%。2008—2025 贷款余额增速由年度新增贷款与 2025 年末余额锚定回推，2006—2007 使用公开年末增速。
- 2025 年末人民币贷款余额锚：[中国政府网](https://english.www.gov.cn/archive/statistics/202601/15/content_WS6968cc25c6d00ca5f9a0896a.html)。
- 月度挖掘机销量：[中国银河证券整理的中国工程机械工业协会月度国内、出口销量表](https://pdf.dfcfw.com/pdf/H3_AP202509091740725610_1.pdf?1757431241000.pdf=)，两项逐月相加，覆盖 2014-01—2025-08。
- 第二张图的房地产新开工面积、基础设施投资和采矿业投资：国家统计局月度累计同比。其中，[2023 年上半年固定资产投资](https://www.stats.gov.cn/sj/zxfb/202307/t20230715_1941270.html)和[2025 年上半年固定资产投资](https://www.stats.gov.cn/sj/zxfbhjd/202507/t20250715_1960412.html)用于交叉核对 6 月基建投资值；各年 12 月与年度公报核对。
- 年度挖掘机销量：2006—2019 为[中国工程机械工业协会、智研咨询整理表](https://www.chyxx.com/industry/202006/874817.html)；2020—2025 为协会年度快报口径。
- 房屋新开工面积：1998—2022 历史表来自[中国房地产估价师与房地产经纪人学会](https://www.cirea.org.cn/content/4778)，2023—2025 接国家统计局年度数据。
- 基础设施与采矿业投资同比：国家统计局历年固定资产投资公报；[2025 年公报](https://www.stats.gov.cn/sj/zxfb/202601/t20260119_1962326.html)。

## 口径说明

- 挖掘机产量与销量不是同一统计口径，不应用两者差额推算库存或出口。
- 月度三线图中，挖掘机线先计算过去 12 个月累计产量相对前 12 个月的同比，PMI 与克强指数取 12 个月滚动均值，再对每条可用历史分别计算总体 Z-score；它比较的是各序列相对自身历史的位置，不能比较绝对水平。
- 月度需求图中，四条线先形成累计同比，再分别对 12 个已公布月度观测取滚动均值。固定资产投资和房地产月报通常不单独发布 1 月数据，因此这三条国家统计局序列的 12 期窗口通常跨约 13 个日历月；不对 1 月插值或前向填充。
- 克强指数没有统一官方发布序列；数字化误差和原图分辨率会影响单月精确值，因此只用于识别长期周期和拐点。
- 协会销量为纳统企业口径，样本覆盖可能随年份变化。
- 基建投资早期公开序列口径不连续，CSV 对 2006—2008 保留缺失值。
