<script setup lang="ts">
/**
 * 组件职责：应用根壳。
 * - 认证路由使用独立布局；已登录用户使用 AppHeader 侧栏 + router-view + DisclaimerGate；
 * - 挂载时拉取远程开关（config.load，一次）与用户设置（meStore.loadSettings）；
 * - 全局背景适配深色（global.css 的 html.dark 变量）；
 * - 字号档位全局化（M-6/L3-4）：watch meStore.settings，经 useFontSize.syncFromSettings
 *   写根级 CSS 变量（--font-* / --el-font-size-*），设置加载或保存后全站即时生效。
 */
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from '@/components/AppHeader.vue'
import DisclaimerGate from '@/components/DisclaimerGate.vue'
import RouteContentView from '@/components/RouteContentView.vue'
import { useConfigStore } from '@/stores/config'
import { useMeStore } from '@/stores/me'
import { useFontSize } from '@/composables/useFontSize'

/** 远程开关 store（App 挂载时拉取一次） */
const configStore = useConfigStore()
const route = useRoute()
const isAuthRoute = computed(() => route.name === 'login')
/** 个人中心 store（设置加载 / 保存后同步全局字号档位） */
const meStore = useMeStore()
/** 全局字号档位组合式函数（单例） */
const { syncFromSettings } = useFontSize()

// 服务器设置变化（loadSettings 完成 / saveSettings 成功）→ 同步全局字号档位
watch(
  () => meStore.settings,
  (s) => {
    if (s) syncFromSettings(s.font_size)
  },
)

// App 挂载：拉取远程开关（失败静默，推荐入口保持可用）+ 用户设置（失败静默，字号档位由 localStorage 兜底）
onMounted(() => {
  void configStore.load()
  void meStore.loadSettings()
})
</script>

<template>
  <div v-if="isAuthRoute" class="auth-shell">
    <main class="auth-main"><router-view /></main>
  </div>
  <div v-else class="app-shell">
    <AppHeader />
    <main
      class="app-main"
      :class="{
        'app-main--home': route.name === 'home',
        'app-main--select': route.name === 'select',
      }"
    >
      <RouteContentView />
    </main>
    <DisclaimerGate />
  </div>
</template>

<style scoped>
.app-shell {
  display: grid;
  grid-template-columns: 208px minmax(0, 1fr);
  min-height: 100dvh;
  background: var(--page-bg);
  transition: background-color 0.25s ease;
}

.app-main {
  width: 100%;
  max-width: 1520px;
  min-width: 0;
  margin: 0 auto;
  padding: 48px clamp(24px, 4vw, 72px) 64px;
}

.app-main--home {
  max-width: none;
  padding: 0;
}

.app-main--select {
  width: 100%;
}

.auth-shell {
  min-height: 100dvh;
  color: var(--text-main);
  background: var(--page-bg);
}

.auth-main {
  min-height: 100dvh;
}

@media (max-width: 900px) {
  .app-shell {
    grid-template-columns: minmax(0, 1fr);
  }

  .app-main {
    padding: 30px 24px 48px;
  }
}

@media (max-width: 560px) {
  .app-main {
    padding: 24px 18px 36px;
  }
}
</style>
