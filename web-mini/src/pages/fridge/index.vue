<!--
  文件级注释：P-22 我的冰箱页（tabBar）。
  - 自 web-stage1 InventoryView 拆出「冰箱列表」部分（购物清单独立分包页，经 BaseCell 入口进入）：
    条目列表（名称 / 数量档位 tag / 位置 / 到期倒计时）、临期置顶排序、临期条目 warning 样式；
  - 顶部固定说明条 INEDIBLE_JUDGE_NOTE（RL-3 第二处：到期日仅提醒，不作可食性判定）；
  - 条目点击 → 分包 ENTRY_EDIT?id=（编辑）；「添加条目」→ ENTRY_EDIT（无 id，
    inventory_add 埋点在 entry-edit 页落）；购物清单入口 BaseCell → SHOPPING；
  - 临期提醒区点击 trackEvent('inventory_expiring_click')；
  - inventory.loadItems() 加载；五态齐备；空态引导添加。
-->
<script setup lang="ts">
import { computed } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import type { InventoryItem } from '@shared/types'
import { locationLabel } from '@shared/utils'
import { INEDIBLE_JUDGE_NOTE } from '@shared/constants'
import { useInventoryStore, daysUntil } from '@/stores/inventory'
import { ROUTES } from '@/utils/routes'
import { flushOnHide, trackEvent } from '@/utils/track'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import BaseTag from '@/components-base/BaseTag.vue'
import BaseCell from '@/components-base/BaseCell.vue'
import BaseButton from '@/components-base/BaseButton.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 库存 store（items / expiringItems / loadItems） */
const inventory = useInventoryStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 数量档位中文映射（对齐源码 LEVEL_LABELS） */
const LEVEL_LABELS: Record<InventoryItem['quantity_level'], string> = {
  low: '少量',
  mid: '有',
  plenty: '充足',
}

/**
 * 到期倒计时文案（对齐源码 expireText：未设置 / 已过期 N 天 / 今天到期 / 还剩 N 天）。
 * @param expireDate 到期日 YYYY-MM-DD
 * @returns 展示文案
 */
function expireText(expireDate: string): string {
  const days = daysUntil(expireDate)
  if (!Number.isFinite(days)) return '未设置'
  if (days < 0) return `已过期 ${Math.abs(days)} 天`
  if (days === 0) return '今天到期'
  return `还剩 ${days} 天`
}

/** 条目是否临期（剩余 ≤3 天含已过期，供 warning 样式） */
const expiringIds = computed(() => new Set(inventory.expiringItems.map((it) => it.id)))

/** 临期置顶排序：剩余天数升序（临期/过期在前，无到期日垫底，对齐源码 sortedItems） */
const sortedItems = computed(() =>
  [...inventory.items].sort((a, b) => daysUntil(a.expire_date) - daysUntil(b.expire_date)),
)

/** 是否空态：加载完成、无错误且无条目 */
const isEmpty = computed(() => !inventory.loading && !inventory.error && inventory.items.length === 0)

/**
 * 点击临期提醒区：埋点 inventory_expiring_click（本条目区即临期聚合展示，进入即行为）。
 * 注：条目级点击不重复埋点（事件口径为「临期提醒点击」）。
 * @returns 无
 */
function onExpiringAreaClick(): void {
  trackEvent('inventory_expiring_click')
}

/**
 * 点击条目 → 分包记录编辑页（携带 id 回填）。
 * @param item 库存条目
 * @returns 无
 */
function editItem(item: InventoryItem): void {
  uni.navigateTo({ url: `${ROUTES.ENTRY_EDIT}?id=${item.id}`, fail: () => {} })
}

/**
 * 添加条目 → 分包记录编辑页（无 id = 新增；inventory_add 埋点由该页落）。
 * @returns 无
 */
function addItem(): void {
  uni.navigateTo({ url: ROUTES.ENTRY_EDIT, fail: () => {} })
}

/**
 * 打开购物清单分包页。
 * @returns 无
 */
function goShopping(): void {
  uni.navigateTo({ url: ROUTES.SHOPPING, fail: () => {} })
}

// onShow：每次进入重拉在库条目（tabBar 页常驻，保证新鲜）
onShow(() => {
  void inventory.loadItems()
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

    <view class="fridge">
      <!-- RL-3 固定说明条（第二处）：到期日仅提醒，不作可食性判定 -->
      <view class="fridge__note">
        <text class="fridge__note-text">{{ INEDIBLE_JUDGE_NOTE }}</text>
      </view>

      <!-- 临期提醒区（有临期条目时渲染；点击埋点） -->
      <view
        v-if="inventory.expiringItems.length > 0"
        class="fridge__expiring"
        @click="onExpiringAreaClick"
      >
        <text class="fridge__expiring-text">
          {{ inventory.expiringItems.length }} 样食材临近到期，优先吃掉它们
        </text>
      </view>

      <!-- 加载态 -->
      <SkeletonPage v-if="inventory.loading" type="list" :rows="4" />

      <!-- 错误态 -->
      <ErrorState v-else-if="inventory.error" kind="server" @retry="inventory.loadItems()" />

      <!-- 空态：引导添加 -->
      <EmptyState
        v-else-if="isEmpty"
        icon="🧊"
        title="冰箱还是空的"
        desc="把家里现有的食材记录进来，推荐会优先用掉它们"
        action-text="添加条目"
        @action="addItem"
      />

      <template v-else>
        <!-- 条目列表（临期置顶） -->
        <view class="fridge__list">
          <view
            v-for="item in sortedItems"
            :key="item.id"
            class="item-card"
            :class="{ 'is-expiring': expiringIds.has(item.id) }"
            @click="editItem(item)"
          >
            <view class="item-card__head">
              <text class="item-card__name">{{ item.ingredient_name }}</text>
              <BaseTag :text="LEVEL_LABELS[item.quantity_level]" kind="info" />
              <BaseTag
                v-if="expiringIds.has(item.id)"
                :text="expireText(item.expire_date)"
                kind="warning"
              />
            </view>
            <view class="item-card__meta">
              <text class="item-card__meta-text">位置：{{ locationLabel(item.location) }}</text>
              <text class="item-card__meta-text">到期：{{ expireText(item.expire_date) }}</text>
            </view>
          </view>
        </view>

        <!-- 添加条目 -->
        <BaseButton class="fridge__add" block @click="addItem">+ 添加条目</BaseButton>
      </template>

      <!-- 购物清单入口 -->
      <view class="fridge__shopping">
        <BaseCell title="购物清单" desc="待买食材、转入库存" arrow @click="goShopping" />
      </view>

      <DisclaimerBar scene="home" />
    </view>
  </view>
</template>

<style scoped lang="scss">
.fridge {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
}

/* ── RL-3 固定说明条 ── */
.fridge__note {
  padding: var(--space-xs) var(--space-md);
  margin-bottom: var(--space-md);
  border-radius: var(--radius-ctrl);
  background: var(--color-info-bg);
}

.fridge__note-text {
  font-size: var(--font-size-sm);
  line-height: 1.5;
  color: var(--text-secondary);
}

/* ── 临期提醒区（warning 语义，可点击埋点） ── */
.fridge__expiring {
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-md);
  min-height: var(--hit-min);
  display: flex;
  align-items: center;
  border-radius: var(--radius-card);
  background: var(--color-warning-bg);
}

.fridge__expiring-text {
  font-size: var(--font-size-base);
  color: var(--color-warning);
}

/* ── 条目列表 ── */
.fridge__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.item-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  border: 1rpx solid transparent;

  /* 临期条目 warning 强调（边框 + 底色双通道，不依赖颜色单独传达） */
  &.is-expiring {
    border-color: var(--color-warning);
    background: var(--color-warning-bg);
  }
}

.item-card__head {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.item-card__name {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-card__meta {
  display: flex;
  gap: var(--space-lg);
}

.item-card__meta-text {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.fridge__add {
  margin-top: var(--space-lg);
}

.fridge__shopping {
  margin-top: var(--space-lg);
  border-radius: var(--radius-card);
  overflow: hidden;
}
</style>
