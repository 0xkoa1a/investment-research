import fs from 'node:fs'
import path from 'node:path'

import { buildContentManifest } from '../site/content.js'

const root = path.resolve(import.meta.dirname, '..')
const site = path.join(root, '_site')
const sourcePlots = path.join(root, 'content', '_assets', 'plots')
const builtPlots = path.join(site, 'plots')
const errors: string[] = []

const filesBelow = (directory: string): string[] => {
  if (!fs.existsSync(directory)) return []
  const output: string[] = []
  const visit = (current: string): void => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const absolute = path.join(current, entry.name)
      if (entry.isDirectory()) visit(absolute)
      else output.push(path.relative(directory, absolute).split(path.sep).join('/'))
    }
  }
  visit(directory)
  return output.sort()
}

if (!fs.existsSync(path.join(site, 'index.html'))) errors.push('缺少 _site/index.html')

try {
  const manifest = buildContentManifest(root)
  const expectedResearch = manifest.research.map((item) => `${item.slug}.html`).sort()
  const actualResearch = fs.existsSync(path.join(site, 'research'))
    ? fs.readdirSync(path.join(site, 'research')).filter((name) => name.endsWith('.html')).sort()
    : []
  if (JSON.stringify(actualResearch) !== JSON.stringify(expectedResearch)) {
    errors.push(`研究路由集合不一致：expected=${expectedResearch.join(',')} actual=${actualResearch.join(',')}`)
  }
  for (const forbidden of ['research/_template.html', 'research.html', 'journal', 'journal.html']) {
    if (fs.existsSync(path.join(site, forbidden))) errors.push(`非研究内容意外进入站点：${forbidden}`)
  }
  const sourceAssets = filesBelow(sourcePlots)
  const builtAssets = filesBelow(builtPlots)
  if (JSON.stringify(sourceAssets) !== JSON.stringify(builtAssets)) {
    errors.push(`Plotly 静态资源集合不一致：source=${sourceAssets.join(',')} built=${builtAssets.join(',')}`)
  }
  const builtFiles = filesBelow(site)
  const forbiddenFiles = builtFiles.filter((name) => /(?:^|\/)(?:trades?|positions?)(?:[./]|$)|\.(?:csv|py|map)$/iu.test(name))
  if (forbiddenFiles.length) errors.push(`公开产物包含禁止文件：${forbiddenFiles.join(',')}`)
  const forbiddenText = ['/journal/', 'content/journal', '决策日志', 'trades.csv', 'reviewed_at']
  for (const name of builtFiles.filter((file) => /\.(?:html|js|css|json)$/u.test(file))) {
    const body = fs.readFileSync(path.join(site, name), 'utf8')
    const match = forbiddenText.find((value) => body.includes(value))
    if (match) errors.push(`公开产物 ${name} 含禁止内容：${match}`)
  }
  console.log(`[site-check] ${manifest.research.length} 篇研究`)
} catch (error) {
  errors.push(error instanceof Error ? error.message : String(error))
}

if (errors.length) {
  for (const error of errors) console.error(`[site-check] FAIL: ${error}`)
  process.exit(1)
}
