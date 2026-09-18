#!/usr/bin/env node
/**
 * Generate the dashboard preview before Vite starts.
 *
 * The preview page is produced by the Python pipeline, so this script locates
 * the project's virtualenv interpreter (falling back to `python` on PATH) and
 * runs `src/generate_dashboard_preview.py`. Generation is best effort: if it
 * fails, Vite still starts and the app shows a clear "not generated" message
 * rather than the dev server dying.
 */
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(here, '..', '..')
const generator = resolve(projectRoot, 'src', 'generate_dashboard_preview.py')

function resolveInterpreter() {
  if (process.env.PYTHON) return process.env.PYTHON
  const venvCandidates = [
    resolve(projectRoot, '.venv', 'Scripts', 'python.exe'), // Windows
    resolve(projectRoot, '.venv', 'bin', 'python'), // macOS / Linux
  ]
  return venvCandidates.find(existsSync) || 'python'
}

if (!existsSync(generator)) {
  console.warn(`[preview] Generator not found at ${generator}; skipping.`)
  process.exit(0)
}

const interpreter = resolveInterpreter()
console.log(`[preview] Generating dashboard preview (${interpreter}) ...`)

const result = spawnSync(interpreter, [generator], {
  cwd: projectRoot,
  stdio: 'inherit',
})

if (result.error || result.status !== 0) {
  console.warn(
    '[preview] Could not generate the dashboard preview; starting anyway.\n' +
      '[preview] The app will show a "not generated" message. Run it manually with:\n' +
      '[preview]   python src/generate_dashboard_preview.py',
  )
}
