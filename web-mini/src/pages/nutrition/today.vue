<!--
  文件级注释：P-20 今日摄入 / 近 7 天营养汇总页（分包 pages/nutrition）。
  - 自 web-stage1 MeView 营养汇总分区迁移（getNutritionSummary(days) 语义）：
    Tab 切换（今日 = days 1 / 近 7 天 = days 7）→ 汇总卡（总热量大数字 + 三大营养素 +
    钠，缺失项「未纳入统计」不按 0 计）+ 今日四餐明细（早/午/晚/加餐，对齐契约
    NutritionDayMeal 字段）+ 近 7 天逐日 kcal 柱状（周内最大值归一，对齐 MeView 柱状语义）；
  - 汇总值固定附注 NUTRITION_ESTIMATE_NOTE（估算值，非实测值，仅客观陈述）；
  - 契约说明：NutritionDayMeal 仅有营养数值（无菜名/份量/时间/recipe_id 字段），
    故餐次条目不做菜谱跳转，仅展示该餐营养构成；
  - 空态（今日还没有记录 → 去做菜按钮 switchTab 回首页）/ 错误重试 / 离线提示条五态齐备；
  - 手动补录入口（BaseCell → 分包 manual 页，对齐 MeView「补录外食」按钮语义）；
  - 免责：DisclaimerBar scene="nutrition"（营养数据为估算值，非实测值）；深浅色 + 字号适配。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import type { ApiError, NutritionDayMeal, NutritionSummaryResponse } from '@shared/types'
import { NUTRITION_ESTIMATE_NOTE, OFFLINE_UNCACHED_TEXT } from '@shared/constants'
import { getNutritionSummary } from '@/api/endpoints'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide } from '@/utils/track'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import BaseCell from '@/components-base/BaseCell.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 页内 Tab：today 今日（days=1）/ week 近 7 天（days=7） */
const activeTab = ref<'today' | 'week'>('today')

/** 汇总数据（当前 Tab 对应天数口径） */
const data = ref<NutritionSummaryResponse | null>(null)
/** 加载中 */
const loading = ref(false)
/** 加载错误 */
const error = ref<ApiError | null>(null)

/** 四餐次序与中文标签（对齐契约 meals 四键） */
const MEAL_LABELS: ReadonlyArray<{ key: keyof NutritionSummaryResponse['days'][number]['meals']; label: string }> = [
  { key: 'breakfast', label: '早餐' },
  { key: 'lunch', label: '午餐' },
  { key: 'dinner', label: '晚餐' },
  { key: 'snack', label: '加餐' },
]

/** 近 7 天逐日 kcal 行（四餐相加；hasData = 当日至少计入一餐） */
const dailyRows = computed(() => {
  const days = data.value?.days ?? []
  return days.map((d) => {
    const total =
      (d.meals.breakfast.kcal ?? 0) +
      (d.meals.lunch.kcal ?? 0) +
      (d.meals.dinner.kcal ?? 0) +
      (d.meals.snack.kcal ?? 0)
    return { date: d.date, kcal: total, hasData: total > 0 }
  })
})

/** 周内最大单日 kcal（柱状归一基数，最小 1 防除零） */
const maxDailyKcal = computed(() => Math.max(1, ...dailyRows.value.map((d) => d.kcal)))

/** 今日四餐明细（仅今日 Tab 展示；全缺数据行在模板中隐藏） */
const todayMeals = computed(() => {
  if (activeTab.value !== 'today' || !data.value || data.value.days.length === 0) return []
  const meals = data.value.days[0]?.meals
  if (!meals) return []
  return MEAL_LABELS.map(({ key, label }) => ({ label, meal: meals[key] as NutritionDayMeal }))
})

/** 是否整体空态：当前 Tab 全部逐日无数据（合计也不渲染） */
const isEmpty = computed(() => !loading.value && !error.value && dailyRows.value.every((d) => !d.hasData))

/** 空态标题（按 Tab 区分口径） */
const emptyTitle = computed(() => (activeTab.value === 'today' ? '今日还没有记录' : '近 7 天还没有记录'))

/** 全周期未纳入统计食材串（空数组不渲染） */
const excludedText = computed(() => {
  const items = data.value?.excluded ?? []
  return items.length > 0 ? `以下食材缺少营养数据，未纳入统计：${items.join('、')}` : ''
})

/**
 * 数值 → 展示文案（缺失项明示「未纳入统计」，不按 0 计）。
 * @param v 数值（可空）
 * @param unit 单位（kcal/g/mg）
 * @returns 展示文案
 */
function numText(v: number | null, unit: string): string {
  return v != null ? `${v} ${unit}` : '未纳入统计'
}

/**
 * 单餐是否有数据（五值任一非空即有；全空行不渲染）。
 * @param meal 单餐营养数据
 * @returns 是否有数据
 */
function mealHasData(meal: NutritionDayMeal): boolean {
  return meal.kcal != null || meal.protein != null || meal.fat != null || meal.carb != null || meal.sodium != null
}

/**
 * 逐日柱状宽度百分比（相对周内最大值归一）。
 * @param kcal 当日 kcal
 * @returns 百分比数值（0~100）
 */
function barPercent(kcal: number): number {
  return Math.min(100, Math.round((kcal / maxDailyKcal.value) * 100))
}

/**
 * ApiError → ErrorState 错误类别（不暴露技术细节）。
 * @param e 归一化 ApiError
 * @returns ErrorState kind
 */
function errorKind(e: ApiError): 'timeout' | 'network' | 'server' {
  if (e.code === 'TIMEOUT') return 'timeout'
  if (e.code === 'NETWORK') return 'network'
  return 'server'
}

/** 错误态类别 */
const errKind = computed(() => (error.value ? errorKind(error.value) : ('server' as const)))

/** 错误态补充说明：离线且无缓存时明示需联网加载 */
const errDetail = computed(() => (!network.isConnected ? OFFLINE_UNCACHED_TEXT : ''))

/**
 * 拉取营养汇总（按当前 Tab 天数；切换 Tab / 重试共用）。
 * @returns 无
 * @throws 不向外抛出（失败写入 error 三态并清空数据）
 */
async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    data.value = await getNutritionSummary(activeTab.value === 'today' ? 1 : 7)
  } catch (e) {
    error.value = e as ApiError
    data.value = null
  } finally {
    loading.value = false
  }
}

/**
 * 切换 Tab 并重拉对应天数数据。
 * @param tab 目标 Tab（today / week）
 * @returns 无
 */
function switchTab(tab: 'today' | 'week'): void {
  if (activeTab.value === tab) return
  activeTab.value = tab
  void load()
}

/**
 * 空态行动：去做菜（tabBar 页经 goRoute 自动 switchTab）。
 * @returns 无
 */
function goHome(): void {
  goRoute(ROUTES.HOME)
}

/**
 * 打开手动补录页（分包 manual）。
 * @returns 无
 */
function goManual(): void {
  goRoute(ROUTES.NUTRITION_MANUAL)
}

// onShow：进入页面拉取当前 Tab 数据（返回刷新保证新鲜）
onShow(() => {
  void load()
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
      <!-- Tab 切换（今日 / 近 7 天） -->
      <view class="today__tabs">
        <view
          class="today__tab"
          :class="{ 'is-active': activeTab === 'today' }"
          @click="switchTab('today')"
        >
          今日
        </view>
        <view
          class="today__tab"
          :class="{ 'is-active': activeTab === 'week' }"
          @click="switchTab('week')"
        >
          近 7 天
        </view>
      </view>

      <!-- 加载态 -->
      <SkeletonPage v-if="loading" type="list" :rows="3" />

      <!-- 错误态 -->
      <ErrorState v-else-if="error" :kind="errKind" :detail="errDetail" @retry="load()" />

      <!-- 空态：全周期无记录 -->
      <EmptyState
        v-else-if="isEmpty"
        icon="🍽️"
        :title="emptyTitle"
        desc="做完菜会自动记入营养汇总，也可手动补录一餐"
        action-text="去做菜"
        @action="goHome"
      />

      <template v-else-if="data">
        <!-- 汇总卡：总热量大数字（固定附注估算值标注）+ 三大营养素 + 钠 -->
        <view class="today__card">
          <view class="today__kcal">
            <text class="today__kcal-value">{{ numText(data.totals.kcal, 'kcal') }}</text>
            <text class="today__kcal-note">{{ NUTRITION_ESTIMATE_NOTE }}</text>
          </view>
          <view class="today__nutrients">
            <view class="today__nutrient">
              <text class="today__nutrient-value">{{ numText(data.totals.protein, 'g') }}</text>
              <text class="today__nutrient-label">蛋白质</text>
            </view>
            <view class="today__nutrient">
              <text class="today__nutrient-value">{{ numText(data.totals.fat, 'g') }}</text>
              <text class="today__nutrient-label">脂肪</text>
            </view>
            <view class="today__nutrient">
              <text class="today__nutrient-value">{{ numText(data.totals.carb, 'g') }}</text>
              <text class="today__nutrient-label">碳水</text>
            </view>
            <view class="today__nutrient">
              <text class="today__nutrient-value">{{ numText(data.totals.sodium, 'mg') }}</text>
              <text class="today__nutrient-label">钠</text>
            </view>
          </view>
        </view>

        <!-- 今日 Tab：四餐明细（对齐契约 NutritionDayMeal，全空餐次不渲染） -->
        <view v-if="activeTab === 'today'" class="today__meals">
          <text class="today__section-title">餐次明细</text>
          <view
            v-for="row in todayMeals"
            v-show="mealHasData(row.meal)"
            :key="row.label"
            class="meal-row"
          >
            <text class="meal-row__label">{{ row.label }}</text>
            <view class="meal-row__body">
              <text class="meal-row__kcal">{{ numText(row.meal.kcal, 'kcal') }}</text>
              <text class="meal-row__meta">
                蛋白 {{ numText(row.meal.protein, 'g') }} · 脂肪 {{ numText(row.meal.fat, 'g') }} ·
                碳水 {{ numText(row.meal.carb, 'g') }}
              </text>
            </view>
          </view>
        </view>

        <!-- 近 7 天 Tab：逐日 kcal 柱状（缺失日明示未纳入统计） -->
        <view v-else class="today__days">
          <text class="today__section-title">每日热量</text>
          <view v-for="d in dailyRows" :key="d.date" class="day-row">
            <text class="day-row__date">{{ d.date.slice(5) }}</text>
            <view class="day-row__bar-track">
              <view
                class="day-row__bar"
                :style="{ width: `${barPercent(d.kcal)}%` }"
                :class="{ 'is-empty': !d.hasData }"
              />
            </view>
            <text v-if="d.hasData" class="day-row__value">{{ d.kcal }} kcal</text>
            <text v-else class="day-row__miss">未纳入统计</text>
          </view>
        </view>

        <!-- 全周期未纳入统计食材说明 -->
        <view v-if="excludedText" class="today__excluded">
          <text class="today__excluded-text">{{ excludedText }}</text>
        </view>

        <!-- 手动补录入口（对齐 MeView「补录外食」语义） -->
        <view class="today__manual">
          <BaseCell
            title="手动记录一餐"
            desc="外食 / 加餐补录，按估算口径计入汇总"
            arrow
            @click="goManual"
          />
        </view>
      </template>

      <!-- 免责（营养区估算口径专门声明） -->
      <DisclaimerBar scene="nutrition" />
    </view>
  </view>
</template>

<style scoped lang="scss">
.today {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
}

/* ── Tab 切换 ── */
.today__tabs {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-md);
}

.today__tab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--hit-min);
  border-radius: var(--radius-ctrl);
  border: 1rpx solid var(--border-color);
  background: var(--bg-card);
  font-size: var(--font-size-base);
  color: var(--text-secondary);

  &.is-active {
    border-color: var(--color-primary);
    background: var(--color-primary-weak);
    color: var(--color-primary);
    font-weight: 600;
  }
}

/* ── 汇总卡 ── */
.today__card {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
}

.today__kcal {
  display: flex;
  align-items: baseline;
  gap: var(--space-sm);
}

.today__kcal-value {
  font-size: 48rpx;
  font-weight: 700;
  color: var(--text-primary);
}

.today__kcal-note {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.today__nutrients {
  display: flex;
  gap: var(--space-sm);
}

.today__nutrient {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8rpx;
  padding: var(--space-sm);
  border-radius: var(--radius-ctrl);
  background: var(--bg-page);
}

.today__nutrient-value {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.today__nutrient-label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

/* ── 区块标题 ── */
.today__section-title {
  display: block;
  margin-bottom: var(--space-sm);
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

/* ── 今日四餐明细 ── */
.today__meals {
  margin-top: var(--space-md);
  display: flex;
  flex-direction: column;
}

.meal-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-md);
  padding: var(--space-sm) 0;
  border-bottom: 1rpx solid var(--divider);

  &:last-child {
    border-bottom: none;
  }
}

.meal-row__label {
  flex-shrink: 0;
  width: 72rpx;
  font-size: var(--font-size-base);
  color: var(--text-primary);
}

.meal-row__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4rpx;
}

.meal-row__kcal {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.meal-row__meta {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

/* ── 近 7 天逐日柱状 ── */
.today__days {
  margin-top: var(--space-md);
  display: flex;
  flex-direction: column;
}

.day-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-xs) 0;
}

.day-row__date {
  flex-shrink: 0;
  width: 88rpx;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.day-row__bar-track {
  flex: 1;
  min-width: 0;
  height: 24rpx;
  border-radius: var(--radius-pill);
  background: var(--bg-page);
  overflow: hidden;
}

.day-row__bar {
  height: 100%;
  border-radius: var(--radius-pill);
  background: var(--color-primary-weak, var(--color-primary));

  &.is-empty {
    background: var(--divider);
  }
}

.day-row__value {
  flex-shrink: 0;
  width: 160rpx;
  text-align: right;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
}

.day-row__miss {
  flex-shrink: 0;
  width: 160rpx;
  text-align: right;
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* ── 未纳入统计食材说明 ── */
.today__excluded {
  margin-top: var(--space-md);
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-ctrl);
  background: var(--color-warning-bg);
}

.today__excluded-text {
  font-size: var(--font-size-sm);
  line-height: 1.5;
  color: var(--color-warning);
  word-break: break-all;
}

.today__manual {
  margin-top: var(--space-lg);
  border-radius: var(--radius-card);
  overflow: hidden;
}
</style>
