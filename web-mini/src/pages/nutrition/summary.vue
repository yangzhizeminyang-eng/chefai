<!--
  文件级注释：P-19 营养总览页（分包 pages/nutrition）。
  - 自 web-stage1 RecipeDetailView 营养估算区迁移（getNutrition 语义，五数值 + 每份口径）：
    每份估算句式（NUTRITION_STATEMENT_PREFIX）+ 三大营养素环形占比（NutritionRing）+
    每份明细（热量/蛋白质/脂肪/碳水/钠，缺失项「未纳入统计」不按 0 计）+
    按份数合计行（total.kcal）+ 未纳入统计食材提示 + estimate_note 估算口径说明；
  - RL-9 固定标注 NUTRITION_ESTIMATE_NOTE（估算值，非实测值；全页仅客观陈述，
    禁止任何法定营养声称类词汇）；
  - 降级态：五数值任一缺失 → DegradedBar（部分内容未能生成）；
  - 免责（六处之三）：DisclaimerBar scene="nutrition"（营养数据为估算值，非实测值）；
  - 入口 query：recipe_id（必传，缺失转空态引导）+ servings（可选 1~20，经
    parseNutritionQuery 复用共享纯函数解析）；onLoad 埋点 nutrition_view；
  - 五态齐备：加载骨架 / 错误重试 / 空态引导 / 离线提示条；深浅色 + 字号三档适配。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad } from '@dcloudio/uni-app'
import type { ApiError, NutritionResult } from '@shared/types'
import { parseNutritionQuery } from '@shared/utils'
import {
  NUTRITION_STATEMENT_PREFIX,
  NUTRITION_ESTIMATE_NOTE,
  OFFLINE_UNCACHED_TEXT,
} from '@shared/constants'
import { getNutrition } from '@/api/endpoints'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide, trackEvent } from '@/utils/track'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import NutritionRing, { type NutritionRingItem } from '@/components/NutritionRing.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import DegradedBar from '@/components/DegradedBar.vue'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 当前菜谱 ID（null = 入口未携带 recipe_id，转空态引导） */
const recipeId = ref<number | null>(null)
/** 入口份数（1~20 整数；null = 未携带或不合法，走后端默认口径） */
const servings = ref<number | null>(null)
/** 营养估算结果 */
const nutrition = ref<NutritionResult | null>(null)
/** 加载中 */
const loading = ref(false)
/** 加载错误 */
const error = ref<ApiError | null>(null)

/** 是否入口缺参（recipe_id 缺失或非法 → 空态） */
const noEntry = computed(() => recipeId.value == null)

/**
 * 降级判定：五数值（热量/蛋白质/脂肪/碳水/钠）任一缺失即视为部分内容未能生成。
 * @returns 是否降级展示 DegradedBar
 */
const degraded = computed(() => {
  const n = nutrition.value
  if (!n) return false
  return n.kcal == null || n.protein == null || n.fat == null || n.carbs == null || n.sodium == null
})

/** 环形占比条目：三大营养素（缺失项不进环，全缺时组件展示内置空态） */
const ringItems = computed<NutritionRingItem[]>(() => {
  const n = nutrition.value
  if (!n) return []
  const items: NutritionRingItem[] = []
  if (n.protein != null) items.push({ label: '蛋白质', value: n.protein, unit: 'g' })
  if (n.fat != null) items.push({ label: '脂肪', value: n.fat, unit: 'g' })
  if (n.carbs != null) items.push({ label: '碳水', value: n.carbs, unit: 'g' })
  return items
})

/**
 * 每份估算句式（NUTRITION_STATEMENT_PREFIX「每份约含」+ 热量 + NUTRITION_ESTIMATE_NOTE 固定标注）。
 * @returns 展示文案（热量缺失时明示未纳入统计）
 */
const statementText = computed(() => {
  const kcal = nutrition.value?.kcal
  if (kcal == null) return `${NUTRITION_STATEMENT_PREFIX}：热量未纳入统计`
  return `${NUTRITION_STATEMENT_PREFIX} ${kcal} kcal（${NUTRITION_ESTIMATE_NOTE}）`
})

/** 按份数合计文案（total.kcal 同源换算；无合计数据不渲染该行） */
const totalLine = computed(() => {
  const n = nutrition.value
  if (!n || n.total?.kcal == null) return ''
  return `按 ${n.per_serving} 份合计：约 ${n.total.kcal} kcal`
})

/** 未纳入统计的食材名串（空数组不渲染提示条） */
const excludedText = computed(() => {
  const items = nutrition.value?.excluded_items ?? []
  return items.length > 0 ? `以下食材未纳入统计：${items.join('、')}` : ''
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
 * ApiError → ErrorState 错误类别（超时/网络/服务三类，不暴露状态码等技术细节）。
 * @param e 归一化 ApiError
 * @returns ErrorState kind
 */
function errorKind(e: ApiError): 'timeout' | 'network' | 'server' {
  if (e.code === 'TIMEOUT') return 'timeout'
  if (e.code === 'NETWORK') return 'network'
  return 'server'
}

/** 错误态类别（error 非空时派生；离线时按网络类处理） */
const errKind = computed(() => {
  if (error.value) return errorKind(error.value)
  return 'server' as const
})

/** 错误态补充说明：离线且无缓存时明示需联网加载 */
const errDetail = computed(() => (!network.isConnected ? OFFLINE_UNCACHED_TEXT : ''))

/**
 * 拉取营养估算（getNutrition；入口携带合法 servings 时随请求携带重算口径）。
 * @returns 无
 * @throws 不向外抛出（失败写入 error 三态并清空数据）
 */
async function loadNutrition(): Promise<void> {
  if (recipeId.value == null) return
  loading.value = true
  error.value = null
  try {
    nutrition.value = await getNutrition(recipeId.value, servings.value ?? undefined)
  } catch (e) {
    error.value = e as ApiError
    nutrition.value = null
  } finally {
    loading.value = false
  }
}

/**
 * 空态行动：回首页（tabBar 页经 goRoute 自动 switchTab）。
 * @returns 无
 */
function goHome(): void {
  goRoute(ROUTES.HOME)
}

// onLoad：解析入口 query（recipe_id 必传、servings 可选 1~20）→ 埋点 nutrition_view → 拉数据
onLoad((options) => {
  const id = Number(options?.recipe_id)
  recipeId.value = Number.isInteger(id) && id > 0 ? id : null
  // 份数解析复用共享纯函数（1~20 整数合法，非法为 null 不传参）
  servings.value = parseNutritionQuery({ servings: options?.servings }).servings
  trackEvent('nutrition_view')
  void loadNutrition()
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

    <view class="summary">
      <!-- 降级提示条：五数值任一缺失（RL-9：仅客观陈述缺失事实，不做营养声称） -->
      <DegradedBar v-if="degraded" />

      <!-- 加载态 -->
      <SkeletonPage v-if="loading" type="detail" :rows="2" />

      <!-- 错误态 -->
      <ErrorState
        v-else-if="error"
        :kind="errKind"
        :detail="errDetail"
        @retry="loadNutrition()"
      />

      <!-- 空态：入口缺 recipe_id -->
      <EmptyState
        v-else-if="noEntry"
        icon="🥗"
        title="缺少菜谱信息"
        desc="请从菜谱详情或完成烹饪页进入查看营养估算"
        action-text="去做菜"
        @action="goHome"
      />

      <template v-else-if="nutrition">
        <view class="summary__card">
          <!-- 每份估算句式（NUTRITION_STATEMENT_PREFIX + NUTRITION_ESTIMATE_NOTE 固定标注） -->
          <text class="summary__statement">{{ statementText }}</text>

          <!-- 三大营养素环形占比（缺失项不进环） -->
          <NutritionRing :items="ringItems" />

          <!-- 每份明细（缺失项「未纳入统计」） -->
          <view class="summary__grid">
            <view class="summary__cell">
              <text class="summary__value">{{ numText(nutrition.kcal, 'kcal') }}</text>
              <text class="summary__label">热量</text>
            </view>
            <view class="summary__cell">
              <text class="summary__value">{{ numText(nutrition.protein, 'g') }}</text>
              <text class="summary__label">蛋白质</text>
            </view>
            <view class="summary__cell">
              <text class="summary__value">{{ numText(nutrition.fat, 'g') }}</text>
              <text class="summary__label">脂肪</text>
            </view>
            <view class="summary__cell">
              <text class="summary__value">{{ numText(nutrition.carbs, 'g') }}</text>
              <text class="summary__label">碳水</text>
            </view>
            <view class="summary__cell">
              <text class="summary__value">{{ numText(nutrition.sodium, 'mg') }}</text>
              <text class="summary__label">钠</text>
            </view>
          </view>

          <!-- 按份数合计（total 同源换算，可缺省） -->
          <text v-if="totalLine" class="summary__total">{{ totalLine }}</text>

          <!-- 未纳入统计食材提示（warning 语义，缺失数据不按 0 计） -->
          <view v-if="excludedText" class="summary__excluded">
            <text class="summary__excluded-text">{{ excludedText }}</text>
          </view>

          <!-- 后端估算口径说明（固定含误差 ±15% 说明） -->
          <text class="summary__note">{{ nutrition.estimate_note }}</text>
        </view>
      </template>

      <!-- 免责（六处之三）：营养区估算口径专门声明 -->
      <DisclaimerBar scene="nutrition" />
    </view>
  </view>
</template>

<style scoped lang="scss">
.summary {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
}

.summary__card {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
}

.summary__statement {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

/* ── 每份明细网格（5 项，两行自适应） ── */
.summary__grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.summary__cell {
  flex: 1 1 30%;
  display: flex;
  flex-direction: column;
  gap: var(--space-2xs, 8rpx);
  padding: var(--space-sm);
  border-radius: var(--radius-ctrl);
  background: var(--bg-page);
}

.summary__value {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.summary__label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.summary__total {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

/* ── 未纳入统计提示条（warning 语义） ── */
.summary__excluded {
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-ctrl);
  background: var(--color-warning-bg);
}

.summary__excluded-text {
  font-size: var(--font-size-sm);
  line-height: 1.5;
  color: var(--color-warning);
  word-break: break-all;
}

.summary__note {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-tertiary);
}
</style>
