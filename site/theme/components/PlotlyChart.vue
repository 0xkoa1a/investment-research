<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { usePageData, withBase } from 'vuepress/client'

interface PlotPayload {
  data: unknown[]
  layout: Record<string, unknown>
}

interface PlotlyRuntime {
  newPlot: (
    element: HTMLElement,
    data: unknown[],
    layout: Record<string, unknown>,
    config: Record<string, unknown>,
  ) => Promise<unknown>
  purge: (element: HTMLElement) => void
  Plots: { resize: (element: HTMLElement) => void }
}

const props = defineProps<{
  chart: string
  caption: string
}>()

const page = usePageData()
const report = computed(() => page.value.path.match(/^\/research\/([a-z0-9]+(?:-[a-z0-9]+)*)\.html$/u)?.[1] ?? '')
const source = computed(() => report.value ? withBase(`/plots/${report.value}/${props.chart}.json`) : '')
const captionId = `plot-caption-${useId().replace(/[^a-z0-9-]/giu, '')}`

const state = ref<'loading' | 'ready' | 'missing' | 'invalid' | 'error'>('loading')
const chartElement = ref<HTMLElement | null>(null)
let plotly: PlotlyRuntime | undefined
let resizeObserver: ResizeObserver | undefined
let controller: AbortController | undefined
let disposed = false

function payloadIsValid(value: unknown): value is PlotPayload {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const payload = value as Record<string, unknown>
  return Array.isArray(payload.data)
    && Boolean(payload.layout)
    && typeof payload.layout === 'object'
    && !Array.isArray(payload.layout)
}

onMounted(async () => {
  controller = new AbortController()
  try {
    if (!source.value) {
      state.value = 'invalid'
      return
    }
    const response = await fetch(source.value, { signal: controller.signal })
    if (!response.ok) {
      state.value = 'missing'
      return
    }
    const payload: unknown = await response.json()
    if (!payloadIsValid(payload)) {
      state.value = 'invalid'
      return
    }
    const runtime = (await import('plotly.js-dist-min')).default as PlotlyRuntime
    if (disposed || !chartElement.value) return
    plotly = runtime
    const { title: _title, height: _height, ...snapshotLayout } = payload.layout
    const margin = typeof snapshotLayout.margin === 'object' && snapshotLayout.margin && !Array.isArray(snapshotLayout.margin)
      ? snapshotLayout.margin as Record<string, unknown>
      : {}
    const layout = {
      ...snapshotLayout,
      autosize: true,
      margin: { l: 54, r: 34, t: 52, b: 52, ...margin },
    }
    const mobile = window.matchMedia('(max-width: 760px)').matches
    await plotly.newPlot(chartElement.value, payload.data, layout, {
      responsive: false,
      displaylogo: false,
      displayModeBar: mobile ? false : 'hover',
      scrollZoom: false,
      modeBarButtonsToRemove: ['lasso2d', 'select2d', 'sendDataToCloud', 'toggleSpikelines'],
    })
    if (disposed || !chartElement.value) return
    state.value = 'ready'
    resizeObserver = new ResizeObserver(() => {
      if (chartElement.value && state.value === 'ready') plotly?.Plots.resize(chartElement.value)
    })
    resizeObserver.observe(chartElement.value)
  } catch (error) {
    if (!disposed && !(error instanceof DOMException && error.name === 'AbortError')) {
      state.value = error instanceof SyntaxError ? 'invalid' : 'error'
    }
  }
})

onBeforeUnmount(() => {
  disposed = true
  controller?.abort()
  resizeObserver?.disconnect()
  if (plotly && chartElement.value) plotly.purge(chartElement.value)
})
</script>

<template>
  <figure class="plotly-figure">
    <div class="plotly-frame">
      <div ref="chartElement" class="plotly-chart" role="group" aria-label="交互式图表" :aria-describedby="captionId" />
      <div v-if="state === 'loading'" class="chart-state" role="status">图表加载中…</div>
      <div v-else-if="state === 'missing'" class="chart-state error" role="alert">图表文件缺失：{{ chart }}</div>
      <div v-else-if="state === 'invalid'" class="chart-state error" role="alert">图表引用或 JSON 无效：{{ chart }}</div>
      <div v-else-if="state === 'error'" class="chart-state error" role="alert">图表渲染失败：{{ chart }}</div>
    </div>
    <figcaption :id="captionId">{{ caption }}</figcaption>
  </figure>
</template>
