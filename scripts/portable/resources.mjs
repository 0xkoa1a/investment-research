import { readFile, stat } from "node:fs/promises"
import path from "node:path"

import { fail } from "./cli.mjs"
import { isInside, replaceAsync } from "./paths.mjs"
import { isExternalUrl, isSpecialUrl } from "./policy.mjs"

const mimeTypes = new Map([
  [".avif", "image/avif"],
  [".css", "text/css"],
  [".gif", "image/gif"],
  [".ico", "image/x-icon"],
  [".jpeg", "image/jpeg"],
  [".jpg", "image/jpeg"],
  [".js", "text/javascript"],
  [".json", "application/json"],
  [".mp3", "audio/mpeg"],
  [".mp4", "video/mp4"],
  [".ogg", "audio/ogg"],
  [".otf", "font/otf"],
  [".pdf", "application/pdf"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".ttf", "font/ttf"],
  [".wav", "audio/wav"],
  [".webm", "video/webm"],
  [".webp", "image/webp"],
  [".woff", "font/woff"],
  [".woff2", "font/woff2"],
])

function splitUrl(value) {
  const match = value.match(/^([^?#]*)(\?[^#]*)?(#.*)?$/u)
  return {
    fragment: match?.[3] ?? "",
    pathname: match?.[1] ?? value,
  }
}

async function resolveLocalAsset(value, baseDirectory, buildDirectory) {
  if (!value || isExternalUrl(value) || isSpecialUrl(value)) return null
  if (/^[a-z][a-z\d+.-]*:/iu.test(value)) return null

  const { fragment, pathname: rawPathname } = splitUrl(value)
  let pathname
  try {
    pathname = decodeURIComponent(rawPathname)
  } catch {
    pathname = rawPathname
  }

  const candidate = pathname.startsWith("/")
    ? path.resolve(buildDirectory, "." + pathname)
    : path.resolve(baseDirectory, pathname)
  if (!isInside(buildDirectory, candidate)) return null

  try {
    if (!(await stat(candidate)).isFile()) return null
  } catch {
    return null
  }
  return { filePath: candidate, fragment }
}

async function assetToDataUrl(asset) {
  const content = await readFile(asset.filePath)
  const mimeType =
    mimeTypes.get(path.extname(asset.filePath).toLowerCase()) ??
    "application/octet-stream"
  return (
    "data:" +
    mimeType +
    ";base64," +
    content.toString("base64") +
    asset.fragment
  )
}

async function inlineCssImports(
  css,
  cssFile,
  buildDirectory,
  unresolved,
  seen,
) {
  return replaceAsync(
    css,
    /@import\s+(?:url\(\s*)?(["'])(.*?)\1\s*\)?\s*([^;]*);/giu,
    async (fullMatch, _quote, value, mediaQuery) => {
      const trimmed = value.trim()
      if (!trimmed || isSpecialUrl(trimmed)) return fullMatch
      if (isExternalUrl(trimmed)) {
        unresolved.add("CSS 外部 @import " + trimmed)
        return fullMatch
      }
      const asset = await resolveLocalAsset(
        trimmed,
        path.dirname(cssFile),
        buildDirectory,
      )
      if (!asset) {
        unresolved.add("CSS @import " + trimmed)
        return fullMatch
      }
      if (seen.has(asset.filePath)) {
        unresolved.add("CSS 循环 @import " + trimmed)
        return fullMatch
      }
      const nextSeen = new Set(seen).add(asset.filePath)
      let imported = await readFile(asset.filePath, "utf8")
      imported = await inlineCss(
        imported,
        asset.filePath,
        buildDirectory,
        unresolved,
        nextSeen,
      )
      const media = mediaQuery.trim()
      if (/\b(?:layer|supports)\b/iu.test(media)) {
        unresolved.add("CSS 条件 @import " + trimmed)
        return fullMatch
      }
      return media ? "@media " + media + " {\n" + imported + "\n}" : imported
    },
  )
}

async function inlineCss(
  css,
  cssFile,
  buildDirectory,
  unresolved,
  seen = new Set([cssFile]),
) {
  css = await inlineCssImports(
    css,
    cssFile,
    buildDirectory,
    unresolved,
    seen,
  )
  const cssDirectory = path.dirname(cssFile)
  return replaceAsync(
    css,
    /url\(\s*(?:(['"])(.*?)\1|([^)'"\s][^)]*?))\s*\)/giu,
    async (fullMatch, _quote, quotedValue, bareValue) => {
      const value = (quotedValue ?? bareValue ?? "").trim()
      const normalizedValue = value
        .replace(/^(?:&quot;|&#34;|&#x22;|&apos;|&#39;|&#x27;)/iu, "")
        .replace(/(?:&quot;|&#34;|&#x22;|&apos;|&#39;|&#x27;)$/iu, "")
      if (!normalizedValue || isSpecialUrl(normalizedValue)) return fullMatch
      if (isExternalUrl(normalizedValue)) {
        unresolved.add("CSS 外部资源 " + normalizedValue)
        return fullMatch
      }
      const asset = await resolveLocalAsset(
        normalizedValue,
        cssDirectory,
        buildDirectory,
      )
      if (!asset) {
        unresolved.add("CSS url(" + normalizedValue + ")")
        return fullMatch
      }
      return 'url("' + (await assetToDataUrl(asset)) + '")'
    },
  )
}

async function inlineAttributeValue(
  value,
  htmlDirectory,
  buildDirectory,
  unresolved,
) {
  if (isSpecialUrl(value) || isExternalUrl(value)) return value
  const asset = await resolveLocalAsset(value, htmlDirectory, buildDirectory)
  if (!asset) {
    unresolved.add(value)
    return value
  }
  return assetToDataUrl(asset)
}

async function inlineSrcset(
  value,
  htmlDirectory,
  buildDirectory,
  unresolved,
) {
  if (/^\s*data:/iu.test(value)) return value
  const candidates = value.split(",")
  const inlined = await Promise.all(
    candidates.map(async (candidate) => {
      const match = candidate.trim().match(/^(\S+)(\s+.*)?$/u)
      if (!match) return candidate
      const url = await inlineAttributeValue(
        match[1],
        htmlDirectory,
        buildDirectory,
        unresolved,
      )
      return url + (match[2] ?? "")
    }),
  )
  return inlined.join(", ")
}

async function inlineResourceTags(html, htmlPath, buildDirectory, unresolved) {
  const htmlDirectory = path.dirname(htmlPath)
  const resourceTagPattern =
    /<(?:img|source|video|audio|track|input|embed|object|use)\b[^>]*>/giu

  return replaceAsync(html, resourceTagPattern, async (tag) => {
    let output = await replaceAsync(
      tag,
      /\b(src|poster|data|href|xlink:href)\s*=\s*(["'])(.*?)\2/giu,
      async (_attribute, name, quote, value) =>
        name +
        "=" +
        quote +
        (await inlineAttributeValue(
          value,
          htmlDirectory,
          buildDirectory,
          unresolved,
        )) +
        quote,
    )
    output = await replaceAsync(
      output,
      /\bsrcset\s*=\s*(["'])(.*?)\1/giu,
      async (_attribute, quote, value) =>
        "srcset=" +
        quote +
        (await inlineSrcset(
          value,
          htmlDirectory,
          buildDirectory,
          unresolved,
        )) +
        quote,
    )
    return output
  })
}

async function inlineLoadedLinks(html, htmlPath, buildDirectory, unresolved) {
  const htmlDirectory = path.dirname(htmlPath)
  return replaceAsync(html, /<link\b[^>]*>/giu, async (tag) => {
    const relation = tag.match(/\brel\s*=\s*(["'])(.*?)\1/iu)?.[2] ?? ""
    if (!/(?:^|\s)(?:icon|manifest)(?:\s|$)/iu.test(relation)) return tag
    return replaceAsync(
      tag,
      /\bhref\s*=\s*(["'])(.*?)\1/giu,
      async (_attribute, quote, value) =>
        "href=" +
        quote +
        (await inlineAttributeValue(
          value,
          htmlDirectory,
          buildDirectory,
          unresolved,
        )) +
        quote,
    )
  })
}

function escapeClosingTag(value, tagName) {
  return value.replace(
    new RegExp("</" + tagName, "giu"),
    "<\\/" + tagName,
  )
}

export async function inlineBuildResources(
  html,
  htmlPath,
  buildDirectory,
  route,
  portableRouteSentinel,
) {
  const unresolved = new Set()
  const htmlDirectory = path.dirname(htmlPath)
  const stylesheetLinks = [
    ...html.matchAll(
      /<link\b(?=[^>]*\brel=["']stylesheet["'])(?=[^>]*\bhref=["']([^"']+)["'])[^>]*>/giu,
    ),
  ]
  for (const match of stylesheetLinks) {
    const asset = await resolveLocalAsset(
      match[1],
      htmlDirectory,
      buildDirectory,
    )
    if (!asset) {
      unresolved.add("stylesheet " + match[1])
      continue
    }
    let css = await readFile(asset.filePath, "utf8")
    css = await inlineCss(css, asset.filePath, buildDirectory, unresolved)
    html = html.replace(
      match[0],
      () => "<style>" + escapeClosingTag(css, "style") + "</style>",
    )
  }

  html = html.replace(
    /<link\b(?=[^>]*\brel=["'](?:modulepreload|preload|prefetch)["'])[^>]*>/giu,
    "",
  )
  html = await inlineLoadedLinks(html, htmlPath, buildDirectory, unresolved)
  html = await inlineResourceTags(html, htmlPath, buildDirectory, unresolved)
  html = await replaceAsync(
    html,
    /<style\b[^>]*>([\s\S]*?)<\/style>/giu,
    async (fullMatch, css) => {
      const inlined = await inlineCss(
        css,
        htmlPath,
        buildDirectory,
        unresolved,
      )
      return fullMatch.replace(css, () => escapeClosingTag(inlined, "style"))
    },
  )
  html = await replaceAsync(
    html,
    /\bstyle\s*=\s*(["'])(.*?)\1/giu,
    async (_fullMatch, quote, css) =>
      "style=" +
      quote +
      (await inlineCss(css, htmlPath, buildDirectory, unresolved)) +
      quote,
  )

  const moduleScripts = [
    ...html.matchAll(
      /<script\b(?=[^>]*\btype=["']module["'])(?=[^>]*\bsrc=["']([^"']+)["'])[^>]*><\/script>/giu,
    ),
  ]
  if (moduleScripts.length !== 1) {
    fail("预期一个 VuePress 客户端入口，实际找到 " + moduleScripts.length + " 个")
  }
  for (const match of moduleScripts) {
    const asset = await resolveLocalAsset(
      match[1],
      htmlDirectory,
      buildDirectory,
    )
    if (!asset) fail("找不到客户端入口：" + match[1])
    let javascript = await readFile(asset.filePath, "utf8")
    if (!javascript.includes(portableRouteSentinel)) {
      fail("客户端入口缺少 portable route 标记，无法保证 file:// 路由")
    }
    const routeLiteral = JSON.stringify(route).slice(1, -1)
    javascript = javascript.replaceAll(
      portableRouteSentinel,
      () => routeLiteral,
    )
    html = html.replace(
      match[0],
      () =>
        '<script type="module">' +
        escapeClosingTag(javascript, "script") +
        "</script>",
    )
  }

  const additionalScripts = [
    ...html.matchAll(
      /<script\b(?=[^>]*\bsrc=["']([^"']+)["'])[^>]*><\/script>/giu,
    ),
  ]
  for (const match of additionalScripts) {
    const asset = await resolveLocalAsset(
      match[1],
      htmlDirectory,
      buildDirectory,
    )
    if (!asset) {
      unresolved.add("script " + match[1])
      continue
    }
    const javascript = await readFile(asset.filePath, "utf8")
    html = html.replace(
      match[0],
      () => "<script>" + escapeClosingTag(javascript, "script") + "</script>",
    )
  }

  return { html, unresolved }
}
