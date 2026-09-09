import assert from 'node:assert/strict'
import test from 'node:test'

import type { SearchItem } from '../../site/content.js'
import { filterSearchItems } from '../../site/theme/search.js'

const items: SearchItem[] = [
  { type: 'research', title: '美国货币政策', summary: '长期研究', headings: ['流动性'], body: '联邦基金利率', path: '/research/us.html' },
  { type: 'research', title: '黄金与实际利率', summary: '跨资产研究', headings: ['观察窗口'], body: '黄金实际利率', path: '/research/gold-real-rates.html' },
]

test('search matches Chinese substrings and space-separated tokens', () => {
  assert.deepEqual(filterSearchItems(items, '货币 流动').map((item) => item.path), ['/research/us.html'])
  assert.deepEqual(filterSearchItems(items, '黄金 实际').map((item) => item.path), ['/research/gold-real-rates.html'])
  assert.equal(filterSearchItems(items, '不存在').length, 0)
})
