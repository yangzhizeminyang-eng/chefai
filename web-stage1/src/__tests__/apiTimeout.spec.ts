/**
 * 文件职责：api 层「按请求超时覆盖」单测（P1 DEF-01 配套测试）。
 * 覆盖：
 *       ① axios 实例创建时默认超时为 DEFAULT_TIMEOUT_MS（12000ms）；
 *       ② 创新生成请求（postInnovationGenerate）以第三参 config 透传
 *          per-request timeout == 60000（INNOVATION_GENERATE_TIMEOUT_MS）；
 *       ③ 普通请求（postAsk）不传第三参，回落实例默认 12000ms。
 * 实现方式：vi.mock 替换 axios 模块（node 环境不发真实请求）。
 *         注意：axios.create 发生在模块导入阶段，vitest 5 进入测试阶段前会重置
 *         hoisted spy 的 mock.calls，故用普通数组捕获实例配置（数组跨阶段保留）。
 * 运行方式：npm run test（vitest run，node 环境，不挂载组件）。
 */
import { describe, expect, it, vi } from 'vitest'

// vi.mock 工厂会被提升到文件顶部，被引用的 spy/容器必须经 vi.hoisted 创建
const { postSpy, createdConfigs } = vi.hoisted(() => ({
  postSpy: vi.fn(),
  createdConfigs: [] as Array<Record<string, unknown> | undefined>,
}))

vi.mock('axios', () => {
  // 替身实例：post 交给 spy 供断言；拦截器仅登记（index.ts 装配阶段会被调用）
  const instance = {
    post: postSpy,
    get: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  }
  return {
    default: {
      // 捕获 axios.create 的实例配置（导入阶段调用，不用 vi.fn 记录）
      create: (config: Record<string, unknown> | undefined) => {
        createdConfigs.push(config)
        return instance
      },
    },
  }
})

import { DEFAULT_TIMEOUT_MS, INNOVATION_GENERATE_TIMEOUT_MS } from '@/api/index'
import { postAsk, postInnovationGenerate } from '@/api/endpoints'

describe('api 按请求超时覆盖（P1 DEF-01）', () => {
  it('实例默认超时为 12000ms（DEFAULT_TIMEOUT_MS）', () => {
    expect(DEFAULT_TIMEOUT_MS).toBe(12000)
    expect(createdConfigs.length).toBeGreaterThanOrEqual(1)
    expect(createdConfigs[0]).toEqual(
      expect.objectContaining({ timeout: 12000 }),
    )
  })

  it('创新生成请求透传 per-request timeout == 60000', async () => {
    postSpy.mockResolvedValueOnce({})
    await postInnovationGenerate(['鸡蛋', '西红柿'])
    expect(postSpy).toHaveBeenCalledTimes(1)
    expect(postSpy).toHaveBeenCalledWith(
      '/v1/innovation/generate',
      { ingredients: ['鸡蛋', '西红柿'] },
      expect.objectContaining({ timeout: 60000 }),
    )
    expect(INNOVATION_GENERATE_TIMEOUT_MS).toBe(60000)
  })

  it('普通请求（postAsk）不覆盖超时，回落实例默认 12000ms', async () => {
    postSpy.mockResolvedValueOnce({})
    await postAsk('番茄炒蛋怎么做')
    // 第三参未传 → 无 per-request timeout 覆盖，走实例默认超时
    expect(postSpy).toHaveBeenCalledWith('/v1/ask', { question: '番茄炒蛋怎么做' })
    const call = postSpy.mock.calls[0]
    expect(call[2]).toBeUndefined()
  })
})
