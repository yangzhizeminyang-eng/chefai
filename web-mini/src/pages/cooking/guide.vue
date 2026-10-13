<!--
  文件级注释：P-15 分步引导页（M4 烹饪闭环核心页，沉浸式烹饪专档）。
  自 web-stage1/src/views/CookGuideView.vue（W-04，1332 行）迁移，拆页落点见下：
  - 会话恢复三轨：内存 store（restoreById 策略①②）→ 本地缓存（cook_session_/cook_steps_）
    → 离线快照（offline_recipe_{id}，recallSessionRecipe 反查；对齐源码断点续做策略）；
  - 离线写入（NFR-3.6）：会话就绪后 saveRecipeSnapshot（步骤 + 基准份数 + 菜名），
    快照已存在则不重复拉网络；过敏原标注另存 cook_allergens_{recipe_id}
    （offlineCache 快照结构不含过敏原字段且属只读资产，故平行落一条 storage 标注）；
  - 沉浸式：navigationStyle custom + BaseNavbar（title=菜名，
    backConfirmText='确认退出烹饪？' 二次确认——进度保留不放弃，对齐源码 onExit 语义；
    onUnload 时把防抖中的断点 PATCH 立即落库）；
  - 屏幕常亮：onShow setKeepScreenOn(true)，onHide/onUnload 关闭（替代源码 Wake Lock）；
  - 烹饪专档：根节点挂 cooking-mode（--font-size-base 提升为 64rpx，独立于用户字号设置）；
  - AllergenAlertBar large 常驻顶部（allergens 在线取 session.allergen_conflict、
    离线取本地标注，大字模式可见——过敏原五处生效之三）；
  - 步骤切换完全本地：store.next/prev 游标推进 + 800ms 防抖静默 PATCH（P95≤300ms 零网络，
    handler 内无任何 createCookingSession/getRecipe 调用）+ trackEvent('cook_step_next')；
  - 份量切换：BasePicker 目标份量 1~10，本地 scaleAmount 换算展示，不发请求不改会话
    （会话份数以创建时为准，重选份数请回菜谱页重新发起）；
  - 语音指令（增强可降级）：按住说话（uni.getRecorderManager 录音）——小程序端 ASR
    服务本期未接入，录音结束以占位提示引导手动快捷 chips（下一步/上一步/计时 5 分钟），
    麦克风权限拒绝 → PermissionGuide + fallback 手动 chips（语音不阻断手动，NFR）；
  - 底部操作条三入口：计时器 / 问厨娘 / 完成烹饪（均带 session_id）；最后一步主按钮
    变「去完成」跳 P-18（完成/放弃与评分在 P-18 收口，本页 onUnload 不额外上报）；
  - 离线态：uni.onNetworkStatusChange 监听 → OfflineBar；无网且无任何缓存数据 →
    恢复失败态（OFFLINE_UNCACHED_TEXT 置灰提示，不转圈）。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { getRecipe } from '@/api/endpoints'
import type { RecipeStep } from '@shared/types'
import { useCookingStore } from '@/stores/cooking'
import { scaleStepHint } from '@shared/utils/scaling'
import { formatAmountText } from '@shared/utils/unit'
import { OFFLINE_UNCACHED_TEXT } from '@shared/constants'
import {
  getRecipeSnapshot,
  recallSessionRecipe,
  rememberSessionRecipe,
  saveRecipeSnapshot,
} from '@/utils/offlineCache'
import { get as storageGet, set as storageSet } from '@/utils/storage'
import { goRoute, ROUTES } from '@/utils/routes'
import { toastInfo } from '@/utils/toast'
import { trackEvent, flushOnHide } from '@/utils/track'
import { setKeepScreenOn } from '@/platform/device'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import AllergenAlertBar from '@/components/AllergenAlertBar.vue'
import BaseNavbar from '@/components/BaseNavbar.vue'
import OfflineBar from '@/components/OfflineBar.vue'
import PermissionGuide from '@/components/PermissionGuide.vue'
import ErrorState from '@/components/ErrorState.vue'
import BaseButton from '@/components-base/BaseButton.vue'
import BasePicker from '@/components-base/BasePicker.vue'
import BaseDialog from '@/components-base/BaseDialog.vue'

/** 过敏原标注存储键前缀（key = cook_allergens_{recipeId}，离线态警示条数据源） */
const ALLERGEN_MARK_PREFIX = 'cook_allergens_'

/** 页面阶段：loading 加载中 / ready 在线会话 / offline 离线快照兜底 / failed 恢复失败 */
type GuidePhase = 'loading' | 'ready' | 'offline' | 'failed'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 烹饪 store（会话 / 本地步骤快照 / 本地切换动作，断点续做数据源） */
const cooking = useCookingStore()

/** 页面阶段（驱动五态渲染） */
const phase = ref<GuidePhase>('loading')

/** 路由注入的会话 ID（onLoad；恢复失败重试与跳转入参共用） */
const sessionId = ref('')

/** 导航栏标题（菜名；离线快照 / 网络拉取补齐，缺省「烹饪引导」） */
const navTitle = ref('烹饪引导')

/** 网络不可用标记（onNetworkStatusChange 实时更新） */
const offline = ref(false)

/** 网络状态监听回调句柄（onUnload 解绑用） */
let networkHandler: ((res: { isConnected: boolean }) => void) | null = null

/* ═══ 渲染数据（在线/离线双轨统一出口，对齐源码 currentStep computed 语义） ═══ */

/** 当前步骤对象（在线取 store getter，离线取快照游标） */
const currentStep = computed(() => {
  if (phase.value === 'offline') return offlineSteps.value[offlineStepNo.value - 1] ?? null
  return cooking.currentStep
})

/** 当前步骤序号（1 起） */
const currentStepNo = computed(() =>
  phase.value === 'offline' ? offlineStepNo.value : cooking.currentStepNo,
)

/** 步骤总数 */
const totalSteps = computed(() =>
  phase.value === 'offline' ? offlineSteps.value.length : cooking.totalSteps,
)

/** 是否最后一步（主按钮变「去完成」） */
const isLast = computed(() => totalSteps.value > 0 && currentStepNo.value >= totalSteps.value)

/** 全量步骤（步骤列表弹层渲染） */
const stepList = computed(() =>
  phase.value === 'offline' ? offlineSteps.value : cooking.steps,
)

/** 进度百分比 = 当前步 / 总步数 */
const progressPercent = computed(() => {
  if (totalSteps.value === 0) return 0
  return Math.round((currentStepNo.value / totalSteps.value) * 100)
})

/* ═══ 离线态本地状态 ═══ */

/** 离线快照步骤（离线模式渲染数据源） */
const offlineSteps = ref<RecipeStep[]>([])

/** 离线模式当前步骤游标（1 起，纯本地推进） */
const offlineStepNo = ref(1)

/** 离线模式关联菜谱 ID（快照回查/标注读取用） */
const offlineRecipeId = ref<number | null>(null)

/** 常驻过敏原警示（在线取会话 allergen_conflict；离线取本地标注） */
const allergens = computed<string[]>(() => {
  if (phase.value === 'offline') {
    const rid = offlineRecipeId.value
    if (rid == null) return []
    return storageGet<string[]>(`${ALLERGEN_MARK_PREFIX}${rid}`, []) ?? []
  }
  return cooking.session?.allergen_conflict ?? []
})

/* ═══ 份量切换（本地换算展示，不发请求） ═══ */

/** 目标份量（初始 = 会话份数；BasePicker 双向绑定） */
const targetServings = ref(1)

/** BasePicker 份量选项（1~10 份） */
const servingsOptions = Array.from({ length: 10 }, (_, i) => ({ label: `${i + 1} 份`, value: i + 1 }))

/**
 * 本步用量缩放系数（目标份量 / 菜谱基准份数；离线态无会话份数固定 1 不误缩放）。
 * @returns 缩放系数
 */
const hintFactor = computed<number>(() => {
  if (phase.value === 'offline') return 1
  const base = cooking.baseServings || cooking.session?.servings || 1
  if (!base || base < 1) return 1
  return targetServings.value / base
})

/**
 * 当前步骤缩放后的本步用量提示（scaleStepHint 缩放 + formatAmountText 单位格式化，
 * 小程序端缺省 gram 展示模式——单位三选归设置页任务范围）。
 * @returns 缩放后的提示文案；无提示返回空串
 */
const scaledAmountHint = computed<string>(() =>
  formatAmountText(scaleStepHint(currentStep.value?.amount_hint, hintFactor.value), 'gram'),
)

/**
 * 秒数转可读耗时（步骤展示，对齐源码 formatDuration）。
 * @param sec 耗时秒数（0 表示无需等待）
 * @returns 可读文案
 */
function formatDuration(sec: number): string {
  if (!sec || sec <= 0) return '无需等待'
  if (sec < 60) return `${sec} 秒`
  return `约 ${Math.round(sec / 60)} 分钟`
}

/* ═══ 会话恢复与离线写入 ═══ */

/**
 * 保存离线快照与过敏原标注（会话就绪后调用）。
 * - 离线快照已存在 → 不重复拉网络（仅确保 sessionId→recipeId 映射在位）；
 * - 快照缺失 → getRecipe 拉菜名（失败空串兜底）后 saveRecipeSnapshot（步骤 + 用量基准）；
 * - 过敏原标注 cook_allergens_{rid}：写后端判定的 allergen_conflict（离线警示条数据源）。
 * @returns 无
 * @throws 不抛出（offlineCache / storage 内部静默降级，写入失败不影响在线烹饪）
 */
async function persistOfflineData(): Promise<void> {
  const session = cooking.session
  if (!session || cooking.steps.length === 0) return
  rememberSessionRecipe(session.id, session.recipe_id)
  // 过敏原标注（平行 storage 键：offlineCache 快照结构只读，不扩展）
  const markKey = `${ALLERGEN_MARK_PREFIX}${session.recipe_id}`
  if (!(storageGet<string[]>(markKey, []) ?? []).length) {
    storageSet(markKey, session.allergen_conflict ?? [])
  }
  // 快照已有则不重复拉网络
  const existing = await getRecipeSnapshot(session.recipe_id)
  if (existing) {
    if (existing.title) navTitle.value = existing.title
    return
  }
  const title = await getRecipe(session.recipe_id)
    .then((d) => d.title)
    .catch(() => '')
  if (title) navTitle.value = title
  await saveRecipeSnapshot({
    recipe_id: session.recipe_id,
    title,
    steps: cooking.steps,
    base_servings: cooking.baseServings,
    session_id: session.id,
  })
}

/**
 * 离线兜底恢复（断点续做三轨之第三轨）：sessionId 反查 recipeId → 读离线快照。
 * @param sid 路由中的会话 ID
 * @returns 兜底成功返回 true；映射/快照缺失返回 false
 * @throws 不抛出（getRecipeSnapshot 内部静默降级）
 */
async function tryOfflineRestore(sid: string): Promise<boolean> {
  const rid = recallSessionRecipe(sid)
  if (rid == null) return false
  const snapshot = await getRecipeSnapshot(rid)
  if (!snapshot || snapshot.steps.length === 0) return false
  offlineSteps.value = snapshot.steps
  offlineStepNo.value = 1
  offlineRecipeId.value = rid
  if (snapshot.title) navTitle.value = snapshot.title
  targetServings.value = 1
  return true
}

/**
 * 启动恢复流程（onLoad 与失败重试共用）：
 * 内存/本地缓存（restoreById）→ 离线快照（tryOfflineRestore）→ 恢复失败态。
 * @returns 无
 * @throws 不抛出（各轨道内部静默降级）
 */
async function bootstrap(): Promise<void> {
  phase.value = 'loading'
  if (cooking.restoreById(sessionId.value)) {
    targetServings.value = cooking.session?.servings ?? 1
    phase.value = 'ready'
    // 离线写入（fire-and-forget，快照/标注失败不影响在线烹饪）
    void persistOfflineData()
    return
  }
  const ok = await tryOfflineRestore(sessionId.value)
  phase.value = ok ? 'offline' : 'failed'
}

/* ═══ 步骤切换（完全本地：游标推进 + store 防抖 PATCH，零网络阻塞） ═══ */

/**
 * 下一步（本地切换）：离线走快照游标；在线走 store（800ms 防抖静默 PATCH 断点）。
 * trackEvent('cook_step_next') 随切换上报；最后一步不在此结束会话（去 P-18 收口）。
 * @returns 无
 */
function goNextStep(): void {
  if (phase.value === 'offline') {
    if (offlineStepNo.value < totalSteps.value) offlineStepNo.value += 1
    return
  }
  if (isLast.value) return
  trackEvent('cook_step_next', { session_id: sessionId.value, step_no: currentStepNo.value })
  void cooking.next()
}

/**
 * 上一步（本地切换）：第一步不回退（store/游标各自边界收敛）。
 * @returns 无
 */
function goPrevStep(): void {
  if (phase.value === 'offline') {
    if (offlineStepNo.value > 1) offlineStepNo.value -= 1
    return
  }
  void cooking.prev()
}

/**
 * 步骤列表跳转（本地切换 + 防抖持久化；离线游标收敛）。
 * @param no 目标步骤序号（1 起）
 * @returns 无
 */
function onJump(no: number): void {
  stepDrawerVisible.value = false
  if (phase.value === 'offline') {
    offlineStepNo.value = Math.min(Math.max(no, 1), Math.max(totalSteps.value, 1))
    return
  }
  void cooking.jumpTo(no)
}

/**
 * 底部主按钮：最后一步 → 跳完成评分页（P-18 收口）；否则本地下一步。
 * @returns 无
 */
function onPrimaryAction(): void {
  if (isLast.value) {
    goRoute(`${ROUTES.COOK_FINISH}?session_id=${encodeURIComponent(sessionId.value)}`)
    return
  }
  goNextStep()
}

/* ═══ 弹层状态 ═══ */

/** 步骤列表弹层可见性 */
const stepDrawerVisible = ref(false)

/** 新手要点区展开标记（要点 + 失败补救折叠） */
const tipsExpanded = ref(false)

/* ═══ 语音指令（增强可降级：录音占位 + 手动快捷 chips 兜底） ═══ */

/** 是否正在录音（按住说话按钮视觉态） */
const recording = ref(false)

/** 麦克风权限引导可见性（权限拒绝时展示，fallback 手动 chips 不阻断） */
const voiceGuideVisible = ref(false)

/** 录音管理器句柄（懒创建；平台不支持时为 null） */
let recorderManager: UniApp.RecorderManager | null = null

/**
 * 懒创建录音管理器并绑定回调（函数）。
 * - onStop：ASR 服务本期未接入（占位）——录音数据不消费，提示改用手动快捷指令；
 * - onError：权限拒绝（operateFail/auth deny）→ 打开 PermissionGuide 引导；
 * @returns 录音管理器或 null（平台不支持）
 * @throws 不抛出
 */
function ensureRecorder(): UniApp.RecorderManager | null {
  if (recorderManager) return recorderManager
  try {
    const mgr = uni.getRecorderManager()
    mgr.onStart(() => {
      recording.value = true
      // 尝试语音即上报 cook_voice_command（无论后续 ASR 是否可用）
      trackEvent('cook_voice_command', { session_id: sessionId.value })
    })
    mgr.onStop(() => {
      recording.value = false
      // ASR 不可用占位：小程序端语音转文本服务未接入，录音不消费，引导手动快捷指令
      toastInfo('语音识别暂未开放，可用下方快捷指令操作')
    })
    mgr.onError(() => {
      recording.value = false
      // 权限拒绝 / 录音失败：展示权限引导，手动 chips 兜底不阻断烹饪
      voiceGuideVisible.value = true
    })
    recorderManager = mgr
    return mgr
  } catch {
    // 平台不支持录音：静默降级为纯手动
    return null
  }
}

/**
 * 按住说话（longpress）：开始录音。
 * @returns 无
 */
function onRecordStart(): void {
  const mgr = ensureRecorder()
  if (!mgr) {
    toastInfo('当前环境不支持语音，可用快捷指令操作')
    return
  }
  try {
    mgr.start({ duration: 10000, format: 'mp3' })
  } catch {
    recording.value = false
  }
}

/**
 * 松开停止（touchend/touchcancel）：结束录音（onStop 占位提示）。
 * @returns 无
 */
function onRecordEnd(): void {
  if (!recording.value || !recorderManager) return
  try {
    recorderManager.stop()
  } catch {
    // 静默
  }
}

/**
 * 快捷指令 chips 下一步：复用 goNextStep（语音指令的降级手动路径，语义一致）。
 * @returns 无
 */
function quickNext(): void {
  goNextStep()
}

/**
 * 快捷指令 chips 上一步：复用 goPrevStep。
 * @returns 无
 */
function quickPrev(): void {
  goPrevStep()
}

/**
 * 快捷指令 chips 计时 5 分钟：跳计时器页并携带快捷时长（P-16 添加表单预填）。
 * @returns 无
 */
function quickTimer(): void {
  goRoute(`${ROUTES.COOK_TIMER}?session_id=${encodeURIComponent(sessionId.value)}&minutes=5`)
}

/* ═══ 底部操作条三入口 ═══ */

/**
 * 跳计时器页（带 session_id；MultiTimer 状态由 P-16 页面持久化维护）。
 * @returns 无
 */
function goTimer(): void {
  goRoute(`${ROUTES.COOK_TIMER}?session_id=${encodeURIComponent(sessionId.value)}`)
}

/**
 * 跳问厨娘页（带 session_id；求助链路与风控在 P-17 收口）。
 * @returns 无
 */
function goAsk(): void {
  goRoute(`${ROUTES.COOK_ASK}?session_id=${encodeURIComponent(sessionId.value)}`)
}

/**
 * 跳完成评分页（带 session_id；finish/放弃/评分在 P-18 收口，本页不重复上报）。
 * @returns 无
 */
function goFinish(): void {
  goRoute(`${ROUTES.COOK_FINISH}?session_id=${encodeURIComponent(sessionId.value)}`)
}

/**
 * 恢复失败态返回按钮：回上一页（推荐列表 / 菜谱详情）。
 * @returns 无
 */
function goBack(): void {
  uni.navigateBack({ fail: () => {} })
}

/* ═══ 生命周期 ═══ */

/**
 * onLoad：解析 session_id 并启动恢复；初始化网络状态监听（离线 OfflineBar 数据源）。
 * @param options 页面参数（session_id）
 * @returns 无
 * @throws 不抛出
 */
onLoad((options) => {
  sessionId.value = decodeURIComponent(options?.session_id ?? '')
  try {
    // 初始网络态 + 后续切换监听（离线提示条实时性）
    offline.value = false
    networkHandler = (res) => {
      offline.value = !res.isConnected
    }
    uni.onNetworkStatusChange(networkHandler)
    uni.getNetworkType({
      success: (res) => {
        offline.value = res.networkType === 'none'
      },
      fail: () => {},
    })
  } catch {
    // 平台不支持网络监听：静态降级（不提示离线）
  }
  void bootstrap()
})

// onShow：申请屏幕常亮（做菜过程锁屏会打断引导；替代源码 Wake Lock）
onShow(() => {
  setKeepScreenOn(true)
})

/**
 * onHide：关闭常亮 + flush 埋点缓冲 + 断点立即落库（防抖 PATCH 提前触发）。
 * @returns 无
 * @throws 不抛出
 */
onHide(() => {
  setKeepScreenOn(false)
  flushOnHide()
  if (phase.value === 'ready') void cooking.persistStep()
})

/**
 * onUnload：关闭常亮 + 解绑网络监听 + 断点立即落库（退出烹饪保留进度，
 * 对齐源码 onExit「确认后先把未落地的防抖 PATCH 立即落库」语义；
 * 完成/放弃的上报与清理由 P-18 负责，本页不额外上报）。
 * @returns 无
 * @throws 不抛出
 */
onUnload(() => {
  setKeepScreenOn(false)
  if (networkHandler) {
    try {
      uni.offNetworkStatusChange(networkHandler)
    } catch {
      // 平台不支持解绑：静默
    }
    networkHandler = null
  }
  if (phase.value === 'ready') void cooking.persistStep()
})
</script>

<template>
  <!-- 沉浸式烹饪专档：cooking-mode（≥64rpx）独立于用户字号设置 -->
  <view class="page cooking-mode" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <BaseNavbar :title="navTitle" back-confirm-text="确认退出烹饪？" />

    <!-- 离线提示条（有缓存内容可正常查看） -->
    <OfflineBar v-if="offline && phase !== 'failed'" />

    <!-- 恢复失败态：无会话缓存且无离线快照（OFFLINE_UNCACHED_TEXT 置灰提示，不转圈） -->
    <view v-if="phase === 'failed'" class="guide guide--failed">
      <ErrorState
        kind="network"
        :detail="`未找到进行中的烹饪会话。${OFFLINE_UNCACHED_TEXT}，请重新从菜谱发起烹饪`"
        retry-text="重新尝试"
        @retry="bootstrap"
      />
      <BaseButton block @click="goBack">返回</BaseButton>
    </view>

    <!-- 步骤数据缺失兜底：会话在但步骤快照为空 -->
    <view v-else-if="totalSteps === 0" class="guide guide--failed">
      <ErrorState kind="server" detail="步骤数据缺失，无法继续引导" retry-text="重新加载" @retry="bootstrap" />
      <BaseButton block @click="goBack">返回</BaseButton>
    </view>

    <!-- 主流程 -->
    <template v-else>
      <!-- 过敏原警示条：常驻顶部 + large 大字模式（五处生效之三） -->
      <AllergenAlertBar :allergens="allergens" large />

      <!-- 进度区 -->
      <view class="guide__progress">
        <view class="guide__progress-track">
          <view class="guide__progress-fill" :style="{ width: `${progressPercent}%` }" />
        </view>
        <text class="guide__progress-text">第 {{ currentStepNo }} 步 / 共 {{ totalSteps }} 步</text>
      </view>

      <!-- 主体大字步骤 -->
      <view class="guide__main">
        <text class="guide__step-no">第 {{ currentStep?.no ?? currentStepNo }} 步</text>
        <text class="guide__step-text">{{ currentStep?.description }}</text>
        <text v-if="scaledAmountHint" class="guide__amount">本步用量：{{ scaledAmountHint }}</text>
        <text class="guide__duration">预计耗时：{{ formatDuration(currentStep?.duration_sec ?? 0) }}</text>

        <!-- 新手要点 / 失败补救（折叠可展开，烹饪中大字少交互） -->
        <view v-if="currentStep?.tips || currentStep?.rescue" class="guide__tips">
          <view class="guide__tips-toggle" @click="tipsExpanded = !tipsExpanded">
            <text>新手要点 / 失败补救</text>
            <text class="guide__tips-arrow">{{ tipsExpanded ? '收起 ▲' : '展开 ▼' }}</text>
          </view>
          <view v-if="tipsExpanded" class="guide__tips-body">
            <text v-if="currentStep?.tips" class="guide__tip-line">要点：{{ currentStep.tips }}</text>
            <text v-if="currentStep?.rescue" class="guide__tip-line">失败补救：{{ currentStep.rescue }}</text>
          </view>
        </view>

        <!-- 份量切换（本地换算展示，不发请求——会话份数以创建时为准） -->
        <view class="guide__servings">
          <text class="guide__servings-label">份量</text>
          <BasePicker v-model="targetServings" :options="servingsOptions" placeholder="选择份量" />
        </view>
      </view>

      <!-- 步骤切换大热区按钮（≥120rpx，完全本地零网络） -->
      <view class="guide__steps">
        <view class="guide__step-btn" :class="{ 'is-disabled': currentStepNo <= 1 }" @click="goPrevStep">
          上一步
        </view>
        <view class="guide__step-btn is-primary" @click="onPrimaryAction">
          {{ isLast ? '去完成' : '下一步' }}
        </view>
      </view>

      <!-- 语音指令区：按住说话 + 手动快捷 chips（语音不阻断手动） -->
      <view class="guide__voice">
        <view
          class="guide__record"
          :class="{ 'is-recording': recording }"
          @longpress="onRecordStart"
          @touchend="onRecordEnd"
          @touchcancel="onRecordEnd"
        >
          {{ recording ? '松开结束…' : '按住说话' }}
        </view>
        <view class="guide__chips">
          <view class="guide__chip" @click="quickNext">下一步</view>
          <view class="guide__chip" @click="quickPrev">上一步</view>
          <view class="guide__chip" @click="quickTimer">计时 5 分钟</view>
        </view>
      </view>

      <!-- 底部操作条三入口 -->
      <view class="guide__footer">
        <view class="guide__footer-btn" @click="goTimer">计时器</view>
        <view class="guide__footer-btn" @click="goAsk">问厨娘</view>
        <view class="guide__footer-btn is-primary" @click="goFinish">完成烹饪</view>
      </view>

      <!-- 步骤列表弹层：全量步骤可点击跳转 -->
      <BaseDialog
        :visible="stepDrawerVisible"
        title="步骤列表"
        position="bottom"
        show-close
        @close="stepDrawerVisible = false"
      >
        <scroll-view scroll-y class="guide__drawer-scroll">
          <view
            v-for="step in stepList"
            :key="step.no"
            class="guide__drawer-step"
            :class="{ 'is-active': step.no === currentStepNo }"
            @click="onJump(step.no)"
          >
            <text class="guide__drawer-no">第 {{ step.no }} 步</text>
            <text class="guide__drawer-desc">{{ step.description }}</text>
          </view>
        </scroll-view>
      </BaseDialog>

      <!-- 麦克风权限引导：权限拒绝后展示（fallback 手动 chips 常驻可用） -->
      <PermissionGuide
        v-if="voiceGuideVisible"
        scope="microphone"
        fallback-text="需要麦克风权限进行语音指令，用于烹饪中免手操作"
      >
        <template #fallback>
          <view class="guide__chip guide__chip--wide" @click="voiceGuideVisible = false">
           不用语音，直接手动操作
          </view>
        </template>
      </PermissionGuide>
    </template>
  </view>
</template>

<style scoped lang="scss">
.guide {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-md);
  /* 底部操作条固定高度让位：留出安全区 + 操作条空间 */
  padding-bottom: calc(200rpx + env(safe-area-inset-bottom));

  &--failed {
    gap: var(--space-md);
  }
}

/* 进度区 */
.guide__progress {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.guide__progress-track {
  height: 14rpx;
  border-radius: 7rpx;
  background: var(--divider);
  overflow: hidden;
}

.guide__progress-fill {
  height: 100%;
  border-radius: 7rpx;
  background: var(--color-primary);
  transition: width 0.25s ease;
}

.guide__progress-text {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

/* 主体大字（cooking-mode 下 --font-size-base=64rpx） */
.guide__main {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.guide__step-no {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.guide__step-text {
  font-size: var(--font-size-base);
  font-weight: 700;
  line-height: 1.5;
  color: var(--text-primary);
}

.guide__amount {
  font-size: 40rpx;
  line-height: 1.5;
  color: var(--color-primary);
  font-weight: 600;
}

.guide__duration {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

/* 新手要点折叠区 */
.guide__tips {
  border-radius: var(--radius-card);
  border: 1rpx solid var(--border-color);
  background: var(--bg-card);
  overflow: hidden;
}

.guide__tips-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: var(--hit-min);
  padding: 0 var(--space-md);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.guide__tips-arrow {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.guide__tips-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-sm) var(--space-md) var(--space-md);
  border-top: 1rpx solid var(--divider);
}

.guide__tip-line {
  font-size: var(--font-size-sm);
  line-height: 1.7;
  color: var(--text-secondary);
}

/* 份量切换 */
.guide__servings {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.guide__servings-label {
  flex-shrink: 0;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

/* 步骤切换大热区按钮：≥120rpx（烹饪中手湿可命中） */
.guide__steps {
  display: flex;
  gap: var(--space-md);
}

.guide__step-btn {
  box-sizing: border-box;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120rpx;
  border-radius: var(--radius-ctrl);
  border: 2rpx solid var(--border-color);
  background: var(--bg-card);
  font-size: 40rpx;
  font-weight: 600;
  color: var(--text-primary);

  &.is-primary {
    background: var(--color-primary);
    border-color: var(--color-primary);
    color: #ffffff;
  }

  &.is-disabled {
    opacity: 0.4;
    pointer-events: none;
  }
}

/* 语音指令区 */
.guide__voice {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.guide__record {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120rpx;
  border-radius: var(--radius-ctrl);
  border: 2rpx dashed var(--color-primary);
  color: var(--color-primary);
  font-size: 40rpx;
  font-weight: 600;

  &.is-recording {
    background: var(--color-primary-weak);
  }
}

.guide__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.guide__chip {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--hit-min);
  padding: 0 var(--space-md);
  border-radius: 999rpx;
  border: 1rpx solid var(--border-color);
  background: var(--bg-card);
  font-size: var(--font-size-sm);
  color: var(--text-primary);

  &--wide {
    margin: var(--space-sm) auto 0;
  }
}

/* 底部操作条（fixed，三入口） */
.guide__footer {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md) calc(var(--space-sm) + env(safe-area-inset-bottom));
  background: var(--bg-page);
  border-top: 1rpx solid var(--divider);
  z-index: 10;
}

.guide__footer-btn {
  box-sizing: border-box;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--hit-min);
  border-radius: var(--radius-ctrl);
  border: 1rpx solid var(--border-color);
  background: var(--bg-card);
  font-size: var(--font-size-sm);
  color: var(--text-primary);

  &.is-primary {
    background: var(--color-primary);
    border-color: var(--color-primary);
    color: #ffffff;
  }
}

/* 步骤列表弹层内滚动区 */
.guide__drawer-scroll {
  max-height: 60vh;
}

.guide__drawer-step {
  display: flex;
  gap: var(--space-sm);
  padding: var(--space-sm) 0;
  border-bottom: 1rpx solid var(--divider);

  &.is-active .guide__drawer-desc {
    color: var(--color-primary);
    font-weight: 600;
  }
}

.guide__drawer-no {
  flex-shrink: 0;
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.guide__drawer-desc {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-primary);
}
</style>
