# 投资研究报告

- [2022～2026 年黄金牛市分析](content/research/gold-evidence.md)
- [技术分析入门：价格行为、指标与投资决策](content/research/technical-analysis.md)
- [经济与投资时间序列：统计口径、数据变换与实时回测](content/research/basics.md)
- [COMEX 黄金：2026年8月至9月初的消息与行情](content/research/gold-outlook.md)
- [A 股红利与防御资产：从分红能力到估值与风格轮动](content/research/dividend-investing.md)
- [中国挖掘机与宏观指标趋势图](content/research/china-excavator-macro-trends.md)

## 写报告

在 VS Code 中打开本仓库，复制 [报告模板](content/research/_template.md)，将副本保存在同一目录，文件名使用小写英文字母、数字和连字符，例如 `gold-evidence.md`。首行写一级标题，下一段可写摘要。

在编辑器里按 `⌘V` 粘贴截图，VS Code 会将图片保存到 `content/research/asset/报告文件名/` 并插入相对链接。正文、公式和表格都可以直接用 Markdown 编辑。完成后，把报告链接加到上面的目录。

## 预览和导出

站点自动收录报告，支持全文搜索、章节目录和公式。使用 Node.js 22.18.0、pnpm 11.19.0，首次运行 `make setup` 安装站点依赖。

- `make preview` 启动本地预览。打开 <http://127.0.0.1:8080/>，保存报告后页面会刷新。
- `make export PAGE=gold-evidence.md` 将单篇报告连同截图、公式和目录打包为 `_exports/gold-evidence.html`，双击即可离线阅读。
- `make render` 检查内容、类型和测试，并在 `_site/` 生成完整站点。GitHub Pages 工作流在推送到 `main` 后构建并发布。

在 VS Code 的「终端 → 运行任务」中也可以启动站点预览，或导出当前打开的报告。
