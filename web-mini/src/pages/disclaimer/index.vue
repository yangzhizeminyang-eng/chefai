<!--
  文件级注释：P-00 免责声明页（免责门）。
  - App.vue onLaunch 检测 disclaimerAgreed=false 时 reLaunch 至本页（P-00 免责门）；
  - 内容为分级免责列表（全部取自 @shared/constants，禁止散落硬编码）：
    AI 生成内容性质 / 营养估算 / 过敏原以标签为准 / 不判定可食性 / 医疗不答 / 就医引导；
  - 底部「我已阅读并同意」：未勾选 checkbox 不可确认（按钮 disabled 联动）；
    确认后调 session.agreeDisclaimer() + trackEvent('disclaimer_agree') → reLaunch 首页。
-->
<script setup lang="ts">
import { ref } from 'vue'
import { onHide } from '@dcloudio/uni-app'
import { useSessionStore } from '@/stores/session'
import { trackEvent, flushOnHide } from '@/utils/track'
import { ROUTES } from '@/utils/routes'
import {
  DISCLAIMER_TEXT,
  DISCLAIMER_NUTRITION,
  NUTRITION_ESTIMATE_NOTE,
  ALLERGEN_ALERT_SUFFIX,
  INEDIBLE_JUDGE_NOTE,
  MEDICAL_REFUSE_TEXT,
  DISCLAIMER_RISK,
} from '@shared/constants'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import BaseButton from '@/components-base/BaseButton.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** session store（agreeDisclaimer / disclaimerAgreed） */
const session = useSessionStore()

/** 是否已勾选「我已阅读并同意」（未勾选时确认按钮禁用） */
const agreed = ref(false)

/** 提交中标记（防连点） */
const submitting = ref(false)

/** 免责条款分级列表（文案全部取自 @shared/constants，单项复用既有常量避免新造安全文案） */
const TERMS: Array<{ title: string; text: string }> = [
  { title: 'AI 生成内容', text: DISCLAIMER_TEXT },
  { title: '营养数据', text: `${DISCLAIMER_NUTRITION}（${NUTRITION_ESTIMATE_NOTE}）` },
  { title: '过敏原提示', text: ALLERGEN_ALERT_SUFFIX },
  { title: '可食性判断边界', text: INEDIBLE_JUDGE_NOTE },
  { title: '医疗边界', text: MEDICAL_REFUSE_TEXT },
  { title: '就医引导', text: DISCLAIMER_RISK },
]

/**
 * 切换勾选态（自绘勾选框，热区 ≥88rpx）。
 * @returns 无
 */
function toggleAgreed(): void {
  agreed.value = !agreed.value
}

/**
 * 确认同意：session.agreeDisclaimer()（本地兜底放行）+ 埋点 disclaimer_agree
 * → reLaunch 首页进入主流程。
 * @returns 无
 * @throws 不抛出（agreeDisclaimer 内部失败不阻塞，仍以本地记忆放行）
 */
async function onAgree(): Promise<void> {
  if (!agreed.value || submitting.value) return
  submitting.value = true
  try {
    await session.agreeDisclaimer()
    trackEvent('disclaimer_agree')
    uni.reLaunch({ url: ROUTES.HOME, fail: () => {} })
  } finally {
    submitting.value = false
  }
}

// 页面隐匿时尽力上报缓冲埋点
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <view class="disclaimer">
      <view class="disclaimer__head">
        <text class="disclaimer__title">免责声明</text>
        <text class="disclaimer__sub">使用 AI 厨娘前，请仔细阅读并确认以下内容</text>
      </view>

      <!-- 分级免责条款列表（文案全部来自 @shared/constants） -->
      <view class="disclaimer__list">
        <view v-for="(term, idx) in TERMS" :key="idx" class="disclaimer__item">
          <text class="disclaimer__item-title">{{ idx + 1 }}. {{ term.title }}</text>
          <text class="disclaimer__item-text">{{ term.text }}</text>
        </view>
      </view>

      <!-- 勾选 + 确认按钮联动：未勾选不可确认 -->
      <view class="disclaimer__agree" @click="toggleAgreed">
        <view class="disclaimer__checkbox" :class="{ 'is-checked': agreed }">
          <text v-if="agreed" class="disclaimer__check-mark">✓</text>
        </view>
        <text class="disclaimer__agree-text">我已阅读并同意以上内容</text>
      </view>

      <BaseButton
        class="disclaimer__btn"
        block
        :disabled="!agreed"
        :loading="submitting"
        @click="onAgree"
      >
        我已阅读并同意
      </BaseButton>
    </view>
  </view>
</template>

<style scoped lang="scss">
.disclaimer {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-lg) var(--space-md) var(--space-xl);
}

.disclaimer__head {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  margin-bottom: var(--space-lg);
}

.disclaimer__title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.disclaimer__sub {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.disclaimer__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
}

.disclaimer__item {
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}

.disclaimer__item-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.disclaimer__item-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-secondary);
}

.disclaimer__agree {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  min-height: var(--hit-min);
  margin-top: var(--space-lg);
}

.disclaimer__checkbox {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40rpx;
  height: 40rpx;
  border: 2rpx solid var(--border-color);
  border-radius: var(--radius-ctrl);
  background: var(--bg-card);
  flex-shrink: 0;

  &.is-checked {
    border-color: var(--color-primary);
    background: var(--color-primary);
  }
}

.disclaimer__check-mark {
  font-size: var(--font-size-sm);
  color: var(--text-inverse);
}

.disclaimer__agree-text {
  font-size: var(--font-size-base);
  color: var(--text-primary);
}

.disclaimer__btn {
  margin-top: var(--space-md);
}
</style>
