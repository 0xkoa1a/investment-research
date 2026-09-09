import assert from 'node:assert/strict'
import { mkdtemp, mkdir, rm, unlink, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import type { TestContext } from 'node:test'

import { buildContentManifest, contentRoute, validateCatalogs } from '../../site/content.js'

async function fixture(context: TestContext): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), 'investment-content-'))
  context.after(() => rm(root, { recursive: true, force: true }))
  await mkdir(path.join(root, 'content', 'research'), { recursive: true })
  await writeFile(path.join(root, 'content', 'research.md'), '---\ntitle: 研究\nsummary: 目录\n---\n')
  await writeFile(path.join(root, 'content', 'research', '_template.md'), '---\ntitle: T\nsummary: T\n---\n')
  return root
}

test('discovers flat content and builds deterministic routes and search', async (context) => {
  const root = await fixture(context)
  await writeFile(path.join(root, 'content', 'research', 'long-cycle.md'), [
    '---', 'title: 长周期', 'summary: 描述', 'data_as_of: 2026-01-02', '---',
    '```html', '<PlotlyChart chart="fake" caption="不应解析" />', '```',
    '## 正文', '货币政策正文', '<PlotlyChart chart="real-chart" caption="真实图注" />', '',
  ].join('\n'))
  const manifest = buildContentManifest(root)
  assert.equal(manifest.research[0].path, '/research/long-cycle.html')
  assert.deepEqual(manifest.contracts[0].plots.map((plot) => plot.chart), ['real-chart'])
  assert.match(manifest.search[0].body, /货币政策正文/u)
  assert.doesNotMatch(manifest.search[0].body, /不应解析/u)
  assert.equal(contentRoute(root, path.join(root, 'content', 'research', 'long-cycle.md')), '/research/long-cycle.html')
})

test('rejects nested Markdown and frontmatter drift', async (context) => {
  const root = await fixture(context)
  await mkdir(path.join(root, 'content', 'research', 'nested'))
  await writeFile(path.join(root, 'content', 'research', 'nested', 'page.md'), '---\ntitle: X\nsummary: X\n---\n')
  assert.throws(() => buildContentManifest(root), /只允许平级 Markdown/u)
})

test('validates the catalog document and research template', async (context) => {
  const root = await fixture(context)
  assert.doesNotThrow(() => validateCatalogs(root))
})

test('manifest reflects add, edit, and delete without an index file', async (context) => {
  const root = await fixture(context)
  const file = path.join(root, 'content', 'research', 'dynamic.md')
  await writeFile(file, '---\r\ntitle: 初始标题\r\nsummary: 初始摘要\r\n---\r\n## 正文\r\n内容\r\n')
  assert.equal(buildContentManifest(root).research[0].title, '初始标题')
  await writeFile(file, '---\ntitle: 更新标题\nsummary: 更新摘要\n---\n## 正文\n内容\n')
  assert.equal(buildContentManifest(root).research[0].title, '更新标题')
  await unlink(file)
  assert.equal(buildContentManifest(root).research.length, 0)
})

test('rejects layout attributes in Plotly content', async (context) => {
  const root = await fixture(context)
  await writeFile(path.join(root, 'content', 'research', 'bad-chart.md'), [
    '---', 'title: 图表', 'summary: 图表', 'data_as_of: 2026-01-01', '---',
    '<PlotlyChart chart="chart" caption="图注" :height="500" />', '',
  ].join('\n'))
  assert.throws(() => buildContentManifest(root), /只使用 chart 与 caption/u)
})

test('rejects malformed non-self-closing Plotly components', async (context) => {
  const root = await fixture(context)
  await writeFile(path.join(root, 'content', 'research', 'plot.md'), [
    '---', 'title: 图表', 'summary: 图表', 'data_as_of: 2026-01-01', '---',
    '<PlotlyChart chart="chart" caption="图注"></PlotlyChart>', '',
  ].join('\n'))
  assert.throws(() => buildContentManifest(root), /完整的自闭合标签/u)
})
