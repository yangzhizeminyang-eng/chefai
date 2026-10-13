<!--
  文件级注释：P-06 食材选择页（W-01；pages/recommend/select）。
  自 web-stage1/src/views/SelectIngredientView.vue（493 行）迁移，语义对齐说明：
  - 食材网格：IngredientGrid 组件（内置本地关键字搜索框，仅 UI 层派生过滤），
    数据源 ingredients store（loadIngredients 全量拉取后按十类分组，分类标签对齐源码）；
  - 已选区：selectedCount + 已选 chips（点 chip 取消选中，toggle 语义与源码一致）；
  - 时令快捷区：页面顶部「当季食材」横向 chips——源码 SelectIngredientView 本身不含
    时令交互，本区交互语义 1:1 对齐源码 SeasonalView：fetchSeasonal + seasonalSubtitle
    副标题 + 点击 toggleSeasonalId（不可变 Set）维护本区选中集合；
    「开始推荐」时把选中当季食材预置进 ingredients store 已选集合（复用 toggle 写入，
    仅对「本区已选且 store 尚无」的食材触发加入侧 toggle，不清空既有手选）；
  - 「开始推荐」底部固定按钮：store 已选 ≥1 才可用（无选中点击 toast 提示）；
  - onLoad 消费 ?q=（search 页「食材类」分流带来的查询词）：调 loadIngredients(undefined, q)
    后端含别名过滤，实现「回退食材名定位」（q 为空则全量拉取）；
  - 埋点：ingredient_manual_select（网格 toggle 与时令 chip 均视为手动选择，点击时落）；
  - 五态：加载（网格骨架）/ 空（食材库空 + 重试）/ 错误（食材库错误 + 重试）/
    离线（OfflineBar）；时令区错误不阻断主功能（轻提示 + 重试）。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad, onReachBottom } from '@dcloudio/uni-app'
import type { Ingredient } from '@shared/types'
import { seasonalSubtitle, toggleSeasonalId } from '@shared/utils'
import { fetchSeasonal } from '@/api/seasonal'
import type { SeasonalResponse } from '@/api/seasonal'
import { useIngredientsStore } from '@/stores/ingredients'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide, trackEvent } from '@/utils/track'
import { toastWarning } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import IngredientGrid, { type IngredientGridCategory, type IngredientGridItem } from '@/components/IngredientGrid.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import OfflineBar from '@/components/OfflineBar.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import BaseButton from '@/components-base/BaseButton.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()
/** 食材 store：分类常量 / 列表三态 / 已选集合 */
const ingredientsStore = useIngredientsStore()

/** IngredientGrid 组件实例（触底时调 expose 的 loadMore 增量渲染） */
const gridRef = ref<InstanceType<typeof IngredientGrid> | null>(null)

/* ── 时令快捷区状态（SeasonalView 语义） ── */

/** 时令响应数据（null = 未加载） */
const seasonal = ref<SeasonalResponse | null>(null)
/** 时令数据加载中 */
const seasonalLoading = ref(false)
/** 时令数据加载错误（true = 失败，轻提示重试不阻断主功能） */
const seasonalError = ref(false)
/** 本区选中的当季食材 ID 集合（不可变更新，增删走 toggleSeasonalId 纯函数） */
const selectedSeasonalIds = ref(new Set<number>())

/** 时令副标题：month 来自服务端，未加载/异常不显示月份数字（纯函数生成） */
const seasonalTitle = computed(() => seasonalSubtitle(seasonal.value?.month))

/** 未知分类码的兜底分组名（对齐源码 other 分类语义） */
const OTHER_CATEGORY_LABEL = '其他'

/**
 * 网格分类数据：全量食材列表按十类分组（未知分类码归入「其他」）。
 * @returns IngredientGrid 需要的分类结构（仅保留非空分组）
 */
const gridCategories = computed<IngredientGridCategory[]>(() => {
  const buckets = new Map<string, IngredientGridItem[]>()
  for (const ing of ingredientsStore.list) {
    const label = ingredientsStore.categories.find((c) => c.code === ing.category)?.label
      ?? OTHER_CATEGORY_LABEL
    const bucket = buckets.get(label) ?? []
    bucket.push({ id: String(ing.id), name: ing.name })
    buckets.set(label, bucket)
  }
  return [...buckets.entries()].map(([category, items]) => ({ category, items }))
})

/**
 * 网格选中态映射（id 字符串 → 是否选中；数据源 ingredients store 已选集合）。
 * @returns Record<string, boolean>
 */
const gridSelected = computed<Record<string, boolean>>(() => {
  const map: Record<string, boolean> = {}
  for (const item of ingredientsStore.selectedList) map[String(item.id)] = true
  return map
})

/**
 * 按 ID 从当前食材列表查条目（toggle 需要完整 Ingredient 结构）。
 * @param id 食材 ID
 * @returns 命中的食材条目；未命中返回 null
 */
function findIngredient(id: number): Ingredient | null {
  return ingredientsStore.list.find((ing) => ing.id === id) ?? null
}

/**
 * 网格食材点选：写入/移出 store 已选集合（toggle 语义与源码一致）并埋点。
 * @param id 食材 ID（组件回传字符串，回转数字）
 * @param name 食材名
 * @returns 无
 */
function onGridToggle(id: string, name: string): void {
  const numId = Number(id)
  const ing = findIngredient(numId)
  ingredientsStore.toggle(ing ?? { id: numId, name, category: '' })
  trackEvent('ingredient_manual_select', { source: 'grid' })
}

/**
 * 已选 chip 点击：取消该食材选中（toggle 语义对称：再点即移出）。
 * @param id 已选食材 ID
 * @param name 已选食材名
 * @returns 无
 */
function removeSelected(id: number, name: string): void {
  const ing = findIngredient(id)
  ingredientsStore.toggle(ing ?? { id, name, category: '' })
}

/**
 * 清空全部已选（含手选与已预置的时令食材）。
 * @returns 无
 */
function clearSelected(): void {
  ingredientsStore.clear()
}

/**
 * 时令 chip 点击：切换本区选中态（不可变替换 ref 值保证响应式）并埋点。
 * @param id 当季食材 ID
 * @returns 无
 */
function toggleSeasonalChip(id: number): void {
  selectedSeasonalIds.value = toggleSeasonalId(selectedSeasonalIds.value, id)
  trackEvent('ingredient_manual_select', { source: 'seasonal' })
}

/**
 * 拉取当月时令数据（失败轻提示不阻断主功能，可重试）。
 * @returns 无
 */
async function loadSeasonal(): Promise<void> {
  seasonalLoading.value = true
  seasonalError.value = false
  try {
    seasonal.value = await fetchSeasonal()
  } catch {
    // 后端降级/网络失败：时令区轻提示，主功能（手选）不受影响
    seasonalError.value = true
  } finally {
    seasonalLoading.value = false
  }
}

/**
 * 「开始推荐」：选中 ≥1 才放行。
 * 把本区选中的当季食材预置进 store 已选集合（仅对 store 尚无的触发加入侧 toggle，
 * 不清空既有手选，语义对齐 SeasonalView.goRecommend）后跳推荐列表。
 * @returns 无
 */
function goRecommend(): void {
  const hasSeasonal = selectedSeasonalIds.value.size > 0
  if (ingredientsStore.selectedCount === 0 && !hasSeasonal) {
    toastWarning('请先选择至少 1 样食材')
    return
  }
  for (const ing of seasonal.value?.ingredients ?? []) {
    if (selectedSeasonalIds.value.has(ing.id) && !ingredientsStore.selected[ing.id]) {
      ingredientsStore.toggle({ id: ing.id, name: ing.name, category: ing.category })
    }
  }
  goRoute(ROUTES.RECOMMEND_LIST)
}

/**
 * 食材库空态行动：重试拉取全量食材。
 * @returns 无
 */
function retryIngredients(): void {
  void ingredientsStore.loadIngredients()
}

/**
 * 已选摘要（最多展示前 6 个食材名，与源码 selectedPreview 口径一致）。
 * @returns 摘要文案；无已选返回空串
 */
const selectedPreview = computed(() => {
  const names = ingredientsStore.selectedList.map((s) => s.name)
  if (names.length <= 6) return names.join('、')
  return `${names.slice(0, 6).join('、')} 等 ${names.length} 样`
})

// onLoad：拉取全量食材；消费 ?q=（食材名定位：后端含别名过滤）
onLoad((options) => {
  const q = typeof options?.q === 'string' ? options.q.trim() : ''
  void ingredientsStore.loadIngredients(undefined, q || undefined)
  void loadSeasonal()
})

// 触底：调用 IngredientGrid expose 的 loadMore() 增量渲染（分片放行防长列表卡顿）
onReachBottom(() => {
  gridRef.value?.loadMore()
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

    <view class="select">
      <!-- ⓪ 时令快捷区：当季食材横向 chips（SeasonalView 语义） -->
      <view class="select__seasonal">
        <view class="select__seasonal-head">
          <text class="select__seasonal-title">{{ seasonalTitle }}</text>
          <text v-if="selectedSeasonalIds.size > 0" class="select__seasonal-count">
            已选 {{ selectedSeasonalIds.size }}
          </text>
        </view>
        <!-- 时令加载骨架 -->
        <view v-if="seasonalLoading" class="select__seasonal-skeleton">
          <view v-for="i in 5" :key="i" class="select__seasonal-skeleton-chip" />
        </view>
        <!-- 时令失败轻提示（不阻断主功能） -->
        <view v-else-if="seasonalError" class="select__seasonal-retry" @click="loadSeasonal">
          时令数据加载失败，点击重试
        </view>
        <!-- 降级空数据：后端无当季映射时如实提示 -->
        <text v-else-if="(seasonal?.ingredients.length ?? 0) === 0" class="select__seasonal-empty">
          当月时令数据待补充
        </text>
        <scroll-view v-else scroll-x class="select__seasonal-scroll">
          <view class="select__seasonal-row">
            <view
              v-for="ing in seasonal?.ingredients ?? []"
              :key="ing.id"
              class="select__seasonal-chip"
              :class="{ 'is-active': selectedSeasonalIds.has(ing.id) }"
              @click="toggleSeasonalChip(ing.id)"
            >
              <text class="select__seasonal-chip-name">{{ ing.name }}</text>
              <text v-if="selectedSeasonalIds.has(ing.id)" class="select__seasonal-chip-check">✓</text>
            </view>
          </view>
        </scroll-view>
      </view>

      <!-- ① 食材网格（内置搜索框：本地关键字过滤，仅 UI 层派生） -->
      <view class="select__grid">
        <IngredientGrid
          ref="gridRef"
          :categories="gridCategories"
          :selected="gridSelected"
          :loading="ingredientsStore.loading"
          @toggle="onGridToggle"
        />
      </view>

      <!-- 错误态：食材库加载失败 + 重试（网格区下方覆盖展示） -->
      <ErrorState
        v-if="ingredientsStore.error && !ingredientsStore.loading"
        kind="server"
        :detail="ingredientsStore.error.message"
        @retry="retryIngredients"
      />

      <!-- 空态：食材库为空（非搜索过滤导致） -->
      <EmptyState
        v-else-if="!ingredientsStore.loading && !ingredientsStore.error && ingredientsStore.list.length === 0"
        icon="🥬"
        title="食材库暂时是空的"
        desc="稍后再来看看，或点击重试"
        action-text="重试"
        @action="retryIngredients"
      />

      <DisclaimerBar scene="home" />
    </view>

    <!-- ② 底部固定操作条：已选 N 样 + 摘要 + 开始推荐 -->
    <view class="select__footer">
      <view class="select__footer-info">
        <text class="select__footer-count">已选 {{ ingredientsStore.selectedCount }} 样</text>
        <text v-if="selectedPreview" class="select__footer-names">{{ selectedPreview }}</text>
      </view>
      <view class="select__footer-chips" v-if="ingredientsStore.selectedCount > 0">
        <scroll-view scroll-x class="select__footer-scroll">
          <view class="select__footer-chip-row">
            <view
              v-for="item in ingredientsStore.selectedList"
              :key="item.id"
              class="select__footer-chip"
              @click="removeSelected(item.id, item.name)"
            >
              <text class="select__footer-chip-name">{{ item.name }}</text>
              <text class="select__footer-chip-remove">×</text>
            </view>
            <view class="select__footer-chip is-clear" @click="clearSelected">
              <text class="select__footer-chip-name">清空</text>
            </view>
          </view>
        </scroll-view>
      </view>
      <BaseButton
        class="select__footer-btn"
        size="lg"
        :disabled="ingredientsStore.selectedCount === 0"
        @click="goRecommend"
      >
        开始推荐
      </BaseButton>
    </view>
  </view>
</template>

<style scoped lang="scss">
.select {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
  /* 底部固定操作条占位 */
  padding-bottom: 220rpx;
}

/* ── 时令快捷区 ── */
.select__seasonal {
  margin-bottom: var(--space-md);
}

.select__seasonal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-sm);
}

.select__seasonal-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.select__seasonal-count {
  font-size: var(--font-size-sm);
  color: var(--color-primary);
}

.select__seasonal-skeleton {
  display: flex;
  gap: var(--space-sm);
}

.select__seasonal-skeleton-chip {
  width: 120rpx;
  height: 64rpx;
  border-radius: var(--radius-pill);
  background: linear-gradient(90deg, var(--bg-page) 25%, var(--divider) 37%, var(--bg-page) 63%);
  background-size: 400% 100%;
  animation: seasonal-skeleton 1.4s ease infinite;
}

@keyframes seasonal-skeleton {
  0% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0 50%;
  }
}

.select__seasonal-retry,
.select__seasonal-empty {
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.select__seasonal-scroll {
  width: 100%;
  white-space: nowrap;
}

.select__seasonal-row {
  display: inline-flex;
  gap: var(--space-sm);
  padding: 4rpx 0;
}

/* 时令 chip：热区 ≥88rpx，选中态主色描边 + ✓ 双通道表达 */
.select__seasonal-chip {
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  gap: 6rpx;
  min-height: var(--hit-min);
  padding: 0 var(--space-md);
  border: 2rpx solid var(--border-color);
  border-radius: var(--radius-pill);
  background: var(--bg-card);

  &.is-active {
    border-color: var(--color-primary);
    background: var(--color-primary-weak);
  }
}

.select__seasonal-chip-name {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
}

.select__seasonal-chip-check {
  font-size: var(--font-size-sm);
  font-weight: 700;
  color: var(--color-primary);
}

/* ── 网格区 ── */
.select__grid {
  margin-bottom: var(--space-md);
}

/* ── 底部固定操作条 ── */
.select__footer {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--bg-card);
  border-top: 1rpx solid var(--divider);
}

.select__footer-info {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  min-height: var(--hit-min);
}

.select__footer-count {
  flex-shrink: 0;
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-primary);
}

.select__footer-names {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.select__footer-scroll {
  width: 100%;
  white-space: nowrap;
}

.select__footer-chip-row {
  display: inline-flex;
  gap: var(--space-xs);
  padding: 4rpx 0;
}

/* 已选 chip：可点击移除，热区 ≥88rpx */
.select__footer-chip {
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  gap: 6rpx;
  min-height: var(--hit-min);
  padding: 0 var(--space-sm);
  border-radius: var(--radius-pill);
  background: var(--color-info-bg);

  &.is-clear {
    background: var(--color-warning-bg);
  }
}

.select__footer-chip-name {
  font-size: var(--font-size-sm);
  color: var(--color-info);
}

.select__footer-chip-remove {
  font-size: var(--font-size-sm);
  color: var(--color-info);
}

.select__footer-btn {
  width: 100%;
}
</style>
