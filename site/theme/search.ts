import type { SearchItem } from '../content-types.js'

export function filterSearchItems(items: SearchItem[], query: string, limit = 20): SearchItem[] {
  const normalized = query.trim().toLocaleLowerCase('zh-CN')
  if (!normalized) return items.slice(0, Math.min(limit, 8))
  const tokens = normalized.split(/\s+/u).filter(Boolean)
  return items.filter((item) => {
    const haystack = [item.title, item.summary, item.headings.join(' '), item.body]
      .join(' ')
      .toLocaleLowerCase('zh-CN')
    return tokens.every((token) => haystack.includes(token))
  }).slice(0, limit)
}
