<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { usePageData } from 'vuepress/client'

import SearchOverlay from './SearchOverlay.vue'

const page = usePageData()
const searchOpen = ref(false)

function onGlobalKeydown(event: KeyboardEvent): void {
  if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase() === 'k') {
    event.preventDefault()
    searchOpen.value = !searchOpen.value
  }
}

watch(() => page.value.path, () => {
  searchOpen.value = false
})

onMounted(() => window.addEventListener('keydown', onGlobalKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onGlobalKeydown))
</script>

<template>
  <header class="site-header">
    <div class="header-primary">
      <RouterLink class="brand" to="/" aria-label="投资研究：研究目录">
        <span class="brand-mark" aria-hidden="true">IR</span>
        <span>投资研究</span>
      </RouterLink>

      <nav class="desktop-nav" aria-label="主导航">
        <RouterLink class="active" to="/">研究</RouterLink>
      </nav>

      <button class="header-search" type="button" aria-label="搜索研究" @click="searchOpen = true">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m16.2 16.2 4 4"/></svg>
        <span>搜索研究</span>
        <kbd>⌘ K</kbd>
      </button>

      <div class="mobile-actions">
        <button type="button" aria-label="打开搜索" @click="searchOpen = true">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m16.2 16.2 4 4"/></svg>
        </button>
      </div>
    </div>

    <SearchOverlay :open="searchOpen" @close="searchOpen = false" />
  </header>
</template>
