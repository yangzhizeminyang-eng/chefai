<script setup lang="ts">
/**
 * 文件级注释：G-01 风控拦截弹窗（安全组件，主包内置）——食品安全 / 过敏原 / 医疗
 * 三类一票否决或医疗拒答时的阻断态提示。
 * 自 web-stage1 风控拦截语义（W-05 BlockedView + 阻断弹窗）迁移：全屏遮罩 + 居中卡片，
 * 遮罩点击不关闭（阻断态必须显式确认），仅提供「我知道了」按钮（emit close，热区 ≥88rpx）。
 * - 文案一律取自 @shared/constants 的 RISK_BLOCK_*_TEXT（安全文案禁止散落硬编码）；
 * - kind 决定语义色调：food → danger / allergen → warning / medical → info（中性色），
 *   图标（圆底叹号）+ 标题 + 正文双通道表达，不依赖颜色单独传达信息；
 * - detail 可选展示后端补充说明。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文，组件内颜色一律 CSS 变量。
 */
import { computed } from 'vue'
import {
  RISK_BLOCK_FOOD_TEXT,
  RISK_BLOCK_ALLERGEN_TEXT,
  RISK_BLOCK_MEDICAL_TEXT,
} from '@shared/constants'

/** 拦截类型（决定文案与语义色调） */
type RiskKind = 'food' | 'allergen' | 'medical'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 弹窗可见性（父级控制；关闭由本组件 emit close 后父级置 false） */
    visible: boolean
    /** 拦截类型：food 食品安全风险 / allergen 过敏原风险 / medical 医疗诊断类 */
    kind: RiskKind
    /** 后端补充说明（可选，展示在主文案下方的小字） */
    detail?: string
  }>(),
  { detail: '' },
)

/** 关闭事件（点击「我知道了」触发；遮罩点击不触发——阻断态必须显式确认） */
const emit = defineEmits<{ (e: 'close'): void }>()

/** kind → 主文案映射（安全文案单点取自 @shared/constants，禁止页面散落硬编码） */
const KIND_TEXT: Record<RiskKind, string> = {
  food: RISK_BLOCK_FOOD_TEXT,
  allergen: RISK_BLOCK_ALLERGEN_TEXT,
  medical: RISK_BLOCK_MEDICAL_TEXT,
}

/** kind → 语义色调修饰类映射（图标底色用中性语义色，语义由文字承载） */
const KIND_CLASS: Record<RiskKind, string> = {
  food: 'is-danger',
  allergen: 'is-warning',
  medical: 'is-info',
}

/** 主文案（按 kind 取常量） */
const mainText = computed(() => KIND_TEXT[props.kind])

/** 图标语义修饰类 */
const kindClass = computed(() => KIND_CLASS[props.kind])

/**
 * 点击「我知道了」：通知父级关闭弹窗（父级负责置 visible = false）。
 * @returns 无
 */
function onConfirm(): void {
  emit('close')
}
</script>

<template>
  <view v-if="visible" class="risk-modal">
    <!-- 全屏遮罩：刻意不绑定点击关闭——风险阻断态必须显式确认（G-01 约束） -->
    <view class="risk-modal__mask" />
    <view class="risk-modal__card">
      <!-- 圆底叹号图标：色系随 kind；形状 + 字符保证灰度/无色觉下语义仍可读 -->
      <view class="risk-modal__icon" :class="kindClass">!</view>
      <text class="risk-modal__title">安全提示</text>
      <text class="risk-modal__text">{{ mainText }}</text>
      <text v-if="detail" class="risk-modal__detail">{{ detail }}</text>
      <view class="risk-modal__btn" @click="onConfirm">我知道了</view>
    </view>
  </view>
</template>

<style scoped lang="scss">
.risk-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 中性半透明遮罩：纯黑半透明在深浅色下均可读（遮罩层通用做法） */
.risk-modal__mask {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.55);
}

.risk-modal__card {
  position: relative;
  box-sizing: border-box;
  width: 560rpx;
  padding: var(--space-lg);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* 圆底叹号图标（96rpx ≥ 热区标准，视觉聚焦） */
.risk-modal__icon {
  box-sizing: border-box;
  width: 96rpx;
  height: 96rpx;
  border-radius: var(--radius-pill);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48rpx;
  font-weight: 700;
  line-height: 1;

  &.is-danger {
    background: var(--color-danger-bg);
    color: var(--color-danger);
  }

  &.is-warning {
    background: var(--color-warning-bg);
    color: var(--color-warning);
  }

  &.is-info {
    background: var(--color-info-bg);
    color: var(--color-info);
  }
}

.risk-modal__title {
  margin-top: var(--space-md);
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.risk-modal__text {
  margin-top: var(--space-sm);
  font-size: var(--font-size-base);
  line-height: 1.6;
  color: var(--text-secondary);
  text-align: center;
  word-break: break-all;
}

/* 后端补充说明：小字弱化展示 */
.risk-modal__detail {
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  line-height: 1.5;
  color: var(--text-tertiary);
  text-align: center;
  word-break: break-all;
}

/* 确认按钮：热区 ≥88rpx，主色实底 */
.risk-modal__btn {
  margin-top: var(--space-lg);
  box-sizing: border-box;
  width: 100%;
  min-height: var(--hit-min);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-ctrl);
  background: var(--color-primary);
  color: var(--text-inverse);
  font-size: var(--font-size-base);
}
</style>
