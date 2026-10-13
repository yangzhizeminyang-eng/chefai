<!--
  文件级注释：P-36 创新条件确认页（多步流程第二步：entry → 本页 → result）。
  - 展示将使用的条件：已选食材 chips（ingredients.selectedList，空则引导去手选
    → ROUTES.RECOMMEND_SELECT）+ 家庭档案摘要（profile.loadAll() 三段档案：
    过敏原（成员 allergen_codes + custom_allergens 汇总去重）/ 设备（skill.equipment）/
    目标（goal.goal 五类中文映射）；任一段失败置空兜底不阻塞）；
  - 确认主链路（对齐 store.generate 语义但分步由页面承接，轮询移交 result 页）：
    ① trackEvent('innovation_precheck') → postInnovationPrecheck；
    ② blocked → RiskBlockModal（kind 按 issue 类型映射，安全类）+
       trackEvent('innovation_blocked')（SAFETY_EVENTS 立即 flush）+ 关闭后返回上一页；
    ③ 通过 → 展示可行性提示条 → trackEvent('innovation_generate') →
       postInnovationJobCreate → goRoute(ROUTES.INNOVATION_RESULT + '?job_id=')；
  - 条件修改入口：「调整食材」→ 返回选择页（ROUTES.RECOMMEND_SELECT）。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad } from '@dcloudio/uni-app'
import type { ApiError, InnovationPrecheckResponse } from '@shared/types'
import { postInnovationJobCreate, postInnovationPrecheck } from '@/api/endpoints'
import { useInnovationStore } from '@/stores/innovation'
import { useProfileStore } from '@/stores/profile'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide, trackEvent } from '@/utils/track'
import { toastError } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import RiskBlockModal from '@/components/RiskBlockModal.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 创新 store（precheck 状态同步 + allPickedNames 生成条件 + onHide 暂停轮询） */
const innovation = useInnovationStore()
/** 家庭档案 store（family/skill/goal 三段摘要） */
const profile = useProfileStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 已选食材名列表（本次生成条件：库选 + 自定义输入合并，与 entry 页同源） */
const pickedNames = computed(() => innovation.allPickedNames)

/** 预检中标记（确认按钮 loading） */
const prechecking = ref(false)

/** 提交任务中标记（precheck 通过后 jobCreate 期间防重复点击） */
const submitting = ref(false)

/** 确认链路失败信息（null = 无错；ErrorState 数据源） */
const confirmError = ref<ApiError | null>(null)

/** 预检通过可行性提示（true = 展示通过提示条） */
const precheckOk = ref(false)

/** 风控拦截弹窗可见性（blocked 信息经 store.precheck 读取） */
const blockedVisible = ref(false)

/** blocked 拦截话术（RiskBlockModal detail 展示） */
const blockedMessage = computed(() => {
  const pre = innovation.precheck
  return pre?.blocked ? (pre.message || '食材组合未通过安全预检') : ''
})

/** blocked 命中的规则编号（可选展示） */
const blockedRuleId = computed(() => {
  const pre = innovation.precheck
  return pre?.blocked ? (pre.rule_id || '') : ''
})

/** 风控拦截弹窗 kind（issue 类型映射：allergen → allergen；其余安全类归 food） */
const blockedKind = computed<'food' | 'allergen'>(() => {
  const pre = innovation.precheck
  return pre?.blocked && pre.rule_id?.includes('allergen') ? 'allergen' : 'food'
})

/** 饮食目标编码 → 中文标签（对齐后端 5 类目标口径） */
const GOAL_LABELS: Record<string, string> = {
  control_weight: '控制体重',
  muscle_gain: '增肌塑形',
  light_salt: '清淡少盐',
  low_sugar: '低糖饮食',
  balanced: '均衡营养',
}

/** 家庭成员过敏原汇总（allergen_codes + custom_allergens 去重；无档案/无过敏原为空数组） */
const allergenNames = computed<string[]>(() => {
  const members = profile.family?.members ?? []
  const set = new Set<string>()
  for (const m of members) {
    for (const code of m.allergen_codes ?? []) set.add(code)
    for (const name of m.custom_allergens ?? []) set.add(name)
  }
  return [...set]
})

/** 已有设备列表（skill 档案；无档案为空数组） */
const equipmentNames = computed<string[]>(() => profile.skill?.equipment ?? [])

/** 饮食目标中文标签（无档案为空串不渲染） */
const goalLabel = computed<string>(() => {
  const goal = profile.goal?.goal
  return goal ? (GOAL_LABELS[goal] ?? goal) : ''
})

/**
 * 关闭拦截弹窗：置不可见并返回上一页（entry），阻断态显式确认后离开本页。
 * @returns 无
 */
function closeBlocked(): void {
  blockedVisible.value = false
  uni.navigateBack({ fail: () => {} })
}

/**
 * 确认并开始生成主链路（precheck → jobCreate → 跳 result 页轮询）：
 * - 无食材时拦截（理论上入口已守卫，此处兜底）；
 * - precheck blocked：写 store.precheck（拦截卡数据源）→ 安全事件上报 → 弹窗；
 * - 通过：提交异步任务并携带 job_id 跳 result 页（轮询在 result 页 onLoad 启动）。
 * @returns 无
 * @throws 不向外抛出（precheck/jobCreate 失败统一写 confirmError 呈现 ErrorState）
 */
async function onConfirm(): Promise<void> {
  if (pickedNames.value.length === 0 || prechecking.value || submitting.value) return
  confirmError.value = null
  precheckOk.value = false
  prechecking.value = true
  trackEvent('innovation_precheck')
  let pre: InnovationPrecheckResponse
  try {
    pre = await postInnovationPrecheck(pickedNames.value)
  } catch (e) {
    prechecking.value = false
    confirmError.value = e as ApiError
    return
  }
  prechecking.value = false
  // 同步 store 预检状态（拦截卡 / 复用语义与 store.generate 一致）
  innovation.precheck = pre
  if (pre.blocked) {
    // 安全类事件优先上报（SAFETY_EVENTS 立即 flush，合规举证优先）
    trackEvent('innovation_blocked')
    blockedVisible.value = true
    return
  }
  precheckOk.value = true
  // 提交异步生成任务（202 秒回），轮询移交 result 页
  submitting.value = true
  trackEvent('innovation_generate')
  try {
    const job = await postInnovationJobCreate(pickedNames.value)
    goRoute(`${ROUTES.INNOVATION_RESULT}?job_id=${encodeURIComponent(job.job_id)}`)
  } catch (e) {
    confirmError.value = e as ApiError
    toastError((e as ApiError).message || '任务提交失败，请重试')
  } finally {
    submitting.value = false
  }
}

/**
 * 确认链路重试（ErrorState retry）：重新走 precheck → jobCreate 主链路。
 * @returns 无
 */
function retryConfirm(): void {
  void onConfirm()
}

/**
 * 调整食材：返回创新入口页（食材编辑已页内闭环，不再跳"怎么吃"选择页——语境一致）。
 * @returns 无
 */
function goSelect(): void {
  uni.navigateBack({ fail: () => {} })
}

// onLoad：进入即拉家庭档案摘要（失败置空兜底，不阻塞确认主链路）
onLoad(() => {
  if (profile.family === null && profile.skill === null && profile.goal === null) {
    void profile.loadAll()
  }
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

    <view class="confirm">
      <!-- 空已选集：引导先去手选（不放出确认链路） -->
      <template v-if="pickedNames.length === 0">
        <EmptyState
          icon="🥬"
          title="还没有选择食材"
          desc="先去挑几样手边的食材，再回来创新"
          action-text="去选食材"
          @action="goSelect"
        />
      </template>

      <template v-else>
        <!-- 已选食材 chips -->
        <view class="confirm__card">
          <view class="confirm__head">
            <text class="confirm__card-title">已选食材（{{ pickedNames.length }}）</text>
            <view class="confirm__edit" @click="goSelect">调整食材</view>
          </view>
          <view class="confirm__chips">
            <view v-for="name in pickedNames" :key="name" class="confirm__chip">
              {{ name }}
            </view>
          </view>
        </view>

        <!-- 家庭档案摘要 -->
        <view class="confirm__card">
          <text class="confirm__card-title">家庭档案摘要</text>
          <view v-if="profile.loading" class="confirm__profile-loading">
            <SkeletonPage type="list" :rows="3" />
          </view>
          <template v-else>
            <view class="confirm__profile-row">
              <text class="confirm__profile-label">过敏原</text>
              <view class="confirm__chips confirm__chips--profile">
                <view v-for="a in allergenNames" :key="a" class="confirm__chip confirm__chip--danger">
                  {{ a }}
                </view>
                <text v-if="allergenNames.length === 0" class="confirm__profile-empty">暂无记录</text>
              </view>
            </view>
            <view class="confirm__profile-row">
              <text class="confirm__profile-label">设备</text>
              <view class="confirm__chips confirm__chips--profile">
                <view v-for="eq in equipmentNames" :key="eq" class="confirm__chip">
                  {{ eq }}
                </view>
                <text v-if="equipmentNames.length === 0" class="confirm__profile-empty">暂无记录</text>
              </view>
            </view>
            <view class="confirm__profile-row">
              <text class="confirm__profile-label">目标</text>
              <view class="confirm__chips confirm__chips--profile">
                <view v-if="goalLabel" class="confirm__chip confirm__chip--primary">{{ goalLabel }}</view>
                <text v-else class="confirm__profile-empty">暂无记录</text>
              </view>
            </view>
          </template>
        </view>

        <!-- 预检通过可行性提示条（info 语义，非阻断） -->
        <view v-if="precheckOk" class="confirm__ok-bar">
          <text class="confirm__ok-text">已通过安全预检，食材组合可以开始创新</text>
        </view>

        <!-- 确认链路错误态（precheck / jobCreate 失败） -->
        <ErrorState
          v-if="confirmError"
          kind="server"
          :detail="confirmError.message"
          @retry="retryConfirm"
        />

        <!-- 确认按钮：主链路入口 -->
        <view
          class="confirm__primary-btn"
          :class="{ 'is-disabled': prechecking || submitting }"
          @click="onConfirm"
        >
          {{ prechecking || submitting ? '正在提交…' : '确认并开始生成' }}
        </view>

        <!-- 免责声明条（G-02：生成结果仅供参考，文案取自 @shared/constants） -->
        <DisclaimerBar scene="risk" />
      </template>
    </view>

    <!-- 风控拦截弹窗（G-01：阻断态显式确认，关闭后返回上一页） -->
    <RiskBlockModal
      :visible="blockedVisible"
      :kind="blockedKind"
      :detail="blockedRuleId ? `${blockedMessage}（规则编号：${blockedRuleId}）` : blockedMessage"
      @close="closeBlocked"
    />
  </view>
</template>

<style scoped lang="scss">
.confirm {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
  padding-bottom: calc(var(--space-lg) + env(safe-area-inset-bottom));
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.confirm__card {
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.confirm__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
}

.confirm__card-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

/* 调整食材入口：文字按钮，热区 ≥88rpx */
.confirm__edit {
  box-sizing: border-box;
  min-height: var(--hit-min);
  display: flex;
  align-items: center;
  padding: 0 var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--color-primary);
}

.confirm__chips {
  margin-top: var(--space-sm);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);

  /* 档案摘要行内 chips：顶部间距收紧 */
  &--profile {
    margin-top: 0;
    flex: 1;
  }
}

.confirm__chip {
  box-sizing: border-box;
  padding: 8rpx var(--space-md);
  min-height: 64rpx;
  display: flex;
  align-items: center;
  border: 1rpx solid var(--border-color);
  border-radius: var(--radius-pill);
  background: var(--bg-page);
  color: var(--text-secondary);
  font-size: var(--font-size-sm);

  /* 过敏原：danger 语义 */
  &--danger {
    border-color: var(--color-danger);
    background: var(--color-danger-bg);
    color: var(--color-danger);
  }

  /* 目标：primary 语义 */
  &--primary {
    border-color: var(--color-primary);
    background: var(--color-primary-weak);
    color: var(--color-primary);
  }
}

.confirm__profile-row {
  margin-top: var(--space-md);
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
}

.confirm__profile-label {
  flex-shrink: 0;
  width: 96rpx;
  font-size: var(--font-size-sm);
  line-height: 64rpx;
  color: var(--text-tertiary);
}

.confirm__profile-empty {
  font-size: var(--font-size-sm);
  line-height: 64rpx;
  color: var(--text-tertiary);
}

.confirm__profile-loading {
  margin-top: var(--space-sm);
}

/* 预检通过提示条：info 色横条（非阻断语义） */
.confirm__ok-bar {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
  padding: var(--space-xs) var(--space-md);
  border-radius: var(--radius-ctrl);
  background: var(--color-info-bg);
}

.confirm__ok-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-info);
}

/* 确认按钮：主色实底整行，热区 ≥96rpx；提交中半透明禁用 */
.confirm__primary-btn {
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
    opacity: 0.5;
  }
}
</style>
