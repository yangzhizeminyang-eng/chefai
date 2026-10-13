<!--
  文件级注释：P-18 完成评分页（烹饪闭环收口，W-04 完成面板拆页落点）。
  自 web-stage1 CookGuideView 完成态面板（DEF-05）迁移，语义对齐：
  - DEF-05 评分幂等：finishCookingSession(sessionId, rating, tags)；重复提交后端 409
    「该次烹饪已完成评价」→ 前端提示「已完成过，不可重复评分」并进入已评价态
    （不弹错误堆栈、不重复埋点），历史记录可查（历史页评分可见）；
  - 评价组件：星级 1~5（大热区 chips）+ 标签多选（对齐源码 RATING_TAGS：太咸/太淡/
    火大了/完美/成品卖相差）；不评价也可直接离开（不强制）；
  - 缺料补录（DEF-12 折叠规则对齐）：候选 = 菜谱主料+辅料食材名（详情接口拉取，
    离线/失败兜底空列表并提示）；候选 >5 折叠展示前 5 +「展开更多」；勾选 >8 提示
    「缺料超过 8 项不计入档案」并禁止继续勾选（宁缺毋滥口径）；勾选缺料提交时以
    「缺料:食材名」并入 tags（后端 finish 契约仅 {rating, tags}，>8 不并入即不入档）；
  - 提交成功：trackEvent('cook_complete') + trackEvent('cook_rating') → 清理断点续做
    缓存（cooking.clearSession 删 cook_session_/cook_steps_ + clearRecipeSnapshot 删
    离线快照 + 删会话→菜谱映射）→ 成功面板：「查看营养」
    （ROUTES.NUTRITION_SUMMARY?recipe_id=，preloadRule 已配 pkg-nutrition 预下载）+
    「回到首页」（switchTab）；
  - 放弃路径：本页「放弃本次烹饪」入口 → 二次确认 → PATCH status='finished'（静默，
    后端需要终态标记）→ 清缓存 → trackEvent('cook_abandon') → 返回烹饪前页面
    （对齐源码：源码无独立放弃上报，此处补齐口径）；
  - 409 幂等态也执行缓存清理（会话已完成，断点缓存不再有用），但不重复埋点。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad } from '@dcloudio/uni-app'
import { finishCookingSession, getRecipe, patchCookingSession } from '@/api/endpoints'
import type { ApiError, RecipeDetail } from '@shared/types'
import { useCookingStore } from '@/stores/cooking'
import { clearRecipeSnapshot } from '@/utils/offlineCache'
import { remove as storageRemove } from '@/utils/storage'
import { goRoute, ROUTES } from '@/utils/routes'
import { toastInfo, toastSuccess, toastWarning } from '@/utils/toast'
import { trackEvent, flushOnHide } from '@/utils/track'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import EmptyState from '@/components/EmptyState.vue'
import BaseButton from '@/components-base/BaseButton.vue'

/** 会话→菜谱映射键（与 offlineCache SESSION_MAP_PREFIX 一致；完成/放弃后清理） */
const SESSION_MAP_PREFIX = 'aicook_session_recipe_'

/** DEF-12 缺料上限：超过 8 项不入档（与后端 MAX_MISSING_INGREDIENTS 口径一致） */
const MISSING_ARCHIVE_LIMIT = 8

/** DEF-12 折叠阈值：候选缺料 >5 折叠展示前 5 +「展开更多」 */
const MISSING_COLLAPSE_COUNT = 5

/** 评价标签选项（对齐源码 RATING_TAGS：PRD P-18） */
const RATING_TAGS: readonly string[] = ['太咸', '太淡', '火大了', '完美', '成品卖相差']

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 烹饪 store（会话实体 / 步骤快照；clearSession 清理入口） */
const cooking = useCookingStore()

/** 路由注入的会话 ID */
const sessionId = ref('')

/** 页面阶段：loading 恢复中 / ready 可评分 / done 已完成 / missing 会话不存在 */
type FinishPhase = 'loading' | 'ready' | 'done' | 'missing'
/** 页面阶段 */
const phase = ref<FinishPhase>('loading')

/** 关联菜谱 ID（清离线快照 / 查看营养跳转用） */
const recipeId = ref<number | null>(null)

/** 本次份数（查看营养跳转附注） */
const servings = ref(1)

/** 导航标题（成功面板菜名展示） */
const navTitle = ref('')

/** 恢复失败错误（ErrorState 重试用；missing 态与错误态区分） */
const restoreError = ref<ApiError | null>(null)

/* ── 评价状态（DEF-05） ── */

/** 星级评分（1~5，0 = 未选择） */
const rating = ref(0)

/** 已勾选评价标签（可多选可空） */
const feedbackTags = ref<string[]>([])

/** 提交进行中（防连点） */
const submitting = ref(false)

/** 已提交态（成功或 409 后置位：组件禁用、不阻断查看营养/回首页） */
const submitted = ref(false)

/* ── 缺料补录（DEF-12） ── */

/** 缺料候选（菜谱主料 + 辅料食材名；拉取失败为空列表） */
const missingCandidates = ref<string[]>([])

/** 候选拉取失败标记（离线提示） */
const missingLoadFailed = ref(false)

/** 已勾选缺料（多选） */
const pickedMissing = ref<string[]>([])

/** 缺料候选展开态（>5 折叠 →「展开更多」） */
const missingExpanded = ref(false)

/** 缺料达上限提示展示（勾满 8 项后常驻警示文案：DEF-12 宁缺毋滥口径） */
const missingOverLimit = computed(() => pickedMissing.value.length >= MISSING_ARCHIVE_LIMIT)

/** 实际并入 tags 的缺料（>8 不入档：截断到 8 项；提示已超限） */
const archiveMissing = computed(() => pickedMissing.value.slice(0, MISSING_ARCHIVE_LIMIT))

/** 缺料候选展示列表（>5 折叠前 5 项，展开后全量） */
const visibleCandidates = computed(() => {
  if (missingExpanded.value || missingCandidates.value.length <= MISSING_COLLAPSE_COUNT) {
    return missingCandidates.value
  }
  return missingCandidates.value.slice(0, MISSING_COLLAPSE_COUNT)
})

/** 是否需要折叠入口（候选 >5 才渲染「展开更多/收起」） */
const hasMoreCandidates = computed(() => missingCandidates.value.length > MISSING_COLLAPSE_COUNT)

/** 成功面板副标题（菜名 + 份数；菜名由恢复时的导航标题兜底） */
const doneTitle = computed(() => {
  const name = navTitle.value || '本次菜谱'
  return `本次完成：${name}（${servings.value} 份）`
})

/**
 * 恢复会话（onLoad / 重试共用）：restoreById（内存 → 本地双缓存）→ 失败进 missing 态。
 * 并行拉取缺料候选（菜谱主料+辅料；离线/失败兜底空列表不阻塞评分主流程）。
 * @returns 无
 * @throws 不抛出（恢复失败进 missing/错误态，页面提供重试与回首页）
 */
async function bootstrap(): Promise<void> {
  phase.value = 'loading'
  restoreError.value = null
  if (cooking.restoreById(sessionId.value) && cooking.session) {
    recipeId.value = cooking.session.recipe_id
    servings.value = cooking.session.servings ?? 1
    phase.value = 'ready'
    void loadMissingCandidates()
    return
  }
  // restoreById 失败：endpoints 无「查询会话」GET 接口，不做远端兜底（对齐源码策略）
  phase.value = 'missing'
}

/**
 * 拉取缺料候选（菜谱主料 + 辅料食材名；调味料一般常备不列入）。
 * @returns 无
 * @throws 不抛出（失败置 missingLoadFailed，缺料区降级提示需联网）
 */
async function loadMissingCandidates(): Promise<void> {
  if (recipeId.value == null) return
  try {
    const detail: RecipeDetail = await getRecipe(recipeId.value)
    navTitle.value = detail.title
    missingCandidates.value = [...detail.main_ingredients, ...detail.side_ingredients]
      .map((item) => item.name ?? '')
      .filter((n) => n.length > 0)
    missingLoadFailed.value = false
  } catch {
    // 离线 / 失败：缺料候选降级为空（评分主流程不受影响）
    missingLoadFailed.value = true
  }
}

/* ── 评分交互 ── */

/**
 * 选择星级（1~5 大热区 chips；已提交态禁止再改）。
 * @param value 星级
 * @returns 无
 */
function pickRating(value: number): void {
  if (submitted.value) return
  rating.value = value
}

/**
 * 切换评价标签勾选（多选；已提交态禁止）。
 * @param tag 标签名
 * @returns 无
 */
function toggleTag(tag: string): void {
  if (submitted.value) return
  const idx = feedbackTags.value.indexOf(tag)
  if (idx >= 0) feedbackTags.value.splice(idx, 1)
  else feedbackTags.value = [...feedbackTags.value, tag]
}

/**
 * 切换缺料勾选（DEF-12：>8 提示不入档并禁止继续勾选；已提交态禁止）。
 * @param name 食材名
 * @returns 无
 */
function toggleMissing(name: string): void {
  if (submitted.value) return
  const idx = pickedMissing.value.indexOf(name)
  if (idx >= 0) {
    pickedMissing.value = pickedMissing.value.filter((n) => n !== name)
    return
  }
  if (pickedMissing.value.length >= MISSING_ARCHIVE_LIMIT) {
    // DEF-12：缺料 >8 不入档，禁止继续勾选并明示口径
    toastWarning(`缺料超过 ${MISSING_ARCHIVE_LIMIT} 项将不计入档案，请按实际勾选`)
    return
  }
  pickedMissing.value = [...pickedMissing.value, name]
}

/**
 * 展开更多 / 收起（DEF-12 折叠交互）。
 * @returns 无
 */
function toggleExpand(): void {
  missingExpanded.value = !missingExpanded.value
}

/**
 * 提交评分（DEF-05 幂等）：
 * - 成功：cook_complete + cook_rating 埋点 → 清理断点续做缓存 → done 成功面板；
 * - 409：幂等提示「已完成过，不可重复评分」（DEF-05），进入已评价态并同样清理缓存
 *   （会话已完成、断点缓存无用），不重复埋点；
 * - 其余错误：toast 提示停留本页可重试。
 * @returns 无
 * @throws 不抛出（错误收敛为提示，不阻断用户离开）
 */
async function onSubmit(): Promise<void> {
  if (!sessionId.value || submitting.value || submitted.value) return
  if (!rating.value) {
    toastWarning('请先选择星级评分')
    return
  }
  submitting.value = true
  try {
    // 缺料以「缺料:食材名」并入 tags（后端 finish 契约 {rating, tags}；>8 已在勾选侧拦截）
    const tags = [...feedbackTags.value, ...archiveMissing.value.map((n) => `缺料:${n}`)]
    await finishCookingSession(sessionId.value, rating.value, tags)
    submitted.value = true
    toastSuccess('已提交，谢谢反馈')
    trackEvent('cook_complete', { session_id: sessionId.value, recipe_id: recipeId.value })
    trackEvent('cook_rating', { session_id: sessionId.value, rating: rating.value })
    await cleanupSessionData()
    phase.value = 'done'
  } catch (e) {
    const err = e as ApiError
    if (err.code === 409) {
      // DEF-05 幂等语义：会话已完成评价（或重复 finish）→ 友好提示不报错弹窗
      submitted.value = true
      toastInfo('已完成过，不可重复评分')
      await cleanupSessionData()
      phase.value = 'done'
    } else {
      toastWarning(err.message || '提交失败，请重试')
    }
  } finally {
    submitting.value = false
  }
}

/**
 * 清理断点续做缓存（完成 / 409 / 放弃共用）：
 * - cooking.clearSession：删 cook_session_{id} / cook_steps_{id} 本地双缓存并重置 store；
 * - clearRecipeSnapshot：删离线快照 offline_recipe_{id} 并同步 LRU 索引；
 * - 删会话→菜谱映射（aicook_session_recipe_{sessionId}，storage 直删完整键）。
 * @returns 无
 * @throws 不抛出（各清理函数内部静默降级）
 */
async function cleanupSessionData(): Promise<void> {
  const rid = recipeId.value
  cooking.clearSession()
  if (rid != null) await clearRecipeSnapshot(rid)
  if (sessionId.value) storageRemove(`${SESSION_MAP_PREFIX}${sessionId.value}`)
}

/**
 * 成功面板「查看营养」：跳营养总览（query 携带 recipe_id；
 * pages/recommend/detail 的 preloadRule 已配置 pkg-nutrition 预下载）。
 * @returns 无
 */
function goNutrition(): void {
  if (recipeId.value == null) return
  goRoute(`${ROUTES.NUTRITION_SUMMARY}?recipe_id=${recipeId.value}`)
}

/**
 * 成功面板「回到首页」：switchTab 回首页（tabBar 页经 goRoute 自动选择跳转方式）。
 * @returns 无
 */
function goHome(): void {
  goRoute(ROUTES.HOME)
}

/**
 * 「放弃本次烹饪」：二次确认 → PATCH status='finished'（终态标记，静默失败）→
 * 清缓存 → trackEvent('cook_abandon') → 返回烹饪前页面（跳过本页与 guide 两层）。
 * @returns 无
 * @throws 不抛出（PATCH 失败静默，放弃以本地清理为准）
 */
function onAbandon(): void {
  if (submitting.value) return
  uni.showModal({
    title: '放弃本次烹饪',
    content: '放弃后本次进度与评分将不会保留，确认放弃？',
    confirmText: '放弃',
    cancelText: '继续做菜',
    success: (res) => {
      if (!res.confirm) return
      void (async () => {
        try {
          // 后端需要终态标记：PATCH status finished（静默失败不阻塞放弃流程）
          await patchCookingSession(sessionId.value, { status: 'finished' }).catch(() => {})
        } catch {
          // 静默
        }
        trackEvent('cook_abandon', { session_id: sessionId.value, recipe_id: recipeId.value })
        await cleanupSessionData()
        // 返回烹饪前页面：delta 2 跳过 guide；栈深不足回退 delta 1
        uni.navigateBack({
          delta: 2,
          fail: () => {
            uni.navigateBack({ delta: 1, fail: () => {} })
          },
        })
      })()
    },
    fail: () => {},
  })
}

/**
 * missing 态「回首页」：会话不存在（已清理/非法进入）时的兜底出口。
 * @returns 无
 */
function goHomeFallback(): void {
  goRoute(ROUTES.HOME)
}

/**
 * onLoad：解析 session_id 并恢复会话。
 * @param options 页面参数（session_id）
 * @returns 无
 * @throws 不抛出
 */
onLoad((options) => {
  sessionId.value = options?.session_id ? decodeURIComponent(options.session_id) : ''
  void bootstrap()
})

// 页面隐匿时尽力上报缓冲埋点（统一页面约定）
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <!-- 恢复中 -->
    <view v-if="phase === 'loading'" class="finish finish--center">
      <text class="finish__loading-text">加载中…</text>
    </view>

    <!-- 会话不存在兜底：已清理 / 非法进入 -->
    <view v-else-if="phase === 'missing'" class="finish finish--center">
      <EmptyState
        icon="🍳"
        title="未找到进行中的烹饪会话"
        desc="会话可能已完成或已放弃，请从菜谱页重新发起烹饪"
        action-text="回到首页"
        @action="goHomeFallback"
      />
    </view>

    <!-- 成功面板：完成 + 已评价态（409 幂等同样进入） -->
    <view v-else-if="phase === 'done'" class="finish">
      <view class="finish__done">
        <text class="finish__done-icon">🎉</text>
        <text class="finish__done-title">恭喜，这道菜完成了！</text>
        <text class="finish__done-sub">{{ doneTitle }}</text>
        <text v-if="submitted" class="finish__done-rated">评价已提交，感谢反馈</text>
      </view>
      <view class="finish__done-actions">
        <BaseButton block size="lg" @click="goNutrition">查看营养</BaseButton>
        <BaseButton block size="lg" type="default" @click="goHome">回到首页</BaseButton>
      </view>
    </view>

    <!-- 主流程：评分 + 标签 + 缺料补录 + 提交/放弃 -->
    <view v-else class="finish">
      <!-- 评分区（DEF-05）：星级大热区 -->
      <view class="finish__card">
        <text class="finish__question">这道菜做得怎么样？</text>
        <view class="finish__stars">
          <view
            v-for="star in 5"
            :key="star"
            class="finish__star"
            :class="{ 'is-active': star <= rating, 'is-disabled': submitted }"
            @click="pickRating(star)"
          >
            {{ star <= rating ? '★' : '☆' }}
          </view>
        </view>
      </view>

      <!-- 评价标签多选（对齐源码 RATING_TAGS） -->
      <view class="finish__card">
        <text class="finish__label">选择标签（可多选）</text>
        <view class="finish__tags">
          <view
            v-for="tag in RATING_TAGS"
            :key="tag"
            class="finish__tag"
            :class="{ 'is-active': feedbackTags.includes(tag), 'is-disabled': submitted }"
            @click="toggleTag(tag)"
          >
            {{ tag }}
          </view>
        </view>
      </view>

      <!-- 缺料补录区（DEF-12：>8 不入档 / >5 折叠） -->
      <view class="finish__card">
        <text class="finish__label">本次缺了哪些食材？（可选）</text>
        <text v-if="missingLoadFailed" class="finish__hint">食材清单需联网加载，暂不可勾选</text>
        <template v-else>
          <view class="finish__tags">
            <view
              v-for="name in visibleCandidates"
              :key="name"
              class="finish__tag"
              :class="{
                'is-active': pickedMissing.includes(name),
                'is-disabled': submitted,
              }"
              @click="toggleMissing(name)"
            >
              {{ name }}
            </view>
          </view>
          <text v-if="hasMoreCandidates" class="finish__expand" @click="toggleExpand">
            {{ missingExpanded ? '收起' : `展开更多（共 ${missingCandidates.length} 项）` }}
          </text>
          <text v-if="missingOverLimit" class="finish__hint finish__hint--warn">
            缺料已勾满 {{ MISSING_ARCHIVE_LIMIT }} 项，达档案上限，不再计入更多
          </text>
        </template>
      </view>

      <!-- 操作区：提交 + 放弃 -->
      <view class="finish__actions">
        <BaseButton
          block
          size="lg"
          :loading="submitting"
          :disabled="submitted || !rating"
          @click="onSubmit"
        >
          {{ submitted ? '已提交，谢谢反馈' : '提交评价' }}
        </BaseButton>
        <BaseButton block size="lg" type="ghost" :disabled="submitting || submitted" @click="onAbandon">
          放弃本次烹饪
        </BaseButton>
      </view>
    </view>
  </view>
</template>

<style scoped lang="scss">
.finish {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-md);
  padding-bottom: calc(var(--space-xl) + env(safe-area-inset-bottom));

  &--center {
    align-items: center;
    justify-content: center;
    min-height: 50vh;
  }
}

.finish__loading-text {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* 卡片容器 */
.finish__card {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  border: 1rpx solid var(--border-color);
}

.finish__question {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--text-primary);
}

.finish__label {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.finish__hint {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);

  &--warn {
    color: var(--color-warning);
  }
}

/* 星级（大热区 ≥120rpx） */
.finish__stars {
  display: flex;
  gap: var(--space-md);
}

.finish__star {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 120rpx;
  height: 120rpx;
  border-radius: var(--radius-ctrl);
  font-size: 72rpx;
  color: var(--text-tertiary);

  &.is-active {
    color: var(--color-warning);
  }

  &.is-disabled {
    opacity: 0.6;
    pointer-events: none;
  }
}

/* 标签 chips */
.finish__tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.finish__tag {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--hit-min);
  padding: 0 var(--space-md);
  border-radius: 999rpx;
  border: 1rpx solid var(--border-color);
  background: var(--bg-page);
  font-size: var(--font-size-sm);
  color: var(--text-primary);

  &.is-active {
    background: var(--color-primary-weak);
    border-color: var(--color-primary);
    color: var(--color-primary);
  }

  &.is-disabled {
    opacity: 0.6;
    pointer-events: none;
  }
}

/* 折叠入口 */
.finish__expand {
  font-size: var(--font-size-sm);
  color: var(--color-info);
}

/* 操作区 */
.finish__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-top: var(--space-sm);
}

/* 成功面板 */
.finish__done {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-xl) var(--space-md);
}

.finish__done-icon {
  font-size: 96rpx;
}

.finish__done-title {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.finish__done-sub {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.finish__done-rated {
  font-size: var(--font-size-sm);
  color: var(--color-primary);
}

.finish__done-actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}
</style>
