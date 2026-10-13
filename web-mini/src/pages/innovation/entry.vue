<!--
  文件级注释：P-35 AI 创新入口页（交互重构：食材编辑页内完成 + 一键创新直出）。
  - 守卫：config.switches.innovation 为 false → EmptyState「功能暂未开放」
    （模块级远程开关，Q-64 五键之一；onShow 经 refreshOnShow() TTL 内免重拉）；
  - 食材编辑（页内闭环，不跳转"怎么吃"选择页——历史交互断裂已修复）：
    已选 chips（点 × 删除，与推荐主流程共用同一已选集 ingredients.selected）
    + 搜索框（300ms 防抖 getIngredients q 搜索）+ 候选 chips（点击加入，已选置灰）；
  - 「开始创新」一键直出：原地 precheck（blocked → RiskBlockModal + innovation_blocked
    安全事件优先上报）→ 通过直接 jobCreate → 携 job_id 跳 result 轮询；
  - P-36 条件确认页保留可达：次级链接「查看生成条件」→ INNOVATION_CONFIRM
    （完整食材 + 家庭档案摘要确认，供需要核对档案的场景）；
  - 「我的创新菜」入口 → ROUTES.INNOVATION_MINE（P-39 列表页）。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import type { ApiError, Ingredient, InnovationPrecheckResponse } from '@shared/types'
import { useConfigStore } from '@/stores/config'
import { useIngredientsStore } from '@/stores/ingredients'
import { useInnovationStore } from '@/stores/innovation'
import { getIngredients, postInnovationPrecheck, postInnovationJobCreate } from '@/api/endpoints'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide, trackEvent } from '@/utils/track'
import { toastError, toastInfo } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import RiskBlockModal from '@/components/RiskBlockModal.vue'
import BaseInput from '@/components-base/BaseInput.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 远程开关 store（switches.innovation 模块级守卫） */
const config = useConfigStore()
/** 食材 store（selectedList 已选集 + toggle 翻转 + clear 清空，与推荐主流程共用） */
const ingredients = useIngredientsStore()
/** 创新 store（precheck 状态同步 + onHide 暂停轮询安全调用） */
const innovation = useInnovationStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 创新模块是否关闭（远程开关显式 false；undefined 视为放开） */
const innovationDisabled = computed(() => config.switches.innovation === false)

/** 已选食材列表（{id, name}，chips 渲染与生成条件来源） */
const pickedList = computed(() => ingredients.selectedList)

/** 已选食材 id 集合（候选置灰判定） */
const pickedIds = computed(() => new Set(pickedList.value.map((s) => s.id)))

/** 搜索关键词（BaseInput 双向绑定） */
const keyword = ref('')

/** 搜索候选食材（q 命中前 10 条；空关键词不展示） */
const candidates = ref<Ingredient[]>([])

/** 搜索请求进行中（候选区提示） */
const searching = ref(false)

/** 预检 + 提交任务进行中（开始创新按钮 loading 与防重复点击） */
const launching = ref(false)

/** 风控拦截弹窗可见性（blocked 信息经 store.precheck 读取） */
const blockedVisible = ref(false)

/** blocked 拦截话术（RiskBlockModal detail 展示） */
const blockedMessage = computed(() => {
  const pre = innovation.precheck
  return pre?.blocked ? (pre.message || '食材组合未通过安全预检') : ''
})

/** 风控拦截弹窗 kind（issue 类型映射：allergen → allergen；其余安全类归 food） */
const blockedKind = computed<'food' | 'allergen'>(() => {
  const pre = innovation.precheck
  return pre?.blocked && pre.rule_id?.includes('allergen') ? 'allergen' : 'food'
})

/** 搜索防抖定时器句柄（300ms 内连续输入只发一次请求） */
let searchTimer: ReturnType<typeof setTimeout> | null = null

/**
 * 搜索框输入回调：300ms 防抖后按关键词拉取候选食材；空关键词清空候选区。
 * @param value 输入框当前值
 * @returns 无
 * @throws 不抛出（搜索失败静默清空候选区，不打断编辑）
 */
function onSearchInput(value: string): void {
  keyword.value = value
  if (searchTimer) clearTimeout(searchTimer)
  const q = value.trim()
  if (!q) {
    candidates.value = []
    searching.value = false
    return
  }
  searching.value = true
  searchTimer = setTimeout(() => {
    void doSearch(q)
  }, 300)
}

/**
 * 执行食材搜索（getIngredients q，候选取前 10 条）；失败静默清空候选区。
 * @param q 关键词（已 trim）
 * @returns 无
 * @throws 不抛出（失败置空候选区——搜索为编辑辅助，不阻断创新主链路）
 */
async function doSearch(q: string): Promise<void> {
  try {
    const res = await getIngredients({ q })
    candidates.value = (res.items ?? []).slice(0, 10)
  } catch {
    candidates.value = []
  } finally {
    searching.value = false
  }
}

/**
 * 翻转候选食材选中态（未选 → 加入；已选 → 移除）。
 * @param ing 候选食材对象
 * @returns 无
 */
function toggleCandidate(ing: Ingredient): void {
  ingredients.toggle(ing)
}

/**
 * 移除已选食材（chips × 按钮）。
 * @param id 食材 id
 * @returns 无
 */
function removePicked(id: number): void {
  const target = pickedList.value.find((s) => s.id === id)
  if (!target) return
  ingredients.toggle({ id: target.id, name: target.name } as Ingredient)
}

/**
 * 清空全部已选食材（chips 区"清空"按钮，二次确认不必要——可重新添加）。
 * @returns 无
 */
function clearPicked(): void {
  if (pickedList.value.length === 0) return
  ingredients.clear()
  toastInfo('已清空已选食材')
}

/**
 * 关闭风控拦截弹窗：留在本页（用户可调整食材后重试）。
 * @returns 无
 */
function closeBlocked(): void {
  blockedVisible.value = false
}

/**
 * 一键开始创新主链路：precheck（原地校验）→ 通过直接 jobCreate → 跳 result 轮询。
 * - 空食材拦截（toast 提示）；
 * - precheck blocked：写 store.precheck → innovation_blocked 安全事件优先上报 → 弹窗；
 * - jobCreate 失败 toast，停留在本页可重试。
 * @returns 无
 * @throws 不向外抛出（precheck/jobCreate 失败统一 toast 呈现）
 */
async function startInnovation(): Promise<void> {
  if (launching.value) return
  if (pickedList.value.length === 0) {
    toastInfo('请先添加需要创新的食材')
    return
  }
  launching.value = true
  trackEvent('innovation_enter')
  trackEvent('innovation_precheck')
  const pickedNames = pickedList.value.map((s) => s.name)
  let pre: InnovationPrecheckResponse
  try {
    pre = await postInnovationPrecheck(pickedNames)
  } catch (e) {
    launching.value = false
    toastError((e as ApiError).message || '预检失败，请重试')
    return
  }
  // 同步 store 预检状态（拦截弹窗数据源；result 页复用语义一致）
  innovation.precheck = pre
  if (pre.blocked) {
    launching.value = false
    // 安全类事件优先上报（SAFETY_EVENTS 立即 flush，合规举证优先）
    trackEvent('innovation_blocked')
    blockedVisible.value = true
    return
  }
  // 预检通过：提交异步生成任务（202 秒回），轮询移交 result 页
  trackEvent('innovation_generate')
  try {
    const job = await postInnovationJobCreate(pickedNames)
    goRoute(`${ROUTES.INNOVATION_RESULT}?job_id=${encodeURIComponent(job.job_id)}`)
  } catch (e) {
    toastError((e as ApiError).message || '任务提交失败，请重试')
  } finally {
    launching.value = false
  }
}

/**
 * 打开条件确认页（P-36 完整条件确认：食材 + 家庭档案摘要，保留可达）。
 * @returns 无
 */
function goConfirm(): void {
  if (pickedList.value.length === 0) {
    toastInfo('请先添加需要创新的食材')
    return
  }
  goRoute(ROUTES.INNOVATION_CONFIRM)
}

/**
 * 打开我的创新菜列表（P-39）。
 * @returns 无
 */
function goMine(): void {
  goRoute(ROUTES.INNOVATION_MINE)
}

// onShow：刷新远程开关（TTL 内为无操作；守卫随开关实时生效）
onShow(() => {
  void config.refreshOnShow()
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

    <!-- 模块开关守卫：关闭时整页替换为空态（不放出后续流程） -->
    <EmptyState
      v-if="innovationDisabled"
      icon="🚧"
      title="功能暂未开放"
      desc="AI 创新菜正在内测打磨中，敬请期待"
    />

    <template v-else>
      <view class="entry">
        <!-- 标题 + 功能说明 -->
        <text class="entry__title">AI 创新一下</text>
        <view class="entry__intro">
          <text class="entry__intro-line">基于你手边的食材和家庭档案（过敏原 / 设备 / 目标），</text>
          <text class="entry__intro-line">由 AI 组合出全新的菜谱，并给出创新依据与营养估算。</text>
          <text class="entry__intro-line entry__intro-line--muted">生成结果仅供参考，请遵循基本烹饪安全常识。</text>
        </view>

        <!-- 食材编辑卡片（页内闭环：搜索 + 增删，不跳转选择页） -->
        <view class="entry__section">
          <view class="entry__section-head">
            <text class="entry__section-title">本次将使用的食材（{{ pickedList.length }}）</text>
            <view
              v-if="pickedList.length > 0"
              class="entry__clear"
              @click="clearPicked"
            >
              清空
            </view>
          </view>

          <!-- 已选 chips：点 × 移除 -->
          <view v-if="pickedList.length > 0" class="entry__chips">
            <view v-for="item in pickedList" :key="item.id" class="entry__chip">
              {{ item.name }}
              <text class="entry__chip-x" @click.stop="removePicked(item.id)">×</text>
            </view>
          </view>
          <text v-else class="entry__empty-hint">还没有添加食材，搜一搜手边有什么</text>

          <!-- 搜索框：300ms 防抖拉候选 -->
          <view class="entry__search">
            <BaseInput
              :model-value="keyword"
              placeholder="搜索食材，如：鸡蛋、培根、海带"
              @update:model-value="onSearchInput"
            />
          </view>

          <!-- 搜索候选：点击加入/移除，已选置灰 -->
          <view v-if="searching" class="entry__candidates-tip">搜索中…</view>
          <view v-else-if="keyword.trim() && candidates.length === 0" class="entry__candidates-tip">
            没有找到匹配的食材
          </view>
          <view v-else-if="candidates.length > 0" class="entry__chips">
            <view
              v-for="c in candidates"
              :key="c.id"
              class="entry__chip entry__chip--candidate"
              :class="{ 'is-picked': pickedIds.has(c.id) }"
              @click="toggleCandidate(c)"
            >
              {{ c.name }}{{ pickedIds.has(c.id) ? ' ✓' : '' }}
            </view>
          </view>
        </view>

        <!-- 底部动作区 -->
        <view class="entry__actions">
          <view
            class="entry__primary-btn"
            :class="{ 'is-disabled': launching }"
            @click="startInnovation"
          >
            {{ launching ? '正在预检食材…' : '开始创新' }}
          </view>
          <view class="entry__confirm-link" @click="goConfirm">查看生成条件（食材 + 家庭档案）</view>
          <view class="entry__mine-link" @click="goMine">我的创新菜</view>
        </view>

        <!-- 免责声明条（G-02：安全文案取自 @shared/constants） -->
        <DisclaimerBar scene="risk" />
      </view>
    </template>

    <!-- 风控拦截弹窗（G-01：blocked 三类呈现；关闭后留在本页可调整食材重试） -->
    <RiskBlockModal
      :visible="blockedVisible"
      :kind="blockedKind"
      :detail="blockedMessage"
      @close="closeBlocked"
    />
  </view>
</template>

<style scoped lang="scss">
.entry {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
  padding-bottom: calc(var(--space-lg) + env(safe-area-inset-bottom));
  display: flex;
  flex-direction: column;
}

.entry__title {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.entry__intro {
  margin-top: var(--space-sm);
  display: flex;
  flex-direction: column;
  gap: 4rpx;
}

.entry__intro-line {
  font-size: var(--font-size-sm);
  line-height: 1.7;
  color: var(--text-secondary);

  /* 弱化补充句：安全提示语义降级为灰字 */
  &--muted {
    color: var(--text-tertiary);
  }
}

.entry__section {
  margin-top: var(--space-lg);
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.entry__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.entry__section-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

/* 清空按钮：弱化文字按钮，热区 ≥88rpx */
.entry__clear {
  box-sizing: border-box;
  min-height: var(--hit-min);
  display: flex;
  align-items: center;
  padding: 0 var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.entry__chips {
  margin-top: var(--space-sm);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
}

/* 已选 chip：主色描边 + × 删除钮（× 热区随 chip ≥88rpx） */
.entry__chip {
  box-sizing: border-box;
  min-height: var(--hit-min);
  padding: 0 var(--space-md);
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  border: 1rpx solid var(--color-primary);
  border-radius: var(--radius-pill);
  background: var(--color-primary-weak);
  color: var(--color-primary);
  font-size: var(--font-size-sm);
}

.entry__chip-x {
  font-size: var(--font-size-base);
  color: var(--color-primary);
}

/* 候选 chip：中性描边；已选置灰并打勾 */
.entry__chip--candidate {
  border-color: var(--border-color);
  background: var(--bg-card);
  color: var(--text-secondary);

  &.is-picked {
    opacity: 0.5;
    border-color: var(--color-primary);
  }
}

.entry__empty-hint {
  margin-top: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.entry__search {
  margin-top: var(--space-md);
}

/* 候选区状态提示（搜索中 / 无结果） */
.entry__candidates-tip {
  margin-top: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.entry__actions {
  margin-top: var(--space-lg);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-sm);
}

/* 主按钮：主色实底整行，热区 ≥88rpx；loading 态半透明并拦截重复点击 */
.entry__primary-btn {
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

  &.is-disabled {
    opacity: 0.6;
  }
}

/* 条件确认次级入口：纯文字弱化链接，保留 P-36 可达 */
.entry__confirm-link {
  box-sizing: border-box;
  min-height: var(--hit-min);
  display: flex;
  align-items: center;
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* 我的创新菜入口：幽灵描边次级按钮 */
.entry__mine-link {
  box-sizing: border-box;
  width: 100%;
  min-height: var(--hit-min);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2rpx solid var(--color-primary);
  border-radius: var(--radius-ctrl);
  color: var(--color-primary);
  font-size: var(--font-size-base);
}
</style>
