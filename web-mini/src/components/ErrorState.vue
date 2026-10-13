<script setup lang="ts">
/**
 * 文件级注释：错误态占位（五态-错误态，安全组件，主包内置）。
 * 阶段一错误兜底语义迁移：文案按 kind 分（network/server/timeout，中文友好，
 * 不暴露技术细节如状态码/堆栈），detail 仅承载页面给的友好补充说明；
 * emit retry 由页面重新发起请求；重试按钮热区 ≥88rpx。
 * 视觉：中性 info 色系（错误用图标 + 文字表达，不依赖颜色单独传达）。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'

/** 错误类别（决定缺省文案） */
export type ErrorKind = 'network' | 'server' | 'timeout'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 错误类别：network 网络不可用 / server 服务异常 / timeout 请求超时 */
    kind?: ErrorKind
    /** 页面提供的友好补充说明（可选；组件不暴露任何技术细节） */
    detail?: string
    /** 重试按钮文案（可选；缺省「重试」） */
    retryText?: string
  }>(),
  { kind: 'server', detail: '', retryText: '' },
)

/** 重试事件（页面重新发起请求） */
const emit = defineEmits<{ (e: 'retry'): void }>()

/** kind → 缺省文案（中文友好，不暴露技术细节） */
const KIND_TEXT: Record<ErrorKind, string> = {
  network: '网络连接不可用，请检查网络后再试',
  server: '服务暂时出了点问题，请稍后重试',
  timeout: '请求超时了，请重试',
}

/** 主文案（按 kind 取缺省文案） */
const mainText = computed(() => KIND_TEXT[props.kind])

/** 重试按钮文案（缺省「重试」） */
const retryLabel = computed(() => (props.retryText ? props.retryText : '重试'))

/**
 * 点击重试：emit retry。
 * @returns 无
 */
function onRetry(): void {
  emit('retry')
}
</script>

<template>
  <view class="error-state">
    <!-- 图标：圆底叹号（形状 + 文字双通道，不依赖颜色） -->
    <view class="error-state__icon">!</view>
    <text class="error-state__text">{{ mainText }}</text>
    <text v-if="detail" class="error-state__detail">{{ detail }}</text>
    <!-- 重试按钮：热区 ≥88rpx -->
    <view class="error-state__retry" @click="onRetry">{{ retryLabel }}</view>
  </view>
</template>

<style scoped lang="scss">
.error-state {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-xl) var(--space-md);
}

.error-state__icon {
  box-sizing: border-box;
  width: 96rpx;
  height: 96rpx;
  border-radius: var(--radius-pill);
  border: 4rpx solid var(--color-info);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48rpx;
  font-weight: 700;
  color: var(--color-info);
  line-height: 1;
}

.error-state__text {
  margin-top: var(--space-md);
  font-size: var(--font-size-base);
  line-height: 1.6;
  color: var(--text-primary);
  text-align: center;
}

.error-state__detail {
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-tertiary);
  text-align: center;
  word-break: break-all;
}

/* 重试按钮：info 描边幽灵样式，热区 ≥88rpx */
.error-state__retry {
  margin-top: var(--space-lg);
  box-sizing: border-box;
  min-width: 240rpx;
  min-height: var(--hit-min);
  padding: 0 var(--space-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  border: 2rpx solid var(--color-info);
  color: var(--color-info);
  font-size: var(--font-size-sm);
}
</style>
