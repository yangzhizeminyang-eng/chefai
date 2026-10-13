<script setup lang="ts">
/**
 * 文件级注释：基础徽标（基础件，统一主题与热区）。
 * 小号状态徽标：背景用对应语义 *-bg 变量色，文字用对应语义色，深浅色自动适配：
 * info 信息 / warning 警示 / danger 危险 / primary 主色 / neutral 中性灰。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'

/** 徽标语义类型 */
export type TagKind = 'info' | 'warning' | 'danger' | 'primary' | 'neutral'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 徽标文字 */
    text: string
    /** 语义类型：info/warning/danger/primary/neutral */
    kind?: TagKind
  }>(),
  { kind: 'info' },
)

/** 语义修饰类 */
const kindClass = computed(() => `is-${props.kind}`)
</script>

<template>
  <view class="base-tag" :class="kindClass">
    <text class="base-tag__text">{{ text }}</text>
  </view>
</template>

<style scoped lang="scss">
.base-tag {
  display: inline-flex;
  align-items: center;
  box-sizing: border-box;
  padding: 4rpx var(--space-sm);
  border-radius: var(--radius-ctrl);

  &.is-info {
    background: var(--color-info-bg);
    color: var(--color-info);
  }

  &.is-warning {
    background: var(--color-warning-bg);
    color: var(--color-warning);
  }

  &.is-danger {
    background: var(--color-danger-bg);
    color: var(--color-danger);
  }

  &.is-primary {
    background: var(--color-primary-weak);
    color: var(--color-primary);
  }

  &.is-neutral {
    background: var(--bg-page);
    color: var(--text-tertiary);
  }
}

.base-tag__text {
  font-size: var(--font-size-sm);
  line-height: 1.5;
}
</style>
