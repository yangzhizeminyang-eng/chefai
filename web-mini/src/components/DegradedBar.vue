<script setup lang="ts">
/**
 * 文件级注释：内容降级提示条（安全组件，主包内置）。
 * 自 web-stage1 推荐结果「partial_failures 非空」降级提示语义迁移：
 * - safeMode = true → SAFE_MODE_BAR_TEXT（安全服务不可用，已切保守模式）；
 * - 否则 → DEGRADED_BAR_TEXT（本次部分内容未能生成，仅供参考）；
 * - text 传入时优先（要求引用 @shared/constants 常量）；
 * - 视觉：info 色横条（--color-info-bg 底 + --color-info 文字），非警示色（非阻断语义）。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'
import { SAFE_MODE_BAR_TEXT, DEGRADED_BAR_TEXT } from '@shared/constants'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 页面定制文案（可选；传入则优先，要求引用 @shared/constants 常量） */
    text?: string
    /** 是否保守模式（安全模式）：true 用 SAFE_MODE_BAR_TEXT，否则用 DEGRADED_BAR_TEXT */
    safeMode?: boolean
  }>(),
  { text: '', safeMode: false },
)

/** 实际展示文案：text 优先，其次按 safeMode 档位取常量 */
const displayText = computed(() => {
  if (props.text) return props.text
  return props.safeMode ? SAFE_MODE_BAR_TEXT : DEGRADED_BAR_TEXT
})
</script>

<template>
  <!-- info 色横条：非阻断提示，纯文字承载语义 -->
  <view class="degraded-bar">
    <text class="degraded-bar__text">{{ displayText }}</text>
  </view>
</template>

<style scoped lang="scss">
.degraded-bar {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
  padding: var(--space-xs) var(--space-md);
  background: var(--color-info-bg);
}

.degraded-bar__text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-info);
  word-break: break-all;
}
</style>
