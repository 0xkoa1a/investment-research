import path from 'node:path'

import { buildContentManifest, researchContract } from '../site/content.js'

const root = path.resolve(import.meta.dirname, '..')
const slug = process.argv[2] ?? ''

try {
  const value = slug === '--all' ? buildContentManifest(root).contracts : researchContract(root, slug)
  process.stdout.write(`${JSON.stringify(value)}\n`)
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error))
  process.exit(1)
}
