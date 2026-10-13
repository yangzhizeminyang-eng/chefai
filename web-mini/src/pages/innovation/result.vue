<!--
  文件级注释：P-37 创新生成结果页（多步流程第三步：confirm 提交任务后跳入本页轮询）。
  - onLoad options.job_id → innovation.startPolling(jobId)（store 内置 2.5s 间隔 /
    100s 上限 / 五态终态判定，succeeded 时完整 recipe 已写入 store.current）；
    无 job_id 且 store.current 存在 → 复用回看（detail 页 reuse 成功后跳入，不重复埋点）；
    两者皆无 → 错误态兜底；
  - 生成中 UI：SkeletonPage（detail 形态）+ 进度文案轮换（5s 一换，禁止白屏转圈）
    + 取消按钮（stopPolling + 返回）；
  - 完成 → 呈现创新菜卡（菜名 / RecipeCover 占位封面 / 亮点标签 / 用量清单 / 步骤摘要）
    + trackEvent('innovation_result')；降级（basis.generated_by === 'template'）→ DegradedBar；
  - 超时/失败（store 归一 TIMEOUT / GENERATION_FAILED）→ ErrorState + 重试
    （重新 postInnovationJobCreate → startPolling，食材取自 ingredients.selectedList）；
  - 轮询 blocked（job 风控拦截，store 映射为 precheck 结构）→ RiskBlockModal +
    trackEvent('innovation_blocked')（安全类立即 flush）+ 关闭后返回上一页；
  - 「查看完整」→ ROUTES.INNOVATION_DETAIL + '?recipe_id='；
  - 生命周期协同：onHide → flushOnHide() + innovation.pausePolling()（轮询 promise
    保持挂起）；onShow → innovation.resumePolling()（窗口内恢复调度）；onUnload →
    innovation.stopPolling() 收尾（防页面销毁后定时器泄漏）。
-->
<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import type { ApiError } from '@shared/types'
import { postInnovationJobCreate } from '@/api/endpoints'
import { useIngredientsStore } from '@/stores/ingredients'
import { useInnovationStore } from '@/stores/innovation'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide, trackEvent } from '@/utils/track'
import { toastInfo } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import DegradedBar from '@/components/DegradedBar.vue'
import RiskBlockModal from '@/components/RiskBlockModal.vue'
import RecipeCover from '@/components/RecipeCover.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'

/** 页面阶段：polling 轮询中 / result 结果呈现 / error 错误态 / blocked 拦截确认 */
type Phase = 'polling' | 'result' | 'error' | 'blocked'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 食材 store（重试时重新取已选食材名） */
const ingredients = useIngredientsStore()
/** 创新 store（startPolling / current / precheck / stopPolling / pausePolling） */
const innovation = useInnovationStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 当前页面阶段（模板三分支渲染依据） */
const phase = ref<Phase>('polling')

/** 错误信息（error 态呈现；null = 无错） */
const pollError = ref<ApiError | null>(null)

/** 风控拦截弹窗可见性（blocked 阶段展示） */
const blockedVisible = ref(false)

/** 进度文案轮换定时器句柄（null = 未启动） */
let progressTimer: ReturnType<typeof setInterval> | null = null

/** 进度文案当前序号（轮换游标） */
const progressIndex = ref(0)

/** 生成中进度文案池（轮换展示，避免白屏等待焦虑） */
const PROGRESS_TEXTS: readonly string[] = [
  '正在为你创作新菜…',
  '正在推敲食材搭配与性味…',
  '正在估算营养并校对安全规则…',
]

/** 当前展示的进度文案 */
const progressText = computed(() => PROGRESS_TEXTS[progressIndex.value % PROGRESS_TEXTS.length])

/** 当前创新菜谱（轮询成功 / 复用回看；null = 无结果） */
const recipe = computed(() => innovation.current)

/** 是否模板降级生成（P1 DEF-01：LLM 超时/失败走规则模板，须展示降级提示条） */
const isDegraded = computed(() => recipe.value?.basis.generated_by === 'template')

/** 亮点标签（basis.pairings 的搭配关系去重前 3 个；空数组不渲染） */
const highlightTags = computed<string[]>(() => {
  const relations = (recipe.value?.basis.pairings ?? []).map((p) => p.relation).filter(Boolean)
  return [...new Set(relations)].slice(0, 3)
})

/**
 * 启动进度文案轮换定时器（polling 阶段调用；重复调用先清理防双定时器）。
 * @returns 无
 */
function startProgressTimer(): void {
  stopProgressTimer()
  progressTimer = setInterval(() => {
    progressIndex.value += 1
  }, 5000)
}

/**
 * 停止进度文案轮换定时器（result / error / blocked / 离开页面时调用）。
 * @returns 无
 */
function stopProgressTimer(): void {
  if (progressTimer) {
    clearInterval(progressTimer)
    progressTimer = null
  }
}

/**
 * 启动指定任务的轮询（onLoad / 重试共用）：切 polling 态并挂轮询 promise。
 * 终态分发：resolve 且 current 存在 → result（埋点 innovation_result）；
 * resolve 但 precheck.blocked → blocked 弹窗（安全事件优先上报）；
 * reject → error（TIMEOUT 归 timeout 态文案，其余归 server 态）。
 * @param jobId 任务 ID（confirm 页 postInnovationJobCreate 返回）
 * @returns 无
 */
function pollJob(jobId: string): void {
  phase.value = 'polling'
  pollError.value = null
  startProgressTimer()
  void innovation.startPolling(jobId).then(
    () => {
      if (innovation.current) {
        phase.value = 'result'
        trackEvent('innovation_result')
      } else if (innovation.precheck?.blocked) {
        // job 风控拦截：安全类事件优先上报，弹窗阻断确认
        phase.value = 'blocked'
        trackEvent('innovation_blocked')
        blockedVisible.value = true
      } else {
        // 无结果亦无拦截（如 stopPolling 收尾）：静默回退轮询前态
        phase.value = 'error'
        pollError.value = { code: 'GENERATION_FAILED', message: '生成已取消，请重新发起' } as ApiError
      }
      stopProgressTimer()
    },
    (e: ApiError) => {
      pollError.value = e
      phase.value = 'error'
      stopProgressTimer()
    },
  )
}

/**
 * 取消等待：停止轮询并返回上一页（confirm 页可重新发起）。
 * @returns 无
 */
function cancelPolling(): void {
  innovation.stopPolling()
  stopProgressTimer()
  uni.navigateBack({ fail: () => {} })
}

/**
 * 关闭拦截弹窗：返回上一页（blocked 后本页无可继续内容）。
 * @returns 无
 */
function closeBlocked(): void {
  blockedVisible.value = false
  uni.navigateBack({ fail: () => {} })
}

/**
 * 重新生成（error 态重试）：重新提交异步任务并再次轮询；
 * 已选集为空时提示先去选食材（不放出注定失败的请求）。
 * @returns 无
 */
function retryGenerate(): void {
  const names = ingredients.selectedList.map((s) => s.name)
  if (names.length === 0) {
    toastInfo('请先去选择食材')
    goRoute(ROUTES.RECOMMEND_SELECT)
    return
  }
  void postInnovationJobCreate(names)
    .then((job) => {
      pollJob(job.job_id)
    })
    .catch((e: ApiError) => {
      pollError.value = e
      phase.value = 'error'
    })
}

/**
 * 查看完整创新菜详情（步骤 / 创新依据 / 采纳 / 反馈在详情页）。
 * @returns 无
 */
function openDetail(): void {
  if (!recipe.value) return
  goRoute(`${ROUTES.INNOVATION_DETAIL}?recipe_id=${recipe.value.id}`)
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

// onLoad：带 job_id → 清旧结果并启动轮询；无 job_id → 复用回看或错误兜底
onLoad((options) => {
  const jobId = options?.job_id ? decodeURIComponent(options.job_id) : ''
  if (jobId) {
    // 新任务：清掉上一次残留结果 / 拦截态，避免旧菜谱闪现
    innovation.resetCurrent()
    pollJob(jobId)
    return
  }
  if (innovation.current) {
    // 复用回看（detail reuse 成功跳入）：直接呈现 current，不重复埋 innovation_result
    phase.value = 'result'
    return
  }
  phase.value = 'error'
  pollError.value = { code: 'GENERATION_FAILED', message: '缺少生成任务，请从确认页重新发起' } as ApiError
})

// onShow：恢复轮询（onHide 暂停后窗口内续跑；未暂停时为无操作）+ 恢复进度文案轮换
onShow(() => {
  innovation.resumePolling()
  if (phase.value === 'polling') startProgressTimer()
})

// onHide：尽力上报缓冲埋点 + 暂停轮询（promise 保持挂起）+ 暂停进度文案轮换
onHide(() => {
  flushOnHide()
  innovation.pausePolling()
  stopProgressTimer()
})

// onUnload：停止轮询与定时器（页面销毁后防定时器泄漏与无效状态写入）
onUnload(() => {
  innovation.stopPolling()
  stopProgressTimer()
})

// 组件卸载兜底（非页面卸载路径，如 HMR）：清理进度定时器
onUnmounted(() => {
  stopProgressTimer()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <!-- 离线提示条 -->
    <OfflineBar v-if="!network.isConnected" />

    <view class="result">
      <!-- ═══ 生成中：骨架 + 进度文案轮换 + 取消 ═══ -->
      <template v-if="phase === 'polling'">
        <SkeletonPage type="detail" :rows="4" />
        <view class="result__progress">
          <text class="result__progress-text">{{ progressText }}</text>
          <text class="result__progress-hint">通常 10–60 秒完成，可稍作等待</text>
        </view>
        <view class="result__cancel" @click="cancelPolling">取消等待</view>
      </template>

      <!-- ═══ 错误态：超时 / 失败归一文案 + 重试 ═══ -->
      <template v-else-if="phase === 'error'">
        <ErrorState
          :kind="pollError?.code === 'TIMEOUT' ? 'timeout' : 'server'"
          :detail="pollError?.message || '生成失败，请重试'"
          retry-text="重新生成"
          @retry="retryGenerate"
        />
      </template>

      <!-- ═══ 结果呈现 ═══ -->
      <template v-else-if="phase === 'result' && recipe">
        <!-- 模板降级提示条（P1 DEF-01：LLM 降级规则模板生成） -->
        <DegradedBar v-if="isDegraded" />

        <!-- 菜名 + AI 创新徽标 + 封面 -->
        <view class="result__card">
          <view class="result__head">
            <text class="result__name">{{ recipe.name }}</text>
            <view class="result__ai-badge">AI 创新</view>
          </view>
          <RecipeCover :name="recipe.name" :palette-seed="String(recipe.id)" size="md" />
          <!-- 亮点标签：搭配关系去重前 3 -->
          <view v-if="highlightTags.length > 0" class="result__tags">
            <view v-for="tag in highlightTags" :key="tag" class="result__tag">{{ tag }}</view>
          </view>
        </view>

        <!-- 用量清单 -->
        <view class="result__card">
          <text class="result__section-title">用量清单</text>
          <view
            v-for="(ing, i) in recipe.ingredients"
            :key="`ing-${i}`"
            class="result__ing-row"
          >
            <text class="result__ing-name">{{ ing.name }}</text>
            <text class="result__ing-amount">{{ ing.amount }}{{ ing.unit }}</text>
          </view>
        </view>

        <!-- 步骤摘要 -->
        <view class="result__card">
          <text class="result__section-title">步骤</text>
          <view v-for="s in recipe.steps" :key="`step-${s.no}`" class="result__step">
            <text class="result__step-desc">{{ s.no }}. {{ s.description }}</text>
            <text v-if="stepDuration(s.duration_sec)" class="result__step-duration">
              ⏱ {{ stepDuration(s.duration_sec) }}
            </text>
          </view>
        </view>

        <!-- 强制声明（后端生成，逐字展示） -->
        <view class="result__disclaimer-strong">
          <text class="result__disclaimer-strong-text">{{ recipe.disclaimer }}</text>
        </view>

        <!-- 查看完整：详情页承载采纳 / 复用 / 评分 / 创新依据 -->
        <view class="result__primary-btn" @click="openDetail">查看完整菜谱</view>

        <!-- 免责声明条（G-02） -->
        <DisclaimerBar scene="detail" />
      </template>

      <!-- ═══ 兜底空态（phase=result 但 current 意外为空，理论不可达防御） ═══ -->
      <template v-else-if="phase === 'result'">
        <EmptyState icon="🍽️" title="结果已失效" desc="请返回确认页重新发起生成" />
      </template>
    </view>

    <!-- 风控拦截弹窗（G-01：job blocked 映射，阻断态显式确认后返回） -->
    <RiskBlockModal
      :visible="blockedVisible"
      :kind="innovation.precheck?.rule_id?.includes('allergen') ? 'allergen' : 'food'"
      :detail="innovation.precheck?.message || '食材组合未通过安全预检'"
      @close="closeBlocked"
    />
  </view>
</template>

<style scoped lang="scss">
.result {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
  padding-bottom: calc(var(--space-lg) + env(safe-area-inset-bottom));
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* ── 生成中 ── */
.result__progress {
  margin-top: var(--space-md);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-xs);
}

.result__progress-text {
  font-size: var(--font-size-base);
  color: var(--text-primary);
}

.result__progress-hint {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* 取消等待：info 描边幽灵按钮，热区 ≥88rpx */
.result__cancel {
  margin-top: var(--space-md);
  align-self: center;
  box-sizing: border-box;
  min-width: 240rpx;
  min-height: var(--hit-min);
  padding: 0 var(--space-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2rpx solid var(--color-info);
  border-radius: var(--radius-pill);
  color: var(--color-info);
  font-size: var(--font-size-sm);
}

/* ── 结果卡 ── */
.result__card {
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.result__head {
  margin-bottom: var(--space-sm);
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.result__name {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* AI 创新徽标：warning 语义 */
.result__ai-badge {
  flex-shrink: 0;
  box-sizing: border-box;
  padding: 4rpx var(--space-sm);
  border-radius: var(--radius-ctrl);
  background: var(--color-warning-bg);
  color: var(--color-warning);
  font-size: var(--font-size-sm);
}

.result__tags {
  margin-top: var(--space-sm);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
}

.result__tag {
  box-sizing: border-box;
  padding: 4rpx var(--space-sm);
  border-radius: var(--radius-ctrl);
  background: var(--color-primary-weak);
  color: var(--color-primary);
  font-size: var(--font-size-sm);
}

.result__section-title {
  display: block;
  margin-bottom: var(--space-sm);
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

/* 用量行：名称 + 量化两端对齐 */
.result__ing-row {
  display: flex;
  justify-content: space-between;
  gap: var(--space-sm);
  padding: var(--space-xs) 0;
  border-bottom: 1rpx dashed var(--divider);
  font-size: var(--font-size-sm);
}

.result__ing-name {
  color: var(--text-primary);
}

.result__ing-amount {
  color: var(--text-tertiary);
}

/* 步骤条目 */
.result__step {
  margin-bottom: var(--space-sm);
  display: flex;
  flex-direction: column;
  gap: 4rpx;
}

.result__step-desc {
  font-size: var(--font-size-sm);
  line-height: 1.7;
  color: var(--text-primary);
}

.result__step-duration {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* 强制声明：警示浅底条（后端逐字文案） */
.result__disclaimer-strong {
  box-sizing: border-box;
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-ctrl);
  background: var(--color-warning-bg);
}

.result__disclaimer-strong-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-warning);
}

/* 查看完整：主色实底整行 */
.result__primary-btn {
  box-sizing: border-box;
  width: 100%;
  min-height: 96rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-ctrl);
  background: var(--color-primary);
  color: var(--text-inverse);
  font-size: var(--font-size-base);
}
</style>
