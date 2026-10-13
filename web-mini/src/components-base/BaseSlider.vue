<script setup lang="ts">
/**
 * 文件级注释：基础滑杆（基础件，v-model 封装 uni 内置 slider）。
 * - 内置 <slider> 的 activeColor 属性仅接受字面色值字符串、无法引用 CSS 变量：
 *   PRIMARY_HEX 与 tokens.scss --color-primary（浅色 #ff7a45）人工同步，
 *   若调整主色需同步修改此处（基础库约束的例外点，见任务规格允许）；
 * - change（松手确认）回传数值 emit update:modelValue；min/max/step 透传；
 * - block-size 28 提高手指操作性（滑块可点面积）。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
/** 主色字面值（与 tokens.scss --color-primary 同步；内置 slider 的 activeColor 仅接受字面色值） */
const PRIMARY_HEX = '#ff7a45'

/** 组件入参 */
withDefaults(
  defineProps<{
    /** 当前值（v-model） */
    modelValue: number
    /** 最小值 */
    min?: number
    /** 最大值 */
    max?: number
    /** 步长 */
    step?: number
  }>(),
  { min: 0, max: 100, step: 1 },
)

/** 值更新事件（v-model 绑定） */
const emit = defineEmits<{ (e: 'update:modelValue', value: number): void }>()

/**
 * 内置 slider change 事件（松手确认）：回传新值。
 * @param e change 事件（detail.value 为新数值）
 * @returns 无
 */
function onChange(e: { detail: { value: number } }): void {
  emit('update:modelValue', e.detail.value)
}
</script>

<template>
  <view class="base-slider">
    <slider
      class="base-slider__inner"
      :value="modelValue"
      :min="min"
      :max="max"
      :step="step"
      :activeColor="PRIMARY_HEX"
      :block-size="28"
      @change="onChange"
    />
  </view>
</template>

<style scoped lang="scss">
.base-slider {
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
  width: 100%;
}

.base-slider__inner {
  width: 100%;
  margin: 0;
}
</style>
