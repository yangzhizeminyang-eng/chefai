import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/endpoints', () => ({
  deleteFavorite: vi.fn(),
  deleteMeAccount: vi.fn(),
  getFavorites: vi.fn(),
  getHistory: vi.fn(),
  getMeExport: vi.fn(),
  getMemberMe: vi.fn(),
  getMemberOrders: vi.fn(),
  getMemberPlan: vi.fn(),
  getSettings: vi.fn(),
  getSignatureDishes: vi.fn(),
  postFeedback: vi.fn(),
  postMemberMockPay: vi.fn(),
  postMemberOrder: vi.fn(),
  putSettings: vi.fn(),
}))

import { getSettings, putSettings } from '@/api/endpoints'
import { useMeStore } from '../me'

describe('个人设置加载状态', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(getSettings).mockReset()
    vi.mocked(putSettings).mockReset()
  })

  it('设置加载失败时保留未加载状态，不能把默认值误当成服务端设置', async () => {
    vi.mocked(getSettings).mockRejectedValue(new Error('network unavailable'))
    const store = useMeStore()

    await store.loadSettings()

    expect(store.settingsLoading).toBe(false)
    expect(store.settings).toBeNull()
    expect(store.settingsError?.message).toBe('network unavailable')
    expect(store.settingsLoadError?.message).toBe('network unavailable')
  })

  it('保存失败只标记保存错误，不覆盖加载状态', async () => {
    vi.mocked(getSettings).mockResolvedValue({
      font_size: 'normal', unit: 'gram', voice_enabled: true, reminder_enabled: true,
    })
    await useMeStore().loadSettings()
    const store = useMeStore()
    vi.mocked(putSettings).mockRejectedValue(new Error('save failed'))

    await expect(store.saveSettings({
      font_size: 'large', unit: 'gram', voice_enabled: true, reminder_enabled: true,
    })).rejects.toThrow('save failed')

    expect(store.settingsLoadError).toBeNull()
    expect(store.settingsSaveError?.message).toBe('save failed')
  })
})
