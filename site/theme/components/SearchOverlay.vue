<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { searchItems as items } from 'virtual:content-manifest'

import { filterSearchItems } from '../search.js'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const input = ref<HTMLInputElement | null>(null)
const query = ref('')
let returnFocus: HTMLElement | null = null

const results = computed(() => filterSearchItems(items, query.value))

function close(): void {
  emit('close')
  requestAnimationFrame(() => returnFocus?.focus())
}

function onKeydown(event: KeyboardEvent): void {
  if (props.open && event.key === 'Escape') close()
  if (props.open && ['ArrowDown', 'ArrowUp'].includes(event.key)) {
    event.preventDefault()
    const buttons = [...(input.value?.closest<HTMLElement>('.search-dialog')
      ?.querySelectorAll<HTMLElement>('.search-result') ?? [])]
    if (!buttons.length) return
    const current = buttons.findIndex((button) => button === document.activeElement)
    const offset = event.key === 'ArrowDown' ? 1 : -1
    const next = current < 0
      ? (offset > 0 ? 0 : buttons.length - 1)
      : (current + offset + buttons.length) % buttons.length
    buttons[next]?.focus()
  }
  if (props.open && event.key === 'Tab') {
    const dialog = input.value?.closest<HTMLElement>('.search-dialog')
    const focusable = [...(dialog?.querySelectorAll<HTMLElement>('button, input, [href], [tabindex]:not([tabindex="-1"])') ?? [])]
    if (!focusable.length) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }
}

watch(() => props.open, async (open) => {
  document.documentElement.classList.toggle('search-locked', open)
  if (open) {
    returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    query.value = ''
    await nextTick()
    input.value?.focus()
  }
})

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  document.documentElement.classList.remove('search-locked')
})
</script>

<template>
  <div v-if="open" class="search-backdrop" role="presentation" @mousedown.self="close">
    <section class="search-dialog" role="dialog" aria-modal="true" aria-labelledby="search-title">
      <h2 id="search-title" class="sr-only">全局搜索</h2>
      <div class="search-input-row">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m16.2 16.2 4 4"/></svg>
        <input ref="input" v-model="query" type="search" placeholder="搜索研究" aria-label="搜索词" />
        <button type="button" aria-label="关闭搜索" @click="close">ESC</button>
      </div>
      <div class="search-results" aria-live="polite">
        <RouterLink v-for="item in results" :key="item.path" class="search-result" :to="item.path" @click="close">
          <span class="search-kind">研究</span>
          <strong>{{ item.title }}</strong>
          <span>{{ item.summary }}</span>
        </RouterLink>
        <p v-if="!results.length" class="search-empty">没有匹配内容。</p>
      </div>
    </section>
  </div>
</template>
