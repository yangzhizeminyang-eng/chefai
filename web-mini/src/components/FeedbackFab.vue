<script setup lang="ts">
/**
 * 文件级注释：全局反馈入口浮动按钮（业务组件）。
 * 自 web-stage1/src/components/FeedbackFab.vue 迁移：阶段一 FAB 点击打开页内弹窗并监听
 * 全局自定义事件（个人中心宫格入口复用）；小程序端改由页面承接反馈页跳转：
 * - 组件只负责固定右下角的浮动按钮（96rpx 圆钮，热区 ≥88rpx）+ emit click；
 * - 沿用阶段一「打开动作幂等 + 防重复触发」节流语义：500ms 内重复点击忽略一次窗口，
 *   避免连点造成多次跳转（阶段一打开弹窗天然幂等，页面跳转需组件侧节流兜底）；
 * - 保留阶段一全局事件复用语义：监听 uni.$on('aicook:open-feedback')（外部入口触发），
 *   收到事件同样走节流 emit click；不使用浏览器事件对象（小程序平台约束）。
 * 使用约束：fixed 定位组件，页面直接放在根节点下即可；由页面根 .page/.dark 提供主题变量。
 */
import { onMounted, onUnmounted, ref } from 'vue'

/** 外部入口打开反馈的自定义事件名（与阶段一 OPEN_FEEDBACK_EVENT 语义一致） */
const OPEN_FEEDBACK_EVENT = 'aicook:open-feedback'

/** 防重复点击节流窗口（毫秒） */
const THROTTLE_MS = 500

/** 点击事件（页面负责跳转反馈页/打开反馈表单） */
const emit = defineEmits<{ (e: 'click'): void }>()

/** 上次触发时间戳（0 = 从未触发），节流判定依据 */
const lastFiredAt = ref(0)

/**
 * 节流触发 click：THROTTLE_MS 内的重复触发被忽略（防连点多次跳转）。
 * @returns 无
 */
function fireThrottled(): void {
  const now = Date.now()
  if (now - lastFiredAt.value < THROTTLE_MS) return
  lastFiredAt.value = now
  emit('click')
}

// 挂载：注册全局事件（外部入口复用本入口）；卸载：移除，避免重复监听
onMounted(() => {
  uni.$on(OPEN_FEEDBACK_EVENT, fireThrottled)
})

onUnmounted(() => {
  uni.$off(OPEN_FEEDBACK_EVENT, fireThrottled)
})
</script>

<template>
  <!-- 右下角固定反馈 FAB：bottom 预留 tabBar 高度 + 底部安全区 -->
  <view class="feedback-fab safe-bottom" @click="fireThrottled">
    <text class="feedback-fab__icon">💬</text>
    <text class="feedback-fab__text">反馈</text>
  </view>
</template>

<style scoped lang="scss">
.feedback-fab {
  position: fixed;
  right: var(--space-md);
  bottom: calc(160rpx + env(safe-area-inset-bottom));
  z-index: 90;
  box-sizing: border-box;
  width: 96rpx;
  height: 96rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  background: var(--color-primary);
  box-shadow: var(--shadow-card);

  /* safe-bottom 只加内边距，FAB 自身尺寸固定，撤销其继承影响 */
  padding-bottom: 0;
}

.feedback-fab__icon {
  font-size: 40rpx;
  line-height: 1.2;
}

.feedback-fab__text {
  font-size: 20rpx;
  line-height: 1.2;
  color: var(--text-inverse);
}
</style>
