<script setup lang="ts">
import { computed } from 'vue'
import { usePageData } from 'vuepress/client'
import { researchItems } from 'virtual:content-manifest'

import SiteHeader from '../components/SiteHeader.vue'
import TableOfContents from '../components/TableOfContents.vue'

const page = usePageData()
interface ArticleMeta {
  title: string
  summary: string
  updated?: unknown
  dataAsOf?: unknown
}

const isCatalog = computed(() => page.value.path === '/')
const meta = computed<ArticleMeta>(() => {
  const source = page.value.frontmatter as Record<string, unknown>
  return {
    title: typeof source.title === 'string' ? source.title : '',
    summary: typeof source.summary === 'string' ? source.summary : '',
    updated: source.updated,
    dataAsOf: source.data_as_of,
  }
})
function formatDate(value: unknown): string {
  if (value instanceof Date) return value.toISOString().slice(0, 10)
  if (typeof value === 'string') return value.slice(0, 10)
  return ''
}
</script>

<template>
  <SiteHeader />

  <main v-if="isCatalog" :key="page.path" class="page-frame catalog-page">
    <header class="catalog-intro">
      <h1>研究</h1>
      <p>浏览长期研究、事件分析与方法记录。</p>
    </header>
    <section class="catalog-list" aria-label="研究目录">
      <RouterLink v-for="item in researchItems" :key="item.slug" class="research-row" :to="item.path">
        <span>
          <strong>{{ item.title }}</strong>
          <small>{{ item.summary }}</small>
        </span>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7"/></svg>
      </RouterLink>
      <p v-if="!researchItems.length" class="catalog-empty">尚无研究。</p>
    </section>
  </main>

  <main v-else :key="page.path" class="page-frame article-shell">
    <article class="article-main">
      <RouterLink class="back-link" to="/">← 返回研究</RouterLink>
      <header class="article-header">
        <h1>{{ meta.title }}</h1>
        <p>{{ meta.summary }}</p>
        <p v-if="meta.updated || meta.dataAsOf" class="research-meta">
          <span v-if="meta.updated">更新于 {{ formatDate(meta.updated) }}</span>
          <span v-if="meta.dataAsOf">数据截至 {{ formatDate(meta.dataAsOf) }}</span>
        </p>
      </header>

      <TableOfContents />
      <Content class="article-content" vp-content />
    </article>
  </main>
</template>
