<script setup lang="ts">
/**
 * 视图职责：会员中心（Task 9 / 路由 /member）。
 * 区块：① 当前会员状态卡：是否有效会员 + 到期时间 + 识别额度进度条；
 *       ② 三档套餐卡（月/季/年）：price_cents/100 展示、权益清单、preview_only 提示；
 *       ③ 购买按钮：payment_switch_on=false 禁用 + 说明；点击 → 创建订单 →
 *          模拟支付确认弹窗（明确标注「模拟支付，小程序端为微信虚拟支付」）→
 *          mock-pay → 成功展示状态；④ 订单列表。
 * 三态：加载 = 骨架；异常 = el-alert + 重试；深色模式全变量适配。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { ApiError, MemberPlan } from '@/api/types'
import { useMeStore } from '@/stores/me'
import { MEMBER_QUOTA_LABEL } from '@/constants/copy'

/** 个人中心 store（会员区数据与购买链路） */
const meStore = useMeStore()

/** 购买进行中（按套餐类型隔离，防连点） */
const purchasingType = ref<string>('')

/** 当前会员状态摘要 */
const memberStatusText = computed(() => {
  const me = meStore.memberMe
  if (!me) return '状态未知'
  if (me.is_member) return `有效会员${me.expire_at ? `，${new Date(me.expire_at).toLocaleDateString()} 到期` : ''}`
  return '尚未开通会员'
})

/** 额度进度百分比 */
const quotaPercent = computed(() => {
  const quota = meStore.memberMe?.quota
  if (!quota || quota.limit <= 0) return 0
  return Math.min(100, Math.round((quota.used / quota.limit) * 100))
})

/**
 * 价格（分）→ 元展示文案。
 * @param cents 价格分
 * @returns 形如「¥18」的文案（整数元省小数，否则保留 2 位）
 */
function priceText(cents: number): string {
  const yuan = cents / 100
  return Number.isInteger(yuan) ? `¥${yuan}` : `¥${yuan.toFixed(2)}`
}

/**
 * 点击「开通」：创建订单 → 模拟支付确认弹窗 → mock-pay → 刷新状态。
 * @param plan 目标套餐
 * @returns 无
 */
async function onPurchase(plan: MemberPlan): Promise<void> {
  if (meStore.plans && !meStore.plans.payment_switch_on) {
    ElMessage.info('支付通道暂未开放，敬请期待')
    return
  }
  if (plan.preview_only) {
    ElMessage.info('该套餐为预览档位，暂不支持购买')
    return
  }
  // 模拟支付确认弹窗：明确标注 web 端为模拟支付
  let confirmed = false
  try {
    await ElMessageBox.confirm(
      `确认开通「${plan.name}」（${priceText(plan.price_cents)}）？` +
        ' 当前 web 端为模拟支付（仅联调），正式环境小程序端为微信虚拟支付。',
      '模拟支付确认',
      { confirmButtonText: '确认支付', cancelButtonText: '取消', type: 'info' },
    )
    confirmed = true
  } catch {
    confirmed = false
  }
  if (!confirmed) return

  purchasingType.value = plan.product_type
  try {
    const paidAt = await meStore.purchase(plan.product_type)
    ElMessage.success(`支付成功（${new Date(paidAt).toLocaleString()}），会员权益已生效`)
  } catch (e) {
    ElMessage.error((e as ApiError).message || '支付失败，请重试')
  } finally {
    purchasingType.value = ''
  }
}

/**
 * 订单状态中文映射。
 * @param status 订单状态
 * @returns 中文文案
 */
function orderStatusText(status: string): string {
  return status === 'paid' ? '已支付' : '待支付'
}

/**
 * 重试会员区数据。
 * @returns 无
 */
function retry(): void {
  void meStore.loadMember()
}

// 挂载：拉取套餐 / 状态 / 订单
onMounted(() => {
  void meStore.loadMember()
})
</script>

<template>
  <section class="page-card member-page">
    <h1 class="page-title">会员中心</h1>

    <!-- 异常态 -->
    <el-alert
      v-if="meStore.memberError"
      class="member-alert"
      type="error"
      :title="`会员信息加载失败：${meStore.memberError.message}`"
      :closable="false"
      show-icon
    >
      <el-button size="small" type="primary" plain @click="retry">重试</el-button>
    </el-alert>

    <!-- 加载态 -->
    <div v-if="meStore.memberLoading" class="member-skeleton">
      <el-skeleton :rows="6" animated />
    </div>

    <template v-else>
      <!-- ① 当前状态与额度 -->
      <div class="status-card">
        <div class="status-line">
          <span class="status-label">当前状态</span>
          <span class="status-value" :class="{ 'status-value--member': meStore.memberMe?.is_member }">
            {{ memberStatusText }}
          </span>
        </div>
        <div v-if="meStore.memberMe" class="status-line quota-line">
          <span class="status-label">{{ MEMBER_QUOTA_LABEL }}</span>
          <el-progress
            class="quota-bar"
            :percentage="quotaPercent"
            :stroke-width="12"
            :format="() => `${meStore.memberMe?.quota.used ?? 0} / ${meStore.memberMe?.quota.limit ?? 0}`"
          />
        </div>
      </div>

      <!-- ② 三档套餐卡 -->
      <div class="plan-grid">
        <div
          v-for="plan in meStore.plans?.plans ?? []"
          :key="plan.product_type"
          class="plan-card"
          :class="{ 'plan-card--preview': plan.preview_only }"
        >
          <span class="plan-name">{{ plan.name }}</span>
          <span class="plan-price">{{ priceText(plan.price_cents) }}</span>
          <ul class="plan-benefits">
            <li v-for="(b, i) in plan.benefits" :key="i">{{ b }}</li>
          </ul>
          <el-tag v-if="plan.preview_only" size="small" type="info" class="plan-tag">
            预览档位
          </el-tag>
          <el-button
            type="primary"
            class="plan-btn"
            :disabled="!meStore.plans?.payment_switch_on || plan.preview_only"
            :loading="purchasingType === plan.product_type"
            @click="onPurchase(plan)"
          >
            {{ plan.preview_only ? '暂不可购' : '开通' }}
          </el-button>
        </div>
      </div>

      <!-- 支付通道关闭说明 -->
      <el-alert
        v-if="meStore.plans && !meStore.plans.payment_switch_on"
        class="member-alert"
        type="info"
        title="支付通道暂未开放（web 端暂不支持购买），开放后可在此开通；正式支付在小程序端通过微信虚拟支付完成"
        :closable="false"
        show-icon
      />

      <!-- ③ 订单列表 -->
      <div class="orders-section">
        <h2 class="section-title">我的订单</h2>
        <el-empty
          v-if="meStore.orders.length === 0"
          description="还没有订单"
          :image-size="72"
        />
        <div v-else class="order-list">
          <div v-for="o in meStore.orders" :key="o.order_no" class="order-item">
            <div class="order-main">
              <span class="order-no">订单号 {{ o.order_no }}</span>
              <span class="order-time">{{ new Date(o.created_at).toLocaleString() }}</span>
            </div>
            <div class="order-side">
              <span class="order-amount">¥{{ (o.amount_cents / 100).toFixed(2) }}</span>
              <el-tag size="small" :type="o.status === 'paid' ? 'success' : 'warning'">
                {{ orderStatusText(o.status) }}
              </el-tag>
            </div>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.member-alert {
  margin-bottom: 14px;
}

.member-skeleton {
  padding: 8px 0 16px;
}

/* ── 状态卡 ── */
.status-card {
  padding: 16px 18px;
  margin-bottom: 18px;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 10px;
  background: var(--el-color-primary-light-9);
}

.status-line {
  display: flex;
  align-items: center;
  gap: 14px;
}

.status-line + .status-line {
  margin-top: 12px;
}

.status-label {
  flex-shrink: 0;
  width: 110px;
  font-size: var(--font-sm);
  color: var(--color-info);
}

.status-value {
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
}

.status-value--member {
  color: var(--el-color-primary);
}

.quota-line {
  flex-wrap: wrap;
}

.quota-bar {
  flex: 1;
  min-width: 200px;
}

/* ── 套餐卡 ── */
.plan-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.plan-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 18px 16px;
  border: 1px solid var(--color-info-border);
  border-radius: 12px;
}

.plan-card--preview {
  opacity: 0.75;
}

.plan-name {
  font-size: var(--font-md);
  font-weight: 700;
  color: var(--text-main);
}

.plan-price {
  font-size: 26px;
  font-weight: 700;
  color: var(--el-color-primary);
}

.plan-benefits {
  flex: 1;
  margin: 0;
  padding-left: 18px;
}

.plan-benefits li {
  font-size: var(--font-sm);
  line-height: 1.9;
  color: var(--color-info);
}

.plan-tag {
  align-self: flex-start;
}

.plan-btn {
  width: 100%;
}

/* ── 订单 ── */
.orders-section {
  padding-top: 14px;
  border-top: 1px solid var(--color-info-border);
}

.section-title {
  margin: 0 0 12px;
  font-size: var(--font-lg);
  font-weight: 600;
  color: var(--text-main);
}

.order-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.order-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
}

.order-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.order-no {
  font-size: var(--font-sm);
  font-weight: 600;
  color: var(--text-main);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.order-time {
  font-size: var(--font-sm);
  color: var(--color-info);
}

.order-side {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.order-amount {
  font-weight: 600;
  color: var(--text-main);
}
</style>
