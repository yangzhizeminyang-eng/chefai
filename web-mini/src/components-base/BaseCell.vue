<script setup lang="ts">
/**
 * 文件级注释：基础列表行（基础件，统一主题与热区）。
 * - 左侧标题（+ 可选小字描述），右侧：默认插槽 slot="right"（自定义值/控件）或箭头；
 * - 整行可点（emit click；disabled 时拦截并降透明度），热区 ≥88rpx；
 * - 行间分割线用 --divider（下边框）。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 行标题 */
    title: string
    /** 行描述小字（可选，标题下方） */
    desc?: string
    /** 是否展示右侧箭头（与 slot="right" 可共存：有插槽时插槽在前） */
    arrow?: boolean
    /** 禁用态（拦截点击 + 降透明度） */
    disabled?: boolean
  }>(),
  { desc: '', arrow: false, disabled: false },
)

/** 点击事件（disabled 状态不触发） */
const emit = defineEmits<{ (e: 'click'): void }>()

/** 是否可点 */
const interactive = computed(() => !props.disabled)

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
    class="base-cell"
    :class="{ 'is-disabled': disabled }"
    @click="onClick"
  >
    <view class="base-cell__body">
      <text class="base-cell__title">{{ title }}</text>
      <text v-if="desc" class="base-cell__desc">{{ desc }}</text>
    </view>
    <view class="base-cell__right">
      <!-- 自定义右侧内容（值/控件）；有插槽优先展示 -->
      <slot name="right" />
      <!-- CSS 双线箭头（不依赖图标库） -->
      <view v-if="arrow" class="base-cell__arrow" />
    </view>
  </view>
</template>

<style scoped lang="scss">
/* 列表行：热区 ≥88rpx，下边框分割线 */
.base-cell {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
  padding: var(--space-xs) var(--space-sm);
  border-bottom: 1rpx solid var(--divider);
  background: var(--bg-card);

  &.is-disabled {
    opacity: 0.5;
  }
}

.base-cell__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.base-cell__title {
  font-size: var(--font-size-base);
  line-height: 1.5;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.base-cell__desc {
  margin-top: 4rpx;
  font-size: var(--font-size-sm);
  line-height: 1.4;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.base-cell__right {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

/* CSS 双线箭头 */
.base-cell__arrow {
  width: 16rpx;
  height: 16rpx;
  border-top: 3rpx solid var(--text-tertiary);
  border-right: 3rpx solid var(--text-tertiary);
  transform: rotate(45deg);
}
</style>
