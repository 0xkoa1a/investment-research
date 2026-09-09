<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

interface Heading {
  id: string
  level: 2 | 3
  title: string
}

const headings = ref<Heading[]>([])
const activeId = ref('')
const mobileOpen = ref(false)
const toc = ref<HTMLElement>()
const markerTop = ref('-2rem')
let animationFrame = 0
let settleTimer: ReturnType<typeof setTimeout> | undefined
let contentObserver: ResizeObserver | undefined

function activeLink(): HTMLElement | null {
  return toc.value?.querySelector<HTMLElement>('.toc-link[aria-current="location"]') ?? null
}

function updateMarker(): void {
  const wrapper = toc.value
  const link = activeLink()
  if (!wrapper || !link) {
    markerTop.value = '-2rem'
    return
  }
  markerTop.value = `${link.offsetTop}px`
}

function keepActiveVisible(): void {
  const wrapper = toc.value
  const link = activeLink()
  if (!wrapper || !link) return
  const top = link.offsetTop
  const bottom = top + link.offsetHeight
  if (top < wrapper.scrollTop) wrapper.scrollTo({ top, behavior: 'smooth' })
  else if (bottom > wrapper.scrollTop + wrapper.clientHeight) {
    wrapper.scrollTo({ top: bottom - wrapper.clientHeight, behavior: 'smooth' })
  }
}

function syncActiveItem(): void {
  nextTick(() => {
    updateMarker()
    keepActiveVisible()
  })
}

function collectHeadings(): void {
  headings.value = Array.from(
    document.querySelectorAll<HTMLHeadingElement>('.article-content :is(h2, h3)[id]'),
  ).map((heading) => ({
    id: heading.id,
    level: Number(heading.tagName.slice(1)) as 2 | 3,
    title: heading.textContent?.trim() ?? '',
  }))
}

function updateActiveHeading(): void {
  animationFrame = 0
  const elements = headings.value
    .map(({ id }) => document.getElementById(id))
    .filter((heading): heading is HTMLElement => Boolean(heading))
  if (!elements.length) return

  const threshold = Math.min(160, window.innerHeight * 0.22)
  let current = elements[0].id
  for (const heading of elements) {
    if (heading.getBoundingClientRect().top > threshold) break
    current = heading.id
  }
  if (document.documentElement.scrollHeight > window.innerHeight + 2
    && window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2) {
    current = elements.at(-1)?.id ?? current
  }
  if (activeId.value !== current) {
    activeId.value = current
    syncActiveItem()
  }
}

function scheduleActiveUpdate(): void {
  if (!animationFrame) animationFrame = requestAnimationFrame(updateActiveHeading)
  if (settleTimer) clearTimeout(settleTimer)
  settleTimer = setTimeout(() => {
    if (!animationFrame) animationFrame = requestAnimationFrame(updateActiveHeading)
  }, 120)
}

watch(mobileOpen, (open) => {
  if (open) syncActiveItem()
})

onMounted(() => {
  collectHeadings()
  contentObserver = new ResizeObserver(scheduleActiveUpdate)
  const content = document.querySelector<HTMLElement>('.article-content')
  if (content) contentObserver.observe(content)
  window.addEventListener('scroll', scheduleActiveUpdate, { passive: true })
  window.addEventListener('resize', scheduleActiveUpdate, { passive: true })
  scheduleActiveUpdate()
})

onBeforeUnmount(() => {
  contentObserver?.disconnect()
  window.removeEventListener('scroll', scheduleActiveUpdate)
  window.removeEventListener('resize', scheduleActiveUpdate)
  if (settleTimer) clearTimeout(settleTimer)
  if (animationFrame) cancelAnimationFrame(animationFrame)
})
</script>

<template>
  <aside v-if="headings.length" class="toc-shell" aria-label="On this page">
    <button
      class="mobile-toc-toggle"
      type="button"
      :aria-expanded="mobileOpen"
      aria-controls="page-outline"
      @click="mobileOpen = !mobileOpen"
    >
      <span>本页目录</span><i aria-hidden="true">⌄</i>
    </button>
    <div id="page-outline" class="toc-panel" :class="{ expanded: mobileOpen }">
      <div class="toc-heading">On this page</div>
      <div ref="toc" class="toc-scroll">
        <nav class="toc">
          <ul class="toc-list">
            <li v-for="heading in headings" :key="heading.id" class="toc-item">
              <a
                class="toc-link"
                :class="`level${heading.level}`"
                :href="`#${heading.id}`"
                :aria-current="activeId === heading.id ? 'location' : undefined"
                @click="activeId = heading.id"
              >{{ heading.title }}</a>
            </li>
          </ul>
        </nav>
        <div class="toc-marker" :style="{ top: markerTop }" aria-hidden="true" />
      </div>
    </div>
  </aside>
</template>
