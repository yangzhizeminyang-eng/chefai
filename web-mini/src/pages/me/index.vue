<!--
  文件级注释：P-25 我的页（tabBar）。
  - 用户卡：匿名 ID 尾号 + 登录按钮（未登录态）→ platform/login.wxLogin()：
    ok=true toast「登录成功」；失败 toast LOGIN_FALLBACK_TEXT（文案取 @shared/constants，
    登录失败永不阻断，降级匿名会话）；
  - 菜单 BaseCell：我的拿手菜 → SIGNATURE / 设置 → SETTINGS / 关于 → ABOUT /
    意见反馈 → FEEDBACK / 会员中心 → MEMBER_CENTER；
  - 会员中心入口仅在 canShowMemberEntry(config.switches.payment) 为 true 时渲染
    （iOS 一切付费入口完全隐藏 + 远程支付开关关闭隐藏，RL-21 / 方案 B 合规红线）；
  - 数据权利入口（导出/注销）放设置分包页，本页不承载（PIPL 职责分离）。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import { LOGIN_FALLBACK_TEXT } from '@shared/constants'
import { useSessionStore } from '@/stores/session'
import { useConfigStore } from '@/stores/config'
import { wxLogin, SESSION_TOKEN_KEY } from '@/platform/login'
import { canShowMemberEntry } from '@/platform/pay'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide } from '@/utils/track'
import { get as storageGet } from '@/utils/storage'
import { toastSuccess, toastInfo } from '@/utils/toast'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import BaseButton from '@/components-base/BaseButton.vue'
import BaseCell from '@/components-base/BaseCell.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 匿名会话 store（anonymousId 尾号展示） */
const session = useSessionStore()
/** 远程开关 store（payment 开关参与会员入口可见性判定） */
const config = useConfigStore()

/** 登录请求进行中（防连点） */
const loggingIn = ref(false)

/** 会话令牌（有值 = 已登录；onShow 时从 storage 恢复） */
const hasToken = ref(false)

/** 匿名 ID 尾号（末 4 位；ID 未就绪时不渲染） */
const anonymousTail = computed(() => {
  const id = session.anonymousId
  return id ? id.slice(-4) : ''
})

/**
 * 微信登录：wxLogin 全流程（内部失败不抛错，返回降级结果由本页 toast）。
 * @returns 无
 * @throws 不抛出（wxLogin 内部全量兜底）
 */
async function onLogin(): Promise<void> {
  if (loggingIn.value) return
  loggingIn.value = true
  try {
    const result = await wxLogin()
    if (result.ok) {
      hasToken.value = true
      toastSuccess('登录成功')
    } else {
      // 降级匿名：文案取 @shared/constants LOGIN_FALLBACK_TEXT（保留本地数据）
      toastInfo(result.message ?? LOGIN_FALLBACK_TEXT)
    }
  } finally {
    loggingIn.value = false
  }
}

// onShow：恢复匿名 ID 与登录令牌态（从登录/设置页返回后即时反映）
onShow(() => {
  hasToken.value = !!storageGet<string>(SESSION_TOKEN_KEY, '')
  void session.ensureAnonymousId()
})

// onHide：尽力上报缓冲埋点
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <view class="me">
      <!-- 用户卡：匿名 ID 尾号 + 登录按钮（未登录态） -->
      <view class="me__card">
        <view class="me__avatar">🍳</view>
        <view class="me__info">
          <text v-if="hasToken" class="me__name">已登录</text>
          <text v-else class="me__name">未登录（匿名使用中）</text>
          <text v-if="anonymousTail" class="me__sub">匿名 ID 尾号 {{ anonymousTail }}</text>
        </view>
        <BaseButton
          v-if="!hasToken"
          size="sm"
          type="default"
          :loading="loggingIn"
          @click="onLogin"
        >
          登录
        </BaseButton>
      </view>

      <!-- 菜单列表 -->
      <view class="me__menu">
        <BaseCell title="我的拿手菜" desc="常做的菜与均分统计" arrow @click="goRoute(ROUTES.SIGNATURE)" />
        <BaseCell title="设置" desc="字号 / 单位 / 语音 / 提醒 / 数据权利" arrow @click="goRoute(ROUTES.SETTINGS)" />
        <BaseCell title="关于" desc="版本与免责说明" arrow @click="goRoute(ROUTES.ABOUT)" />
        <!-- 会员中心：RL-21 / 方案 B——iOS 与支付开关关闭时入口完全隐藏（非置灰） -->
        <BaseCell
          v-if="canShowMemberEntry(config.switches.payment)"
          title="会员中心"
          desc="识别额度与订单"
          arrow
          @click="goRoute(ROUTES.MEMBER_CENTER)"
        />
        <BaseCell title="意见反馈" desc="问题与建议" arrow @click="goRoute(ROUTES.FEEDBACK)" />
      </view>

      <DisclaimerBar scene="home" />
    </view>
  </view>
</template>

<style scoped lang="scss">
.me {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
}

/* ── 用户卡 ── */
.me__card {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-lg) var(--space-md);
  margin-bottom: var(--space-lg);
  border-radius: var(--radius-card);
  background: var(--bg-card);
}

.me__avatar {
  width: 96rpx;
  height: 96rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  background: var(--color-primary-weak);
  font-size: 48rpx;
  flex-shrink: 0;
}

.me__info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}

.me__name {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.me__sub {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* ── 菜单 ── */
.me__menu {
  border-radius: var(--radius-card);
  overflow: hidden;
}
</style>
