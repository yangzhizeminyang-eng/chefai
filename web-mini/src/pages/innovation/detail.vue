<!--
  文件级注释：P-38 创新菜详情页（多步流程终点：entry → confirm → result → 本页；mine 列表点入同页）。
  - onLoad options.recipe_id → innovation.fetchById(id)（GET /v1/innovation/recipes/{id}，
    store.current 同步更新）；非法 / 缺参 → 错误态兜底；
  - 完整呈现：封面（RecipeCover lg 占位色板）+ 菜名 + AI 创新徽标 + 强制声明
    （recipe.disclaimer 逐字展示）+ 用量清单 + 步骤（含小贴士）+ 营养估算（缺失灰字）
    + 「为什么推荐这道菜」折叠区（展开展示搭配规则 / 食性标注，首次展开
    trackEvent('innovation_reason_view')）+ 模板降级（generated_by=template）→ DegradedBar；
  - 操作：采纳（adopt → innovation_adopt + toast「已加入我的创新菜」，已采纳禁用态）/
    再做一次（BaseDialog 确认 → reuse → innovation_reuse → 跳 result 页复用回看）/
    去烹饪（innovation_cook；源码无创新菜 cook 独立链路，常规烹饪会话依赖常规
    recipe_id，此处如实引导按步骤烹饪）/ 反馈（BaseDialog 星级 + 评论 →
    sendFeedback → innovation_feedback）；
  - 免责声明条 DisclaimerBar scene="detail"（G-02）。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad } from '@dcloudio/uni-app'
import type { ApiError } from '@shared/types'
import { useInnovationStore } from '@/stores/innovation'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide, trackEvent } from '@/utils/track'
import { toastError, toastInfo, toastSuccess, toastWarning } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import ErrorState from '@/components/ErrorState.vue'
import DegradedBar from '@/components/DegradedBar.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import RecipeCover from '@/components/RecipeCover.vue'
import BaseDialog from '@/components-base/BaseDialog.vue'
import BaseInput from '@/components-base/BaseInput.vue'
import BaseButton from '@/components-base/BaseButton.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 创新 store（fetchById / adopt / reuse / sendFeedback / current / myRecipes） */
const innovation = useInnovationStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 页面阶段：loading 详情加载中 / ready 呈现 / error 加载失败 */
type Phase = 'loading' | 'ready' | 'error'

/** 当前页面阶段 */
const phase = ref<Phase>('loading')

/** 当前菜谱 ID（操作动作复用；0 = 未载入） */
const recipeId = ref(0)

/** 详情加载错误（error 态呈现） */
const loadError = ref<ApiError | null>(null)

/** 当前创新菜谱（fetchById 成功后经 store.current 取得） */
const recipe = computed(() => innovation.current)

/** 是否模板降级生成（P1 DEF-01：LLM 超时/失败走规则模板） */
const isDegraded = computed(() => recipe.value?.basis.generated_by === 'template')

/** 是否已采纳当前菜（「我的创新菜」已含该 id → 按钮禁用态） */
const isAdopted = computed(() =>
  recipe.value ? innovation.myRecipes.some((r) => r.id === recipe.value?.id) : false,
)

/** 采纳动作进行中（防重复点击） */
const adopting = ref(false)

/** 「为什么推荐这道菜」折叠区展开态 */
const reasonExpanded = ref(false)

/** reason 埋点是否已上报（每菜谱首次展开上报一次） */
const reasonTracked = ref(false)

/** 搭配规则条目数（折叠区摘要文案用） */
const pairingCount = computed(() => recipe.value?.basis.pairings.length ?? 0)

/** 食性标注条目数（折叠区摘要文案用） */
const propertyCount = computed(() => recipe.value?.basis.properties.length ?? 0)

/* ── 再做一次（复用）确认弹层 ── */

/** 复用确认弹层可见性 */
const reuseDialogVisible = ref(false)

/** 复用动作进行中 */
const reusing = ref(false)

/* ── 反馈弹层 ── */

/** 反馈弹层可见性 */
const feedbackVisible = ref(false)

/** 反馈评分（0 = 未选，1~5） */
const feedbackRating = ref(0)

/** 反馈评论（可选） */
const feedbackComment = ref('')

/** 反馈提交中 */
const feedbackSubmitting = ref(false)

/** 星级选项（1~5，渲染源） */
const STAR_LEVELS: readonly number[] = [1, 2, 3, 4, 5]

/**
 * 拉取详情（onLoad / 错误重试共用）。
 * @param id 创新菜谱 ID
 * @returns 无
 * @throws 不向外抛出（fetchById 失败写 loadError 呈现 ErrorState）
 */
async function loadRecipe(id: number): Promise<void> {
  phase.value = 'loading'
  loadError.value = null
  try {
    await innovation.fetchById(id)
    phase.value = 'ready'
  } catch (e) {
    loadError.value = e as ApiError
    phase.value = 'error'
  }
}

/**
 * 展开折叠区：首次展开上报 innovation_reason_view（每菜谱一次）。
 * @returns 无
 */
function toggleReason(): void {
  reasonExpanded.value = !reasonExpanded.value
  if (reasonExpanded.value && !reasonTracked.value) {
    trackEvent('innovation_reason_view')
    reasonTracked.value = true
  }
}

/**
 * 采纳当前菜：adopt 成功 → 埋点 + toast；失败 toast（来源：adopt 抛出或 current 缺失）。
 * @returns 无
 * @throws 不向外抛出（接口失败就地提示）
 */
async function onAdopt(): Promise<void> {
  if (!recipe.value || adopting.value || isAdopted.value) return
  adopting.value = true
  try {
    const ok = await innovation.adopt(recipe.value)
    if (ok) {
      trackEvent('innovation_adopt')
      toastSuccess('已加入我的创新菜')
    }
  } catch (e) {
    toastError((e as ApiError).message || '采纳失败，请重试')
  } finally {
    adopting.value = false
  }
}

/**
 * 请求复用：打开确认弹层（对齐源码 reuse 前弹确认语义）。
 * @returns 无
 */
function askReuse(): void {
  reuseDialogVisible.value = true
}

/**
 * 确认复用：reuse 成功 → 埋点 + toast + 跳 result 页复用回看（无 job_id 分支直接呈现
 * store.current）；失败写 error 提示并留在本页。
 * @returns 无
 * @throws 不向外抛出（reuse 失败写 store.error，就地提示）
 */
async function confirmReuse(): Promise<void> {
  if (reusing.value) return
  reusing.value = true
  const ok = await innovation.reuse(recipeId.value)
  reusing.value = false
  if (ok) {
    reuseDialogVisible.value = false
    trackEvent('innovation_reuse')
    toastSuccess('已载入这道创新菜，可查看或直接采纳')
    goRoute(ROUTES.INNOVATION_RESULT)
  } else {
    reuseDialogVisible.value = false
    toastError(innovation.error?.message || '复用失败，请重试')
  }
}

/**
 * 取消复用：关闭弹层。
 * @returns 无
 */
function cancelReuse(): void {
  reuseDialogVisible.value = false
}

/**
 * 去烹饪：埋点 innovation_cook；源码创新菜无独立 cook 链路（常规烹饪会话依赖常规
 * recipe_id，创新菜不在菜谱库），如实引导按详情步骤直接烹饪。
 * @returns 无
 */
function onCook(): void {
  trackEvent('innovation_cook')
  toastInfo('创新菜暂不支持自动烹饪指导，可参照上方步骤直接烹饪')
}

/**
 * 打开反馈弹层：重置星级与评论。
 * @returns 无
 */
function openFeedback(): void {
  feedbackRating.value = 0
  feedbackComment.value = ''
  feedbackVisible.value = true
}

/**
 * 选择星级（1~5）。
 * @param level 星级
 * @returns 无
 */
function pickStar(level: number): void {
  feedbackRating.value = level
}

/**
 * 提交反馈：未打分拦截提示；成功 → 埋点 + toast + 关闭弹层；失败就地提示。
 * @returns 无
 * @throws 不向外抛出（sendFeedback 失败就地提示）
 */
async function submitFeedback(): Promise<void> {
  if (!recipe.value || feedbackSubmitting.value) return
  if (feedbackRating.value === 0) {
    toastWarning('请先打分（1~5 星）')
    return
  }
  feedbackSubmitting.value = true
  try {
    await innovation.sendFeedback(recipe.value.id, feedbackRating.value, feedbackComment.value.trim() || undefined)
    trackEvent('innovation_feedback')
    toastSuccess('感谢你的反馈')
    feedbackVisible.value = false
  } catch (e) {
    toastError((e as ApiError).message || '提交失败，请重试')
  } finally {
    feedbackSubmitting.value = false
  }
}

/**
 * 取消反馈：关闭弹层。
 * @returns 无
 */
function cancelFeedback(): void {
  feedbackVisible.value = false
}

/**
 * 详情重试（ErrorState retry）：按当前 recipeId 重新拉取。
 * @returns 无
 */
function retryLoad(): void {
  if (recipeId.value > 0) void loadRecipe(recipeId.value)
}

/**
 * 营养单项展示文案（null → 「未纳入统计」灰字，对齐源码 nutritionText）。
 * @param label 营养名
 * @param value 数值（可空）
 * @param unit 单位
 * @returns 文案
 */
function nutritionText(label: string, value: number | null, unit: string): string {
  return value == null ? `${label}：未纳入统计` : `${label}：${value}${unit}`
}

/**
 * 步骤耗时格式化（对齐源码 stepDuration；0/缺省返回空串不渲染）。
 * @param sec 耗时秒数
 * @returns 文案（如「45 秒」「约 3 分钟」）
 */
function stepDuration(sec: number): string {
  if (!sec || sec <= 0) return ''
  return sec < 60 ? `${sec} 秒` : `约 ${Math.round(sec / 60)} 分钟`
}

// onLoad：解析 recipe_id 并拉取详情（非法参数走错误态兜底）
onLoad((options) => {
  const raw = options?.recipe_id ? decodeURIComponent(options.recipe_id) : ''
  const id = Number.parseInt(raw, 10)
  if (!Number.isInteger(id) || id <= 0) {
    phase.value = 'error'
    loadError.value = { code: 'BAD_REQUEST', message: '缺少创新菜标识，请从列表或结果页进入' } as ApiError
    return
  }
  recipeId.value = id
  void loadRecipe(id)
})

// onHide：尽力上报缓冲埋点 + 暂停创新轮询（本页未轮询时为无操作，统一约定）
onHide(() => {
  flushOnHide()
  innovation.pausePolling()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <!-- 离线提示条 -->
    <OfflineBar v-if="!network.isConnected" />

    <view class="detail">
      <!-- 加载态 -->
      <SkeletonPage v-if="phase === 'loading'" type="detail" :rows="5" />

      <!-- 错误态 -->
      <ErrorState
        v-else-if="phase === 'error'"
        kind="server"
        :detail="loadError?.message"
        @retry="retryLoad"
      />

      <template v-else-if="recipe">
        <!-- 模板降级提示条（P1 DEF-01） -->
        <DegradedBar v-if="isDegraded" />

        <!-- 头部：封面 + 菜名 + 徽标 -->
        <view class="detail__card">
          <RecipeCover :name="recipe.name" :palette-seed="String(recipe.id)" size="lg" />
          <view class="detail__head">
            <text class="detail__name">{{ recipe.name }}</text>
            <view class="detail__ai-badge">AI 创新</view>
          </view>
        </view>

        <!-- 强制声明（后端生成，逐字展示，警示浅底） -->
        <view class="detail__disclaimer-strong">
          <text class="detail__disclaimer-strong-text">{{ recipe.disclaimer }}</text>
        </view>

        <!-- 用量清单 -->
        <view class="detail__card">
          <text class="detail__section-title">用量清单</text>
          <view
            v-for="(ing, i) in recipe.ingredients"
            :key="`ing-${i}`"
            class="detail__ing-row"
          >
            <text class="detail__ing-name">{{ ing.name }}</text>
            <text class="detail__ing-amount">{{ ing.amount }}{{ ing.unit }}</text>
          </view>
        </view>

        <!-- 步骤（完整，含小贴士） -->
        <view class="detail__card">
          <text class="detail__section-title">步骤</text>
          <view v-for="s in recipe.steps" :key="`step-${s.no}`" class="detail__step">
            <text class="detail__step-desc">{{ s.no }}. {{ s.description }}</text>
            <text v-if="stepDuration(s.duration_sec)" class="detail__step-duration">
              ⏱ {{ stepDuration(s.duration_sec) }}
            </text>
            <text v-if="s.tips" class="detail__step-tips">要点：{{ s.tips }}</text>
          </view>
        </view>

        <!-- 营养估算（缺失灰字「未纳入统计」） -->
        <view class="detail__card">
          <text class="detail__section-title">营养估算</text>
          <view class="detail__nutri-grid">
            <text
              class="detail__nutri-item"
              :class="{ 'is-muted': recipe.nutrition.kcal == null }"
            >
              {{ nutritionText('热量', recipe.nutrition.kcal, ' kcal') }}
            </text>
            <text
              class="detail__nutri-item"
              :class="{ 'is-muted': recipe.nutrition.protein == null }"
            >
              {{ nutritionText('蛋白质', recipe.nutrition.protein, 'g') }}
            </text>
            <text
              class="detail__nutri-item"
              :class="{ 'is-muted': recipe.nutrition.fat == null }"
            >
              {{ nutritionText('脂肪', recipe.nutrition.fat, 'g') }}
            </text>
            <text
              class="detail__nutri-item"
              :class="{ 'is-muted': recipe.nutrition.carb == null }"
            >
              {{ nutritionText('碳水', recipe.nutrition.carb, 'g') }}
            </text>
          </view>
          <text v-if="recipe.nutrition.excluded.length > 0" class="detail__excluded">
            未纳入统计：{{ recipe.nutrition.excluded.join('、') }}
          </text>
        </view>

        <!-- 来源说明区：「为什么推荐这道菜」折叠（展开首次埋 innovation_reason_view） -->
        <view class="detail__card">
          <view class="detail__reason-head" @click="toggleReason">
            <text class="detail__section-title detail__section-title--tight">为什么推荐这道菜</text>
            <text class="detail__reason-arrow">{{ reasonExpanded ? '收起 ▲' : '展开 ▼' }}</text>
          </view>
          <text class="detail__reason-summary">
            搭配规则 {{ pairingCount }} 条 · 食性标注 {{ propertyCount }} 条
          </text>
          <template v-if="reasonExpanded">
            <view
              v-for="(p, i) in recipe.basis.pairings"
              :key="`pair-${i}`"
              class="detail__basis-row"
            >
              <view class="detail__basis-tag">{{ p.relation }}</view>
              <text class="detail__basis-text">{{ p.a }} × {{ p.b }}：{{ p.rationale }}</text>
            </view>
            <view
              v-for="(pr, i) in recipe.basis.properties"
              :key="`prop-${i}`"
              class="detail__basis-row"
            >
              <view class="detail__basis-tag detail__basis-tag--warning">{{ pr.name }}</view>
              <text class="detail__basis-text">{{ pr.note }}</text>
            </view>
            <text
              v-if="pairingCount === 0 && propertyCount === 0"
              class="detail__profile-empty"
            >
              本道菜未附带创新依据说明
            </text>
          </template>
        </view>

        <!-- 操作按钮区 -->
        <view class="detail__actions">
          <BaseButton
            type="primary"
            block
            :disabled="isAdopted"
            :loading="adopting"
            @click="onAdopt"
          >
            {{ isAdopted ? '已采纳' : '采纳这道菜' }}
          </BaseButton>
          <BaseButton type="default" block :disabled="reusing" @click="askReuse">
            再做一次
          </BaseButton>
          <BaseButton type="default" block @click="onCook">去烹饪</BaseButton>
          <BaseButton type="ghost" block @click="openFeedback">为它评分</BaseButton>
        </view>

        <!-- 免责声明条（G-02：scene=detail 取 DISCLAIMER_DETAIL 常量） -->
        <DisclaimerBar scene="detail" />
      </template>
    </view>

    <!-- 再做一次确认弹层（对齐源码 reuse 前确认语义） -->
    <BaseDialog
      :visible="reuseDialogVisible"
      title="再做一次"
      position="center"
      @close="cancelReuse"
    >
      <view class="detail-dialog">
        <text class="detail-dialog__text">
          将基于「{{ recipe?.name }}」重新开做，生成结果置为当前创新菜，可继续采纳或评分。
        </text>
        <view class="detail-dialog__actions">
          <BaseButton type="default" block @click="cancelReuse">取消</BaseButton>
          <BaseButton type="primary" block :loading="reusing" @click="confirmReuse">确定</BaseButton>
        </view>
      </view>
    </BaseDialog>

    <!-- 评分反馈弹层（星级 + 评论，对齐源码 el-rate + textarea 语义） -->
    <BaseDialog
      :visible="feedbackVisible"
      title="为创新菜评分"
      position="center"
      @close="cancelFeedback"
    >
      <view class="detail-dialog">
        <text class="detail-dialog__text">{{ recipe?.name }}</text>
        <view class="detail-dialog__stars">
          <view
            v-for="level in STAR_LEVELS"
            :key="level"
            class="detail-dialog__star"
            :class="{ 'is-active': feedbackRating >= level }"
            @click="pickStar(level)"
          >
            ★
          </view>
        </view>
        <BaseInput
          v-model="feedbackComment"
          type="textarea"
          :maxlength="200"
          placeholder="说说哪里好（或不好），可选"
        />
        <view class="detail-dialog__actions">
          <BaseButton type="default" block @click="cancelFeedback">取消</BaseButton>
          <BaseButton type="primary" block :loading="feedbackSubmitting" @click="submitFeedback">
            提交
          </BaseButton>
        </view>
      </view>
    </BaseDialog>
  </view>
</template>

<style scoped lang="scss">
.detail {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
  padding-bottom: calc(var(--space-lg) + env(safe-area-inset-bottom));
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.detail__card {
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.detail__head {
  margin-top: var(--space-sm);
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.detail__name {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--text-primary);
}

/* AI 创新徽标：warning 语义 */
.detail__ai-badge {
  flex-shrink: 0;
  box-sizing: border-box;
  padding: 4rpx var(--space-sm);
  border-radius: var(--radius-ctrl);
  background: var(--color-warning-bg);
  color: var(--color-warning);
  font-size: var(--font-size-sm);
}

/* 强制声明：警示浅底条 */
.detail__disclaimer-strong {
  box-sizing: border-box;
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-ctrl);
  background: var(--color-warning-bg);
}

.detail__disclaimer-strong-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-warning);
}

.detail__section-title {
  display: block;
  margin-bottom: var(--space-sm);
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);

  /* 折叠区标题与摘要行紧凑排版 */
  &--tight {
    margin-bottom: 0;
  }
}

/* 用量行：名称 + 量化两端对齐 */
.detail__ing-row {
  display: flex;
  justify-content: space-between;
  gap: var(--space-sm);
  padding: var(--space-xs) 0;
  border-bottom: 1rpx dashed var(--divider);
  font-size: var(--font-size-sm);
}

.detail__ing-name {
  color: var(--text-primary);
}

.detail__ing-amount {
  color: var(--text-tertiary);
}

/* 步骤条目：描述 + 耗时 + 小贴士 */
.detail__step {
  margin-bottom: var(--space-sm);
  display: flex;
  flex-direction: column;
  gap: 4rpx;
}

.detail__step-desc {
  font-size: var(--font-size-sm);
  line-height: 1.7;
  color: var(--text-primary);
}

.detail__step-duration {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.detail__step-tips {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-warning);
}

/* 营养两列网格 */
.detail__nutri-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs) var(--space-lg);
}

.detail__nutri-item {
  font-size: var(--font-size-sm);
  line-height: 1.7;
  color: var(--text-primary);

  /* 缺失项灰字（未纳入统计语义） */
  &.is-muted {
    color: var(--text-tertiary);
  }
}

.detail__excluded {
  display: block;
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-tertiary);
}

/* 折叠区头部：标题 + 展开箭头，热区 ≥88rpx */
.detail__reason-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
  min-height: var(--hit-min);
}

.detail__reason-arrow {
  flex-shrink: 0;
  font-size: var(--font-size-sm);
  color: var(--color-primary);
}

.detail__reason-summary {
  display: block;
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* 创新依据条目：语义标签 + 说明 */
.detail__basis-row {
  margin-top: var(--space-sm);
  display: flex;
  align-items: flex-start;
  gap: var(--space-xs);
}

.detail__basis-tag {
  flex-shrink: 0;
  box-sizing: border-box;
  padding: 4rpx var(--space-sm);
  border-radius: var(--radius-ctrl);
  background: var(--color-info-bg);
  color: var(--color-info);
  font-size: var(--font-size-sm);

  /* 食性标注：warning 语义区分 */
  &--warning {
    background: var(--color-warning-bg);
    color: var(--color-warning);
  }
}

.detail__basis-text {
  font-size: var(--font-size-sm);
  line-height: 1.7;
  color: var(--text-primary);
  word-break: break-all;
}

.detail__profile-empty {
  display: block;
  margin-top: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* 操作按钮区：纵向整行按钮栈 */
.detail__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

/* ── 弹层内容 ── */
.detail-dialog {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-sm) 0 var(--space-md);
}

.detail-dialog__text {
  font-size: var(--font-size-base);
  line-height: 1.6;
  color: var(--text-primary);
}

.detail-dialog__stars {
  display: flex;
  gap: var(--space-sm);
}

/* 星级：未选中灰、选中主色，热区 ≥88rpx */
.detail-dialog__star {
  box-sizing: border-box;
  width: var(--hit-min);
  height: var(--hit-min);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 44rpx;
  color: var(--text-tertiary);

  &.is-active {
    color: var(--color-primary);
  }
}

.detail-dialog__actions {
  display: flex;
  gap: var(--space-sm);
}
</style>
