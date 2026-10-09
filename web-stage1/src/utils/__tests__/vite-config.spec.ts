import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const viteConfigPath = fileURLToPath(new URL('../../../vite.config.ts', import.meta.url))

describe('Vite development configuration', () => {
  it('does not inject the incompatible Vue DevTools runtime', () => {
    const configSource = readFileSync(viteConfigPath, 'utf8')

    expect(configSource).not.toContain("from 'vite-plugin-vue-devtools'")
    expect(configSource).not.toContain('vueDevTools()')
    expect(configSource).toMatch(/devtools:\s*false/)
  })
})
