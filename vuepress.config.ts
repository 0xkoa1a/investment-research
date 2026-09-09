import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { katex } from '@mdit/plugin-katex'
import { viteBundler } from '@vuepress/bundler-vite'
import { defineUserConfig } from 'vuepress'
import type { PageOptions, Plugin } from 'vuepress/core'

import { buildContentManifest, contentPagePatterns, contentRoute } from './site/content.js'

const root = path.dirname(fileURLToPath(import.meta.url))
const researchDir = path.join(root, 'content', 'research')
const contentManifestId = 'virtual:content-manifest'
const resolvedContentManifestId = `\0${contentManifestId}`
const repositoryName = process.env.GITHUB_REPOSITORY?.split('/')[1] ?? ''
const inferredBase = process.env.GITHUB_ACTIONS === 'true' && repositoryName ? `/${repositoryName}/` : '/'
const base = (process.env.VUEPRESS_BASE ?? inferredBase) as `/${string}/`
if (!base.startsWith('/') || !base.endsWith('/')) {
  throw new Error(`VUEPRESS_BASE 必须以 / 开头和结尾，当前为 ${base}`)
}

const contentRoutes: Plugin = {
  name: 'content-routes',
  extendsPageOptions(options: PageOptions) {
    if (!options.filePath) return
    const route = contentRoute(root, options.filePath)
    if (route) options.path = route
  },
}

export default defineUserConfig({
  base,
  lang: 'zh-CN',
  title: '投资研究',
  description: '长期研究、事件分析与方法记录',
  dest: path.join(root, '_site'),
  temp: path.join(root, '.cache/vuepress-temp'),
  cache: path.join(root, '.cache/vuepress-cache'),
  public: path.join(root, 'content/_assets'),
  pagePatterns: [...contentPagePatterns],
  bundler: viteBundler({
    viteOptions: {
      build: { chunkSizeWarningLimit: 5000 },
      plugins: [{
        name: 'content-manifest',
        resolveId(id) {
          return id === contentManifestId ? resolvedContentManifestId : undefined
        },
        load(id) {
          if (id !== resolvedContentManifestId) return undefined
          const manifest = buildContentManifest(root)
          return [
            `export const researchItems = ${JSON.stringify(manifest.research)}`,
            `export const searchItems = ${JSON.stringify(manifest.search)}`,
          ].join('\n')
        },
        configureServer(server) {
          let timer: ReturnType<typeof setTimeout> | undefined
          const contentRoot = `${researchDir}${path.sep}`
          const refresh = (_event: string, file: string): void => {
            const absolute = path.resolve(file)
            if (!absolute.endsWith('.md') || !absolute.startsWith(contentRoot)) return
            if (path.basename(absolute).startsWith('_')) return
            if (timer) clearTimeout(timer)
            timer = setTimeout(() => {
              const module = server.moduleGraph.getModuleById(resolvedContentManifestId)
              if (module) server.moduleGraph.invalidateModule(module)
              server.ws.send({ type: 'full-reload', path: '*' })
            }, 180)
          }
          server.watcher.add(researchDir)
          server.watcher.on('all', refresh)
          server.httpServer?.once('close', () => {
            if (timer) clearTimeout(timer)
            server.watcher.off('all', refresh)
          })
        },
      }],
    },
  }),
  theme: {
    name: 'vuepress-theme-investment-research',
    clientConfigFile: path.join(root, 'site/theme/client.ts'),
  },
  plugins: [
    contentRoutes,
  ],
  extendsMarkdown: (md) => {
    md.use(katex)
  },
  head: [
    ['meta', { name: 'theme-color', content: '#ffffff' }],
    ['meta', { name: 'color-scheme', content: 'light' }],
    ['link', {
      rel: 'icon',
      href: 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22%3E%3Crect width=%2264%22 height=%2264%22 rx=%2210%22 fill=%22%230d2142%22/%3E%3Ctext x=%2232%22 y=%2242%22 text-anchor=%22middle%22 font-family=%22Georgia,serif%22 font-size=%2232%22 fill=%22%23d59a2a%22%3EIR%3C/text%3E%3C/svg%3E',
    }],
  ],
})
