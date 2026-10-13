<script setup lang="ts">
/**
 * 文件级注释：基础表单容器（基础件，轻封装）。
 * - 仅承载 label 列宽上下文：根节点注入 --form-label-width 变量，
 *   页面表单行内 .form-label 读取该变量统一列宽（本组件不做校验，页面自行校验）；
 * - 默认插槽承载表单项；表单行的行布局由页面自组（flex）。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 表单 label 列宽（CSS 长度串，如 '176rpx'；经 --form-label-width 变量供行内读取） */
    labelWidth?: string
  }>(),
  { labelWidth: '176rpx' },
)

/** 根节点样式（注入 label 列宽变量） */
const rootStyle = { '--form-label-width': props.labelWidth }
</script>

<template>
  <view class="base-form" :style="rootStyle">
    <slot />
  </view>
</template>

<style scoped lang="scss">
.base-form {
  display: block;
  width: 100%;

  /* label 列宽变量缺省值（props 注入覆盖） */
  --form-label-width: 176rpx;
}
</style>
