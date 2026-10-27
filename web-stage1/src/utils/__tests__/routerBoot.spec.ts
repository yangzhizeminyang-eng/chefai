import { describe, expect, it, vi } from 'vitest'
import { mountAfterRouterReady } from '../routerBoot'

describe('mountAfterRouterReady', () => {
  it('does not mount the app until the initial route is ready', async () => {
    let resolveReady!: () => void
    const ready = new Promise<void>((resolve) => {
      resolveReady = resolve
    })
    const mount = vi.fn()

    const mounting = mountAfterRouterReady({ isReady: () => ready }, mount)

    expect(mount).not.toHaveBeenCalled()

    resolveReady()
    await mounting

    expect(mount).toHaveBeenCalledOnce()
  })
})
