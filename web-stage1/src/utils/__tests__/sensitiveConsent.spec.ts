import { describe, expect, it, vi } from 'vitest'
import { saveAfterSensitiveConsent } from '@/utils/sensitiveConsent'

describe('saveAfterSensitiveConsent', () => {
  it('does not save sensitive data when consent persistence fails', async () => {
    const save = vi.fn<() => Promise<void>>()
    await expect(saveAfterSensitiveConsent(
      () => Promise.reject(new Error('consent unavailable')),
      save,
    )).rejects.toThrow('consent unavailable')
    expect(save).not.toHaveBeenCalled()
  })

  it('saves data after consent is persisted', async () => {
    const order: string[] = []
    await saveAfterSensitiveConsent(
      async () => { order.push('consent') },
      async () => { order.push('save') },
    )
    expect(order).toEqual(['consent', 'save'])
  })
})
