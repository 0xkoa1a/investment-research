# 投资研究工作空间

公开的投资研究与报告仓库。Python 负责数据、统计和图表快照；VuePress + Vite 读取已经提交的 Markdown 与 Plotly JSON，生成 GitHub Pages 静态站点。普通站点构建不会刷新数据或改写研究结论。

## 内容边界

- `content/research/` 存放报告正文；构建期自动扫描，不需要登记清单。
- 研究使用稳定 slug，无需日期、标签或主题分类。
- `/` 直接显示研究目录，不承担首页叙事。
- 仓库不保存交易、仓位、账户或个人决策日志。

```text
content/
├── research.md
├── research/
│   ├── _template.md
│   └── <stable-topic-slug>.md
└── _assets/plots/<report-slug>/

scripts/research/
└── <slug>.py
```

## 环境

- Node.js 固定为 `22.18.0`，见 `.node-version`。
- Node 包使用 `pnpm 11.19.0`，VuePress 与插件均锁定确切版本。
- Python 依赖由 uv 安装到 `.venv`。

```bash
uv sync
pnpm install --frozen-lockfile
make check
make test
```

需要抓取 FRED 数据时，将 `.env.example` 复制为 `.env` 并填写 `FRED_API_KEY`。密钥文件不会进入 Git。

## 工作流：只维护真正需要维护的东西

### 报告：文字手写，图表按需委托

1. 复制 `content/research/_template.md`，给研究取稳定 slug。正文、公式、表格、来源和结论由你直接编辑；没有日期也完全可以。
2. 如果需要图表，在正文明确写出想比较的变量、区间、频率、统计方法、图形类型和图注。Markdown 只维护 `<PlotlyChart chart="<chart-id>" caption="..." />`；Vue 根据当前研究自动解析资源路径和响应式尺寸。你不需要维护 Python 细节，我会按要求拉取/读取数据、计算并生成 Plotly JSON。
3. 图表脚本与快照通过 `make analyze REPORT=<slug>` 一起更新。命令只替换这一篇研究的 `_assets/plots/<slug>/`，不会改写正文，也不会让普通 `make render` 重新计算结果。

纯文字研究不需要脚本、`data_as_of` 或图表产物；只有写了 `<PlotlyChart>` 的研究才需要这些配套文件。

报告没有自动刷新结论的后台流程。需要更新时才启动一次 agent 工作。

### 更新数据

```bash
make update
```

这一步抓取数据并重建 `data/processed/`，不会自动更新任何研究正文或研究图表。默认要求所有请求序列成功；部分失败时保留旧 raw 数据、返回失败且不重建。只有明确接受旧数据继续参与构建时，才使用：

```bash
make update UPDATE_ARGS=--allow-partial
```

### 显式重算一篇研究

```bash
make analyze REPORT=<slug>
```

`REPORT` 必须是安全 slug，并且同时存在 `content/research/<slug>.md` 与 `scripts/research/<slug>.py`。脚本先写入临时目录；Plotly JSON、manifest、哈希、正文引用和 `data_as_of` 全部校验成功后，才会原子替换 `content/_assets/plots/<slug>/`。正文和图表快照应一起提交到 Git。

新研究从 `content/research/_template.md` 复制。新文件会自动出现在研究目录；`make preview` 运行期间新增、删除或修改 Markdown 也会自动重建目录与搜索，无需重启或维护索引。

### 构建与预览站点

```bash
make render   # 构建 _site/ 并校验路由与资源边界
make preview  # 本地热更新，默认 http://127.0.0.1:8080
```

站点构建只读取研究与版本化图表，不依赖 Python、notebook、CDN 或网络。Plotly 在浏览器端从锁定的本地包动态加载。

### 统一检查

```bash
make check
make render
```

检查覆盖 Node/Python 环境、内容 schema、安全 slug、Plotly JSON/manifest、资源引用、Python/Node 单元测试和 Vue SFC 类型。`make render` 会在构建后自动确认路由和静态资源边界。

push/PR 会执行检查、测试和离线构建；`main` 分支通过后由 GitHub Actions 将 `_site/` 发布到 GitHub Pages。Pages workflow 只上传静态站点产物。

## 其他需要维护的工作

- **数据**：只有图表或统计需要新数据时才运行 `make update`；它只更新原始/派生数据，不改正文和快照。
- **研究脚本**：每篇带图表的研究一个 `scripts/research/<slug>.py`，由 agent 维护。脚本输出只允许标准 Plotly JSON。
- **站点**：日常不需要手工维护导航、索引或搜索；构建期自动扫描 Markdown。改完内容后运行 `make check` 和 `make render`。

## 数据与代码

```text
data/raw/         原始数据，增量合并并保留未返回历史
data/processed/   可重建派生数据，不进 Git
src/inv/          抓取、对齐、统计与可视化公共代码
scripts/research/ 每篇带图表研究的按需分析脚本
content/_assets/   已提交的 Plotly 图表快照
```

数据字段的来源、口径、单位和频率见 `data/SOURCES.md`。FRED 最新修订值位于 `data/raw/fred/`；每个观测期的最早可证 vintage 值及可用日位于 `data/raw/fred_first_release/`（目录名为兼容旧数据保留）。新增原始序列在 `src/inv/config.py` 中登记；派生方式在 `src/inv/dataset.py` 中显式定义。

`dataset.load(freq, view="asof_close")` 默认读取按最早可证可用日构建的安全视图；长期描述性研究若确实需要按统计观测期排列的最新修订值，应显式使用 `view="observation"`。默认视图以 SPX 实际交易记录作为日历，市场价格不前向填充；缺少日内发布时间的宏观数据从下一交易时段保守生效。这里的“最早可证”是 ALFRED 留存的最早 vintage，并不声称等于档案覆盖前的真实历史首发时刻。

## 方法提醒

- 相关性使用收益率或一阶差分，不用非平稳的价格水平。
- 相关性与 beta 会随时间变化，避免用一个静态数字概括全部时期。
- 利率使用差分，不使用收益率。
- 回归残差是模型未解释部分，不等于已识别的因果贡献。

本仓库不包含交易记录、行情驾驶舱、主题分类或自动更新研究结论的能力。
