// The Stealth-Scribe logo assets are stored as base64 text (*.b64) so the whole repo
// stays plain text and diffs/CI stay clean. This decodes them back into real
// image files in public/ before Vite builds. Runs automatically via the
// "predev" and "prebuild" npm scripts.

import { readdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const publicDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public')

if (!existsSync(publicDir)) {
  console.error('decode-assets: no public/ directory found')
  process.exit(1)
}

let decoded = 0
for (const name of readdirSync(publicDir)) {
  if (!name.endsWith('.b64')) continue
  const target = join(publicDir, name.slice(0, -4))
  const raw = readFileSync(join(publicDir, name), 'utf8').replace(/\s+/g, '')
  writeFileSync(target, Buffer.from(raw, 'base64'))
  decoded++
}

console.log(`decode-assets: wrote ${decoded} image file(s) into public/`)
