<script setup lang="ts">
/**
 * 组件职责：应用根壳。
 * - 布局：AppHeader（顶部固定）+ main（router-view，max-width 1200 居中）+ DisclaimerGate（首次全屏弹窗）；
 * - 挂载时拉取远程开关（config.load，一次）与用户设置（meStore.loadSettings）；
 * - 全局背景适配深色（global.css 的 html.dark 变量）；
 * - 字号档位全局化（M-6/L3-4）：watch meStore.settings，经 useFontSize.syncFromSettings
 *   写根级 CSS 变量（--font-* / --el-font-size-*），设置加载或保存后全站即时生效。
 */
import { onMounted, watch } from 'vue'
import AppHeader from '@/components/AppHeader.vue'
import DisclaimerGate from '@/components/DisclaimerGate.vue'
import { useConfigStore } from '@/stores/config'
import { useMeStore } from '@/stores/me'
import { useFontSize } from '@/composables/useFontSize'

/** 远程开关 store（App 挂载时拉取一次） */
const configStore = useConfigStore()
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
  <div class="app-shell">
    <!-- 顶部固定条：品牌 + 导航 + 深色切换 -->
    <AppHeader />

    <!-- 主内容区：max-width 1200 居中 -->
    <main class="app-main">
      <router-view />
    </main>

    <!-- 首次进入免责声明全屏弹窗（已同意则不渲染内容） -->
    <DisclaimerGate />
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: var(--page-bg);
  transition: background-color 0.25s ease;
}

.app-main {
  max-width: var(--page-max-width);
  margin: 0 auto;
  padding: 20px 16px 48px;
}
</style>
