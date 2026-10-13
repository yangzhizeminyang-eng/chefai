<script setup lang="ts">
/**
 * 文件级注释：基础选择器（基础件，v-model 封装 uni 内置 picker mode=selector）。
 * - options：{ label, value } 列表；picker 内置弹层选择，展示区渲染当前项 label；
 * - 未选中（modelValue 不在 options 中）时展示 placeholder；
 * - change 事件按选中 index 找到对应 option.value，emit update:modelValue；
 * - 展示区热区 ≥88rpx，未选中态 placeholder 用 --text-tertiary 弱化。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'

/** 选项结构 */
export interface PickerOption {
  /** 展示文案 */
  label: string
  /** 选项值（回传给页面的业务值） */
  value: string | number
}

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 当前选中值（v-model；对应 options[].value） */
    modelValue: string | number
    /** 选项列表 */
    options: PickerOption[]
    /** 未选中时的占位文案 */
    placeholder?: string
  }>(),
  { placeholder: '请选择' },
)

/** 值更新事件（v-model 绑定，回传 option.value） */
const emit = defineEmits<{ (e: 'update:modelValue', value: string | number): void }>()

/** picker 的 range（label 文案数组，内置 selector 按索引展示） */
const rangeLabels = computed(() => props.options.map((opt) => opt.label))

/** 当前选中项索引（未命中返回 -1，picker 以 0 兜底展示第一项文案区仍显 placeholder） */
const currentIndex = computed(() =>
  props.options.findIndex((opt) => opt.value === props.modelValue),
)

/** 当前选中项展示文案（未选中展示 placeholder） */
const displayLabel = computed(() => {
  const opt = props.options[currentIndex.value]
  return opt ? opt.label : props.placeholder
})

/** 是否处于未选中态（控制展示区文字弱化） */
const isPlaceholder = computed(() => currentIndex.value < 0)

/**
 * 内置 picker change 事件：按 index 找 option.value 回传。
 * @param e change 事件（detail.value 为选中索引，微信端为字符串）
 * @returns 无
 */
function onChange(e: { detail: { value: number | string } }): void {
  const idx = Number(e.detail.value)
  const opt = props.options[idx]
  if (opt) emit('update:modelValue', opt.value)
}
</script>

<template>
  <picker
    class="base-picker"
    mode="selector"
    :range="rangeLabels"
    :value="currentIndex < 0 ? 0 : currentIndex"
    @change="onChange"
  >
    <!-- 展示区：热区 ≥88rpx，未选中态弱化文字 -->
    <view class="base-picker__display" :class="{ 'is-placeholder': isPlaceholder }">
      <text class="base-picker__text">{{ displayLabel }}</text>
      <view class="base-picker__arrow" />
    </view>
  </picker>
</template>

<style scoped lang="scss">
.base-picker {
  display: block;
  width: 100%;
}

.base-picker__display {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-xs);
  min-height: var(--hit-min);
  padding: 0 var(--space-sm);
  border: 1rpx solid var(--border-color);
  border-radius: var(--radius-ctrl);
  background: var(--bg-card);

  &.is-placeholder .base-picker__text {
    color: var(--text-tertiary);
  }
}

.base-picker__text {
  font-size: var(--font-size-base);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 下拉箭头：CSS 双线（不依赖图标库） */
.base-picker__arrow {
  flex-shrink: 0;
  width: 16rpx;
  height: 16rpx;
  border-right: 3rpx solid var(--text-tertiary);
  border-bottom: 3rpx solid var(--text-tertiary);
  transform: rotate(45deg);
}
</style>
