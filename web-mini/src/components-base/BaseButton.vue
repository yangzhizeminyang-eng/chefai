<script setup lang="ts">
/**
 * 文件级注释：基础按钮（基础件，统一主题与热区）。
 * - type：primary 主色实底 / default 白底描边 / danger 危险实底 / ghost 幽灵描边；
 * - size：sm 72rpx（豁免说明：仅搜索框旁、行内密集操作等紧凑区使用；默认场景用 md/lg）
 *   / md 88rpx（=热区标准）/ lg 96rpx；
 * - loading：展示转圈 spinner 并强制 disabled（loading 时 disabled 视觉与事件双禁用）；
 * - disabled：半透明禁用态，拦截 click；
 * - block：整行宽度；圆角 --radius-ctrl。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'

/** 按钮视觉类型 */
export type ButtonType = 'primary' | 'default' | 'danger' | 'ghost'

/** 按钮尺寸档位 */
export type ButtonSize = 'sm' | 'md' | 'lg'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 视觉类型：primary/default/danger/ghost */
    type?: ButtonType
    /** 尺寸：sm 72rpx（仅密集区）/ md 88rpx / lg 96rpx */
    size?: ButtonSize
    /** 加载态（展示 spinner 并禁用点击） */
    loading?: boolean
    /** 禁用态 */
    disabled?: boolean
    /** 整行宽度 */
    block?: boolean
  }>(),
  { type: 'primary', size: 'md', loading: false, disabled: false, block: false },
)

/** 点击事件（loading/disabled 状态下不触发） */
const emit = defineEmits<{ (e: 'click'): void }>()

/** 尺寸修饰类 */
const sizeClass = computed(() => `is-${props.size}`)

/** 是否可点（loading 或 disabled 均不可点） */
const interactive = computed(() => !props.loading && !props.disabled)

/**
 * 点击处理：仅可点状态向外 emit click。
 * @returns 无
 */
function onClick(): void {
  if (interactive.value) emit('click')
}
</script>

<template>
  <view
    class="base-button"
    :class="[`is-${type}`, sizeClass, { 'is-block': block, 'is-disabled': !interactive }]"
    @click="onClick"
  >
    <!-- loading spinner：CSS 转圈（currentColor 随文字色） -->
    <view v-if="loading" class="base-button__spinner" />
    <text class="base-button__text"><slot /></text>
  </view>
</template>

<style scoped lang="scss">
.base-button {
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-xs);
  padding: 0 var(--space-md);
  border-radius: var(--radius-ctrl);
  font-size: var(--font-size-base);

  /* 尺寸：sm 72rpx（豁免：仅密集区使用）/ md 88rpx（热区标准）/ lg 96rpx */
  &.is-sm {
    min-height: 72rpx;
    font-size: var(--font-size-sm);
  }

  &.is-md {
    min-height: var(--hit-min);
  }

  &.is-lg {
    min-height: 96rpx;
  }

  /* 类型 */
  &.is-primary {
    background: var(--color-primary);
    color: var(--text-inverse);
  }

  &.is-default {
    background: var(--bg-card);
    color: var(--text-primary);
    border: 1rpx solid var(--border-color);
  }

  &.is-danger {
    background: var(--color-danger);
    color: var(--text-inverse);
  }

  &.is-ghost {
    background: transparent;
    color: var(--color-primary);
    border: 2rpx solid var(--color-primary);
  }

  /* 整行 */
  &.is-block {
    display: flex;
    width: 100%;
  }

  /* 禁用态：视觉 + 事件双禁用 */
  &.is-disabled {
    opacity: 0.5;
  }
}

.base-button__text {
  line-height: 1.4;
}

/* loading spinner：currentColor 转圈 */
.base-button__spinner {
  width: 28rpx;
  height: 28rpx;
  border-radius: var(--radius-pill);
  border: 4rpx solid currentColor;
  border-top-color: transparent;
  animation: base-button-spin 0.8s linear infinite;
}

@keyframes base-button-spin {
  0% {
    transform: rotate(0deg);
  }

  100% {
    transform: rotate(360deg);
  }
}
</style>
