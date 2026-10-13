<script setup lang="ts">
/**
 * 文件级注释：基础弹层（基础件，统一主题与热区）。
 * - 遮罩 + 弹层两段式；position：bottom 底部弹层（默认，带底部安全区）/ center 居中弹层；
 * - visible 由父级控制；关闭途径：右上关闭按钮（showClose）、遮罩点击（maskClosable
 *   默认 true）、父级调 emit close 后置 visible=false；
 * - 默认插槽承载弹层内容；标题可选；关闭按钮热区 ≥88rpx；
 * - 遮罩为中性半透明黑（深浅色通用）；弹层底 var(--bg-card)，深色自动适配。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'

/** 弹层位置 */
export type DialogPosition = 'center' | 'bottom'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 弹层可见性（父级控制；关闭由本组件 emit close 后父级置 false） */
    visible: boolean
    /** 弹层标题（可选；有值渲染标题栏） */
    title?: string
    /** 是否展示右上关闭按钮 */
    showClose?: boolean
    /** 弹层位置：bottom 底部（默认）/ center 居中 */
    position?: DialogPosition
    /** 遮罩点击是否可关闭（默认 true；阻断态弹层传 false） */
    maskClosable?: boolean
  }>(),
  { title: '', showClose: false, position: 'bottom', maskClosable: true },
)

/** 关闭事件（关闭按钮/遮罩点击触发；父级负责置 visible=false） */
const emit = defineEmits<{ (e: 'close'): void }>()

/** 位置修饰类 */
const positionClass = computed(() => `is-${props.position}`)

/**
 * 遮罩点击：maskClosable 才 emit close。
 * @returns 无
 */
function onMaskClick(): void {
  if (props.maskClosable) emit('close')
}

/**
 * 右上关闭按钮：直接 emit close。
 * @returns 无
 */
function onCloseClick(): void {
  emit('close')
}
</script>

<template>
  <view v-if="visible" class="base-dialog">
    <!-- 遮罩：maskClosable 才响应点击关闭 -->
    <view class="base-dialog__mask" @click="onMaskClick" />

    <!-- 弹层：bottom 底部圆角上沿 / center 居中卡片 -->
    <view class="base-dialog__panel" :class="positionClass">
      <view v-if="title || showClose" class="base-dialog__head">
        <text class="base-dialog__title">{{ title }}</text>
        <!-- 关闭按钮：热区 ≥88rpx -->
        <view v-if="showClose" class="base-dialog__close" @click="onCloseClick">×</view>
      </view>
      <view class="base-dialog__body">
        <slot />
      </view>
    </view>
  </view>
</template>

<style scoped lang="scss">
.base-dialog {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 900;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

/* 中性半透明遮罩（深浅色通用） */
.base-dialog__mask {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.55);
}

.base-dialog__panel {
  position: relative;
  box-sizing: border-box;
  width: 100%;
  max-height: 80vh;
  overflow-y: auto;
  background: var(--bg-card);
  border-radius: var(--radius-card) var(--radius-card) 0 0;
  padding: var(--space-md) var(--space-md) calc(var(--space-md) + env(safe-area-inset-bottom));

  /* center 居中卡片形态 */
  &.is-center {
    align-self: center;
    width: 600rpx;
    border-radius: var(--radius-card);
    padding-bottom: var(--space-md);
  }
}

.base-dialog__head {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--hit-min);
  margin-bottom: var(--space-xs);
}

.base-dialog__title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
  text-align: center;
}

/* 关闭按钮：热区 ≥88rpx，右上角 */
.base-dialog__close {
  position: absolute;
  right: calc(-1 * var(--space-xs));
  top: 50%;
  transform: translateY(-50%);
  box-sizing: border-box;
  width: var(--hit-min);
  height: var(--hit-min);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-lg);
  color: var(--text-tertiary);
}

.base-dialog__body {
  display: block;
}
</style>
