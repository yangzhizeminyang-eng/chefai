<!--
  文件级注释：P-10 推荐列表页（W-02；pages/recommend/list）。
  自 web-stage1/src/views/RecommendView.vue（466 行）迁移，语义对齐说明：
  - onLoad 发起推荐：recommend store fetchRecommend（内部按请求指纹防重复）；
    askMode=true 时一律跳过手选初始重拉（NEW-02 守卫：问句结果不被覆写，直接呈现）；
  - 三档分组渲染（✅现在就能做 / 🛒差1–2样 / 💡需要多买几样，groupResults 纯函数），
    卡片 RecipeCard（askMode 隐藏覆盖率语义由卡片本身不渲染该列承接）；
  - 埋点：recommend_request（请求发出）、recommend_impression（列表渲染完成，单次）、
    recommend_click（卡片点击跳详情）；
  - 🔴 RL-1 blocked 处理：响应为短路体时页面全屏 RiskBlockModal（kind 按
    payload.risk.category 映射 food/allergen/medical，detail 传后端说明正文），
    不渲染任何业务列表内容；trackEvent('safety_block')（medical 类改落
    medical_refuse，安全事件立即 flush）；关闭弹窗清 blockedPayload 并 navigateBack；
  - safeMode → DegradedBar(safeMode)；partialNotice → DegradedBar(文案)；
    notice → 信息行；不足 8 条如实说明（源码 insufficientNotice 口径）；
  - 过滤统计行（「已为你过滤 N 道」）→ 点击进 P-11 filtered 页；
  - 空态：EmptyState +「换个食材试试」返回选择页；五态齐备（加载/空/错误/离线/降级）。
-->
<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { onHide, onLoad } from '@dcloudio/uni-app'
import type { BlockedResponse, RecommendResultItem } from '@shared/types'
import { groupResults } from '@shared/utils'
import { useRecommendStore } from '@/stores/recommend'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide, trackEvent } from '@/utils/track'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import { DEGRADED_BAR_TEXT } from '@shared/constants'
import RiskBlockModal from '@/components/RiskBlockModal.vue'
import DegradedBar from '@/components/DegradedBar.vue'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import RecipeCard, { type RecipeCardLike } from '@/components/RecipeCard.vue'
import BaseTag from '@/components-base/BaseTag.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()
/** 推荐 store：三档结果 / 加载态 / 过滤数据 / blockedPayload / askMode */
const recommendStore = useRecommendStore()

/** 全屏拦截弹窗可见性（blockedPayload 非空即展示，RL-1） */
const blockVisible = ref(false)
/** 是否已落过 recommend_impression（单次口径，防重复埋点） */
let impressionSent = false

/** 三档分组定义（顺序即展示顺序，对齐源码 GROUPS） */
const GROUPS = [
  { level: 'can_cook_now', title: '✅ 现在就能做' },
  { level: 'missing_1_2', title: '🛒 差 1–2 样' },
  { level: 'need_more', title: '💡 需要多买几样' },
] as const

/**
 * 三档分组结果（groupResults 纯函数；未知 match_level 条目不落入任何档）。
 * @returns 带标题与条目的分组数组
 */
const grouped = computed(() => {
  const buckets = groupResults(recommendStore.results as RecommendResultItem[])
  return GROUPS.map((g) => ({ ...g, items: buckets[g.level] }))
})

/**
 * 推荐条目 → RecipeCard 数据适配（RecommendResultItem → RecipeCardLike）。
 * @param r 推荐结果条目
 * @returns 卡片条目（cover_url 为 null 时转 undefined 走占位回落）
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

/** 被过滤计数总计（allergen + dietary_restriction + difficulty + equipment，含设备维度） */
const filteredTotal = computed(() => {
  const f = recommendStore.filtered
  return (f.allergen ?? 0) + (f.dietary_restriction ?? 0) + (f.difficulty ?? 0) + (f.equipment ?? 0)
})

/** 不足 8 条如实说明（宁缺毋滥口径，源码 insufficientNotice；ask 直达态不展示） */
const insufficientNotice = computed(() => {
  if (recommendStore.askMode) return ''
  const n = recommendStore.results.length
  if (n === 0 || n >= 8) return ''
  return `本次为你匹配到 ${n} 道菜谱（推荐上限 8 道）：现有食材组合有限，宁缺毋滥，不为凑数填充低质推荐。`
})

/**
 * 拦截类别码 → RiskBlockModal kind 映射。
 * medical_refusal → medical（中性）/ allergen_conflict → allergen（警示）/ 其余 → food（危险）。
 * @param category risk.category 编码
 * @returns RiskBlockModal 的 kind
 */
function blockedKind(category: string): 'food' | 'allergen' | 'medical' {
  if (category === 'medical_refusal') return 'medical'
  if (category === 'allergen_conflict') return 'allergen'
  return 'food'
}

/** 拦截弹窗 kind（computed 包装 blockedKind） */
const blockKind = computed<'food' | 'allergen' | 'medical'>(() =>
  blockedKind(recommendStore.blockedPayload?.risk?.category ?? ''),
)

/** 拦截弹窗补充说明（后端 risk.body 正文直出） */
const blockDetail = computed(() => recommendStore.blockedPayload?.risk?.body ?? '')

/**
 * 进入页面发起推荐（NEW-02：askMode 一律不重拉）。
 * 埋点 recommend_request（请求发出）；响应为短路体 → 全屏 RiskBlockModal（RL-1）；
 * 正常体且列表非空 → nextTick 后落 recommend_impression（单次）。
 * @returns 无
 */
async function initialFetch(): Promise<void> {
  if (recommendStore.askMode) {
    // ask 直达态：结果已在 store（applyAskResults 落库），直接呈现不重发请求
    await sendImpression()
    return
  }
  trackEvent('recommend_request')
  await recommendStore.fetchRecommend()
  if (recommendStore.blockedPayload) {
    showBlockModal()
    return
  }
  await sendImpression()
}

/**
 * 列表渲染完成后落 recommend_impression（单次；有结果才落）。
 * @returns 无
 */
async function sendImpression(): Promise<void> {
  if (impressionSent || recommendStore.results.length === 0) return
  await nextTick()
  impressionSent = true
  trackEvent('recommend_impression', { count: recommendStore.results.length })
}

/**
 * 展示全屏拦截弹窗并落安全埋点（medical 类落 medical_refuse，其余落 safety_block；
   安全类事件在 track 内立即 flush，合规举证优先）。
 * @returns 无
 */
function showBlockModal(): void {
  const payload: BlockedResponse | null = recommendStore.blockedPayload
  const isMedical = payload?.risk?.category === 'medical_refusal'
  trackEvent(isMedical ? 'medical_refuse' : 'safety_block', {
    category: payload?.risk?.category ?? '',
    rule_code: payload?.risk?.rule_code ?? '',
  })
  blockVisible.value = true
}

/**
 * 关闭拦截弹窗：清 blockedPayload 并返回上一页（RL-1 关闭语义）。
 * @returns 无
 */
function closeBlockModal(): void {
  blockVisible.value = false
  recommendStore.blockedPayload = null
  uni.navigateBack({ fail: () => {} })
}

/**
 * 卡片点击 → 菜谱详情（携带 recipe_id）+ recommend_click 埋点。
 * @param card 被点击的卡片条目
 * @returns 无
 */
function goDetail(card: RecipeCardLike): void {
  trackEvent('recommend_click', { recipe_id: card.id })
  goRoute(`${ROUTES.RECIPE_DETAIL}?recipe_id=${card.id}`)
}

/**
 * 过滤统计行点击 → P-11 被过滤清单页。
 * @returns 无
 */
function goFiltered(): void {
  goRoute(ROUTES.RECOMMEND_FILTERED)
}

/**
 * 编辑食材 → 返回食材选择页（摘要栏入口；空态行动同）。
 * @returns 无
 */
function goSelect(): void {
  goRoute(ROUTES.RECOMMEND_SELECT)
}

/**
 * 错误重试：强制重发推荐请求（绕过请求指纹）。
 * @returns 无
 */
function retry(): void {
  void recommendStore.fetchRecommend(true)
}

// onLoad：发起推荐（askMode 守卫在 initialFetch 内）
onLoad(() => {
  void initialFetch()
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

    <!-- 🔴 RL-1：blocked 态——blockedPayload 非空时页面仅渲染全屏拦截弹窗，
         不渲染任何业务列表内容（摘要/通知/列表全部排除，拦截体纯净语义） -->
    <template v-if="recommendStore.blockedPayload">
      <view class="rlist__blocked-mask-body" />
      <RiskBlockModal
        :visible="blockVisible"
        :kind="blockKind"
        :detail="blockDetail"
        @close="closeBlockModal"
      />
    </template>

    <!-- 业务内容区（blocked 态整区排除） -->
    <view v-else class="rlist">
      <!-- 摘要栏：手选 = 已用食材 + 编辑入口；ask 直达 = 来源问句 + 改手选 -->
      <view class="rlist__summary">
        <template v-if="recommendStore.askMode">
          <view class="rlist__summary-row">
            <text class="rlist__summary-label">来自你的提问：</text>
            <text class="rlist__summary-question">{{ recommendStore.askQuestion }}</text>
          </view>
          <view class="rlist__summary-link" @click="goSelect">
            <text class="rlist__summary-link-text">改为手选食材</text>
          </view>
        </template>
        <template v-else>
          <view class="rlist__summary-row">
            <text class="rlist__summary-label">已用食材：</text>
            <view class="rlist__summary-tags">
              <BaseTag v-for="name in recommendStore.usedIngredients" :key="name" :text="name" kind="info" />
            </view>
          </view>
          <view class="rlist__summary-link" @click="goSelect">
            <text class="rlist__summary-link-text">编辑食材</text>
          </view>
        </template>
      </view>

      <!-- 保守模式条（§5.7 / RL-4：SAFE_MODE_BAR_TEXT 常量收口） -->
      <DegradedBar v-if="recommendStore.safeMode" safe-mode />

      <!-- 部分失败说明条（partial_failures 非空：DEGRADED_BAR_TEXT + 明细） -->
      <view v-if="recommendStore.partialNotice" class="rlist__notice is-warning">
        <text class="rlist__notice-text">{{ DEGRADED_BAR_TEXT }}</text>
        <text class="rlist__notice-detail">{{ recommendStore.partialNotice }}</text>
      </view>

      <!-- 后端附加提示（notice 非空如实展示） -->
      <view v-if="recommendStore.notice" class="rlist__notice is-info">
        <text class="rlist__notice-text">{{ recommendStore.notice }}</text>
      </view>

      <!-- 错误态：错误 + 重试 -->
      <ErrorState
        v-if="recommendStore.error && !recommendStore.loading"
        kind="server"
        :detail="recommendStore.error.message"
        @retry="retry"
      />

      <!-- 加载态：骨架 +「正在为你挑选…」 -->
      <template v-if="recommendStore.loading">
        <SkeletonPage type="list" :rows="5" />
        <text class="rlist__loading-text">正在为你挑选…</text>
      </template>

      <template v-else-if="!recommendStore.error">
        <!-- 空态：无匹配 + 换个食材试试 -->
        <EmptyState
          v-if="recommendStore.results.length === 0"
          icon="🍽️"
          title="现有食材暂时匹配不到合适的菜"
          desc="换个食材组合，或放宽条件再试试"
          action-text="换个食材试试"
          @action="goSelect"
        />

        <template v-else>
          <!-- 过滤统计行：点击进被过滤清单页 -->
          <view v-if="filteredTotal > 0 && !recommendStore.askMode" class="rlist__filtered" @click="goFiltered">
            <text class="rlist__filtered-text">已为你过滤 {{ filteredTotal }} 道（点击查看明细）</text>
          </view>

          <!-- 不足 8 条如实说明（宁缺毋滥） -->
          <view v-if="insufficientNotice" class="rlist__notice is-info">
            <text class="rlist__notice-text">{{ insufficientNotice }}</text>
          </view>

          <!-- 三档分组渲染（RL-1：blocked 态整个业务区由 v-if 排除，见下方模板分支） -->
          <view v-for="group in grouped" :key="group.level" class="rlist__group">
            <template v-if="group.items.length > 0">
              <text class="rlist__group-title">{{ group.title }}（{{ group.items.length }}）</text>
              <view class="rlist__cards">
                <RecipeCard
                  v-for="r in group.items"
                  :key="r.recipe_id"
                  :item="toCardItem(r)"
                  @click="goDetail(toCardItem(r))"
                />
              </view>
            </template>
          </view>

          <!-- 调度取证线索（trace_id / request_id 小字，溯源用） -->
          <view class="rlist__trace">
            <text class="rlist__trace-text">
              trace：{{ recommendStore.traceId || '—' }} · request_id：{{ recommendStore.requestId || '—' }}
            </text>
          </view>
        </template>
      </template>

      <DisclaimerBar scene="home" />
    </view>
  </view>
</template>

<style scoped lang="scss">
.rlist {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
}

/* ── 摘要栏 ── */
.rlist__summary {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-md);
  border-radius: var(--radius-ctrl);
  background: var(--color-info-bg);
}

.rlist__summary-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-xs);
  min-height: var(--hit-min);
}

.rlist__summary-label {
  flex-shrink: 0;
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.rlist__summary-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
}

.rlist__summary-question {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
}

.rlist__summary-link {
  align-self: flex-start;
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
}

.rlist__summary-link-text {
  font-size: var(--font-size-sm);
  color: var(--color-primary);
}

/* ── 通知条 ── */
.rlist__notice {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-md);
  border-radius: var(--radius-ctrl);

  &.is-warning {
    background: var(--color-warning-bg);
  }

  &.is-info {
    background: var(--color-info-bg);
  }
}

.rlist__notice-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  word-break: break-all;

  .is-warning & {
    color: var(--color-warning);
  }

  .is-info & {
    color: var(--color-info);
  }
}

.rlist__notice-detail {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-secondary);
  word-break: break-all;
}

.rlist__loading-text {
  display: block;
  margin-top: var(--space-md);
  text-align: center;
  font-size: var(--font-size-base);
  color: var(--text-tertiary);
}

/* ── 过滤统计行 ── */
.rlist__filtered {
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
  margin-bottom: var(--space-md);
  padding: 0 var(--space-md);
  border-radius: var(--radius-ctrl);
  background: var(--color-info-bg);
}

.rlist__filtered-text {
  font-size: var(--font-size-sm);
  color: var(--color-info);
}

/* ── 三档分组 ── */
.rlist__group {
  margin-top: var(--space-md);
}

.rlist__group-title {
  display: block;
  margin-bottom: var(--space-sm);
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.rlist__cards {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

/* ── 调度取证线索 ── */
.rlist__trace {
  margin-top: var(--space-lg);
}

.rlist__trace-text {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
  word-break: break-all;
}

/* blocked 态业务占位：阻断期间页面主体留白（不渲染任何业务信息，RL-1） */
.rlist__blocked-mask-body {
  min-height: 400rpx;
}
</style>
