# Repository instructions

## Public boundary

- Treat the repository, its full Git history, CI logs, build artifacts, and GitHub Pages output as public.
- Keep published content under `content/research/`. Do not add journals, trades, positions, account data, broker exports, entry or exit prices, stop levels, targets, P&L, or personal decision records.
- Keep secrets in ignored local environment files. Never commit API keys, tokens, credentials, account identifiers, or private filesystem paths.
- Before every push, run `make check`, `make render`, and `git diff --check`. Inspect `_site/` with `scripts/check-site.ts` before deployment.

## Content and computation

- Markdown owns report prose, formulas, tables, citations, and conclusions.
- Python owns data retrieval, statistics, and versioned Plotly snapshots.
- A normal site build must not fetch data, rerun analysis, or change report conclusions.
- Preserve unrelated report prose, sources, data snapshots, and user edits.

## 理解式研究报告的偏好

以下约定适用于理解式研究报告；用户对具体任务的明确要求优先。目标是帮助读者理解已经发生的行情、消息与影响机制。

### 内容与叙事

- 循序渐进地组织内容：先解释研究对象的特点和必要概念，再交代背景、梳理具体行情，随后结合影响因素与关键事件展开分析。按读者理解所需调整顺序，不沿用数据抓取或研究阶段的排列顺序。
- 默认包含：研究对象及价格特点、历史与宏观背景、主要影响机制、具体行情与转折、关键消息及市场反应、相关资金或需求证据，以及反例和仍不能确定的因果关系。各部分按证据的重要性安排篇幅。
- 事件分析讲清楚消息内容、当时已有的认识、可能影响价格的机制，以及发布前后的实际反应。区分当次发布与后续修订，不把同时发生直接写成因果。
- 图表与解释相邻，说明读者应当看到什么、它支持什么理解。同一论点只完整解释一次，避免按因素和按事件重复叙述整段行情。
- 默认不包含未来投资展望、方向建议、情景推演、未来事件日历、操作建议、价格目标或交易安排；只有用户明确要求时才另行加入。当时市场对政策的预期可以作为历史证据。

### 语言与呈现

- 使用通俗、准确、连贯的中文段落，一段讲清一个主要意思。先说重点，再给解释和必要证据，让后一句承接前一句。
- 优先使用常见词、具体例子和明确动词。术语首次出现时就地解释，数字与技术细节只保留到足以帮助理解的程度。
- 正文以段落为主；确实并列、有顺序或适合比较的信息才使用列表、表格。避免嵌套列表、术语堆砌、套话、机械过渡、不必要的对比句，以及重复正文的小结。
- 不显示引用标记、引用链接、脚注、参考文献列表或单列来源署名，也不把普通说明包在引用块中。支撑结论的来源与核验依据保存在支持资料中；理解事实所必需的机构、指标和事件名称可正常使用。
- 不写数据获取、快照、版本、哈希、写作进度、Phase状态、待审阅提示、修改过程或修订记录等元信息。更新和数据截止日期使用页面现有字段，正文不重复说明。
- 品种、单位、实际统计区间、必要的观测日与消息发布时间，以及影响解释的数据缺口，属于理解证据所需的内容，简短放在相应位置。研究数字本身应按论述需要保留。

### 分阶段推进

- 单篇报告逐阶段完善。阶段按具体研究任务划分，通常从研究准备、行情梳理、因素检验、事件复盘推进到整合审查。
- 每次只完成用户明确授权的阶段；“继续”“下一步”只授权下一阶段。阶段完成后在对话中说明结果并暂停，修改请求先落实到当前阶段。
- 阶段安排、确认状态和检查记录放在对话或支持资料中，报告正文始终呈现为连贯的研究文章。
