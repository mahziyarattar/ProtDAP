// Mol*'s npm package only ships prebuilt viewer assets (a global-script
// bundle, not an ES module), so it can't be `import`ed through Vite like a
// normal dependency - see the comment in StructureViewer.tsx. Instead we
// copy the prebuilt bundle into public/ so it can be loaded via a plain
// <script>/<link> tag at runtime. Runs automatically before dev/build (see
// package.json's pre* hooks) so it stays in sync with the installed
// molstar version without a manual copy step.
import { cpSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const srcDir = join(__dirname, '..', 'node_modules', 'molstar', 'build', 'viewer')
const destDir = join(__dirname, '..', 'public', 'molstar-viewer')

if (!existsSync(srcDir)) {
  console.warn(`[copy-molstar-assets] molstar viewer build not found at ${srcDir}, skipping.`)
  process.exit(0)
}

mkdirSync(destDir, { recursive: true })
cpSync(srcDir, destDir, { recursive: true })
console.log(`[copy-molstar-assets] copied molstar viewer assets to ${destDir}`)
