<script setup lang="ts">
/**
 * 视图职责：W-04 分步引导页（灶台大字，对齐 UI 清单 W-04 行）。
 * 区块：① 顶部：过敏原警示条（会话 allergen_conflict 时）+「退出」按钮（二次确认）
 *       ② 进度：el-progress + 「第 X 步 / 共 Y 步」
 *       ③ 主体大字：步骤描述 ≥32px（cook-step-text）+ 本步用量提示 ≥20px + 预计耗时
 *       ④ 新手要点区：key_point + failure_tips（折叠可展开）
 *       ⑤ 底部操作：「上一步」「下一步」大按钮（纯本地切换 ≤300ms；store 更新 +
 *          800ms 防抖静默 PATCH）；第一步禁用上一步；最后一步「下一步」变「完成」
 *       ⑥「步骤列表」按钮 → el-drawer 全量步骤可点击跳转。
 * Task 9 增强：
 *       ⑦ 多路计时器（右下抽屉，≥3 路并行倒计时，本地 MultiTimer 实现，
 *          归零 el-notification 提示，不依赖网络）；
 *       ⑧ 屏幕常亮（Wake Lock API：进入页面申请、离开/隐藏释放，try/catch 静默降级）；
 *       ⑨「求助」按钮（弹窗输入问题 → POST /v1/cooking/sessions/{id}/help →
 *          三态展示：回答列表 / 拦截话术 / 429 当日超限提示）。
 * Task 6b 修复：
 *       ⑩ R5/L4 完成态落地：最后一步「完成」后停留本页展示收尾面板（恭喜完成 +
 *          本次菜谱名 + 「再做一次 / 返回首页 / 查看营养」），不再直接跳回 /select；
 *          结束会话的后端调用（finishCookingSession）保持不变。
 *       ⑪ R7/L3-3 计时器抽屉关闭修复：Element Plus 内置关闭按钮为无名称图标按钮
 *          （仅 SVG、无 aria-label，可点击区域极小），自动化测试按可访问性快照
 *          无法按名称定位/命中，表现为「点击关闭无效、JS 直调可关」；改为自定义
 *          header + aria-label="关闭此对话框" 的显式按钮，并 append-to-body 置顶
 *          弹层（详见模板处注释）。
 * 断点续做恢复策略：内存 store（同会话 id 直接复用）→ localStorage
 * cook_session_{id}（会话实体）+ cook_steps_{id}（步骤快照与步骤号）→ IndexedDB
 * 离线快照（F 模块：会话建立成功时写入，恢复失败时回退渲染，顶部提示离线模式）→
 * 都无则提示并回 /select（endpoints 无「查询会话」GET 接口，阶段一不做远端兜底）。
 * F 模块新增：
 *       ⑫ 离线可读（NFR-3.6）：进入引导保存菜谱快照到 IndexedDB（utils/offlineCache），
 *          断点恢复失败时回退本地快照渲染步骤，不依赖网络；
 *       ⑬ 免手语音（PRD US-F4）：Web Speech API 指令白名单本地解析（utils/voiceCommand），
 *          「下一步/上一步/暂停/继续」映射到既有切换与计时器处理函数。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import { Mic as MicIcon, Timer as TimerIcon } from '@element-plus/icons-vue'
import { finishCookingSession, getRecipe, postCookingHelp } from '@/api/endpoints'
import type { ApiError, RecipeStep } from '@/api/types'
import { useCookingStore } from '@/stores/cooking'
import { MultiTimer, formatCountdown, type TimerSnapshot } from '@/utils/timer'
import { scaleStepHint } from '@/utils/scaling'
import {
  getRecipeSnapshot,
  recallSessionRecipe,
  rememberSessionRecipe,
  saveRecipeSnapshot,
  type RecipeSnapshot,
} from '@/utils/offlineCache'
import {
  createVoiceCommandController,
  type VoiceCommand,
  type VoiceCommandError,
} from '@/utils/voiceCommand'
import AllergenAlertBar from '@/components/AllergenAlertBar.vue'

/** 路由（取 :sessionId 与退出/完成跳转） */
const route = useRoute()
const router = useRouter()
/** 烹饪 store：会话 / 本地步骤索引 / 本地切换动作 */
const cookingStore = useCookingStore()

/** 会话恢复失败标记（内存与本地缓存均无 → 提示后回 /select） */
const restoreFailed = ref(false)
/** 「完成」请求进行中 */
const finishing = ref(false)
/** 步骤列表抽屉可见性 */
const drawerVisible = ref(false)

/* ═══ F 模块 ⑫：离线可读（IndexedDB 快照兜底） ═══ */

/** 离线模式标记（true = 断点恢复失败后已回退本地快照渲染） */
const offlineMode = ref(false)
/** 离线快照（steps 为渲染数据源，title 供提示条展示） */
const offlineSnapshot = ref<RecipeSnapshot | null>(null)
/** 离线模式当前步骤号（纯本地切换，1 起） */
const offlineStepNo = ref(1)

/** 当前步骤对象（离线态取快照，在线取 store getter） */
const currentStep = computed<RecipeStep | null>(() => {
  if (offlineMode.value) {
    return offlineSnapshot.value?.steps[offlineStepNo.value - 1] ?? null
  }
  return cookingStore.currentStep
})

/** 当前步骤序号（离线态取本地游标，在线取 store） */
const currentStepNo = computed<number>(() =>
  offlineMode.value ? offlineStepNo.value : cookingStore.currentStepNo,
)

/** 步骤总数（离线态取快照长度，在线取 store） */
const totalSteps = computed<number>(() =>
  offlineMode.value ? (offlineSnapshot.value?.steps.length ?? 0) : cookingStore.totalSteps,
)

/** 全量步骤列表（步骤列表抽屉渲染；离线态取快照） */
const stepList = computed<RecipeStep[]>(() =>
  offlineMode.value ? (offlineSnapshot.value?.steps ?? []) : cookingStore.steps,
)

/** 底部主按钮文案（离线态无会话可结束，最后一步仍是「下一步」） */
const primaryLabel = computed<string>(() => (!offlineMode.value && isLast.value ? '完成' : '下一步'))

/** 是否最后一步（「下一步」变「完成」） */
const isLast = computed(
  () => totalSteps.value > 0 && currentStepNo.value >= totalSteps.value,
)

/** 进度百分比 = 当前步 / 总步数 */
const progressPercent = computed(() => {
  if (totalSteps.value === 0) return 0
  return Math.round((currentStepNo.value / totalSteps.value) * 100)
})

/**
 * 本步用量缩放系数（M3/R3 修复：本步用量随会话份数缩放）。
 * = 会话份数 / 菜谱基准份数；基准份数缺失/非法时以会话份数兜底（系数 1 = 不缩放）。
 * 离线态无会话份数，固定系数 1（按基准份数原样展示，不误缩放）。
 * @returns 缩放系数
 */
const hintFactor = computed<number>(() => {
  if (offlineMode.value) return 1
  const sessionServings = cookingStore.session?.servings ?? 1
  const base = cookingStore.baseServings || sessionServings
  if (!base || base < 1) return 1
  return sessionServings / base
})

/**
 * 当前步骤缩放后的本步用量提示（响应式：随当前步骤与份数联动重算）。
 * @returns 缩放后的提示文案；无提示返回空串
 */
const scaledAmountHint = computed<string>(() =>
  scaleStepHint(currentStep.value?.amount_hint, hintFactor.value),
)

/**
 * 秒数转可读耗时（步骤展示）。
 * @param sec 耗时秒数（0 表示无需等待）
 * @returns 可读文案
 */
function formatDuration(sec: number): string {
  if (!sec || sec <= 0) return '无需等待'
  if (sec < 60) return `${sec} 秒`
  return `约 ${Math.round(sec / 60)} 分钟`
}

/**
 * 退出烹饪引导：ElMessageBox 二次确认（进度保留在会话与本地缓存）。
 * 确认后先把未落地的防抖 PATCH 立即落库，再回食材选择页。
 * @returns 无
 */
function onExit(): void {
  ElMessageBox.confirm('退出后进度将保留，确认退出？', '退出烹饪引导', {
    confirmButtonText: '确认退出',
    cancelButtonText: '继续做菜',
    type: 'warning',
  })
    .then(() => {
      // 将防抖中的断点立即落库，保证下次断点续做准确
      void cookingStore.persistStep()
      void router.push('/select')
    })
    .catch(() => {
      // 用户取消：继续做菜，无操作
    })
}

/** ═══ R5/L4 完成态落地 ═══ */

/** 完成态标记：true = 展示本页收尾面板（不再直接跳回 /select） */
const finished = ref(false)

/** 「再做一次」重建会话请求进行中 */
const restarting = ref(false)

/**
 * 完成态快照：完成面板展示与「再做一次」所需数据。
 * 在 clearSession 清空 store 前保存（菜名需临时拉取菜谱详情补齐）。
 */
const finishedInfo = ref<{
  /** 关联菜谱 ID（「再做一次」重建会话 /「查看营养」跳详情页用） */
  recipeId: number
  /** 菜谱名（详情拉取失败时模板兜底「本次菜谱」） */
  title: string
  /** 本次份数（再做一次沿用） */
  servings: number
  /** 步骤快照（再做一次重建会话的步骤数据源） */
  steps: RecipeStep[]
  /** 菜谱基准份数（再做一次沿用，保证用量缩放系数一致） */
  baseServings: number
} | null>(null)

/**
 * 完成面板副标题（菜名 + 份数）。
 * @returns 形如「本次完成：番茄炒蛋（2 份）」；无快照返回空串
 */
const finishSubTitle = computed<string>(() => {
  const info = finishedInfo.value
  if (!info) return ''
  return `本次完成：${info.title || '本次菜谱'}（${info.servings} 份）`
})

/**
 * 是否允许「再做一次」（步骤快照存在才可重建会话，异常空快照时按钮禁用兜底）。
 * @returns 可重建返回 true
 */
const canRestart = computed<boolean>(() => (finishedInfo.value?.steps.length ?? 0) > 0)

/**
 * 最后一步点「完成」：调 finishCookingSession 结束会话（完成记录照旧落库）→
 * 保存完成态快照（并行拉取菜名，失败不阻塞）→ 清理本地缓存与 store →
 * 停留本页进入完成态面板（R5/L4：不再直接 push('/select')）。
 * @returns 无
 * @throws finishCookingSession 失败时以 ElMessage 提示并保持当前步骤
 */
async function onFinish(): Promise<void> {
  if (!cookingStore.session || finishing.value) return
  finishing.value = true
  const session = cookingStore.session
  try {
    // 并行：结束会话（后端完成记录）+ 拉取菜名（完成面板展示用；失败兜底空串不阻塞完成流程）
    const [, detail] = await Promise.all([
      finishCookingSession(session.id),
      getRecipe(session.recipe_id).catch(() => null),
    ])
    ElMessage.success('做菜完成')
    // clearSession 会清空 store，完成面板与「再做一次」所需数据先落快照
    //（steps 为引用替换式清空，此处保存的旧数组引用内容不受影响）
    finishedInfo.value = {
      recipeId: session.recipe_id,
      title: detail?.title ?? '',
      servings: session.servings ?? 1,
      steps: cookingStore.steps,
      baseServings: cookingStore.baseServings,
    }
    cookingStore.clearSession()
    finished.value = true
  } catch (e) {
    ElMessage.error((e as ApiError).message || '完成失败，请重试')
  } finally {
    finishing.value = false
  }
}

/**
 * 完成态「再做一次」：以本次份数/步骤快照重新创建烹饪会话（后端新会话从步骤 1 开始），
 * 成功后退出完成态并 replace 到新会话地址（刷新后仍可断点续做）。
 * @returns 无
 * @throws startSession 失败时以 ElMessage 提示，保持完成态面板
 */
async function onCookAgain(): Promise<void> {
  const info = finishedInfo.value
  if (!info || restarting.value) return
  restarting.value = true
  try {
    await cookingStore.startSession(info.recipeId, info.servings, info.steps, info.baseServings)
    finished.value = false
    finishedInfo.value = null
    // 新会话建立成功：同步刷新离线快照与 sessionId 映射（fire-and-forget，失败不影响引导）
    void saveOfflineSnapshot()
    void router.replace(`/cook/${cookingStore.session?.id ?? ''}`)
  } catch (e) {
    ElMessage.error((e as ApiError).message || '重新开始失败，请重试')
  } finally {
    restarting.value = false
  }
}

/**
 * 完成态「返回首页」：跳转首页（/）。
 * @returns 无
 */
function goHome(): void {
  void router.push('/')
}

/**
 * 完成态「查看营养」：跳转本菜谱详情页（营养估算入口在详情页内，一步可达的最小路径）。
 * @returns 无
 */
function goNutrition(): void {
  const id = finishedInfo.value?.recipeId
  if (id != null) void router.push(`/recipe/${id}`)
}

/**
 * 推进到下一步（在线走 store 本地切换；离线态走快照游标）。
 * 语音「下一步」也复用此函数：不触发「完成」，避免误结束会话。
 * @returns 无
 */
function goNextStep(): void {
  if (offlineMode.value) {
    if (offlineStepNo.value < totalSteps.value) offlineStepNo.value += 1
    return
  }
  if (!isLast.value) void cookingStore.next()
}

/**
 * 回退到上一步（在线走 store 本地切换；离线态走快照游标）。
 * @returns 无
 */
function goPrevStep(): void {
  if (offlineMode.value) {
    if (currentStepNo.value > 1) offlineStepNo.value -= 1
    return
  }
  void cookingStore.prev()
}

/**
 * 底部主按钮点击：非最后一步 → 本地下一步；最后一步（在线会话）→ 完成会话。
 * 离线态无会话可结束，始终走本地推进。
 * @returns 无
 */
function onPrimaryAction(): void {
  if (!offlineMode.value && isLast.value) {
    void onFinish()
  } else {
    goNextStep()
  }
}

/**
 * 步骤列表抽屉点击跳转（在线：本地切换 + 防抖持久化；离线：快照游标收敛）。
 * @param no 目标步骤序号
 * @returns 无
 */
function onJump(no: number): void {
  drawerVisible.value = false
  if (offlineMode.value) {
    offlineStepNo.value = Math.min(Math.max(no, 1), Math.max(totalSteps.value, 1))
    return
  }
  void cookingStore.jumpTo(no)
}

/**
 * 恢复失败后的返回动作：回食材选择页。
 * @returns 无
 */
function goSelect(): void {
  void router.push('/select')
}

/* ═══ Task 9 增强 ⑦：多路计时器 ═══ */

/** 计时器抽屉可见性 */
const timerDrawerVisible = ref(false)
/** 全部计时器快照（onChange 同步，供渲染） */
const timerList = ref<TimerSnapshot[]>([])
/** 多路计时器实例（非响应式，状态经 onChange 同步到 timerList） */
const multiTimer = new MultiTimer((event) => {
  timerList.value = event.timers
  if (event.type === 'finish' && event.id != null) {
    const t = event.timers.find((x) => x.id === event.id)
    ElNotification({
      title: '计时结束',
      message: `「${t?.name ?? '计时器'}」时间到了，看看锅里的情况`,
      type: 'warning',
      duration: 8000,
    })
  }
})

/** 新计时器名称 */
const newTimerName = ref('')
/** 新计时器分钟数 */
const newTimerMinutes = ref(5)
/** 快捷预设（常用烹饪时长，≥3 路并行的典型场景） */
const QUICK_PRESETS: Array<{ name: string; minutes: number }> = [
  { name: '焯水', minutes: 1 },
  { name: '煎制', minutes: 3 },
  { name: '炖煮', minutes: 5 },
  { name: '焖煮', minutes: 8 },
  { name: '蒸制', minutes: 10 },
]
/** 是否有运行中计时（底部按钮角标） */
const hasRunningTimer = computed(() => timerList.value.some((t) => t.status === 'running'))

/**
 * 打开计时器抽屉。
 * @returns 无
 */
function openTimerDrawer(): void {
  timerDrawerVisible.value = true
}

/**
 * 新增一路计时（抽屉表单：名称 + 分钟数）。
 * @returns 无
 */
function addTimer(): void {
  const minutes = Number(newTimerMinutes.value)
  if (!Number.isFinite(minutes) || minutes <= 0 || minutes > 180) {
    ElMessage.warning('请输入 1~180 分钟之间的时长')
    return
  }
  const name = newTimerName.value.trim() || `计时 ${multiTimer.list().length + 1}`
  multiTimer.start(name, minutes * 60)
  newTimerName.value = ''
  newTimerMinutes.value = 5
}

/**
 * 新增快捷预设计时。
 * @param preset 预设项
 * @returns 无
 */
function addPreset(preset: { name: string; minutes: number }): void {
  multiTimer.start(`${preset.name} ${preset.minutes} 分钟`, preset.minutes * 60)
}

/**
 * 暂停某路计时。
 * @param id 计时器 ID
 * @returns 无
 */
function pauseTimer(id: number): void {
  multiTimer.pause(id)
}

/**
 * 恢复某路计时。
 * @param id 计时器 ID
 * @returns 无
 */
function resumeTimer(id: number): void {
  multiTimer.resume(id)
}

/**
 * 重置某路计时（回满量）。
 * @param id 计时器 ID
 * @returns 无
 */
function resetTimer(id: number): void {
  multiTimer.reset(id)
}

/**
 * 移除某路计时。
 * @param id 计时器 ID
 * @returns 无
 */
function clearTimer(id: number): void {
  multiTimer.clear(id)
}

/* ═══ Task 9 增强 ⑧：屏幕常亮（Wake Lock API）═══ */

/** Wake Lock 能力的最小类型视图（规避 lib.dom 版本差异，运行时特性检测） */
interface WakeLockSentinelLike {
  released: boolean
  release: () => Promise<void>
}
type NavigatorWithWakeLock = Navigator & {
  wakeLock?: { request: (type: 'screen') => Promise<WakeLockSentinelLike> }
}

/** 当前持有的 Wake Lock 句柄（null = 未持有/不支持） */
let wakeLockSentinel: WakeLockSentinelLike | null = null

/**
 * 申请屏幕常亮（try/catch 静默降级：不支持/被拒均不影响烹饪流程）。
 * @returns 无
 */
async function requestWakeLock(): Promise<void> {
  try {
    const nav = navigator as NavigatorWithWakeLock
    if (!nav.wakeLock || wakeLockSentinel) return
    wakeLockSentinel = await nav.wakeLock.request('screen')
  } catch {
    // 不支持或用户拒绝：静默降级，不提示打断做菜
    wakeLockSentinel = null
  }
}

/**
 * 释放屏幕常亮（页面离开/隐藏时调用）。
 * @returns 无
 */
async function releaseWakeLock(): Promise<void> {
  try {
    await wakeLockSentinel?.release()
  } catch {
    // 释放失败无需处理
  } finally {
    wakeLockSentinel = null
  }
}

/**
 * 页面可见性恢复时重新申请（系统在后台会自动释放 Wake Lock）。
 * @returns 无
 */
function onVisibilityChange(): void {
  if (document.visibilityState === 'visible') {
    void requestWakeLock()
  }
}

/* ═══ F 模块 ⑫：离线可读（IndexedDB 快照，NFR-3.6） ═══ */

/**
 * 保存当前菜谱离线快照（会话建立成功时调用：进入引导 / 「再做一次」重建会话）。
 * 并行写 sessionId→recipeId 映射（恢复失败反查用）；菜名异步补齐，拉取失败以
 * 空串兜底仍保存步骤（离线可读的核心是步骤，菜名仅为提示条展示增强）。
 * @returns 无
 * @throws 不抛出（offlineCache 内部静默降级，保存失败不影响在线烹饪流程）
 */
async function saveOfflineSnapshot(): Promise<void> {
  const session = cookingStore.session
  if (!session || cookingStore.steps.length === 0) return
  rememberSessionRecipe(session.id, session.recipe_id)
  const title = await getRecipe(session.recipe_id)
    .then((detail) => detail.title)
    .catch(() => '')
  await saveRecipeSnapshot({
    recipe_id: session.recipe_id,
    title,
    steps: cookingStore.steps,
    base_servings: cookingStore.baseServings,
    session_id: session.id,
  })
}

/**
 * 断点恢复失败时的离线兜底：经 sessionId 映射反查 recipeId → 读取 IndexedDB
 * 快照 → 成功则进入离线模式（渲染本地缓存步骤，不依赖网络与会话）。
 * @param sessionId 路由中的会话 ID
 * @returns 兜底成功返回 true（offlineMode 已置位）；映射/快照缺失返回 false
 * @throws 不抛出（getRecipeSnapshot 内部静默降级）
 */
async function tryOfflineRestore(sessionId: string): Promise<boolean> {
  const recipeId = recallSessionRecipe(sessionId)
  if (recipeId == null) return false
  const snapshot = await getRecipeSnapshot(recipeId)
  if (!snapshot || snapshot.steps.length === 0) return false
  offlineSnapshot.value = snapshot
  offlineStepNo.value = 1
  offlineMode.value = true
  return true
}

/* ═══ F 模块 ⑬：免手语音（PRD US-F4，白名单本地解析） ═══ */

/** 语音开关状态（true = 正在监听麦克风） */
const voiceOn = ref(false)

/**
 * 暂停全部运行中的计时器（语音 timer_pause 落点，复用单路暂停函数）。
 * @returns 无
 */
function pauseAllTimers(): void {
  for (const t of timerList.value) {
    if (t.status === 'running') pauseTimer(t.id)
  }
}

/**
 * 恢复全部已暂停的计时器（语音 timer_resume 落点，复用单路恢复函数）。
 * @returns 无
 */
function resumeAllTimers(): void {
  for (const t of timerList.value) {
    if (t.status === 'paused') resumeTimer(t.id)
  }
}

/**
 * 语音指令分发：映射到既有动作函数（步骤切换 / 计时器暂停恢复），不重复实现。
 * @param command 白名单命中的指令
 * @returns 无
 */
function handleVoiceCommand(command: VoiceCommand): void {
  switch (command) {
    case 'next':
      goNextStep()
      break
    case 'prev':
      goPrevStep()
      break
    case 'timer_pause':
      pauseAllTimers()
      break
    case 'timer_resume':
      resumeAllTimers()
      break
  }
}

/**
 * 语音识别错误处理（经 onError 回调进入，不抛出）：
 * no-speech/aborted（没说话/主动停止）静默；权限类错误关闭开关并提示；其余轻提示。
 * @param error 错误对象（原生错误码 + 中文说明）
 * @returns 无
 */
function onVoiceError(error: VoiceCommandError): void {
  if (error.code === 'no-speech' || error.code === 'aborted') return
  if (error.code === 'not-allowed' || error.code === 'service-not-allowed') {
    voiceOn.value = false
    ElMessage.warning(error.message)
    return
  }
  ElMessage.warning(`语音识别异常：${error.message}`)
}

/** 语音控制器实例（识别 → 白名单解析 → handleVoiceCommand 分发） */
const voiceController = createVoiceCommandController({
  onCommand: handleVoiceCommand,
  onError: onVoiceError,
})

/**
 * 切换语音控制开关：开启开始识别监听，关闭停止；浏览器不支持时一次性提示。
 * @returns 无
 */
function toggleVoice(): void {
  if (!voiceController.supported) {
    ElMessage.info('当前浏览器不支持语音控制')
    return
  }
  if (voiceOn.value) {
    voiceController.stop()
    voiceOn.value = false
    return
  }
  voiceController.start()
  voiceOn.value = true
}

/* ═══ Task 9 增强 ⑨：烹饪求助 ═══ */

/** 求助弹窗可见性 */
const helpVisible = ref(false)
/** 求助问题输入 */
const helpQuestion = ref('')
/** 求助请求进行中 */
const helpLoading = ref(false)
/** 求助展示态：idle 输入 / answers 回答列表 / blocked 拦截话术 / limit 当日超限 */
const helpState = ref<'idle' | 'answers' | 'blocked' | 'limit'>('idle')
/** 回答列表 */
const helpAnswers = ref<string[]>([])
/** 拦截话术（blocked 时） */
const helpBlockedMessage = ref('')

/**
 * 打开求助弹窗（重置为输入态）。
 * @returns 无
 */
function openHelp(): void {
  helpQuestion.value = ''
  helpState.value = 'idle'
  helpAnswers.value = []
  helpBlockedMessage.value = ''
  helpVisible.value = true
}

/**
 * 提交求助：POST /v1/cooking/sessions/{id}/help。
 * - 正常 → 回答列表态；
 * - 返回体带 blocked → 拦截话术态；
 * - 429（当日超限）→ 超限提示态；其余错误 → ElMessage。
 * @returns 无
 */
async function onHelpSubmit(): Promise<void> {
  const question = helpQuestion.value.trim()
  if (!question || !cookingStore.session) return
  helpLoading.value = true
  try {
    const res = await postCookingHelp(cookingStore.session.id, question)
    if ('blocked' in res && res.blocked) {
      helpBlockedMessage.value = res.message ?? res.title ?? '该问题未通过安全检查，请换一种问法'
      helpState.value = 'blocked'
      return
    }
    helpAnswers.value = 'answers' in res ? (res.answers ?? []) : []
    helpState.value = 'answers'
  } catch (e) {
    const err = e as ApiError
    if (err.code === 429) {
      helpState.value = 'limit'
    } else {
      ElMessage.error(err.message || '求助失败，请重试')
    }
  } finally {
    helpLoading.value = false
  }
}

// 挂载即恢复会话：内存 store → 本地缓存 → IndexedDB 离线快照（离线可读兜底）；
// 全部无则提示并回 /select。恢复成功同步申请屏幕常亮（做菜过程锁屏会打断引导），
// 并把当前菜谱快照写入 IndexedDB（F 模块 ⑫，fire-and-forget 失败不影响在线逻辑）。
onMounted(() => {
  const sessionId = route.params.sessionId as string
  const restored = cookingStore.restoreById(sessionId)
  if (restored) {
    void saveOfflineSnapshot()
    void requestWakeLock()
    document.addEventListener('visibilitychange', onVisibilityChange)
    return
  }
  // 内存与 localStorage 均无 → 尝试 IndexedDB 离线快照兜底（断网/缓存被清时仍可读步骤）
  void tryOfflineRestore(sessionId).then((ok) => {
    if (ok) return
    restoreFailed.value = true
    ElMessage.warning('未找到进行中的烹饪会话，请重新从菜谱发起')
    void router.replace('/select')
  })
})

// 卸载：释放 Wake Lock、停掉全部计时器、停止语音识别、解绑可见性监听
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  void releaseWakeLock()
  multiTimer.clearAll()
  voiceController.stop()
})
</script>

<template>
  <section class="page-card cook-page">
    <!-- 恢复失败兜底（通常已被 replace 离开） -->
    <el-empty v-if="restoreFailed" description="会话不存在或已结束">
      <el-button type="primary" @click="goSelect">返回选食材</el-button>
    </el-empty>

    <!-- ⑩ R5/L4 完成态落地：完成后停留本页展示收尾面板（注意分支顺序必须位于
         totalSteps === 0 兜底之前——完成时 store 已清空，totalSteps 为 0） -->
    <div v-else-if="finished" class="cook-finish">
      <el-result icon="success" title="恭喜，这道菜完成了！" :sub-title="finishSubTitle">
        <template #extra>
          <el-button
            type="primary"
            size="large"
            class="cook-finish-btn"
            :loading="restarting"
            :disabled="!canRestart"
            @click="onCookAgain"
          >
            再做一次
          </el-button>
          <el-button size="large" class="cook-finish-btn" @click="goHome">返回首页</el-button>
          <el-button size="large" class="cook-finish-btn" @click="goNutrition">查看营养</el-button>
        </template>
      </el-result>
    </div>

    <!-- 步骤数据缺失兜底：会话在但步骤快照为空（离线兜底成功时快照必有步骤，不触发） -->
    <el-empty v-else-if="totalSteps === 0" description="步骤数据缺失，无法继续引导">
      <el-button type="primary" @click="goSelect">返回选食材</el-button>
    </el-empty>

    <template v-else>
      <!-- ⑫ 离线模式顶部提示：断点恢复失败、由 IndexedDB 快照渲染 -->
      <el-alert
        v-if="offlineMode"
        class="cook-offline-alert"
        type="warning"
        :closable="false"
        show-icon
        title="离线模式：显示本地缓存的步骤"
      />

      <!-- ① 顶部：过敏原警示条（冲突时）+ 语音开关 + 退出 -->
      <div class="cook-top">
        <div class="cook-alert-slot">
          <AllergenAlertBar
            :allergens="cookingStore.session?.allergen_conflict ?? []"
            conflict
          />
        </div>
        <div class="cook-top-actions">
          <!-- ⑬ 免手语音开关：开启监听麦克风，白名单指令驱动翻步/计时 -->
          <el-button
            class="cook-voice"
            size="large"
            :type="voiceOn ? 'primary' : 'default'"
            @click="toggleVoice"
          >
            <el-icon class="cook-btn-icon"><MicIcon /></el-icon>
            {{ voiceOn ? '语音开' : '语音关' }}
          </el-button>
          <el-button class="cook-exit" size="large" @click="onExit">退出</el-button>
        </div>
      </div>

      <!-- ② 进度：百分比 + 第 X 步 / 共 Y 步 -->
      <div class="cook-progress">
        <el-progress
          class="cook-progress-bar"
          :percentage="progressPercent"
          :stroke-width="14"
          :format="() => `${progressPercent}%`"
        />
        <span class="cook-progress-text">第 {{ currentStepNo }} 步 / 共 {{ totalSteps }} 步</span>
      </div>

      <!-- ③ 主体大字步骤 -->
      <div class="cook-main">
        <p class="cook-step-no">第 {{ currentStep?.no }} 步</p>
        <!-- 大字 ≥32px：灶台 50cm 可读 -->
        <p class="cook-step-text">{{ currentStep?.description }}</p>
        <!-- 本步用量提示 ≥20px（已按会话份数缩放） -->
        <p v-if="currentStep?.amount_hint" class="cook-amount-hint">
          本步用量：{{ scaledAmountHint }}
        </p>
        <p class="cook-duration">⏱ 预计耗时：{{ formatDuration(currentStep?.duration_sec ?? 0) }}</p>

        <!-- ④ 新手要点区：要点 + 失败补救（折叠可展开） -->
        <el-collapse v-if="currentStep?.tips || currentStep?.rescue" class="cook-tips">
          <el-collapse-item title="新手要点 / 失败补救" name="tips">
            <p v-if="currentStep?.tips" class="cook-tip-line">要点：{{ currentStep.tips }}</p>
            <p v-if="currentStep?.rescue" class="cook-tip-line">失败补救：{{ currentStep.rescue }}</p>
          </el-collapse-item>
        </el-collapse>
      </div>

      <!-- ⑤ 底部操作：上一步 / 下一步（本地切换；离线态走快照游标）+ 计时器 / 求助 / 步骤列表 -->
      <div class="cook-actions">
        <el-button
          class="cook-btn"
          size="large"
          :disabled="currentStepNo <= 1"
          @click="goPrevStep"
        >
          上一步
        </el-button>
        <el-button
          class="cook-btn cook-btn--primary"
          type="primary"
          size="large"
          :loading="finishing"
          @click="onPrimaryAction"
        >
          {{ primaryLabel }}
        </el-button>
        <el-button class="cook-btn" size="large" @click="openTimerDrawer">
          <el-icon v-if="hasRunningTimer" class="cook-btn-icon"><TimerIcon /></el-icon>
          计时器
        </el-button>
        <el-button class="cook-btn" size="large" @click="openHelp">求助</el-button>
        <el-button class="cook-btn" size="large" @click="drawerVisible = true">步骤列表</el-button>
      </div>

      <!-- ⑥ 步骤列表抽屉：全量步骤可点击跳转（离线态渲染快照步骤） -->
      <el-drawer v-model="drawerVisible" title="步骤列表" size="380px">
        <div
          v-for="step in stepList"
          :key="step.no"
          class="drawer-step"
          :class="{ 'drawer-step--active': step.no === currentStepNo }"
          role="button"
          @click="onJump(step.no)"
        >
          <span class="drawer-step-no">第 {{ step.no }} 步</span>
          <span class="drawer-step-desc">{{ step.description }}</span>
        </div>
      </el-drawer>

      <!-- ⑦ 多路计时器抽屉（右下，≥3 路并行倒计时）
           R7/L3-3 修复说明：
           根因 —— Element Plus 内置关闭按钮（.el-drawer__close-btn）内部仅有 SVG 图标，
           无 aria-label / 无文本，可访问名称为空且可点击区域只有右上角小图标；自动化
           测试依赖可访问性快照按名称定位控件，无法命中该按钮，表现为「两次点击无效、
           弹窗仍在前台（JS 直调可关闭）」。事件绑定与 v-model 链路本身正常（JS 直调
           可关即证明），属可访问命名/命中区域缺陷，与 L3-1 同族。
           修复 —— ① :show-close="false" 移除内置无名按钮，避免双关闭控件混淆定位；
           ② 自定义 #header 放显式「关闭」按钮并标注 aria-label="关闭此对话框"，
           直绑 timerDrawerVisible=false，首次点击即关闭；③ append-to-body 将弹层
           teleport 到 body 顶层，规避宿主容器层叠上下文对遮罩与命中的干扰。 -->
      <el-drawer
        v-model="timerDrawerVisible"
        title="并行计时器"
        size="380px"
        direction="rtl"
        append-to-body
        :show-close="false"
      >
        <!-- 自定义 header：标题 + 具名关闭按钮（aria-label 供自动化/读屏精准定位） -->
        <template #header>
          <div class="timer-header">
            <span class="timer-header-title">并行计时器</span>
            <el-button text aria-label="关闭此对话框" @click="timerDrawerVisible = false">
              关闭
            </el-button>
          </div>
        </template>

        <!-- 快捷预设 -->
        <p class="timer-label">快捷计时：</p>
        <div class="timer-presets">
          <el-button
            v-for="p in QUICK_PRESETS"
            :key="p.name"
            size="small"
            @click="addPreset(p)"
          >
            {{ p.name }} {{ p.minutes }} 分钟
          </el-button>
        </div>

        <!-- 自定义计时 -->
        <div class="timer-form">
          <el-input v-model="newTimerName" size="small" maxlength="12" placeholder="名称（可选）" class="timer-name" />
          <el-input-number v-model="newTimerMinutes" :min="1" :max="180" size="small" controls-position="right" class="timer-min" />
          <span class="timer-unit">分钟</span>
          <el-button type="primary" size="small" @click="addTimer">开始</el-button>
        </div>

        <el-divider />

        <!-- 计时列表 -->
        <el-empty v-if="timerList.length === 0" description="还没有计时，先加一路" :image-size="64" />
        <div v-else class="timer-list">
          <div
            v-for="t in timerList"
            :key="t.id"
            class="timer-item"
            :class="{ 'timer-item--done': t.status === 'finished' }"
          >
            <div class="timer-head">
              <span class="timer-name">{{ t.name }}</span>
              <el-tag size="small" :type="t.status === 'finished' ? 'danger' : t.status === 'paused' ? 'info' : 'success'">
                {{ t.status === 'finished' ? '已结束' : t.status === 'paused' ? '已暂停' : '计时中' }}
              </el-tag>
            </div>
            <p class="timer-remaining" :class="{ 'timer-remaining--done': t.status === 'finished' }">
              {{ formatCountdown(t.remainingSec) }}
            </p>
            <div class="timer-actions">
              <el-button v-if="t.status === 'running'" size="small" @click="pauseTimer(t.id)">暂停</el-button>
              <el-button v-if="t.status === 'paused'" size="small" type="primary" @click="resumeTimer(t.id)">继续</el-button>
              <el-button size="small" @click="resetTimer(t.id)">重置</el-button>
              <el-button size="small" type="danger" plain @click="clearTimer(t.id)">移除</el-button>
            </div>
          </div>
        </div>
      </el-drawer>

      <!-- ⑨ 求助弹窗：输入 → 回答列表 / 拦截话术 / 超限提示 三态 -->
      <el-dialog v-model="helpVisible" title="做菜求助" width="440px" align-center>
        <!-- 输入态 -->
        <el-input
          v-if="helpState === 'idle'"
          v-model="helpQuestion"
          type="textarea"
          :rows="3"
          maxlength="100"
          placeholder="卡住了？问问厨娘，如：糖色炒苦了还能救吗"
        />

        <!-- 回答列表态 -->
        <div v-else-if="helpState === 'answers'" class="help-answers">
          <p v-if="helpAnswers.length === 0" class="help-empty">厨娘暂时没有好建议，请注意安全操作</p>
          <div v-for="(a, i) in helpAnswers" :key="i" class="help-answer">
            {{ a }}
          </div>
        </div>

        <!-- 拦截话术态 -->
        <el-alert
          v-else-if="helpState === 'blocked'"
          type="warning"
          title="该问题未通过安全检查"
          :description="helpBlockedMessage"
          :closable="false"
          show-icon
        />

        <!-- 当日超限态 -->
        <el-alert
          v-else
          type="info"
          title="今日求助次数已用完"
          description="今天的求助额度用完了，明天再来问吧；紧急情况请先关火处理，安全第一。"
          :closable="false"
          show-icon
        />

        <template #footer>
          <template v-if="helpState === 'idle'">
            <el-button @click="helpVisible = false">取消</el-button>
            <el-button type="primary" :loading="helpLoading" @click="onHelpSubmit">发送求助</el-button>
          </template>
          <template v-else-if="helpState === 'answers'">
            <el-button @click="helpState = 'idle'">再问一个</el-button>
            <el-button type="primary" @click="helpVisible = false">好的</el-button>
          </template>
          <template v-else-if="helpState === 'blocked'">
            <el-button @click="helpState = 'idle'">换个问法</el-button>
            <el-button type="primary" @click="helpVisible = false">知道了</el-button>
          </template>
          <template v-else>
            <el-button type="primary" @click="helpVisible = false">知道了</el-button>
          </template>
        </template>
      </el-dialog>
    </template>
  </section>
</template>

<style scoped>
.cook-page {
  min-height: calc(100vh - var(--header-height) - 88px);
  display: flex;
  flex-direction: column;
}

/* ── 顶部：警示条 + 退出 ── */
.cook-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.cook-alert-slot {
  flex: 1;
  min-width: 0;
}

/* 无冲突时警示条不渲染，占位避免退出按钮跳动 */
.cook-alert-slot:empty {
  display: none;
}

.cook-exit {
  flex-shrink: 0;
  min-height: 44px;
}

/* ── F 模块：顶部右侧动作区（语音开关 + 退出） ── */
.cook-top-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.cook-voice {
  min-height: 44px;
}

/* ── F 模块 ⑫：离线模式顶部提示条 ── */
.cook-offline-alert {
  margin-bottom: 12px;
}

/* ── 进度 ── */
.cook-progress {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 16px 0 8px;
}

.cook-progress-bar {
  flex: 1;
}

.cook-progress-text {
  flex-shrink: 0;
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
}

/* ── 主体大字 ── */
.cook-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 20px 8px;
  text-align: center;
}

.cook-step-no {
  margin: 0 0 12px;
  font-size: var(--font-md);
  color: var(--color-info);
}

/* 烹饪专档大字：≥32px（50cm 可读），深浅模式均用主文字色保证对比度 */
.cook-step-text {
  margin: 0 auto 16px;
  max-width: 720px;
  font-size: 34px;
  font-weight: 700;
  line-height: 1.6;
  color: var(--text-main);
  overflow-wrap: anywhere;
}

/* 本步用量提示 ≥20px */
.cook-amount-hint {
  margin: 0 auto 12px;
  max-width: 720px;
  font-size: 21px;
  font-weight: 600;
  line-height: 1.6;
  color: var(--color-warning);
}

.cook-duration {
  margin: 0 auto 8px;
  font-size: var(--font-lg);
  color: var(--text-main);
}

.cook-tips {
  max-width: 720px;
  margin: 12px auto 0;
  text-align: left;
}

.cook-tip-line {
  margin: 6px 0;
  font-size: var(--font-md);
  line-height: 1.8;
  color: var(--text-main);
}

/* ── 底部操作：大按钮（≥44pt 点击区域）── */
.cook-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 18px;
  padding: 12px 0 4px;
}

.cook-btn {
  min-width: 132px;
  min-height: 52px;
  font-size: var(--font-lg);
}

.cook-btn--primary {
  min-width: 160px;
}

/* ── 步骤抽屉 ── */
.drawer-step {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  margin-bottom: 8px;
  border: 1px solid var(--color-info-border);
  border-radius: 8px;
  cursor: pointer;
}

.drawer-step--active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.drawer-step-no {
  font-size: var(--font-sm);
  font-weight: 600;
  color: var(--el-color-primary);
}

.drawer-step-desc {
  font-size: var(--font-md);
  line-height: 1.6;
  color: var(--text-main);
}

/* ── R5/L4 完成态落地面板 ── */
.cook-finish {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 完成面板按钮：与烹饪页大按钮一致的舒适点击区域 */
.cook-finish-btn {
  min-width: 132px;
  min-height: 44px;
}

/* ── R7 修复：计时器抽屉自定义 header（标题 + 具名关闭按钮）── */
.timer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.timer-header-title {
  font-size: var(--font-lg);
  font-weight: 600;
  color: var(--text-main);
}

/* ── Task 9 ⑦：计时器抽屉 ── */
.cook-btn-icon {
  margin-right: 4px;
}

.timer-label {
  margin: 0 0 8px;
  font-size: var(--font-sm);
  color: var(--color-info);
}

.timer-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.timer-form {
  display: flex;
  align-items: center;
  gap: 8px;
}

.timer-name {
  flex: 1;
}

.timer-min {
  width: 96px;
}

.timer-unit {
  flex-shrink: 0;
  font-size: var(--font-sm);
  color: var(--color-info);
}

.timer-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.timer-item {
  padding: 12px 14px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
}

.timer-item--done {
  border-color: var(--color-danger-border);
  background: var(--color-danger-bg);
}

.timer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.timer-name {
  font-weight: 600;
  color: var(--text-main);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timer-remaining {
  margin: 8px 0;
  font-size: 32px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-main);
  text-align: center;
}

.timer-remaining--done {
  color: var(--color-danger);
}

.timer-actions {
  display: flex;
  gap: 6px;
}

/* ── Task 9 ⑨：求助弹窗 ── */
.help-answers {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.help-answer {
  padding: 10px 12px;
  border: 1px solid var(--color-info-border);
  border-radius: 8px;
  background: var(--color-info-bg);
  font-size: var(--font-md);
  line-height: 1.7;
  color: var(--text-main);
}

.help-empty {
  margin: 0;
  font-size: var(--font-sm);
  color: var(--color-info);
}
</style>
