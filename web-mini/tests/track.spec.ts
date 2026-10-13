/**
 * 文件级注释：track 埋点单元测试——mock endpoints.postTrackEvents，
 * 覆盖：①缓冲满 10 条自动 flush；②安全类事件立即 flush；③flush 失败静默清空不抛异常。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

/** mock 端点层（后端 /v1/track/events 本期未实现，真实链路即静默丢弃） */
vi.mock('@/api/endpoints', () => ({
  postTrackEvents: vi.fn(async () => undefined),
}))

import { postTrackEvents } from '@/api/endpoints'
import { trackEvent, flushTrack, resetTrackStateForTest } from '@/utils/track'

/** 拿到 mock 实例并收紧类型 */
const mockedPost = vi.mocked(postTrackEvents)

beforeEach(() => {
  resetTrackStateForTest()
  mockedPost.mockReset()
  mockedPost.mockImplementation(async () => undefined)
})

describe('track 埋点缓冲与上报', () => {
  it('缓冲满 10 条自动 flush（9 条不上报，第 10 条整批上报）', async () => {
    for (let i = 0; i < 9; i++) {
      trackEvent('app_enter')
    }
    expect(mockedPost).not.toHaveBeenCalled()
    trackEvent('app_enter') // 第 10 条 → 触发 flush
    await vi.waitFor(() => expect(mockedPost).toHaveBeenCalledTimes(1))
    const batch = mockedPost.mock.calls[0]?.[0] ?? []
    expect(batch).toHaveLength(10)
    expect(batch[0]?.name).toBe('app_enter')
    expect(typeof batch[0]?.ts).toBe('number')
    expect(String(batch[0]?.request_id)).toMatch(/^req_/)
  })

  it('安全类事件立即 flush（缓冲仅 1 条也即刻上报）', async () => {
    trackEvent('safety_block', { scene: 'food_safety' })
    await vi.waitFor(() => expect(mockedPost).toHaveBeenCalledTimes(1))
    const batch = mockedPost.mock.calls[0]?.[0] ?? []
    expect(batch).toHaveLength(1)
    expect(batch[0]?.name).toBe('safety_block')
  })

  it('flush 失败静默清空缓冲且不抛异常（复现后端 404 预期场景）', async () => {
    trackEvent('recommend_request')
    trackEvent('recipe_detail_view')
    mockedPost.mockRejectedValueOnce(new Error('404 Not Found'))
    // 失败必须 resolve 而非 reject（埋点永不阻断主流程）
    await expect(flushTrack()).resolves.toBeUndefined()
    // 缓冲已清空：再次 flush 不再发起请求（失败即丢弃，不重试）
    await flushTrack()
    expect(mockedPost).toHaveBeenCalledTimes(1)
  })

  it('manual flushTrack：成功上报整批缓冲', async () => {
    trackEvent('cook_start')
    trackEvent('cook_complete')
    await flushTrack()
    expect(mockedPost).toHaveBeenCalledTimes(1)
    expect(mockedPost.mock.calls[0]?.[0]).toHaveLength(2)
  })
})
