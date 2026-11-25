import { defineClientConfig } from 'vuepress/client'

import 'katex/dist/katex.min.css'
import './styles.css'

import Layout from './layouts/Layout.vue'
import NotFound from './layouts/NotFound.vue'

export default defineClientConfig({
  layouts: {
    Layout,
    NotFound,
  },
})
