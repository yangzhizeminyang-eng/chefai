<!--
  文件级注释：P-32 会员权益预览页（pages/member 分包）。
  - 权益对比：免费 vs 会员识别额度对比（3 次/日 vs 10 次/日，口径对齐 PRD 会员权益；
    运行时真实额度以 MemberMeResponse.quota 为准，在会员中心页展示进度）；
  - 套餐权益明细：me.loadMember() → plans.plans（MemberPlan：名称/价格/权益列表）逐卡展示；
  - 🔴 购买 CTA 与会员中心保持同一守卫口径（RL-21 方案 B）：
    show = canShowMemberEntry(config.switches.payment) 为 false 时——
    不渲染任何购买按钮 / 价格 / 套餐卡（也不发起含价格的套餐请求），
    仅展示免费 vs 会员额度对比信息供浏览，并附一行非交互的未开放说明文字；
  - show=true 时提供「去开通」CTA → 会员中心页（本页不直接建单/支付）；
  - 三态：SkeletonPage / ErrorState（重试）/ 离线提示条；onHide flush 埋点。
-->
<script setup lang="ts">
import { computed } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import { useMeStore } from '@/stores/me'
import { useConfigStore } from '@/stores/config'
import { canShowMemberEntry } from '@/platform/pay'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide } from '@/utils/track'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import ErrorState from '@/components/ErrorState.vue'
import BaseButton from '@/components-base/BaseButton.vue'
import BaseTag from '@/components-base/BaseTag.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 个人中心 store（plans / memberLoading / memberError / loadMember） */
const me = useMeStore()
/** 远程开关 store（payment 开关参与 CTA 守卫判定） */
const config = useConfigStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/**
 * 购买 CTA 可见性（与会员中心页同口径守卫，RL-21 方案 B）：
 * iOS（未签约虚拟支付）或远程支付开关关闭时为 false → 不渲染任何 CTA 与价格。
 */
const show = computed(() => canShowMemberEntry(config.switches.payment))

/** 免费 vs 会员权益对比行（额度口径对齐 PRD：免费 3 次/日、会员 10 次/日；以服务端契约为准） */
const QUOTA_ROWS: Array<{ label: string; free: string; member: string }> = [
  { label: '食材识别额度', free: '3 次 / 日', member: '10 次 / 日' },
]

/**
 * 价格（分）→ 元展示文案（与会员中心页同口径）。
 * @param cents 价格分
 * @returns 形如「¥18」「¥18.50」的文案
 */
function priceText(cents: number): string {
  const yuan = cents / 100
  return Number.isInteger(yuan) ? `¥${yuan}` : `¥${yuan.toFixed(2)}`
}

/**
 * 前往会员中心开通（仅 show=true 时渲染的 CTA）。
 * @returns 无
 * @throws 不抛出（goRoute 内部静默）
 */
function goCenter(): void {
  goRoute(ROUTES.MEMBER_CENTER)
}

// onShow：先刷新支付开关（TTL 内无操作），仅入口可见时拉取套餐（不可见时零请求，纯信息浏览）
onShow(() => {
  void config.refreshOnShow().then(() => {
    if (canShowMemberEntry(config.switches.payment)) {
      void me.loadMember()
    }
  })
})

// onHide：尽力上报缓冲埋点
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <view class="benefits">
      <!-- 离线提示条 -->
      <OfflineBar v-if="!network.isConnected" />

      <!-- 权益对比（免费 vs 会员）：信息浏览区，不受支付守卫限制 -->
      <view class="benefits__compare">
        <text class="benefits__section-title">免费 vs 会员</text>
        <view class="benefits__table">
          <view class="benefits__row benefits__row--head">
            <text class="benefits__cell benefits__cell--label">权益</text>
            <text class="benefits__cell">免费</text>
            <text class="benefits__cell benefits__cell--member">会员</text>
          </view>
          <view v-for="row in QUOTA_ROWS" :key="row.label" class="benefits__row">
            <text class="benefits__cell benefits__cell--label">{{ row.label }}</text>
            <text class="benefits__cell">{{ row.free }}</text>
            <text class="benefits__cell benefits__cell--member">{{ row.member }}</text>
          </view>
        </view>
      </view>

      <!-- 🔴 守卫分支：入口不可见 → 仅信息浏览，无任何 CTA / 价格 / 套餐卡（含请求） -->
      <template v-if="!show">
        <view class="benefits__hint">
          <text class="benefits__hint-text">会员购买入口暂未开放，权益详情以开通页为准</text>
        </view>
      </template>

      <!-- ═══ 入口可见：套餐权益明细 + 去开通 CTA ═══ -->
      <template v-else>
        <!-- 加载态 -->
        <SkeletonPage v-if="me.memberLoading" type="list" :rows="3" />

        <!-- 错误态（重试） -->
        <ErrorState v-else-if="me.memberError" kind="server" @retry="me.loadMember()" />

        <template v-else>
          <view class="benefits__plans">
            <view
              v-for="plan in me.plans?.plans ?? []"
              :key="plan.product_type"
              class="plan-card"
            >
              <view class="plan-card__head">
                <text class="plan-card__name">{{ plan.name }}</text>
                <BaseTag v-if="plan.preview_only" text="预览档位" kind="info" />
              </view>
              <text class="plan-card__price">{{ priceText(plan.price_cents) }}</text>
              <view class="plan-card__benefits">
                <text v-for="(b, i) in plan.benefits" :key="i" class="plan-card__benefit">· {{ b }}</text>
              </view>
            </view>
          </view>

          <!-- 去开通 CTA（仅展示与跳转，建单/支付在会员中心页完成） -->
          <BaseButton class="benefits__cta" block @click="goCenter">去开通</BaseButton>
        </template>
      </template>
    </view>
  </view>
</template>

<style scoped lang="scss">
.benefits {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md) var(--space-md) var(--space-xl);
}

.benefits__section-title {
  display: block;
  margin-bottom: var(--space-sm);
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

/* ── 对比表 ── */
.benefits__compare {
  margin-bottom: var(--space-lg);
}

.benefits__table {
  border-radius: var(--radius-card);
  background: var(--bg-card);
  overflow: hidden;
}

.benefits__row {
  display: flex;
  align-items: center;
  border-bottom: 1rpx solid var(--divider);

  &--head {
    background: var(--color-primary-weak);
    border-bottom: none;
  }

  &:last-child {
    border-bottom: none;
  }
}

.benefits__cell {
  flex: 1;
  min-width: 0;
  padding: var(--space-sm) var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  text-align: center;

  &--label {
    flex: 1.2;
    text-align: left;
    padding-left: var(--space-md);
    color: var(--text-primary);
  }

  &--member {
    color: var(--color-primary);
    font-weight: 600;
  }
}

/* ── 未开放说明（非交互纯文字，非 CTA） ── */
.benefits__hint {
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-lg);
  border-radius: var(--radius-card);
  background: var(--color-info-bg);
}

.benefits__hint-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-secondary);
}

/* ── 套餐卡 ── */
.benefits__plans {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}

.plan-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-lg) var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
}

.plan-card__head {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.plan-card__name {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.plan-card__price {
  font-size: 44rpx;
  font-weight: 700;
  color: var(--color-primary);
}

.plan-card__benefits {
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}

.plan-card__benefit {
  font-size: var(--font-size-sm);
  line-height: 1.7;
  color: var(--text-secondary);
}

.benefits__cta {
  margin-top: var(--space-xs);
}
</style>
