import { constants as fsConstants } from "node:fs"
import { access, readdir, stat } from "node:fs/promises"
import path from "node:path"

import { fail } from "./cli.mjs"

export function isInside(parent, candidate) {
  const relative = path.relative(parent, candidate)
  return (
    relative !== ".." &&
    !relative.startsWith(".." + path.sep) &&
    !path.isAbsolute(relative)
  )
}

export async function ensureFile(filePath) {
  await access(filePath, fsConstants.R_OK)
  if (!(await stat(filePath)).isFile()) fail("不是文件：" + filePath)
}

export async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const absolute = path.join(directory, entry.name)
    if (entry.isDirectory()) files.push(...(await walk(absolute)))
    else if (entry.isFile()) files.push(absolute)
  }
  return files
}

export function toPosix(value) {
  return value.split(path.sep).join("/")
}

export function pageRouteFromHtml(buildDir, htmlPath) {
  const relative = toPosix(path.relative(buildDir, htmlPath))
  if (relative === "index.html") return "/"
  if (relative.endsWith("/index.html")) {
    return "/" + relative.slice(0, -"index.html".length)
  }
  return "/" + relative
}

export function replaceAsync(value, pattern, replacer) {
  const matches = [...value.matchAll(pattern)]
  if (!matches.length) return Promise.resolve(value)
  return Promise.all(matches.map((match) => replacer(...match))).then(
    (replacements) => {
      let cursor = 0
      let output = ""
      for (let index = 0; index < matches.length; index += 1) {
        const match = matches[index]
        output += value.slice(cursor, match.index) + replacements[index]
        cursor = match.index + match[0].length
      }
      return output + value.slice(cursor)
    },
  )
}
