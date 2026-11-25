#!/usr/bin/env node

import {
  mkdir,
  mkdtemp,
  readFile,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

import { fail, parseArguments } from "./portable/cli.mjs"
import { inspectPortableSources } from "./portable/javascript.mjs"
import {
  ensureFile,
  isInside,
  pageRouteFromHtml,
  walk,
} from "./portable/paths.mjs"
import {
  collectInternalLinks,
  collectPortabilityIssues,
  injectStrictRuntimePolicy,
} from "./portable/policy.mjs"
import { inlineBuildResources } from "./portable/resources.mjs"
import {
  formatBytes,
  injectMetadata,
  runCommand,
} from "./portable/runtime.mjs"

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.dirname(scriptDir)
const portableRouteSentinel = "/__VUEPRESS_PORTABLE_TARGET__.html"
const packageJson = JSON.parse(
  await readFile(path.join(rootDir, "package.json"), "utf8"),
)

async function totalSize(files) {
  const sizes = await Promise.all(files.map(async (file) => (await stat(file)).size))
  return sizes.reduce((total, size) => total + size, 0)
}

async function main() {
  const options = parseArguments(process.argv.slice(2))
  const sourceDir = path.join(rootDir, "content", "research")
  const pageRelative = options.page.replaceAll("\\", "/")
    .replace(/^(?:\.\/)?(?:content\/)?research\//u, "")
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*\.md$/u.test(pageRelative)) {
    fail("请指定 content/research/ 下的报告，例如 technical-analysis.md")
  }
  const sourcePath = path.join(sourceDir, pageRelative)
  await ensureFile(sourcePath)

  const defaultOutput = path.join(
    rootDir,
    "_exports",
    pageRelative.replace(/\.md$/iu, ".html"),
  )
  const outputPath = path.resolve(rootDir, options.output ?? defaultOutput)
  if (!isInside(rootDir, outputPath)) {
    fail("导出目标必须位于仓库内")
  }
  if (path.extname(outputPath).toLowerCase() !== ".html") {
    fail("导出目标必须是 .html 文件")
  }

  const sourceLabel = "content/research/" + pageRelative
  const sourceIssues = await inspectPortableSources({ sourcePath, sourceLabel })
  if (sourceIssues.length && !options.allowExternal) {
    fail("作者源码包含运行时网络依赖：\n- " + sourceIssues.join("\n- "))
  }
  if (sourceIssues.length) {
    console.warn(
      "\n允许的作者源码网络依赖：\n- " + sourceIssues.join("\n- "),
    )
  }

  const workDirectory = await mkdtemp(path.join(rootDir, ".vuepress-export-"))
  const buildDirectory = path.join(workDirectory, "dist")
  const tempDirectory = path.join(workDirectory, "temp")
  const cacheDirectory = path.join(workDirectory, "cache")

  try {
    console.log("\n导出 " + pageRelative)
    // VuePress writes its compiled config beside the entry file. Give each export its own entry.
    const configPath = path.join(workDirectory, "vuepress.config.ts")
    await writeFile(configPath, 'export { default } from "../vuepress.config.ts"\n')
    const vuepressBin = path.join(
      rootDir,
      "node_modules",
      ".bin",
      process.platform === "win32" ? "vuepress.cmd" : "vuepress",
    )
    await runCommand(
      vuepressBin,
      ["build", ".", "--config", configPath],
      {
        cwd: rootDir,
        env: {
          ...process.env,
          VUEPRESS_EXPORT_CACHE: cacheDirectory,
          VUEPRESS_EXPORT_DEST: buildDirectory,
          VUEPRESS_EXPORT_PAGE: pageRelative,
          VUEPRESS_EXPORT_TEMP: tempDirectory,
          VUEPRESS_PORTABLE_EXPORT: "1",
          VITE_PORTABLE_EXPORT: "1",
        },
      },
    )

    const buildFiles = await walk(buildDirectory)
    const htmlFiles = buildFiles.filter(
      (file) => file.endsWith(".html") && path.basename(file) !== "404.html",
    )
    if (htmlFiles.length !== 1) {
      fail("预期一个页面 HTML，实际找到 " + htmlFiles.length + " 个")
    }

    const htmlPath = htmlFiles[0]
    const route = pageRouteFromHtml(buildDirectory, htmlPath)
    let html = await readFile(htmlPath, "utf8")
    const inlined = await inlineBuildResources(
      html,
      htmlPath,
      buildDirectory,
      route,
      portableRouteSentinel,
    )
    html = inlined.html

    const audit = collectPortabilityIssues(html, inlined.unresolved)
    if (audit.issues.length && !options.allowExternal) {
      fail("页面不是完全自包含：\n- " + audit.issues.join("\n- "))
    }
    if (audit.issues.length) {
      console.warn(
        "\n允许的非自包含依赖：\n- " + audit.issues.join("\n- "),
      )
    }
    if (audit.warnings.length) {
      console.warn("\n运行期审计提示：\n- " + audit.warnings.join("\n- "))
    }

    const internalLinks = collectInternalLinks(html)
    if (internalLinks.length) {
      console.warn(
        "\n离线时可能不可用的站内链接：\n- " +
          internalLinks.join("\n- "),
      )
    }

    if (!options.allowExternal) html = injectStrictRuntimePolicy(html)
    html = await injectMetadata({
      html,
      packageJson,
      rootDirectory: rootDir,
      sourceLabel,
    })

    await mkdir(path.dirname(outputPath), { recursive: true })
    const atomicPath = outputPath + ".tmp-" + process.pid
    try {
      await writeFile(atomicPath, html)
      await rename(atomicPath, outputPath)
    } finally {
      await rm(atomicPath, { force: true })
    }

    const javascriptBytes = await totalSize(
      buildFiles.filter((file) => file.endsWith(".js")),
    )
    const cssBytes = await totalSize(
      buildFiles.filter((file) => file.endsWith(".css")),
    )
    const finalBytes = (await stat(outputPath)).size

    console.log("\n资源体积")
    console.log("  JavaScript  " + formatBytes(javascriptBytes))
    console.log("  CSS         " + formatBytes(cssBytes))
    console.log("  单文件 HTML " + formatBytes(finalBytes))
    if (finalBytes > 25 * 1024 ** 2) {
      console.warn("  警告：导出文件超过 25 MiB")
    } else if (finalBytes > 10 * 1024 ** 2) {
      console.warn("  提示：导出文件超过 10 MiB")
    }
    console.log("\n已生成 " + path.relative(rootDir, outputPath))
  } finally {
    await rm(workDirectory, { recursive: true, force: true })
  }
}

main().catch((error) => {
  console.error("\n导出失败：" + error.message)
  process.exitCode = 1
})
