<!--
  文件级注释：P-33 我的订单页（pages/member 分包）。
  - 数据源：me.loadMember()（getMemberOrders 三段并行之一）→ me.orders（MemberOrderItem）；
  - 列表四要素（对齐 MemberOrderItem 契约）：商品名（product_type → 套餐名）/
    金额（amount_cents 分转元）/ 订单号（order_no）/ 时间（已支付展示支付时间，
    未支付展示创建时间）；状态徽标 paid 已支付 / pending 待支付；
  - 条目点击展开详情：完整订单号 + 创建时间 + 支付时间（可选交互，本地展开态）；
  - 退款口径：web-stage1 源码 V1.0 无退款语义（MemberView 无退款入口/文案），
    本页按源码口径不渲染退款说明行；
  - 空态「还没有订单」；三态 SkeletonPage / ErrorState（重试）/ 离线提示条；
    onShow 拉取，onHide flush 埋点。
-->
<script setup lang="ts">
import { ref } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import type { MemberOrderItem } from '@shared/types'
import { useMeStore } from '@/stores/me'
import { flushOnHide } from '@/utils/track'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import BaseTag from '@/components-base/BaseTag.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 个人中心 store（orders / memberLoading / memberError / loadMember） */
const me = useMeStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 当前展开详情的订单号（'' = 全部收起；本地展开态，不落库） */
const expandedOrderNo = ref('')

/** 套餐类型 → 商品名（对齐套餐命名口径：月卡/季卡/年卡） */
const PRODUCT_NAMES: Record<MemberOrderItem['product_type'], string> = {
  monthly: '月卡',
  quarterly: '季卡',
  yearly: '年卡',
}

/**
 * 时间格式化（YYYY-MM-DD HH:mm，对齐收藏/历史页 formatTime 口径）。
 * @param iso ISO 8601 时间串
 * @returns 格式化文案；非法输入原样返回
 */
function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/**
 * 金额（分）→ 元展示文案。
 * @param cents 金额分
 * @returns 形如「¥18.00」的文案
 */
function amountText(cents: number): string {
  return `¥${(cents / 100).toFixed(2)}`
}

/**
 * 条目主时间：已支付优先展示支付时间，未支付展示创建时间。
 * @param item 订单条目
 * @returns 展示时间串
 */
function mainTime(item: MemberOrderItem): string {
  return item.paid_at ?? item.created_at
}

/**
 * 点击条目：切换详情展开/收起（同一时间至多展开一条）。
 * @param item 订单条目
 * @returns 无
 */
function toggleExpand(item: MemberOrderItem): void {
  expandedOrderNo.value = expandedOrderNo.value === item.order_no ? '' : item.order_no
}

// onShow：拉取订单（loadMember 三段并行，从支付页返回后即时刷新状态）
onShow(() => {
  void me.loadMember()
})

// onHide：尽力上报缓冲埋点
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <!-- 离线提示条 -->
    <OfflineBar v-if="!network.isConnected" />

    <view class="orders">
      <!-- 加载态 -->
      <SkeletonPage v-if="me.memberLoading" type="list" :rows="4" />

      <!-- 错误态（重试） -->
      <ErrorState v-else-if="me.memberError" kind="server" @retry="me.loadMember()" />

      <!-- 空态 -->
      <EmptyState
        v-else-if="me.orders.length === 0"
        icon="🧾"
        title="还没有订单"
        desc="开通会员后，购买记录会出现在这里"
      />

      <!-- 订单列表 -->
      <view v-else class="orders__list">
        <view
          v-for="item in me.orders"
          :key="item.order_no"
          class="order-card"
          @click="toggleExpand(item)"
        >
          <view class="order-card__head">
            <text class="order-card__product">{{ PRODUCT_NAMES[item.product_type] ?? item.product_type }}</text>
            <BaseTag :text="item.status === 'paid' ? '已支付' : '待支付'" :kind="item.status === 'paid' ? 'primary' : 'warning'" />
          </view>
          <view class="order-card__body">
            <text class="order-card__amount">{{ amountText(item.amount_cents) }}</text>
            <text class="order-card__time">{{ formatTime(mainTime(item)) }}</text>
          </view>
          <text class="order-card__no">订单号 {{ item.order_no }}</text>

          <!-- 展开详情：创建/支付时间明细 -->
          <view v-if="expandedOrderNo === item.order_no" class="order-card__detail">
            <view class="order-card__detail-row">
              <text class="order-card__detail-label">创建时间</text>
              <text class="order-card__detail-value">{{ formatTime(item.created_at) }}</text>
            </view>
            <view class="order-card__detail-row">
              <text class="order-card__detail-label">支付时间</text>
              <text class="order-card__detail-value">{{ item.paid_at ? formatTime(item.paid_at) : '未支付' }}</text>
            </view>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<style scoped lang="scss">
.orders {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md) var(--space-md) var(--space-xl);
}

.orders__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.order-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-md) var(--space-lg);
  border-radius: var(--radius-card);
  background: var(--bg-card);
}

.order-card__head {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.order-card__product {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.order-card__body {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.order-card__amount {
  flex-shrink: 0;
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.order-card__time {
  flex: 1;
  min-width: 0;
  text-align: right;
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.order-card__no {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
  word-break: break-all;
}

/* ── 展开详情 ── */
.order-card__detail {
  display: flex;
  flex-direction: column;
  gap: 6rpx;
  padding-top: var(--space-xs);
  border-top: 1rpx solid var(--divider);
}

.order-card__detail-row {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.order-card__detail-label {
  flex-shrink: 0;
  width: 140rpx;
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.order-card__detail-value {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}
</style>
