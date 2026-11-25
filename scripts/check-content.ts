import path from 'node:path'

import { buildContentManifest, validateCatalogs } from '../site/content.js'

const root = path.resolve(import.meta.dirname, '..')
const errors: string[] = []

try {
  validateCatalogs(root)
  const manifest = buildContentManifest(root)
  console.log(`[content-check] ${manifest.research.length} 篇研究`)
} catch (error) {
  errors.push(error instanceof Error ? error.message : String(error))
}

if (errors.length) {
  for (const error of errors) console.error(`[content-check] FAIL: ${error}`)
  process.exit(1)
}
