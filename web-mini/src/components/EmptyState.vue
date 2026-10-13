<script setup lang="ts">
/**
 * 文件级注释：空态占位（五态-空态，安全组件，主包内置）。
 * 阶段一「无数据空态」语义迁移：图标（emoji 字符，无额外依赖）+ 标题 + 说明 +
 * 可选行动按钮（actionText 有值才渲染，热区 ≥88rpx），行动逻辑 emit action 由页面承接。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 空态图标（emoji 字符；缺省空盘 🍽️） */
    icon?: string
    /** 空态标题（必填，一句话说明当前为什么是空的） */
    title: string
    /** 空态补充说明（可选小字） */
    desc?: string
    /** 行动按钮文案（可选；有值才渲染按钮） */
    actionText?: string
  }>(),
  { icon: '', desc: '', actionText: '' },
)

/** 行动按钮事件（点击按钮触发；页面负责跳转/刷新等） */
const emit = defineEmits<{ (e: 'action'): void }>()

/** 图标字符（缺省 🍽️） */
const iconChar = computed(() => (props.icon ? props.icon : '🍽️'))

/**
 * 点击行动按钮：emit action。
 * @returns 无
 */
function onAction(): void {
  emit('action')
}
</script>

<template>
  <view class="empty-state">
    <!-- 图标：大号 emoji（灰度下仍可见形状，非纯色彩表达） -->
    <text class="empty-state__icon">{{ iconChar }}</text>
    <text class="empty-state__title">{{ title }}</text>
    <text v-if="desc" class="empty-state__desc">{{ desc }}</text>
    <!-- 行动按钮：热区 ≥88rpx，actionText 有值才渲染 -->
    <view v-if="actionText" class="empty-state__action" @click="onAction">{{ actionText }}</view>
  </view>
</template>

<style scoped lang="scss">
.empty-state {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-xl) var(--space-md);
}

.empty-state__icon {
  font-size: 96rpx;
  line-height: 1.2;
}

.empty-state__title {
  margin-top: var(--space-md);
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
  text-align: center;
}

.empty-state__desc {
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-tertiary);
  text-align: center;
  word-break: break-all;
}

/* 行动按钮：主色实底，热区 ≥88rpx */
.empty-state__action {
  margin-top: var(--space-lg);
  box-sizing: border-box;
  min-width: 240rpx;
  min-height: var(--hit-min);
  padding: 0 var(--space-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  background: var(--color-primary);
  color: var(--text-inverse);
  font-size: var(--font-size-sm);
}
</style>
