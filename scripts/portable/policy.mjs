import { inspectBundledJavaScript } from "./javascript.mjs"

export function isExternalUrl(value) {
  return /^(?:https?:)?\/\//iu.test(value)
}

export function isSpecialUrl(value) {
  return /^(?:data:|blob:|mailto:|tel:|javascript:|#)/iu.test(value)
}

export function collectPortabilityIssues(html, unresolved) {
  const issues = new Set(unresolved)
  const warnings = new Set()
  const documentMarkup = html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/giu, "<script></script>")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/giu, "<style></style>")
  const inspectResourceTag = (tag) => {
    for (const match of tag.matchAll(
      /\b(?:src|srcset|poster|data|href|xlink:href)\s*=\s*(["'])(.*?)\1/giu,
    )) {
      const value = match[2].trim()
      if (!value || isSpecialUrl(value)) continue
      if (isExternalUrl(value)) issues.add("外部资源 " + value)
      else issues.add("未内联资源 " + value)
    }
  }
  const resourceTags =
    /<(?:script|img|source|video|audio|track|iframe|embed|object|use)\b[^>]*>/giu
  for (const tag of documentMarkup.match(resourceTags) ?? []) {
    inspectResourceTag(tag)
  }
  for (const tag of documentMarkup.match(/<link\b[^>]*>/giu) ?? []) {
    const relation = tag.match(/\brel\s*=\s*(["'])(.*?)\1/iu)?.[2] ?? ""
    if (
      /(?:^|\s)(?:stylesheet|icon|manifest|modulepreload|preload|prefetch)(?:\s|$)/iu.test(
        relation,
      )
    ) {
      inspectResourceTag(tag)
    }
  }

  const scripts = [
    ...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/giu),
  ]
  for (const script of scripts) {
    const type = script[1].match(/\btype\s*=\s*(["'])(.*?)\1/iu)?.[2]
    if (type && !/(?:java|ecma)script|module/iu.test(type)) continue
    const inspected = inspectBundledJavaScript(script[2])
    inspected.issues.forEach((issue) => issues.add(issue))
    inspected.warnings.forEach((warning) => warnings.add(warning))
  }

  return {
    issues: [...issues].sort(),
    warnings: [...warnings].sort(),
  }
}

export function collectInternalLinks(html) {
  const links = new Set()
  const documentMarkup = html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/giu, "")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/giu, "")
  for (const match of documentMarkup.matchAll(
    /<a\b[^>]*\bhref\s*=\s*(["'])(.*?)\1/giu,
  )) {
    const value = match[2].trim()
    if (
      value &&
      !isSpecialUrl(value) &&
      !isExternalUrl(value) &&
      !/^(?:mailto:|tel:)/iu.test(value)
    ) {
      links.add(value)
    }
  }
  return [...links].sort()
}

const contentSecurityPolicy = [
  "default-src 'none'",
  "base-uri 'none'",
  "connect-src 'none'",
  "font-src data:",
  "form-action 'none'",
  "frame-src data: blob:",
  "img-src data: blob:",
  "media-src data: blob:",
  "object-src data:",
  "script-src 'unsafe-inline' 'unsafe-eval' blob:",
  "style-src 'unsafe-inline'",
  "worker-src data: blob:",
].join("; ")

const runtimeGuard = [
  "<script>",
  "(() => {",
  "  const blocked = [];",
  "  Object.defineProperty(window, '__PORTABLE_NETWORK_BLOCKS__', { value: blocked });",
  "  const target = (value) => {",
  "    if (typeof Request !== 'undefined' && value instanceof Request) return value.url;",
  "    return String(value ?? '');",
  "  };",
  "  const allowed = (value) => {",
  "    try {",
  "      const url = new URL(target(value), document.baseURI);",
  "      return url.protocol === 'data:' || url.protocol === 'blob:' || url.href === 'about:blank';",
  "    } catch {",
  "      return false;",
  "    }",
  "  };",
  "  const deny = (api, value) => {",
  "    const message = '[portable] blocked ' + api + ': ' + target(value);",
  "    blocked.push(message);",
  "    console.error(message);",
  "    throw new Error(message);",
  "  };",
  "  if (typeof window.fetch === 'function') {",
  "    const original = window.fetch.bind(window);",
  "    window.fetch = (input, init) => allowed(input) ? original(input, init) : Promise.reject((() => { try { deny('fetch', input); } catch (error) { return error; } })());",
  "  }",
  "  if (typeof window.XMLHttpRequest === 'function') {",
  "    const open = window.XMLHttpRequest.prototype.open;",
  "    window.XMLHttpRequest.prototype.open = function(method, url, ...rest) {",
  "      if (!allowed(url)) deny('XMLHttpRequest', url);",
  "      return open.call(this, method, url, ...rest);",
  "    };",
  "  }",
  "  for (const name of ['WebSocket', 'EventSource', 'Worker', 'SharedWorker']) {",
  "    const Original = window[name];",
  "    if (typeof Original !== 'function') continue;",
  "    window[name] = new Proxy(Original, {",
  "      construct(Target, args, NewTarget) {",
  "        if (!allowed(args[0])) deny(name, args[0]);",
  "        return Reflect.construct(Target, args, NewTarget);",
  "      }",
  "    });",
  "  }",
  "  if (typeof navigator.sendBeacon === 'function') {",
  "    const sendBeacon = navigator.sendBeacon.bind(navigator);",
  "    try {",
  "      navigator.sendBeacon = (url, data) => allowed(url) ? sendBeacon(url, data) : (deny('navigator.sendBeacon', url), false);",
  "    } catch {}",
  "  }",
  "})();",
  "</script>",
].join("\n")

export function injectStrictRuntimePolicy(html) {
  const policyMeta =
    '<meta http-equiv="Content-Security-Policy" content="' +
    contentSecurityPolicy +
    '">'
  return html.replace(
    /<head([^>]*)>/iu,
    (match) => match + "\n" + policyMeta + "\n" + runtimeGuard,
  )
}
