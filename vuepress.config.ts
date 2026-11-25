import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { katex } from '@mdit/plugin-katex'
import { viteBundler } from '@vuepress/bundler-vite'
import { defineUserConfig } from 'vuepress'
import type { PageOptions, Plugin } from 'vuepress/core'

import { buildContentManifest, contentPagePatterns, contentRoute, reportPageSource } from './site/content.js'
import { portableFileRouterPlugin } from './site/portable-file-router.js'

const root = path.dirname(fileURLToPath(import.meta.url))
const researchDir = path.join(root, 'content', 'research')
const contentManifestId = 'virtual:content-manifest'
const resolvedContentManifestId = `\0${contentManifestId}`
const isPortableExport = process.env.VUEPRESS_PORTABLE_EXPORT === '1'
const portablePage = process.env.VUEPRESS_EXPORT_PAGE
if (isPortableExport && !/^[a-z0-9]+(?:-[a-z0-9]+)*\.md$/u.test(portablePage ?? '')) {
  throw new Error('VUEPRESS_EXPORT_PAGE 必须指向一篇研究报告')
}

const repositoryName = process.env.GITHUB_REPOSITORY?.split('/')[1] ?? ''
const inferredBase = process.env.GITHUB_ACTIONS === 'true' && repositoryName ? `/${repositoryName}/` : '/'
const base = (isPortableExport ? '/' : process.env.VUEPRESS_BASE ?? inferredBase) as `/${string}/`
if (!base.startsWith('/') || !base.endsWith('/')) {
  throw new Error(`VUEPRESS_BASE 必须以 / 开头和结尾，当前为 ${base}`)
}

const contentRoutes: Plugin = {
  name: 'content-routes',
  extendsPageOptions(options: PageOptions) {
    if (!options.filePath) return
    const route = contentRoute(root, options.filePath)
    if (!route) return
    options.path = route
    if (route !== '/') {
      const page = reportPageSource(readFileSync(options.filePath, 'utf8'))
      options.frontmatter = { ...options.frontmatter, ...page.frontmatter }
      options.content = page.content
    }
  },
}

export default defineUserConfig({
  base,
  lang: 'zh-CN',
  title: '投资研究',
  description: '长期研究、事件分析与方法记录',
  dest: isPortableExport ? process.env.VUEPRESS_EXPORT_DEST : path.join(root, '_site'),
  temp: isPortableExport ? process.env.VUEPRESS_EXPORT_TEMP : path.join(root, '.cache/vuepress-temp'),
  cache: isPortableExport ? process.env.VUEPRESS_EXPORT_CACHE : path.join(root, '.cache/vuepress-cache'),
  shouldPreload: isPortableExport ? false : undefined,
  shouldPrefetch: isPortableExport ? false : undefined,
  pagePatterns: isPortableExport ? [`content/research/${portablePage}`] : [...contentPagePatterns],
  bundler: viteBundler({
    viteOptions: {
      // VS Code inserts screenshot links as images/<report>/<file>.
      resolve: { alias: { images: path.join(researchDir, 'images') } },
      build: {
        chunkSizeWarningLimit: 5000,
        ...(isPortableExport && {
          assetsInlineLimit: () => true,
          cssCodeSplit: false,
          modulePreload: false,
          rolldownOptions: { output: { codeSplitting: false } },
        }),
      },
      plugins: [
        ...(isPortableExport ? [portableFileRouterPlugin()] : []),
        {
          name: 'content-manifest',
          resolveId(id) {
            return id === contentManifestId ? resolvedContentManifestId : undefined
          },
          load(id) {
            if (id !== resolvedContentManifestId) return undefined
            if (isPortableExport) return 'export const researchItems = [], searchItems = []'
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
        },
      ],
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
