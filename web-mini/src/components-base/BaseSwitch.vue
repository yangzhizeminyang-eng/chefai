<script setup lang="ts">
/**
 * 文件级注释：基础开关（基础件，v-model 封装 uni 内置 switch）。
 * - 内置 <switch> 的 color 属性仅接受字面色值字符串、无法引用 CSS 变量：
 *   PRIMARY_HEX 与 tokens.scss --color-primary（浅色 #ff7a45）人工同步，
 *   若调整主色需同步修改此处（基础库约束的例外点，见任务规格允许）；
 * - 深色模式下开关轨道由系统渲染，主色激活块在两种主题下均可读；
 * - change 事件回传布尔值 emit update:modelValue；disabled 透传内置组件。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
/** 主色字面值（与 tokens.scss --color-primary 同步；内置 switch 的 color 仅接受字面色值） */
const PRIMARY_HEX = '#ff7a45'

/** 组件入参 */
withDefaults(
  defineProps<{
    /** 开关状态（v-model） */
    modelValue: boolean
    /** 禁用态 */
    disabled?: boolean
  }>(),
  { disabled: false },
)

/** 状态更新事件（v-model 绑定） */
const emit = defineEmits<{ (e: 'update:modelValue', value: boolean): void }>()

/**
 * 内置 switch change 事件：回传新状态。
 * 参数用 Event 宽类型 + 内部收窄（detail.value）：模板中小写 switch 由编译器匹配为
 * SVG 原生元素事件（payload 无 detail 结构），小程序运行时事件携带 detail.value——
 * 宽类型保证类型检查通过，收窄保证运行时取值正确。
 * @param e change 事件（detail.value 为新布尔值）
 * @returns 无
 */
function onChange(e: Event): void {
  const detail = (e as { detail?: { value?: boolean } }).detail
  emit('update:modelValue', detail?.value ?? false)
}
</script>

<template>
  <view class="base-switch">
    <switch
      class="base-switch__inner"
      :checked="modelValue"
      :color="PRIMARY_HEX"
      :disabled="disabled"
      @change="onChange"
    />
  </view>
</template>

<style scoped lang="scss">
.base-switch {
  display: inline-flex;
  align-items: center;
  min-height: var(--hit-min);
}
</style>
