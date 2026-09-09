import fs from 'node:fs'
import path from 'node:path'

import matter from 'gray-matter'
import MarkdownIt from 'markdown-it'

import type {
  ContentManifest,
  PlotReference,
  ResearchContract,
  ResearchItem,
  SearchItem,
} from './content-types.js'

export type {
  ContentManifest,
  PlotReference,
  ResearchContract,
  ResearchItem,
  SearchItem,
} from './content-types.js'

interface MarkdownToken {
  type: string
  tag: string
  content: string
  map: [number, number] | null
  children: MarkdownToken[] | null
}

export const contentPagePatterns = [
  'content/research.md',
  'content/research/*.md',
  '!content/research/_*.md',
] as const

interface ParsedMarkdown {
  data: Record<string, unknown>
  tokens: MarkdownToken[]
  headings: Array<{ level: number; title: string; line: number }>
  plainText: string
  plots: PlotReference[]
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/u
const SAFE_SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/u
const PLOT_TAG = /<PlotlyChart\b([\s\S]*?)\/>/gu
const ATTRIBUTE = /([:@]?[A-Za-z][\w:.-]*)\s*=\s*"([^"]*)"/gu
const markdown = new MarkdownIt({ html: true })
const collator = new Intl.Collator('zh-CN')

function relative(root: string, file: string): string {
  return path.relative(root, file).split(path.sep).join('/')
}

function requiredString(data: Record<string, unknown>, key: string, file: string): string {
  const value = data[key]
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${file}: frontmatter.${key} 必须是非空字符串`)
  }
  return value.trim()
}

function optionalDate(data: Record<string, unknown>, key: string, file: string): string | undefined {
  const value = data[key]
  if (value === undefined || value === null || value === '') return undefined
  const normalized = value instanceof Date ? value.toISOString().slice(0, 10) : String(value)
  if (!ISO_DATE.test(normalized)) throw new Error(`${file}: frontmatter.${key} 必须是 ISO 日期`)
  return normalized
}

function rejectExtraFields(data: Record<string, unknown>, allowed: readonly string[], file: string): void {
  const extra = Object.keys(data).filter((key) => !allowed.includes(key)).sort()
  if (extra.length) throw new Error(`${file}: 含未允许的 frontmatter：${extra.join(', ')}`)
}

function inlineText(token: MarkdownToken | undefined): string {
  if (!token) return ''
  if (!token.children) return token.content.trim()
  return token.children
    .filter((child) => ['text', 'code_inline', 'image'].includes(child.type))
    .map((child) => child.content)
    .join(' ')
    .replace(/\s+/gu, ' ')
    .trim()
}

function parsePlotReferences(tokens: MarkdownToken[], file: string): PlotReference[] {
  const plots: PlotReference[] = []
  const ids = new Set<string>()
  for (const token of tokens) {
    if (!['html_block', 'html_inline', 'inline'].includes(token.type) || !token.content.includes('<PlotlyChart')) continue
    const matches = [...token.content.matchAll(PLOT_TAG)]
    if (!matches.length || token.content.replace(PLOT_TAG, '').includes('<PlotlyChart')) {
      throw new Error(`${file}: PlotlyChart 必须使用完整的自闭合标签`)
    }
    for (const match of matches) {
      const attributes = new Map<string, string>()
      for (const attribute of match[1].matchAll(ATTRIBUTE)) {
        const [, name, value] = attribute
        if (attributes.has(name)) throw new Error(`${file}: PlotlyChart 属性 ${name} 重复`)
        attributes.set(name, value.trim())
      }
      const unsupported = [...attributes.keys()].filter((name) => !['chart', 'caption'].includes(name))
      if (unsupported.length) {
        throw new Error(`${file}: PlotlyChart 不允许属性 ${unsupported.join(', ')}；只使用 chart 与 caption`)
      }
      const chart = attributes.get('chart') ?? ''
      const caption = attributes.get('caption') ?? ''
      if (!SAFE_SLUG.test(chart)) throw new Error(`${file}: PlotlyChart 缺少安全 chart 标识`)
      if (!caption) throw new Error(`${file}: PlotlyChart 必须提供 caption`)
      if (ids.has(chart)) throw new Error(`${file}: PlotlyChart chart=${chart} 重复`)
      ids.add(chart)
      plots.push({ chart, caption })
    }
  }
  return plots
}

function parseMarkdown(filePath: string, displayPath: string): ParsedMarkdown {
  const source = fs.readFileSync(filePath, 'utf8')
  if (!/^---[^\S\r\n]*\r?\n/u.test(source)) throw new Error(`${displayPath}: 缺少 frontmatter`)
  let parsed: matter.GrayMatterFile<string>
  try {
    parsed = matter(source)
  } catch (error) {
    throw new Error(`${displayPath}: frontmatter 无效：${error instanceof Error ? error.message : String(error)}`)
  }
  const data = parsed.data as Record<string, unknown>
  const tokens = markdown.parse(parsed.content, {}) as MarkdownToken[]
  const headings: ParsedMarkdown['headings'] = []
  const text: string[] = []
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index]
    if (token.type === 'heading_open') {
      headings.push({
        level: Number.parseInt(token.tag.slice(1), 10),
        title: inlineText(tokens[index + 1]),
        line: (token.map?.[0] ?? 0) + 1,
      })
    }
    if (token.type === 'inline') {
      const value = inlineText(token)
      if (value) text.push(value)
    }
  }
  return {
    data,
    tokens,
    headings,
    plainText: text.join(' ').replace(/\s+/gu, ' ').trim(),
    plots: parsePlotReferences(tokens, displayPath),
  }
}

function researchFiles(root: string): string[] {
  const directory = path.join(root, 'content', 'research')
  if (!fs.existsSync(directory)) return []
  const names: string[] = []
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const absolute = path.join(directory, entry.name)
    if (entry.isDirectory()) {
      const nestedMarkdown = fs.readdirSync(absolute, { recursive: true }).some((name) => String(name).endsWith('.md'))
      if (nestedMarkdown) throw new Error(`${relative(root, absolute)}: 内容目录只允许平级 Markdown`)
      continue
    }
    if (entry.isFile() && entry.name.endsWith('.md') && !entry.name.startsWith('_')) names.push(entry.name)
  }
  return names.sort((left, right) => left.localeCompare(right, 'en'))
}

function researchDocument(root: string, name: string): { item: ResearchItem; parsed: ParsedMarkdown; contract: ResearchContract } {
  const filePath = path.join(root, 'content', 'research', name)
  const displayPath = relative(root, filePath)
  const slug = name.slice(0, -3)
  if (!SAFE_SLUG.test(slug)) throw new Error(`${displayPath}: 研究文件名必须是安全稳定 slug`)
  const parsed = parseMarkdown(filePath, displayPath)
  rejectExtraFields(parsed.data, ['title', 'summary', 'updated', 'data_as_of'], displayPath)
  const item: ResearchItem = {
    type: 'research',
    title: requiredString(parsed.data, 'title', displayPath),
    summary: requiredString(parsed.data, 'summary', displayPath),
    updated: optionalDate(parsed.data, 'updated', displayPath),
    dataAsOf: optionalDate(parsed.data, 'data_as_of', displayPath),
    path: `/research/${slug}.html`,
    slug,
  }
  if (parsed.plots.length && !item.dataAsOf) throw new Error(`${displayPath}: 含图表时必须填写 data_as_of`)
  return {
    item,
    parsed,
    contract: { slug, source: displayPath, dataAsOf: item.dataAsOf, plots: parsed.plots },
  }
}

export function contentRoute(root: string, filePath: string): string | undefined {
  const absolute = path.resolve(filePath)
  const content = path.join(root, 'content')
  if (absolute === path.join(content, 'research.md')) return '/'
  const directory = path.join(content, 'research')
  if (path.dirname(absolute) !== directory || path.basename(absolute).startsWith('_')) return undefined
  const slug = path.basename(absolute, '.md')
  if (!SAFE_SLUG.test(slug)) throw new Error(`${relative(root, absolute)}: 文件名不是安全 slug`)
  return `/research/${slug}.html`
}

export function buildContentManifest(root: string): ContentManifest {
  const researchDocuments = researchFiles(root).map((name) => researchDocument(root, name))
  const research = researchDocuments.map(({ item }) => item)
    .sort((left, right) => collator.compare(left.title, right.title) || left.slug.localeCompare(right.slug, 'en'))
  const parsedByKey = new Map<string, ParsedMarkdown>([
    ...researchDocuments.map(({ item, parsed }) => [`research:${item.slug}`, parsed] as const),
  ])
  const search = research.map((item) => {
    const parsed = parsedByKey.get(`${item.type}:${item.slug}`)
    if (!parsed) throw new Error(`内部错误：缺少 ${item.type}/${item.slug} 解析结果`)
    return {
      type: item.type,
      title: item.title,
      summary: item.summary,
      headings: parsed.headings.filter((heading) => heading.level >= 2).map((heading) => heading.title),
      body: parsed.plainText,
      path: item.path,
    }
  })
  return { research, search, contracts: researchDocuments.map(({ contract }) => contract) }
}

export function researchContract(root: string, slug: string): ResearchContract {
  if (!SAFE_SLUG.test(slug)) throw new Error('研究 slug 无效')
  const contract = buildContentManifest(root).contracts.find((item) => item.slug === slug)
  if (!contract) throw new Error(`缺少研究正文：content/research/${slug}.md`)
  return contract
}

export function validateCatalogs(root: string): void {
  const filePath = path.join(root, 'content', 'research.md')
  if (!fs.existsSync(filePath)) throw new Error('缺少 content/research.md')
  const displayPath = relative(root, filePath)
  const parsed = parseMarkdown(filePath, displayPath)
  rejectExtraFields(parsed.data, ['title', 'summary'], displayPath)
  requiredString(parsed.data, 'title', displayPath)
  requiredString(parsed.data, 'summary', displayPath)
  const template = path.join(root, 'content', 'research', '_template.md')
  if (!fs.existsSync(template)) throw new Error('缺少 content/research/_template.md')
  const publicRoot = path.join(root, 'content', '_assets')
  const publicEntries = fs.existsSync(publicRoot) ? fs.readdirSync(publicRoot) : []
  const unexpected = publicEntries.filter((name) => name !== 'plots')
  if (unexpected.length) throw new Error(`content/_assets 只允许 plots/：${unexpected.join(', ')}`)
}
