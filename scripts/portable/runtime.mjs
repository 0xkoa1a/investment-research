import { spawn } from "node:child_process"

export async function runCommand(command, args, options = {}) {
  await new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: "inherit", ...options })
    child.once("error", reject)
    child.once("exit", (code, signal) => {
      if (code === 0) resolve()
      else {
        reject(
          new Error(
            command + " 失败（code=" + code + ", signal=" + signal + "）",
          ),
        )
      }
    })
  })
}

export async function gitValue(rootDirectory, args, fallback) {
  return new Promise((resolve) => {
    const child = spawn("git", args, {
      cwd: rootDirectory,
      stdio: ["ignore", "pipe", "ignore"],
    })
    let output = ""
    child.stdout.on("data", (chunk) => {
      output += chunk
    })
    child.once("error", () => resolve(fallback))
    child.once("exit", (code) =>
      resolve(code === 0 ? output.trim() : fallback),
    )
  })
}

export function formatBytes(bytes) {
  if (bytes < 1024) return bytes + " B"
  if (bytes < 1024 ** 2) return (bytes / 1024).toFixed(1) + " KiB"
  return (bytes / 1024 ** 2).toFixed(1) + " MiB"
}

const escapeHtmlAttribute = (value) =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")

export async function injectMetadata({
  html,
  packageJson,
  rootDirectory,
  sourceLabel,
}) {
  const commit = await gitValue(
    rootDirectory,
    ["rev-parse", "HEAD"],
    "unknown",
  )
  const dirty = Boolean(
    await gitValue(rootDirectory, ["status", "--porcelain"], ""),
  )
  const generatedAt = new Date().toISOString()
  const metadata = [
    '<meta name="portable-source" content="' +
      escapeHtmlAttribute(sourceLabel) +
      '">',
    '<meta name="portable-commit" content="' +
      escapeHtmlAttribute(commit) +
      '">',
    '<meta name="portable-dirty" content="' + dirty + '">',
    '<meta name="portable-generated-at" content="' +
      generatedAt +
      '">',
    '<meta name="portable-exporter" content="' +
      escapeHtmlAttribute(packageJson.name + "@" + packageJson.version) +
      '">',
    "<!-- portable-export source=" +
      sourceLabel +
      " commit=" +
      commit +
      " dirty=" +
      dirty +
      " generated=" +
      generatedAt +
      " -->",
  ].join("\n")
  return html.replace("</head>", () => metadata + "\n</head>")
}
