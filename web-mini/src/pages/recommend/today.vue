<!--
  文件级注释：今天吃什么页（pages/recommend/today，融合 web 端 TodayView + SeasonalView）。
  自 web-stage1/src/views/TodayView.vue（随机推选）与 SeasonalView.vue（时令食材）融合迁移：
  - 随机推选区：fetchDayMenu（GET /v1/day-menu，零输入直出 ≤6 道，随机推选语义与 web 一致）
    + groupDayMenuByTime 耗时口径分组（⏱≤15 分钟 / 15–30 分钟 / 🛒需备料，空档不渲染）
    + 「换一换」（携带上一批全部 recipe_id 作为 exclude_ids 重拉；连续 3 次同批 →
    toast「试试放宽条件或去选食材」，按钮保持可用）；
  - 时令吃什么融合区：fetchSeasonal（month + 当季食材 + 当季菜谱 ≤8 道）
    + 当季食材 chips（点选 / 全选 / 清空，toggleSeasonalId 纯函数维护）
    + 「用当季食材推荐」（选中食材预置进 ingredients.selected 与推荐主流程共用，
    仅对"本页新选中"的触发加入侧 toggle，去 recommend/list——askMode 守卫不拦）；
  - 未建档黄条（home.data && !hasProfile → 去建档，不阻断浏览；聚合未加载不误报）；
  - 口径说明条（零输入按耗时分组）+ RL-3 合规说明条（当季信息仅为食材供应参考，固定文案）；
  - 兜底入口：「我有食材，去选食材」→ select；「用冰箱里的食材」→ fridge（switchTab）；
  - 五态：骨架（正在为你挑今天这顿）/ 空（notice 展示）/ 错误重试 / 离线条；
  - 底部免责条（G-02）。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import type { ApiError, Ingredient, RecommendResultItem } from '@shared/types'
import { groupDayMenuByTime, seasonalSubtitle, toggleSeasonalId } from '@shared/utils'
import { fetchDayMenu } from '@/api/dayMenu'
import { fetchSeasonal } from '@/api/seasonal'
import type { SeasonalIngredient } from '@/api/seasonal'
import { useHomeStore } from '@/stores/home'
import { useIngredientsStore } from '@/stores/ingredients'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide, trackEvent } from '@/utils/track'
import { toastInfo } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import RecipeCard, { type RecipeCardLike } from '@/components/RecipeCard.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import BaseButton from '@/components-base/BaseButton.vue'

/** 「连续 3 次无新结果」提示阈值（新批与上一批 id 集合完全相同的连续次数） */
const STALE_REPEAT_LIMIT = 3

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()
/** 首页聚合 store（未建档黄条数据源，只读复用） */
const home = useHomeStore()
/** 食材 store（时令食材预置已选集，与推荐主流程共用） */
const ingredients = useIngredientsStore()

/* ── 随机推选区状态（对齐 web TodayView） ── */
/** 加载中标记（骨架与「换一换」置灰共用） */
const loading = ref(false)
/** 加载错误（归一化 ApiError，null 表示无错） */
const error = ref<ApiError | null>(null)
/** 当前批零输入推荐结果（≤6 道，页面按耗时分组） */
const results = ref<RecommendResultItem[]>([])
/** 后端附加提示文案（空态时展示，有则展示） */
const notice = ref('')
/** 连续相同批次计数（模块级可变状态，请求失败不计入） */
let staleStreak = 0

/* ── 时令融合区状态（对齐 web SeasonalView） ── */
/** 时令响应数据（null = 未加载/降级前） */
const seasonal = ref<{ month: number; ingredients: SeasonalIngredient[]; recipes: RecommendResultItem[] } | null>(null)
/** 时令数据加载中标记 */
const seasonalLoading = ref(false)
/** 已选中的当季食材 ID 集合（不可变更新，增删走 toggleSeasonalId 纯函数） */
const selectedIds = ref(new Set<number>())
/** 「用当季食材推荐」跳转进行中标记（按钮 loading 态） */
const going = ref(false)

/** 耗时口径分组结果（空档已被纯函数过滤，直接渲染） */
const grouped = computed(() => groupDayMenuByTime(results.value))

/** 月份副标题：month 来自服务端，未加载/异常时不显示月份数字（纯函数生成） */
const seasonalSub = computed(() => seasonalSubtitle(seasonal.value?.month))

/** 时令数据缺失判定：请求成功但后端降级无当季数据（不留白不报错） */
const seasonalNoData = computed(() => (seasonal.value?.ingredients.length ?? 0) === 0)

/**
 * 推荐条目 → RecipeCard 数据适配（RecommendResultItem → RecipeCardLike）。
 * @param r 推荐结果条目
 * @returns 卡片条目（cover_url 为空时转 undefined 走占位回落）
 */
function toCardItem(r: RecommendResultItem): RecipeCardLike {
  return {
    id: String(r.recipe_id),
    name: r.title,
    total_time: r.time_minutes,
    difficulty: r.difficulty,
    allergens: r.allergens,
    cover_url: r.cover_image_url ?? undefined,
  }
}

/**
 * 判定两个批次是否为同一批（recipe_id 集合完全一致，忽略顺序与重复）。
 * @param prevIds 上一批 recipe_id 集合
 * @param nextIds 新批 recipe_id 集合
 * @returns 集合大小相等且上一批每个 id 都出现在新批中为 true
 */
function sameIdSet(prevIds: Set<number>, nextIds: Set<number>): boolean {
  if (prevIds.size !== nextIds.size) return false
  for (const id of prevIds) {
    if (!nextIds.has(id)) return false
  }
  return true
}

/**
 * 拉取零输入直出推荐（首拉与「换一换」共用）。
 * 匿名身份由请求层统一携带 X-Anonymous-Id 头，后端据此执行档案硬过滤。
 * @param excludeIds 上一批结果的 recipe_id 列表（「换一换」排除语义；空 = 首次请求）
 * @returns 请求成功为 true（供「换一换」判断是否比对批次；失败时结果态不变且不比对）
 */
async function load(excludeIds: number[] = []): Promise<boolean> {
  loading.value = true
  error.value = null
  try {
    const resp = await fetchDayMenu(excludeIds)
    results.value = resp.results ?? []
    notice.value = resp.notice ?? ''
    return true
  } catch (e) {
    error.value = e as ApiError
    return false
  } finally {
    loading.value = false
  }
}

/**
 * 「换一换」：携带当前批全部 recipe_id 作为 exclude_ids 重拉（每次仍重发，不空转）。
 * 连续 3 次新批与上一批 recipe_id 集合完全相同（候选池不足）→ toast 提示，按钮保持可用。
 * @returns 无
 */
async function refreshBatch(): Promise<void> {
  if (loading.value) return
  const prevIds = new Set(results.value.map((r) => r.recipe_id))
  const ok = await load([...prevIds])
  if (!ok) return
  const nextIds = new Set(results.value.map((r) => r.recipe_id))
  if (sameIdSet(prevIds, nextIds)) {
    staleStreak += 1
    if (staleStreak >= STALE_REPEAT_LIMIT) {
      toastInfo('试试放宽条件或去选食材')
      staleStreak = 0
    }
  } else {
    staleStreak = 0
  }
}

/**
 * 异常重试：重发当前批次请求（沿用当前 results 作为 exclude_ids，语义同「换一换」）。
 * @returns 无
 */
function retry(): void {
  void load(results.value.map((r) => r.recipe_id))
}

/**
 * 拉取当月时令数据（独立三态；失败不清空已有数据仅置 seasonalLoading 收尾）。
 * @returns 无
 * @throws 不抛出（失败静默——时令区为融合增强区，不影响随机推选主区）
 */
async function loadSeasonal(): Promise<void> {
  seasonalLoading.value = true
  try {
    seasonal.value = await fetchSeasonal()
  } catch {
    // 时令数据失败静默：融合增强区失败不阻断"今天吃什么"主区
  } finally {
    seasonalLoading.value = false
  }
}

/**
 * 点击当季食材标签：切换选中态（不可变替换 ref 值保证响应式触发）。
 * @param ing 被点击的当季食材
 * @returns 无
 */
function toggleSelect(ing: SeasonalIngredient): void {
  selectedIds.value = toggleSeasonalId(selectedIds.value, ing.id)
}

/**
 * 全选：把全部当季食材 ID 一次性加入选中集合。
 * @returns 无
 */
function selectAll(): void {
  selectedIds.value = new Set((seasonal.value?.ingredients ?? []).map((i) => i.id))
}

/**
 * 清空：重置选中集合为空。
 * @returns 无
 */
function clearSelection(): void {
  selectedIds.value = new Set()
}

/**
 * 「用当季食材推荐」：把选中食材预置进 ingredients.selected（仅对"本页新选中"的
 * 触发加入侧 toggle，结构 {id, name} 与手选一致），随后跳推荐列表（askMode 守卫不拦）。
 * @returns 无
 */
function goSeasonalRecommend(): void {
  if (selectedIds.value.size === 0 || going.value) return
  going.value = true
  try {
    for (const ing of seasonal.value?.ingredients ?? []) {
      if (selectedIds.value.has(ing.id) && !ingredients.selected[ing.id]) {
        ingredients.toggle({ id: ing.id, name: ing.name, category: ing.category } as Ingredient)
      }
    }
    goRoute(ROUTES.RECOMMEND_LIST)
  } finally {
    going.value = false
  }
}

/**
 * 结果卡片点击 → 菜谱详情（携带 recipe_id）+ recommend_click 埋点。
 * @param card 被点击卡片
 * @returns 无
 */
function goDetail(card: RecipeCardLike): void {
  trackEvent('recommend_click', { recipe_id: card.id })
  goRoute(`${ROUTES.RECIPE_DETAIL}?recipe_id=${card.id}`)
}

/**
 * 去建档（未建档黄条动作）。
 * @returns 无
 */
function goProfile(): void {
  goRoute(ROUTES.PROFILE_LIST)
}

/**
 * 兜底：我有食材，去选食材。
 * @returns 无
 */
function goSelect(): void {
  goRoute(ROUTES.RECOMMEND_SELECT)
}

/**
 * 兜底：用冰箱里的食材（tabBar 页 switchTab）。
 * @returns 无
 */
function goFridge(): void {
  goRoute(ROUTES.FRIDGE)
}

// 首次显示时并行拉取：随机推选主区 + 时令融合区（互不阻塞）
onShow(() => {
  if (results.value.length === 0 && !loading.value && !error.value) {
    void load()
  }
  if (seasonal.value === null && !seasonalLoading.value) {
    void loadSeasonal()
  }
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

    <view class="today">
      <!-- 标题 + 副标题 -->
      <text class="today__title">今天吃什么</text>
      <text class="today__subtitle">没想好？先看这几道</text>

      <!-- 未建档黄条：聚合数据已加载且未建档时展示（不阻断浏览）；未加载不误报 -->
      <view v-if="home.data && !home.hasProfile" class="today__alert today__alert--warn">
        <text class="today__alert-text">还没有建立家庭档案，建好后推荐会更懂你（过敏原 / 口味 / 厨艺）</text>
        <view class="today__alert-btn" @click="goProfile">去建档</view>
      </view>

      <!-- 口径说明条：零输入按耗时口径分组 -->
      <view class="today__alert today__alert--info">
        <text class="today__alert-text">未选食材，按耗时口径分组；选择食材后结果更准</text>
      </view>

      <!-- 换一换（loading 中禁用；每次携带上一批全部 recipe_id 重拉） -->
      <view class="today__toolbar">
        <BaseButton
          type="primary"
          size="sm"
          :disabled="loading"
          @click="refreshBatch"
        >
          换一换
        </BaseButton>
      </view>

      <!-- 错误态：重试 -->
      <ErrorState v-if="error" kind="server" @retry="retry" />

      <!-- 加载态：骨架 + 文案（禁止全屏转圈） -->
      <template v-else-if="loading">
        <SkeletonPage type="list" :rows="4" />
        <text class="today__loading-text">正在为你挑今天这顿</text>
      </template>

      <!-- 结果态 / 空态 / 兜底区 -->
      <template v-else>
        <!-- 空态：说明 + 后端 notice（有则展示） -->
        <EmptyState
          v-if="results.length === 0"
          icon="🍽️"
          title="暂时没有合适的推荐"
          :desc="notice || '换个时间再来看看，或去选几样食材'"
        />

        <!-- 耗时口径分组渲染（空档不渲染） -->
        <view v-for="group in grouped" :key="group.key" class="today__group">
          <view class="today__group-divider" />
          <view class="today__group-title">
            {{ group.title }}
            <text class="today__group-badge">{{ group.items.length }}</text>
          </view>
          <view class="today__cards">
            <RecipeCard
              v-for="r in group.items"
              :key="r.recipe_id"
              :item="toCardItem(r)"
              @click="goDetail(toCardItem(r))"
            />
          </view>
        </view>

        <!-- 兜底区（空态与结果态均展示） -->
        <view class="today__fallback">
          <BaseButton type="primary" @click="goSelect">我有食材，去选食材</BaseButton>
          <BaseButton type="ghost" @click="goFridge">用冰箱里的食材</BaseButton>
        </view>
      </template>

      <!-- ── 时令吃什么融合区（SeasonalView 语义） ── -->
      <view class="today__seasonal">
        <view class="today__group-divider today__group-divider--top" />
        <view class="today__seasonal-head">
          <text class="today__seasonal-title">时令吃什么</text>
          <text v-if="seasonalSub" class="today__seasonal-sub">{{ seasonalSub }}</text>
        </view>

        <!-- RL-3 合规说明条（固定文案一字不改） -->
        <view class="today__alert today__alert--info">
          <text class="today__alert-text">当季信息仅为食材供应参考，不代表食材品质或营养优劣</text>
        </view>

        <!-- 时令区加载中（轻提示，不与主区骨架叠加） -->
        <text v-if="seasonalLoading" class="today__seasonal-tip">时令数据加载中…</text>

        <!-- 数据缺失：后端降级空数据 → 空态 + 兜底入口，不留白不报错 -->
        <EmptyState
          v-else-if="seasonalNoData"
          icon="🗓️"
          title="当月时令数据待补充"
          desc="看看全部食材库挑几样手边的"
          action-text="看看全部食材库"
          @action="goSelect"
        />

        <template v-else>
          <!-- 当季食材 chips（点选 / 全选 / 清空） -->
          <view class="today__chips">
            <view
              v-for="ing in seasonal?.ingredients ?? []"
              :key="ing.id"
              class="today__chip"
              :class="{ 'is-active': selectedIds.has(ing.id) }"
              @click="toggleSelect(ing)"
            >
              {{ ing.name }}
            </view>
          </view>
          <view class="today__chips-ops">
            <view class="today__chip-op" @click="selectAll">全选</view>
            <view class="today__chip-op" @click="clearSelection">清空</view>
          </view>

          <!-- 用当季食材推荐（选中 ≥1 才可用） -->
          <BaseButton
            type="primary"
            :disabled="selectedIds.size === 0 || going"
            @click="goSeasonalRecommend"
          >
            用当季食材推荐{{ selectedIds.size > 0 ? `（已选 ${selectedIds.size} 样）` : '' }}
          </BaseButton>

          <!-- 当季菜谱（≤8 道，无覆盖率语义） -->
          <template v-if="(seasonal?.recipes ?? []).length > 0">
            <view class="today__group-title today__group-title--seasonal">
              当季菜谱
              <text class="today__group-badge">{{ (seasonal?.recipes ?? []).length }}</text>
            </view>
            <view class="today__cards">
              <RecipeCard
                v-for="r in seasonal?.recipes ?? []"
                :key="r.recipe_id"
                :item="toCardItem(r)"
                @click="goDetail(toCardItem(r))"
              />
            </view>
          </template>
          <text v-else class="today__seasonal-tip">当季菜谱整理中，可先用上方食材去推荐</text>
        </template>
      </view>

      <!-- 底部免责条（G-02 通用档位） -->
      <DisclaimerBar scene="detail" />
    </view>
  </view>
</template>

<style scoped lang="scss">
.today {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
  padding-bottom: calc(var(--space-lg) + env(safe-area-inset-bottom));
  display: flex;
  flex-direction: column;
}

.today__title {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.today__subtitle {
  margin-top: 4rpx;
  font-size: var(--font-size-sm);
  color: var(--color-info);
}

/* 提示条：warn 黄 / info 蓝灰（安全色同时带文字语义，不依赖颜色） */
.today__alert {
  margin-top: var(--space-md);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-ctrl);
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);

  &--warn {
    background: var(--color-warning-bg);
  }

  &--info {
    background: var(--color-info-bg);
  }
}

.today__alert-text {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  line-height: 1.6;
}

.today__alert-btn {
  align-self: flex-start;
  box-sizing: border-box;
  min-height: 64rpx;
  padding: 0 var(--space-md);
  display: flex;
  align-items: center;
  border: 1rpx solid var(--color-warning);
  border-radius: var(--radius-ctrl);
  color: var(--color-warning);
  font-size: var(--font-size-sm);
}

.today__toolbar {
  margin-top: var(--space-md);
  display: flex;
  justify-content: flex-end;
}

.today__loading-text {
  margin-top: var(--space-md);
  text-align: center;
  color: var(--color-info);
  font-size: var(--font-size-sm);
}

/* 耗时分组 */
.today__group {
  margin-top: var(--space-lg);
}

.today__group-divider {
  height: 1rpx;
  background: var(--divider);

  &--top {
    margin-top: var(--space-xl);
  }
}

.today__group-title {
  margin-top: var(--space-md);
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);

  &--seasonal {
    margin-top: var(--space-lg);
  }
}

.today__group-badge {
  box-sizing: border-box;
  min-width: 40rpx;
  height: 40rpx;
  padding: 0 8rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  background: var(--color-primary-weak);
  color: var(--color-primary);
  font-size: var(--font-size-sm);
}

.today__cards {
  margin-top: var(--space-sm);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

/* 兜底按钮组 */
.today__fallback {
  margin-top: var(--space-xl);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

/* ── 时令融合区 ── */
.today__seasonal {
  margin-top: var(--space-md);
}

.today__seasonal-head {
  margin-top: var(--space-md);
  display: flex;
  align-items: baseline;
  gap: var(--space-sm);
}

.today__seasonal-title {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.today__seasonal-sub {
  font-size: var(--font-size-sm);
  color: var(--color-info);
}

.today__seasonal-tip {
  margin-top: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* 当季食材 chips：点选高亮主色 */
.today__chips {
  margin-top: var(--space-md);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
}

.today__chip {
  box-sizing: border-box;
  min-height: var(--hit-min);
  padding: 0 var(--space-md);
  display: flex;
  align-items: center;
  border: 1rpx solid var(--border-color);
  border-radius: var(--radius-pill);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: var(--font-size-sm);

  &.is-active {
    border-color: var(--color-primary);
    background: var(--color-primary-weak);
    color: var(--color-primary);
  }
}

.today__chips-ops {
  margin-top: var(--space-xs);
  display: flex;
  gap: var(--space-lg);
}

.today__chip-op {
  box-sizing: border-box;
  min-height: var(--hit-min);
  display: flex;
  align-items: center;
  font-size: var(--font-size-sm);
  color: var(--color-primary);
}
</style>
