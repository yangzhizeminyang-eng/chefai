<!--
  文件级注释：P-30 关于页（pages/member 分包，静态页）。
  - 应用名 / 版本号：常量承载（小程序端无法运行时读取 manifest.json，与
    src/manifest.json 的 name / versionName 人工同步）；
  - 免责声明全文：复用 P-00 免责门页的分级条目（文案全部取自 @shared/constants，
    禁止散落硬编码，两处同源保证口径一致）；
  - 图片来源标注：IMAGE_SOURCE_NOTE（HowToCook 语料配图，Unlicense 公有领域）；
  - 隐私协议 / 用户协议入口：BaseCell 占位（协议文档待上线，点击 toast 提示；
    上线后可替换为 webview 页跳转——本期无 webview 页，保留注释不建页面）；
  - 备案号占位行：上线前填入真实 ICP 备案号（文档 §13.5，属发布检查项）。
-->
<script setup lang="ts">
import { onHide } from '@dcloudio/uni-app'
import {
  DISCLAIMER_TEXT,
  DISCLAIMER_NUTRITION,
  ALLERGEN_ALERT_SUFFIX,
  INEDIBLE_JUDGE_NOTE,
  MEDICAL_REFUSE_TEXT,
  DISCLAIMER_RISK,
  IMAGE_SOURCE_NOTE,
} from '@shared/constants'
import { flushOnHide } from '@/utils/track'
import { toastInfo } from '@/utils/toast'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import BaseCell from '@/components-base/BaseCell.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 应用名（与 src/manifest.json name 同步维护） */
const APP_NAME = 'AI 厨娘'

/** 版本号（与 src/manifest.json versionName 同步维护；小程序端无法运行时读取 manifest） */
const APP_VERSION = '0.1.0'

/** 免责声明分级条目（与 P-00 免责门页同源：文案全部取自 @shared/constants） */
const TERMS: Array<{ title: string; text: string }> = [
  { title: 'AI 生成内容', text: DISCLAIMER_TEXT },
  { title: '营养数据', text: DISCLAIMER_NUTRITION },
  { title: '过敏原提示', text: ALLERGEN_ALERT_SUFFIX },
  { title: '可食性判断边界', text: INEDIBLE_JUDGE_NOTE },
  { title: '医疗边界', text: MEDICAL_REFUSE_TEXT },
  { title: '就医引导', text: DISCLAIMER_RISK },
]

/**
 * 点击协议入口（隐私协议 / 用户协议均为占位）。
 * @param kind 协议类型（仅用于提示文案区分）
 * @returns 无
 * @throws 不抛出（toast 内部全捕获）
 */
function onAgreement(kind: '隐私协议' | '用户协议'): void {
  toastInfo(`${kind}文档待上线`)
}

// onHide：尽力上报缓冲埋点
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <view class="about">
      <!-- 应用标识卡 -->
      <view class="about__head">
        <view class="about__logo">🍳</view>
        <text class="about__name">{{ APP_NAME }}</text>
        <text class="about__version">版本 {{ APP_VERSION }}</text>
      </view>

      <!-- 免责声明全文（复用 P-00 分级条目口径） -->
      <view class="about__group">
        <text class="about__group-title">免责声明</text>
        <view class="about__terms">
          <view v-for="(term, idx) in TERMS" :key="idx" class="about__term">
            <text class="about__term-title">{{ idx + 1 }}. {{ term.title }}</text>
            <text class="about__term-text">{{ term.text }}</text>
          </view>
        </view>
      </view>

      <!-- 图片来源标注 -->
      <view class="about__note">
        <text class="about__note-text">{{ IMAGE_SOURCE_NOTE }}</text>
      </view>

      <!-- 协议入口（占位：协议文档待上线，上线后可替换为 webview 页跳转） -->
      <view class="about__group about__group--cells">
        <BaseCell title="隐私协议" arrow @click="onAgreement('隐私协议')" />
        <BaseCell title="用户协议" arrow @click="onAgreement('用户协议')" />
      </view>

      <!-- 备案号占位行：上线前填入真实 ICP 备案号（文档 §13.5 发布检查项） -->
      <view class="about__icp">
        <text class="about__icp-text">ICP 备案号：待上线前填入</text>
      </view>

      <DisclaimerBar scene="home" />
    </view>
  </view>
</template>

<style scoped lang="scss">
.about {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-lg) var(--space-md) var(--space-xl);
}

.about__head {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-xs);
  padding: var(--space-lg) 0;
  margin-bottom: var(--space-lg);
}

.about__logo {
  width: 128rpx;
  height: 128rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-card);
  background: var(--color-primary-weak);
  font-size: 72rpx;
}

.about__name {
  margin-top: var(--space-xs);
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.about__version {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.about__group {
  margin-bottom: var(--space-lg);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  padding: var(--space-md) var(--space-sm) var(--space-xs);

  &--cells {
    padding: 0;
    overflow: hidden;
  }
}

.about__group-title {
  display: block;
  margin: 0 0 var(--space-sm) var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.about__terms {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: 0 var(--space-xs) var(--space-sm);
}

.about__term {
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}

.about__term-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.about__term-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-secondary);
}

.about__note {
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-lg);
  border-radius: var(--radius-card);
  background: var(--color-info-bg);
}

.about__note-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-secondary);
}

.about__icp {
  display: flex;
  justify-content: center;
  padding: var(--space-md) 0;
}

.about__icp-text {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}
</style>
