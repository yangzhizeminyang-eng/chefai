/**
 * 测试职责：DisclaimerBar 组件解析回归（修复「Failed to resolve component: DisclaimerBar」）。
 *
 * 背景：
 *     NotFoundView 与 BlockedView 模板使用了 <DisclaimerBar> 但 script setup 缺少
 *     import——Vue 无法解析组件，SSR/客户端将其渲染为空的未知元素，页面底部
 *     免责条（G-02 固定附着）实际缺失。本测试以 SSR 渲染断言免责文案出现，
 *     防止「用了组件忘了 import」再次发生。
 *
 * 运行环境：vitest node（vue/server-renderer SSR，与 RouteContentView.spec.ts 同风格）。
 * element-plus 组件以轻量桩注册（全量插件在 node 环境 OOM；桩仅透传默认 slot，
 * 保证视图逻辑可渲染、断言聚焦 DisclaimerBar 解析本身）。
 */
import { createSSRApp, defineComponent } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import BlockedView from '../BlockedView.vue'
import NotFoundView from '../NotFoundView.vue'
import { useRecommendStore } from '@/stores/recommend'
import type { RiskDetail } from '@/api/types'

/** G-02 通用免责固定句式的可断言片段 */
const DISCLAIMER_FRAGMENT = '不构成医疗或营养治疗建议'

/**
 * 注册 element-plus 组件桩（内部函数）。
 *
 * 说明：
 *     桩仅渲染默认 slot（ disclaimer 断言所需的最小行为），不引入全量插件。
 *
 * 参数：
 *     app：待注册的 SSR 应用。
 *
 * 返回值：
 *     None。
 *
 * 异常：
 *     无。
 */
function stubElementPlus(app: ReturnType<typeof createSSRApp>): void {
  const slotStub = defineComponent({ setup: (_, { slots }) => () => slots.default?.() })
  for (const name of ['el-card', 'el-button', 'el-empty']) {
    app.component(name, slotStub)
  }
  // el-dialog：SSR 下不渲染内容即可（未打开态语义）
  app.component('el-dialog', defineComponent({ setup: () => () => null }))
}

/**
 * 构造最小 RiskDetail（BlockedView 主分支渲染的数据前提）（内部函数）。
 *
 * 返回值：
 *     RiskDetail：全字段最小合法载荷。
 *
 * 异常：
 *     无。
 */
function fakeRisk(): RiskDetail {
  return {
    category: 'food_safety_high_risk',
    rule_code: 'FS-003',
    risk_level: 'high',
    message_id: 'MSG-FS-003',
    title: '测试风险',
    body: '测试说明',
    correct_action: '测试建议',
    after_consumption_advice: '',
    evidence_ref: ['FS-003@rules-test'],
  }
}

describe('DisclaimerBar 组件解析回归', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('NotFoundView 渲染底部免责条文案', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/not-exist-page', component: NotFoundView },
      ],
    })
    await router.push('/not-exist-page')
    await router.isReady()

    const app = createSSRApp(NotFoundView)
    app.use(router)
    stubElementPlus(app)

    const html = await renderToString(app)
    expect(html).toContain('404 · 页面不存在')
    expect(html).toContain(DISCLAIMER_FRAGMENT)
  })

  it('BlockedView 渲染底部免责条文案', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/blocked', component: BlockedView }],
    })
    await router.push('/blocked')
    await router.isReady()

    useRecommendStore().blockedPayload = {
      request_id: 'req-test',
      blocked: true,
      overrides_all: true,
      risk: fakeRisk(),
    }

    const app = createSSRApp(BlockedView)
    app.use(router)
    stubElementPlus(app)

    const html = await renderToString(app)
    expect(html).toContain('测试风险')
    expect(html).toContain(DISCLAIMER_FRAGMENT)
  })
})
