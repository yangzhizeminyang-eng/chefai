<!--
  文件级注释：P-31 会员中心页（pages/member 分包，🔴 RL-21 合规重点）。
  - 入口/渲染红线（RL-21 方案 B，iOS 判定见文档 §13.4）：
    页面顶部守卫 show = canShowMemberEntry(config.switches.payment)——iOS（未签约）
    或远程支付开关关闭时 show=false，整页仅渲染 EmptyState「会员服务暂未开放」，
    不渲染任何套餐 / 价格 / 购买按钮（连不可用按钮也不展示），也不发起会员区请求；
  - show=true：me.loadMember()（getMemberPlan + getMemberMe + getMemberOrders 三段并行）：
    ① 当前会员态卡（是否会员 + 到期时间 + MEMBER_QUOTA_LABEL 额度进度条）；
    ② 三档套餐卡（名称 / 价格分转元 / 权益摘要；preview_only 档仅展示不可购）；
    ③ 购买按钮 → trackEvent('subscribe_click') → createVirtualOrder(planId) 建单 →
       支付链路（本期后端为 mock-pay 占位契约，M5 替换真实微信虚拟支付，见 completePayment 注释）
       → 成功 trackEvent('purchase_success') + toast + me.loadMember() 刷新会员态；
  - 幂等口径：同套餐未完成订单复用 order_no 重试，不重复创建订单；
  - 三态：SkeletonPage / ErrorState（重试）/ 离线提示条；onHide flush 埋点。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import { MEMBER_QUOTA_LABEL } from '@shared/constants'
import type { MemberPlan } from '@shared/types'
import { useMeStore } from '@/stores/me'
import { useConfigStore } from '@/stores/config'
import {
  canShowMemberEntry,
  createVirtualOrder,
  requestVirtualPay,
  type PlanType,
  type VirtualPayParams,
} from '@/platform/pay'
import { postMemberMockPay } from '@/api/endpoints'
import { ROUTES, goRoute } from '@/utils/routes'
import { trackEvent, flushOnHide } from '@/utils/track'
import { toastSuccess, toastInfo, toastError } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import BaseButton from '@/components-base/BaseButton.vue'
import BaseCell from '@/components-base/BaseCell.vue'
import BaseTag from '@/components-base/BaseTag.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 个人中心 store（plans / memberMe / memberLoading / memberError / loadMember） */
const me = useMeStore()
/** 远程开关 store（payment 开关参与入口守卫判定） */
const config = useConfigStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/**
 * 入口可见性（🔴 RL-21 方案 B 守卫）：iOS（平台未签约虚拟支付）或远程支付开关关闭
 * 时为 false——整页退化为 EmptyState，任何套餐/价格/购买按钮都不渲染。
 */
const show = computed(() => canShowMemberEntry(config.switches.payment))

/** 购买进行中的套餐类型（'' = 空闲；按套餐隔离 loading 防连点） */
const purchasingType = ref('')

/** 未完成订单暂存（key = 套餐类型）：支付失败后保留，重试复用同一 order_no（幂等，不重复建单） */
interface PendingOrder {
  /** 订单号 */
  orderNo: string
  /** 订单响应附带的支付签名要素（本期 mock-pay 占位契约下为 null；M5 真实虚拟支付时后端补齐） */
  payParams: VirtualPayParams | null
}
const pendingOrders = ref<Partial<Record<PlanType, PendingOrder>>>({})

/** 当前会员状态摘要文案（对齐源码 memberStatusText 语义） */
const memberStatusText = computed(() => {
  const m = me.memberMe
  if (!m) return '状态未知'
  if (m.is_member) {
    return m.expire_at ? `有效会员，${formatDate(m.expire_at)} 到期` : '有效会员'
  }
  return '尚未开通会员'
})

/** 额度进度百分比（0~100，limit<=0 兜底 0） */
const quotaPercent = computed(() => {
  const quota = me.memberMe?.quota
  if (!quota || quota.limit <= 0) return 0
  return Math.min(100, Math.round((quota.used / quota.limit) * 100))
})

/**
 * 日期格式化（YYYY-MM-DD）。
 * @param iso ISO 8601 时间串
 * @returns 格式化文案；非法输入原样返回
 */
function formatDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/**
 * 价格（分）→ 元展示文案（对齐源码 priceText）。
 * @param cents 价格分
 * @returns 形如「¥18」「¥18.50」的文案
 */
function priceText(cents: number): string {
  const yuan = cents / 100
  return Number.isInteger(yuan) ? `¥${yuan}` : `¥${yuan.toFixed(2)}`
}

/**
 * 从订单响应防御式提取支付签名要素。
 * 本期后端为 mock-pay 占位契约：MemberOrderCreateResponse 不含支付字段（提取结果为 null）；
 * M5 接入真实微信虚拟支付时后端将在订单响应补齐 pay_params，本函数即可透传，无需改造调用方。
 * @param order 订单创建响应
 * @returns 支付签名要素（缺失返回 null）
 */
function extractPayParams(order: unknown): VirtualPayParams | null {
  const pay = (order as { pay_params?: Partial<VirtualPayParams> } | null)?.pay_params
  if (pay && typeof pay.signData === 'string' && typeof pay.paySig === 'string') {
    return { signData: pay.signData, paySig: pay.paySig, mode: pay.mode, package: pay.package }
  }
  return null
}

/**
 * 完成支付：优先调微信虚拟支付（requestVirtualPay），降级走模拟支付。
 * 降级口径（本期 mock-pay 占位契约，M5 替换真实虚拟支付）：
 * ① 订单响应无支付签名要素（后端仅支持 mock-pay）→ 直接 postMemberMockPay 模拟支付完成；
 * ② requestVirtualPay 返回 PAY_UNSUPPORTED（运行环境无虚拟支付 API，如开发者工具）→ 模拟支付兜底；
 * ③ 其余支付失败（PAY_FAILED / 用户取消）→ 原样抛出由调用方 toast（保留 pending 订单供重试）。
 * @param pending 未完成订单（order_no + 支付要素）
 * @returns 无
 * @throws 支付失败时抛出 { code, message } 对象（PAY_FAILED 等）
 */
async function completePayment(pending: PendingOrder): Promise<void> {
  if (pending.payParams) {
    try {
      await requestVirtualPay(pending.orderNo, pending.payParams)
      return
    } catch (e) {
      const code = (e as { code?: string }).code
      if (code !== 'PAY_UNSUPPORTED') throw e
      // PAY_UNSUPPORTED：环境不支持虚拟支付 → 降级模拟支付（M5 前联调兜底）
    }
  }
  // 后端仅支持 mock-pay（本期占位契约）→ 模拟支付完成；iOS 永不到达此处（入口守卫已拦截）
  await postMemberMockPay(pending.orderNo)
}

/**
 * 点击购买按钮（任一套餐）：先埋点 subscribe_click，再走建单与支付链路。
 * - 幂等：pendingOrders 已有同套餐未完成订单时复用 order_no，不重复创建；
 * - 成功：trackEvent('purchase_success') + toast + 刷新会员态（me.loadMember）并清除暂存；
 * - 失败：toast（保留 pending 订单，重试复用同一订单号）。
 * @param plan 目标套餐
 * @returns 无
 * @throws 不向外抛出（建单/支付异常均就地转错误 toast）
 */
async function onPurchase(plan: MemberPlan): Promise<void> {
  if (purchasingType.value) return
  // 点击任一购买按钮即埋点（口径：subscribe_click）
  trackEvent('subscribe_click', { product_type: plan.product_type })
  if (me.plans && !me.plans.payment_switch_on) {
    toastInfo('支付通道暂未开放，敬请期待')
    return
  }
  if (plan.preview_only) {
    toastInfo('该套餐为预览档位，暂不支持购买')
    return
  }
  purchasingType.value = plan.product_type
  try {
    // 幂等建单：已有同套餐未完成订单则复用，否则新建并暂存
    let pending = pendingOrders.value[plan.product_type]
    if (!pending) {
      const created = await createVirtualOrder(plan.product_type)
      pending = { orderNo: created.order_no, payParams: extractPayParams(created) }
      pendingOrders.value = { ...pendingOrders.value, [plan.product_type]: pending }
    }
    await completePayment(pending)
    trackEvent('purchase_success', { product_type: plan.product_type })
    toastSuccess('支付成功，会员权益已生效')
    const rest = { ...pendingOrders.value }
    delete rest[plan.product_type]
    pendingOrders.value = rest
    // 刷新会员态与额度（loadMember 三段并行，含订单列表）
    void me.loadMember()
  } catch (e) {
    toastError((e as { message?: string }).message || '支付失败，请重试')
  } finally {
    purchasingType.value = ''
  }
}

// onShow：先刷新支付开关（TTL 内无操作），仅入口可见时拉会员区数据（不可见时零请求零渲染）
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
    <!-- ═══ 🔴 RL-21 守卫：入口不可见 → 整页仅渲染空态，无任何套餐/价格/购买按钮 ═══ -->
    <EmptyState
      v-if="!show"
      icon="🔒"
      title="会员服务暂未开放"
      desc="会员功能暂不可用，开放后这里会提供开通入口"
    />

    <!-- ═══ 入口可见：会员中心主体 ═══ -->
    <view v-else class="center">
      <!-- 离线提示条 -->
      <OfflineBar v-if="!network.isConnected" />

      <!-- 加载态 -->
      <SkeletonPage v-if="me.memberLoading" type="list" :rows="4" />

      <!-- 错误态（重试） -->
      <ErrorState v-else-if="me.memberError" kind="server" @retry="me.loadMember()" />

      <template v-else>
        <!-- ① 当前会员态与额度 -->
        <view class="center__status">
          <view class="center__status-row">
            <text class="center__status-label">当前状态</text>
            <text class="center__status-value" :class="{ 'is-member': me.memberMe?.is_member }">
              {{ memberStatusText }}
            </text>
          </view>
          <view v-if="me.memberMe" class="center__status-row">
            <text class="center__status-label">{{ MEMBER_QUOTA_LABEL }}</text>
            <view class="center__quota">
              <view class="center__quota-bar">
                <view class="center__quota-fill" :style="{ width: quotaPercent + '%' }" />
              </view>
              <text class="center__quota-text">{{ me.memberMe.quota.used }} / {{ me.memberMe.quota.limit }}</text>
            </view>
          </view>
        </view>

        <!-- ② 三档套餐卡 -->
        <view class="center__plans">
          <view
            v-for="plan in me.plans?.plans ?? []"
            :key="plan.product_type"
            class="plan-card"
            :class="{ 'is-preview': plan.preview_only }"
          >
            <view class="plan-card__head">
              <text class="plan-card__name">{{ plan.name }}</text>
              <BaseTag v-if="plan.preview_only" text="预览档位" kind="info" />
            </view>
            <text class="plan-card__price">{{ priceText(plan.price_cents) }}</text>
            <view class="plan-card__benefits">
              <text v-for="(b, i) in plan.benefits" :key="i" class="plan-card__benefit">· {{ b }}</text>
            </view>
            <BaseButton
              class="plan-card__btn"
              block
              :disabled="!me.plans?.payment_switch_on || plan.preview_only"
              :loading="purchasingType === plan.product_type"
              @click="onPurchase(plan)"
            >
              {{ plan.preview_only ? '暂不可购' : '开通' }}
            </BaseButton>
          </view>
        </view>

        <!-- 支付通道关闭说明（非 iOS 且开关关闭时给出原因；iOS 走不到此分支） -->
        <view v-if="me.plans && !me.plans.payment_switch_on" class="center__hint">
          <text class="center__hint-text">支付通道暂未开放，开放后可在此开通会员</text>
        </view>

        <!-- ③ 订单入口（订单列表独立分包页承载） -->
        <view class="center__orders-entry">
          <BaseCell title="我的订单" desc="购买记录与支付状态" arrow @click="goRoute(ROUTES.MEMBER_ORDERS)" />
        </view>
      </template>
    </view>
  </view>
</template>

<style scoped lang="scss">
.center {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md) var(--space-md) var(--space-xl);
}

/* ── 状态卡 ── */
.center__status {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-lg) var(--space-md);
  margin-bottom: var(--space-lg);
  border-radius: var(--radius-card);
  background: var(--color-primary-weak);
}

.center__status-row {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.center__status-label {
  flex-shrink: 0;
  width: 220rpx;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.center__status-value {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);

  &.is-member {
    color: var(--color-primary);
  }
}

.center__quota {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.center__quota-bar {
  flex: 1;
  height: 14rpx;
  border-radius: var(--radius-pill);
  background: var(--divider);
  overflow: hidden;
}

.center__quota-fill {
  height: 100%;
  border-radius: var(--radius-pill);
  background: var(--color-primary);
}

.center__quota-text {
  flex-shrink: 0;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

/* ── 套餐卡 ── */
.center__plans {
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

  &.is-preview {
    opacity: 0.75;
  }
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
  font-size: 48rpx;
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

.plan-card__btn {
  margin-top: var(--space-xs);
}

/* ── 说明与订单入口 ── */
.center__hint {
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-lg);
  border-radius: var(--radius-card);
  background: var(--color-info-bg);
}

.center__hint-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-secondary);
}

.center__orders-entry {
  border-radius: var(--radius-card);
  overflow: hidden;
}
</style>
