<!--
  文件级注释：P-11 被过滤清单页（pages/recommend/filtered）。
  数据源与口径说明（对齐 recommend store 源码语义）：
  - 统计行：主推荐响应 filtered_by 计数求和（allergen + dietary_restriction + difficulty +
    equipment），与列表页统计行同源同数（DEF-03 一致性）；
  - 分组明细：POST /v1/recommend/filtered 重放接口（fetchFilteredItems，store 内已按
    「多成员并集去重」口径组装 allergen_codes / dietary_restrictions，明细与主推荐过滤
    条件同口径），按原因类型码（allergen / taboo / difficulty / equipment）分组展示：
    每组展示数量（组内被过滤菜谱去重数）与原因标签（{type, detail} 的 detail 后端文案直出，
    type 中文映射走 store 导出的 filterReasonLabel）；
  - 过敏原分组明确「因过敏原被过滤 N 道」（过敏原五处生效之五）；
    进入页面即 trackEvent('filtered_by_allergen')；
  - 明细重放失败：store 已 toast 降级（filteredLoadFailed），页面走 ErrorState 重试；
  - 空态：无被过滤菜谱（EmptyState）。五态齐备（加载/空/错误/离线）。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad } from '@dcloudio/uni-app'
import type { FilteredRecipeItem } from '@shared/types'
import { filterReasonLabel, useRecommendStore } from '@/stores/recommend'
import { ROUTES, goRoute } from '@/utils/routes'
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

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()
/** 推荐 store：filtered 计数 + filteredItems 明细 + 重放 action */
const recommendStore = useRecommendStore()

/** 重放明细加载中（页面本地态，覆盖 store 拉取过程） */
const loading = ref(false)

/** 统计行总数：主推荐 filtered_by 求和（与列表页同源同数，DEF-03） */
const filteredTotal = computed(() => {
  const f = recommendStore.filtered
  return (f.allergen ?? 0) + (f.dietary_restriction ?? 0) + (f.difficulty ?? 0) + (f.equipment ?? 0)
})

/** 因过敏原被过滤的数量（过敏原五处生效之五：分组明确的口径来源） */
const allergenCount = computed(() => recommendStore.filtered.allergen ?? 0)

/** 分组条目结构（按原因类型聚合的明细视图） */
interface ReasonGroup {
  /** 原因类型码（allergen / taboo / difficulty / equipment） */
  type: string
  /** 类型中文标签（filterReasonLabel 映射） */
  label: string
  /** 组内被过滤菜谱数（按 recipe_id 去重） */
  count: number
  /** 组内去重原因文案（后端 detail 直出，同文案合并） */
  reasons: string[]
  /** 组内被过滤菜谱名列表（保持后端返回顺序） */
  titles: string[]
}

/**
 * 明细按原因类型分组（一菜多原因会在多个分组各计一次；组内按 recipe_id 去重计数）。
 * @returns 分组数组（按类型码首现顺序）
 */
const reasonGroups = computed<ReasonGroup[]>(() => {
  const order: string[] = []
  const map = new Map<string, ReasonGroup>()
  for (const item of recommendStore.filteredItems as FilteredRecipeItem[]) {
    for (const reason of item.filter_reasons) {
      let group = map.get(reason.type)
      if (!group) {
        group = { type: reason.type, label: filterReasonLabel(reason.type), count: 0, reasons: [], titles: [] }
        map.set(reason.type, group)
        order.push(reason.type)
      }
      if (!group.titles.includes(item.title)) {
        group.titles.push(item.title)
        group.count += 1
      }
      if (!group.reasons.includes(reason.detail)) group.reasons.push(reason.detail)
    }
  }
  return order.map((type) => map.get(type) as ReasonGroup)
})

/**
 * 拉取被过滤明细（重放接口；store 内部失败已 toast 并置 filteredLoadFailed）。
 * @returns 无
 */
async function loadFiltered(): Promise<void> {
  loading.value = true
  await recommendStore.fetchFilteredItems()
  loading.value = false
}

/**
 * 错误重试：重新拉取被过滤明细。
 * @returns 无
 */
function retry(): void {
  void loadFiltered()
}

/**
 * 返回推荐列表（本页为列表页过滤统计行的下钻页）。
 * @returns 无
 */
function goBack(): void {
  goRoute(ROUTES.RECOMMEND_LIST)
}

// onLoad：进入即拉明细 + 落 filtered_by_allergen（过敏原五处生效之五，查看被过滤清单行为）
onLoad(() => {
  trackEvent('filtered_by_allergen', { allergen_count: allergenCount.value })
  void loadFiltered()
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

    <view class="rfiltered">
      <!-- 统计行：与列表页数量一致（filtered_by 求和，DEF-03） -->
      <view class="rfiltered__summary">
        <text class="rfiltered__summary-text">本次推荐共为你过滤 {{ filteredTotal }} 道</text>
        <text v-if="allergenCount > 0" class="rfiltered__summary-allergen">
          因过敏原被过滤 {{ allergenCount }} 道
        </text>
      </view>

      <!-- 加载态：明细重放中 -->
      <SkeletonPage v-if="loading" type="list" :rows="4" />

      <!-- 错误态：明细重放失败（store 已 toast）+ 重试 -->
      <ErrorState
        v-else-if="recommendStore.filteredLoadFailed"
        kind="server"
        detail="过滤明细加载失败"
        @retry="retry"
      />

      <!-- 空态：无被过滤菜谱 -->
      <EmptyState
        v-else-if="recommendStore.filteredItems.length === 0"
        icon="✅"
        title="当前没有被过滤的菜谱"
        desc="你的食材与档案条件没有触发过滤，回到推荐继续挑选吧"
        action-text="返回推荐列表"
        @action="goBack"
      />

      <!-- 分组明细：按原因类型（过敏原/忌口/难度/设备） -->
      <template v-else>
        <view v-for="group in reasonGroups" :key="group.type" class="rfiltered__group">
          <view class="rfiltered__group-head">
            <text class="rfiltered__group-title">{{ group.label }}</text>
            <!-- 过敏原分组明确句式（RL 口径：因过敏原被过滤 N 道） -->
            <text class="rfiltered__group-count">
              {{ group.type === 'allergen' ? `因过敏原被过滤 ${group.count} 道` : `被过滤 ${group.count} 道` }}
            </text>
          </view>
          <!-- 原因标签：detail 后端文案直出（type 中文映射 filterReasonLabel） -->
          <view class="rfiltered__reasons">
            <BaseTag v-for="reason in group.reasons" :key="reason" :text="reason" kind="neutral" />
          </view>
          <!-- 组内菜谱清单 -->
          <view class="rfiltered__items">
            <view v-for="title in group.titles" :key="title" class="rfiltered__item">
              <text class="rfiltered__item-title">{{ title }}</text>
              <BaseTag text="已过滤" kind="danger" />
            </view>
          </view>
        </view>
      </template>

      <DisclaimerBar scene="home" />
    </view>
  </view>
</template>

<style scoped lang="scss">
.rfiltered {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
}

/* ── 统计行 ── */
.rfiltered__summary {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-md);
  border-radius: var(--radius-ctrl);
  background: var(--color-info-bg);
}

.rfiltered__summary-text {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.rfiltered__summary-allergen {
  font-size: var(--font-size-sm);
  color: var(--color-danger);
}

/* ── 分组 ── */
.rfiltered__group {
  margin-top: var(--space-md);
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.rfiltered__group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
}

.rfiltered__group-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.rfiltered__group-count {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.rfiltered__reasons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  margin-top: var(--space-sm);
}

.rfiltered__items {
  display: flex;
  flex-direction: column;
  margin-top: var(--space-sm);
}

.rfiltered__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
  min-height: var(--hit-min);
  padding: var(--space-xs) 0;
  border-bottom: 1rpx solid var(--divider);

  &:last-child {
    border-bottom: none;
  }
}

.rfiltered__item-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
}
</style>
