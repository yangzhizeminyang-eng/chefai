<script setup lang="ts">
/**
 * 文件级注释：离线提示条（安全组件，主包内置）。
 * 自 web-stage1 离线模式顶部提示语义（CookGuideView 离线 alert 等）迁移：
 * - 缺省文案 OFFLINE_BAR_TEXT（当前网络不可用，已缓存内容可正常查看）；
 * - text 传入时优先（要求引用 @shared/constants 常量）；
 * - 视觉：info 色横条（与 DegradedBar 同族但独立组件，离线场景常驻页面顶部流式布局）。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'
import { OFFLINE_BAR_TEXT } from '@shared/constants'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 页面定制文案（可选；传入则优先，要求引用 @shared/constants 常量） */
    text?: string
  }>(),
  { text: '' },
)

/** 实际展示文案：text 优先，缺省 OFFLINE_BAR_TEXT */
const displayText = computed(() => (props.text ? props.text : OFFLINE_BAR_TEXT))
</script>

<template>
  <!-- 顶部横条：页面置于根节点下方第一个元素，随内容滚动（非 fixed，避免遮挡导航） -->
  <view class="offline-bar">
    <text class="offline-bar__text">{{ displayText }}</text>
  </view>
</template>

<style scoped lang="scss">
.offline-bar {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
  padding: var(--space-xs) var(--space-md);
  background: var(--color-info-bg);
  border-bottom: 1rpx solid var(--divider);
}

.offline-bar__text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-info);
  word-break: break-all;
}
</style>
