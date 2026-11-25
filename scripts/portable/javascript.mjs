import { readFile } from "node:fs/promises"

import ts from "typescript"

const networkFunctions = new Set(["fetch", "sendBeacon"])
const networkConstructors = new Set(["EventSource", "SharedWorker", "WebSocket", "Worker"])
const isInlineRuntimeUrl = (value) => /^(?:data:|blob:|about:blank|#)/iu.test(value.trim())

function callName(expression) {
  if (ts.isIdentifier(expression)) return expression.text
  if (ts.isPropertyAccessExpression(expression)) return expression.name.text
  return null
}

function literal(node) {
  return node && (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node))
    ? node.text
    : null
}

function inspect(source, fileName, bundled) {
  const issues = new Set()
  const warnings = new Set()
  const script = ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, false)
  if (script.parseDiagnostics.length) {
    const message = ts.flattenDiagnosticMessageText(script.parseDiagnostics[0].messageText, " ")
    issues.add(fileName + ": 脚本无法解析：" + message)
    return { issues: [...issues], warnings: [] }
  }

  function report(node, api, argument) {
    const url = literal(argument)
    if (api !== "import" && url !== null && isInlineRuntimeUrl(url)) return
    if (bundled) {
      if (api === "import") issues.add("仍存在脚本模块依赖：" + (url ?? "动态参数"))
      else if (url !== null) issues.add("运行时资源 " + api + "(" + url + ")")
      else warnings.add("产物包含 " + api + "(动态参数)，由运行期断网守卫兜底")
      return
    }
    const { line } = script.getLineAndCharacterOfPosition(node.getStart(script))
    issues.add(fileName + ":" + (line + 1) + ": 运行时网络 API " + api + "(" + (url ?? "动态参数") + ")")
  }

  function visit(node) {
    if (ts.isImportDeclaration(node) || (ts.isExportDeclaration(node) && node.moduleSpecifier)) {
      if (bundled) report(node, "import", node.moduleSpecifier)
    } else if (ts.isCallExpression(node)) {
      const name = callName(node.expression)
      if (networkFunctions.has(name)) report(node, name, node.arguments[0])
      else if (node.expression.kind === ts.SyntaxKind.ImportKeyword) report(node, "import", node.arguments[0])
    } else if (ts.isNewExpression(node)) {
      const name = callName(node.expression)
      if (networkConstructors.has(name)) report(node, name, node.arguments?.[0])
    }
    ts.forEachChild(node, visit)
  }
  visit(script)
  return { issues: [...issues], warnings: [...warnings] }
}

export async function inspectPortableSources({ sourcePath, sourceLabel }) {
  const source = await readFile(sourcePath, "utf8")
  return [...source.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/giu)]
    .flatMap((match, index) => inspect(match[1], sourceLabel + "#script-" + (index + 1) + ".ts", false).issues)
}

export function inspectBundledJavaScript(source) {
  return inspect(source, "bundle.js", true)
}
