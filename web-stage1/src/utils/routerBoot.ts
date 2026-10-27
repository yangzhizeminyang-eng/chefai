import type { Router } from 'vue-router'

export async function mountAfterRouterReady(
  router: Pick<Router, 'isReady'>,
  mount: () => void,
): Promise<void> {
  await router.isReady()
  mount()
}
