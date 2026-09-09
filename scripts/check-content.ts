import fs from 'node:fs'
import path from 'node:path'

import { buildContentManifest, validateCatalogs } from '../site/content.js'

const root = path.resolve(import.meta.dirname, '..')
const errors: string[] = []

try {
  validateCatalogs(root)
  const manifest = buildContentManifest(root)
  const plotReports = new Set(manifest.contracts.filter((item) => item.plots.length).map((item) => item.slug))
  const scriptRoot = path.join(root, 'scripts', 'research')
  const assetRoot = path.join(root, 'content', '_assets', 'plots')
  const scripts = new Set(fs.readdirSync(scriptRoot).filter((name) => name.endsWith('.py')).map((name) => name.slice(0, -3)))
  const assets = new Set(fs.readdirSync(assetRoot, { withFileTypes: true }).filter((entry) => entry.isDirectory()).map((entry) => entry.name))
  for (const slug of plotReports) {
    if (!scripts.has(slug)) errors.push(`含图表的研究缺少分析脚本：scripts/research/${slug}.py`)
    if (!assets.has(slug)) errors.push(`含图表的研究缺少快照目录：content/_assets/plots/${slug}`)
  }
  for (const slug of scripts) if (!plotReports.has(slug)) errors.push(`分析脚本没有对应 Plotly 引用：scripts/research/${slug}.py`)
  for (const slug of assets) if (!plotReports.has(slug)) errors.push(`图表快照没有对应 Plotly 引用：content/_assets/plots/${slug}`)
  console.log(`[content-check] ${manifest.research.length} 篇研究`)
} catch (error) {
  errors.push(error instanceof Error ? error.message : String(error))
}

for (const legacy of ['templates', 'notes', 'research', 'journal', 'content/journal', 'content/journal.md']) {
  if (fs.existsSync(path.join(root, legacy))) errors.push(`旧目录仍存在：${legacy}`)
}

const ignored = new Set(['.git', '.venv', 'node_modules', '_site', '.cache'])
const forbiddenNames = new Set(['_quarto.yml', '.quarto', '_freeze'])
const visit = (directory: string): void => {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (entry.isDirectory() && ignored.has(entry.name)) continue
    const absolute = path.join(directory, entry.name)
    if (forbiddenNames.has(entry.name)) errors.push(`仍存在 Quarto 残余：${path.relative(root, absolute)}`)
    if (entry.isDirectory()) visit(absolute)
    else if (entry.name.endsWith('.qmd')) errors.push(`仍存在 .qmd：${path.relative(root, absolute)}`)
  }
}
visit(root)

if (errors.length) {
  for (const error of errors) console.error(`[content-check] FAIL: ${error}`)
  process.exit(1)
}
