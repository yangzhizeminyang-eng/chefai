import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import RouteContentView from '../RouteContentView.vue'

describe('RouteContentView', () => {
  it('keeps fragment-root route pages inside an animatable element', async () => {
    const FragmentPage = defineComponent({
      setup: () => () => [h('main', 'page content'), h('footer', 'fixed action bar')],
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: FragmentPage }],
    })
    await router.push('/')
    await router.isReady()

    const app = createSSRApp(RouteContentView)
    app.use(router)

    const html = await renderToString(app)

    expect(html).toMatch(/<div class="route-content-shell"[^>]*>/)
    expect(html).toContain('<main>page content</main>')
    expect(html).toContain('<footer>fixed action bar</footer>')
  })
})
