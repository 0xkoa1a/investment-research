import type { Plugin as VitePlugin } from "vite"

export const portableRouteSentinel = "/__VUEPRESS_PORTABLE_TARGET__.html"

export function portableFileRouterPlugin(): VitePlugin {
  return {
    name: "vuepress-portable-file-router",
    enforce: "pre",
    transform(code, id) {
      const normalizedId = id.split("?", 1)[0]?.replaceAll("\\", "/") ?? ""
      if (!normalizedId.endsWith("/@vuepress/client/dist/app.js")) return

      const historySource =
        "const historyCreator = __VUEPRESS_SSR__ ? createMemoryHistory : createWebHistory;"
      const historyReplacement = "const historyCreator = createMemoryHistory;"
      const startupSource =
        /if \(!__VUEPRESS_SSR__\) createVueApp\(\)\.then\(\(\{ app, router \}\) => \{\n\trouter\.isReady\(\)\.then\(\(\) => \{/
      const startupReplacement = `if (!__VUEPRESS_SSR__) createVueApp().then(async ({ app, router }) => {
\tawait router.replace(${JSON.stringify(portableRouteSentinel)});
\trouter.isReady().then(() => {`

      const withMemoryHistory = code.replace(historySource, historyReplacement)
      if (withMemoryHistory === code) {
        throw new Error(
          "VuePress client router changed: could not enable memory history for portable export",
        )
      }

      const withPortableRoute = withMemoryHistory.replace(
        startupSource,
        startupReplacement,
      )
      if (withPortableRoute === withMemoryHistory) {
        throw new Error(
          "VuePress client startup changed: could not inject the portable page route",
        )
      }

      return { code: withPortableRoute, map: null }
    },
  }
}
