<script setup lang="ts">
/**
 * 组件职责：应用根壳。
 * - 布局：AppHeader（顶部固定）+ main（router-view，max-width 1200 居中）+ DisclaimerGate（首次全屏弹窗）；
 * - 挂载时拉取远程开关（config.load，一次），全局背景适配深色（global.css 的 html.dark 变量）。
 */
import { onMounted } from 'vue'
import AppHeader from '@/components/AppHeader.vue'
import DisclaimerGate from '@/components/DisclaimerGate.vue'
import { useConfigStore } from '@/stores/config'

/** 远程开关 store（App 挂载时拉取一次） */
const configStore = useConfigStore()

// App 挂载：拉取远程开关（失败静默，推荐入口保持可用）
onMounted(() => {
  void configStore.load()
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
