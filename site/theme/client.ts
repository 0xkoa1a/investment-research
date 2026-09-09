import { defineClientConfig } from 'vuepress/client'

import 'katex/dist/katex.min.css'
import './styles.css'

import PlotlyChart from './components/PlotlyChart.vue'
import Layout from './layouts/Layout.vue'
import NotFound from './layouts/NotFound.vue'

export default defineClientConfig({
  enhance({ app }) {
    app.component('PlotlyChart', PlotlyChart)
  },
  layouts: {
    Layout,
    NotFound,
  },
})
