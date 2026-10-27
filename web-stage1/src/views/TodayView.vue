<script setup lang="ts">
/**
 * 视图职责：/today「今天吃什么」零输入直出推荐决策页（add-home-entries-and-covers，对齐文档12 方案 B）。
 * 区块：① 标题「今天吃什么」+ 副标题「没想好？先看这几道」；
 *       ② 未建档黄条（homeStore.data 已加载且未建档时展示 + 去建档入口，不阻断浏览；
 *          聚合数据未加载时不误报，对齐 HomeView 的 `homeStore.data && ...` 写法）；
 *       ③ 口径说明条（零输入未选食材，按耗时口径分组；选择食材后结果更准。
 *          零输入无覆盖语义，不按 match_level 分组、不展示覆盖率）；
 *       ④ 主操作行「换一换」（loading 中 disabled；点击携带当前批全部 recipe_id 作为
 *          exclude_ids 重拉，每次仍重发不空转；连续 3 次新批与上一批 id 集合完全相同
 *          → toastInfo 提示「试试放宽条件或去选食材」，按钮保持可用）；
 *       ⑤ 三态：初次 loading = 骨架 + 「正在为你挑今天这顿」；换一换时保留当前结果；error = el-alert + 重试；
 *          空（!error && results.length===0）= el-empty「暂时没有合适的推荐」
 *          + 响应 notice（有则展示）+ 底部兜底按钮组；
 *       ⑥ 耗时口径分组渲染（utils/today.groupDayMenuByTime：⏱≤15 分钟 / ⏱15–30 分钟 /
 *          🛒需备料；RecipeCard :show-coverage="false"，栅格对齐 RecommendView .card-list）；
 *       ⑦ 兜底区：「我有食材，去选食材」→ /select；「用冰箱里的食材」→ /inventory
 *          （home store 无库存数据，恒显示，由目标页兜底）；
 *       ⑧ 底部免责条（DisclaimerBar variant=default）。
 * 生命周期：onMounted 首拉；本页不拉 home 聚合（黄条仅消费既有 store 数据）。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Opportunity, Refresh, Refrigerator } from '@element-plus/icons-vue'
import { fetchDayMenu } from '@/api/dayMenu'
import type { ApiError, RecommendResultItem } from '@/api/types'
import { useHomeStore } from '@/stores/home'
import { groupDayMenuByTime } from '@/utils/today'
import { parseOrdinal } from '@/utils/voiceCommand'
import { globalIntentFallback, setVoicePageHandler } from '@/utils/voiceAgent'
import { toastInfo } from '@/utils/toast'
import RecipeCard from '@/components/RecipeCard.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'

/** 路由（去建档 / 去选食材 / 用冰箱里的食材跳转） */
const router = useRouter()
/** 首页聚合 store（仅读取未建档提示所需数据，本页不主动拉取） */
const homeStore = useHomeStore()

/** 加载中标记（骨架与「换一换」置灰共用） */
const loading = ref(false)
/** 加载错误（归一化 ApiError，null 表示无错） */
const error = ref<ApiError | null>(null)
/** 当前批零输入推荐结果（≤6 道，match_level 恒为 can_cook_now，页面按耗时分组） */
const results = ref<RecommendResultItem[]>([])
/** 后端附加提示文案（空态时随 el-empty 展示，有则展示） */
const notice = ref('')

/** 「连续 3 次无新结果」提示阈值（新批与上一批 id 集合完全相同的连续次数） */
const STALE_REPEAT_LIMIT = 3
/** 连续相同批次计数（模块级可变状态，请求失败不计入） */
let staleStreak = 0

/** 耗时口径分组结果（空档已被纯函数过滤，直接 v-for 渲染） */
const grouped = computed(() => groupDayMenuByTime(results.value))

/**
 * 语音点菜：打开列表中第 no 个菜谱（内部函数）。
 * 顺序与页面视觉顺序一致（按耗时分组从上到下）。
 * @param no 序数（1 起）
 * @returns 无
 */
function openByOrdinal(no: number): void {
  const flat = grouped.value.flatMap((g) => g.items)
  const item = flat[no - 1]
  if (!item) {
    toastInfo(`当前只有 ${flat.length} 道推荐，可以说「换一换」`)
    return
  }
  toastInfo(`已为你打开第 ${no} 个：${item.title}`)
  void router.push(`/recipe/${item.recipe_id}`)
}

/**
 * 本页语音转写处理器（注册进全局语音助手）：
 * 「第一个/第N个/随便来一个」语音点菜，「换一换」刷新批次，其余走 LLM 意图兜底。
 * @param text 最终转写文本
 * @returns 无
 */
async function handleVoiceTranscript(text: string): Promise<void> {
  if (/随便|来一个/.test(text)) {
    openByOrdinal(1)
    return
  }
  const no = parseOrdinal(text)
  if (no != null) {
    openByOrdinal(no)
    return
  }
  if (/换一换|换一批/.test(text)) {
    void refreshBatch()
    return
  }
  await globalIntentFallback(text)
}

/**
 * 判定两个批次是否为同一批（recipe_id 集合完全一致，忽略顺序与重复）。
 * @param prevIds 上一批 recipe_id 集合
 * @param nextIds 新批 recipe_id 集合
 * @returns 集合大小相等且上一批每个 id 都出现在新批中为 true
 */
function sameIdSet(prevIds: Set<number>, nextIds: Set<number>): boolean {
  if (prevIds.size !== nextIds.size) return false
  for (const id of prevIds) {
    if (!nextIds.has(id)) return false
  }
  return true
}

/**
 * 拉取零输入直出推荐（首拉与「换一换」共用）。
 * 匿名身份由 axios 拦截器统一携带 X-Anonymous-Id 头，后端据此执行档案硬过滤。
 * @param excludeIds 上一批结果的 recipe_id 列表（「换一换」排除语义；空 = 首次请求）
 * @returns 请求成功为 true（供「换一换」判断是否比对批次；失败时结果态不变且不比对）
 */
async function load(excludeIds: number[] = []): Promise<boolean> {
  loading.value = true
  error.value = null
  try {
    const resp = await fetchDayMenu(excludeIds)
    results.value = resp.results ?? []
    notice.value = resp.notice ?? ''
    return true
  } catch (e) {
    error.value = e as ApiError
    return false
  } finally {
    loading.value = false
  }
}

/**
 * 「换一换」：携带当前批全部 recipe_id 作为 exclude_ids 重拉（每次仍重发，不空转）。
 * 连续 3 次新批与上一批 recipe_id 集合完全相同（候选池不足，后端排除后无新批可出）
 * → toastInfo 提示「试试放宽条件或去选食材」，按钮保持可用；请求失败不计入相同批次计数。
 * @returns 无
 */
async function refreshBatch(): Promise<void> {
  if (loading.value) return
  const prevIds = new Set(results.value.map((r) => r.recipe_id))
  const ok = await load([...prevIds])
  if (!ok) return
  const nextIds = new Set(results.value.map((r) => r.recipe_id))
  if (sameIdSet(prevIds, nextIds)) {
    staleStreak += 1
    if (staleStreak >= STALE_REPEAT_LIMIT) {
      toastInfo('试试放宽条件或去选食材')
      staleStreak = 0
    }
  } else {
    staleStreak = 0
  }
}

/**
 * 异常重试：重发当前批次请求（沿用当前 results 作为 exclude_ids，语义同「换一换」）。
 * @returns 无
 */
function retry(): void {
  void load(results.value.map((r) => r.recipe_id))
}

// 挂载即首拉（零输入直出，无「请先选择食材」拦截）
onMounted(() => {
  void load()
  setVoicePageHandler(handleVoiceTranscript)
})

onBeforeUnmount(() => {
  setVoicePageHandler(null)
})
</script>

<template>
  <section class="page-card today-page">
    <!-- ① 标题 + 副标题（不得出现绝对化/疗效表述） -->
    <h1 class="page-title">今天吃什么</h1>
    <p class="page-subtitle">没想好？先看这几道</p>

    <!-- ② 未建档黄条：聚合数据已加载且未建档时展示（不阻断浏览）；未加载不误报 -->
    <el-alert
      v-if="homeStore.data && !homeStore.hasProfile"
      class="today-alert"
      type="warning"
      title="还没有建立家庭档案，建好后推荐会更懂你（过敏原 / 口味 / 厨艺）"
      :closable="false"
      show-icon
    >
      <el-button size="small" type="warning" plain @click="router.push('/profile')">
        去建档
      </el-button>
    </el-alert>

    <!-- ③ 口径说明条：零输入按耗时口径分组（覆盖率三档不成立，对齐文档12 §6.3 规则 3） -->
    <el-alert
      class="today-alert today-note"
      type="info"
      title="选了食材之后推荐更准哦"
      :closable="false"
      show-icon
    >
      <template #icon><Opportunity /></template>
    </el-alert>

    <!-- ④ 主操作行：换一换（loading 中 disabled；每次携带上一批全部 recipe_id 重拉） -->
    <div class="toolbar">
      <el-button class="shuffle-button" type="primary" :loading="loading" @click="refreshBatch">
        <el-icon class="shuffle-icon"><Refresh /></el-icon>
        换一换
      </el-button>
    </div>

    <!-- ⑤-1 异常态：错误 + 重试 -->
    <el-alert v-if="error" type="error" :title="error.message" :closable="false" show-icon>
      <el-button size="small" type="primary" plain @click="retry">重试</el-button>
    </el-alert>

    <!-- ⑤-2 加载态：骨架 + 文案 -->
    <div v-if="loading && results.length === 0" class="loading-block">
      <el-skeleton :rows="6" animated />
      <p class="loading-text">正在为你挑今天这顿</p>
    </div>

    <!-- ⑤-3 / ⑥ / ⑦：非加载且无异常时渲染空态、分组结果与兜底区 -->
    <template v-else-if="!error">
      <!-- 空态：说明 + 后端 notice（有则展示） -->
      <el-empty v-if="results.length === 0" description="暂时没有合适的推荐">
        <p v-if="notice" class="empty-notice">{{ notice }}</p>
      </el-empty>

      <!-- ⑥ 耗时口径分组渲染（⏱≤15 分钟 / ⏱15–30 分钟 / 🛒需备料；空档不渲染） -->
      <div v-for="group in grouped" :key="group.key" class="group-section">
        <el-divider class="group-divider">
          <span class="group-title">
            {{ group.title }}
            <el-badge :value="group.items.length" type="primary" class="group-badge" />
          </span>
        </el-divider>
        <!-- 推荐卡片：零输入无覆盖语义，隐藏覆盖率列 -->
        <TransitionGroup
          name="recipe-shuffle"
          tag="div"
          class="card-list"
          :aria-busy="loading"
        >
          <RecipeCard
            v-for="item in group.items"
            :key="item.recipe_id"
            :item="item"
            :show-coverage="false"
          />
        </TransitionGroup>
      </div>

      <!-- ⑦ 兜底区（空态与结果态均展示；home store 无库存数据，按钮恒显示，由目标页兜底） -->
      <div class="fallback-actions">
        <el-button class="fallback-action fallback-action--primary" type="primary" @click="router.push('/select')">
          <span>我有食材，去选食材</span>
          <el-icon aria-hidden="true"><ArrowRight /></el-icon>
        </el-button>
        <el-button class="fallback-action fallback-action--secondary" @click="router.push('/inventory')">
          <el-icon aria-hidden="true"><Refrigerator /></el-icon>
          <span>用冰箱里的食材</span>
        </el-button>
      </div>
    </template>

    <!-- ⑧ 底部免责条（G-02 通用档位） -->
    <DisclaimerBar variant="default" />
  </section>
</template>

<style scoped>
.today-page {
  padding-bottom: 28px;
}

/* ── 副标题（page-title 全局样式自带 margin-bottom: 16px，负 margin 收紧间距） ── */
.page-subtitle {
  margin: -10px 0 16px;
  font-size: var(--font-md);
  color: var(--color-info);
}

.today-alert {
  margin-bottom: 14px;
}

.today-note {
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--line-strong) 72%, var(--accent));
  border-radius: 8px;
  background: var(--surface-soft);
}

.today-note :deep(.el-alert__icon) {
  color: var(--accent-deep);
  font-size: 18px;
}

.today-note :deep(.el-alert__title) {
  color: var(--text-main);
  font-size: 14px;
  font-weight: 500;
}

/* ── 主操作行：换一换 ── */
.toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}

.toolbar :deep(.shuffle-button) {
  min-height: 42px;
  gap: 8px;
  padding: 0 18px;
  border: 0;
  border-radius: 8px;
  background: var(--accent-deep);
  box-shadow: 0 3px 10px rgba(36, 72, 58, 0.14);
  transition: transform 180ms ease, box-shadow 180ms ease, background-color 180ms ease;
}

.toolbar :deep(.shuffle-button:not(.is-disabled):hover) {
  transform: translateY(-2px);
  background: color-mix(in srgb, var(--accent-deep) 92%, white);
  box-shadow: 0 7px 16px rgba(36, 72, 58, 0.2);
}

.shuffle-icon {
  transition: transform 260ms cubic-bezier(0.2, 0.8, 0.2, 1);
}

.toolbar :deep(.shuffle-button:not(.is-disabled):hover .shuffle-icon) {
  transform: rotateY(180deg);
}

.toolbar :deep(.shuffle-button:focus-visible) {
  outline: 2px solid var(--accent-deep);
  outline-offset: 3px;
}

.loading-block {
  padding: 8px 0;
}

.loading-text {
  margin: 12px 0 0;
  text-align: center;
  color: var(--color-info);
  font-size: var(--font-md);
}

/* ── 空态 notice 附加说明 ── */
.empty-notice {
  margin: 0;
  font-size: var(--font-sm);
  color: var(--color-info);
}

/* ── 耗时口径分组（风格对齐 RecommendView 的 group-divider / group-title） ── */
.group-divider {
  margin: 22px 0 14px;
}

.group-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: var(--font-lg);
  font-weight: 600;
  color: var(--text-main);
}

.group-badge {
  vertical-align: middle;
}

/* ── 卡片栅格（自 RecommendView .card-list 复制对齐） ── */
.card-list {
  position: relative;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}

.card-list :deep(.recipe-card) {
  transition: transform 220ms cubic-bezier(0.2, 0.8, 0.2, 1),
    border-color 180ms ease, box-shadow 220ms ease;
}

.card-list :deep(.recipe-card:hover),
.card-list :deep(.recipe-card:focus-within) {
  transform: translateY(-3px);
  box-shadow: 0 9px 22px rgba(36, 72, 58, 0.12);
}

.card-list :deep(.card-cover .cover-img),
.card-list :deep(.card-cover .cover-placeholder) {
  transition: transform 300ms cubic-bezier(0.16, 1, 0.3, 1);
}

.card-list :deep(.recipe-card:hover .card-cover .cover-img),
.card-list :deep(.recipe-card:hover .card-cover .cover-placeholder),
.card-list :deep(.recipe-card:focus-within .card-cover .cover-img),
.card-list :deep(.recipe-card:focus-within .card-cover .cover-placeholder) {
  transform: scale(1.02);
}

.recipe-shuffle-enter-active,
.recipe-shuffle-move {
  transition: opacity 240ms ease, transform 360ms cubic-bezier(0.2, 0.8, 0.2, 1);
}

.recipe-shuffle-enter-active:nth-child(2) { transition-delay: 45ms; }
.recipe-shuffle-enter-active:nth-child(3) { transition-delay: 90ms; }
.recipe-shuffle-enter-active:nth-child(4) { transition-delay: 135ms; }
.recipe-shuffle-enter-active:nth-child(5) { transition-delay: 180ms; }
.recipe-shuffle-enter-active:nth-child(6) { transition-delay: 225ms; }

.recipe-shuffle-enter-from {
  opacity: 0;
  transform: translateY(10px) rotate(0.5deg);
}

.card-list :deep(.equipment-tag.el-tag) {
  color: var(--text-muted);
  border-color: color-mix(in srgb, var(--line-strong) 78%, var(--accent));
  border-radius: 6px;
  background: var(--surface-soft);
}

/* ── 底部兜底按钮组 ── */
.fallback-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 14px;
  width: min(100%, 530px);
  margin: 30px auto 0;
}

.fallback-actions :deep(.fallback-action) {
  box-sizing: border-box;
  flex: 1 1 240px;
  min-width: 0;
  min-height: 48px;
  margin: 0;
  padding: 0 18px;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
  transition:
    transform 180ms ease,
    box-shadow 180ms ease,
    background-color 180ms ease,
    border-color 180ms ease;
}

.fallback-actions :deep(.fallback-action--primary) {
  justify-content: space-between;
  color: var(--text-on-accent);
  border-color: var(--el-color-primary);
  background: var(--el-color-primary);
  box-shadow: 0 3px 10px color-mix(in srgb, var(--accent-deep) 18%, transparent);
}

.fallback-actions :deep(.fallback-action--secondary) {
  justify-content: center;
  color: var(--text-main);
  border-color: var(--sidebar-line);
  background: var(--surface-soft);
}

.fallback-actions :deep(.fallback-action .el-icon) {
  flex: 0 0 auto;
  font-size: 18px;
}

.fallback-actions :deep(.fallback-action--primary .el-icon) {
  margin-left: 10px;
  transition: transform 180ms ease;
}

.fallback-actions :deep(.fallback-action--secondary .el-icon) {
  margin-right: 9px;
  color: var(--accent-deep);
}

.fallback-actions :deep(.fallback-action--primary:not(.is-disabled):hover) {
  color: var(--text-on-accent);
  border-color: var(--el-color-primary);
  background: color-mix(in srgb, var(--el-color-primary) 90%, var(--text-main));
  box-shadow: 0 7px 16px color-mix(in srgb, var(--accent-deep) 24%, transparent);
  transform: translateY(-2px);
}

.fallback-actions :deep(.fallback-action--primary:not(.is-disabled):hover .el-icon) {
  transform: translateX(2px);
}

.fallback-actions :deep(.fallback-action--secondary:not(.is-disabled):hover) {
  color: var(--text-main);
  border-color: color-mix(in srgb, var(--line-strong) 68%, var(--accent-deep));
  background: var(--surface-hover);
  transform: translateY(-2px);
}

.fallback-actions :deep(.fallback-action:focus-visible) {
  outline: 2px solid var(--accent-deep);
  outline-offset: 3px;
}

@media (max-width: 640px) {
  .fallback-actions {
    flex-direction: column;
    width: min(100%, 360px);
  }

  .fallback-actions :deep(.fallback-action) {
    flex: 0 0 auto;
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .toolbar :deep(.shuffle-button),
  .shuffle-icon,
  .fallback-actions :deep(.fallback-action),
  .fallback-actions :deep(.fallback-action .el-icon),
  .card-list :deep(.recipe-card),
  .card-list :deep(.card-cover .cover-img),
  .card-list :deep(.card-cover .cover-placeholder),
  .recipe-shuffle-enter-active,
  .recipe-shuffle-move {
    transition-duration: 0.01ms !important;
    transition-delay: 0ms !important;
  }

  .toolbar :deep(.shuffle-button:not(.is-disabled):hover),
  .fallback-actions :deep(.fallback-action--primary:not(.is-disabled):hover),
  .fallback-actions :deep(.fallback-action--secondary:not(.is-disabled):hover),
  .card-list :deep(.recipe-card:hover),
  .card-list :deep(.recipe-card:focus-within) {
    transform: none;
  }

  .toolbar :deep(.shuffle-button:not(.is-disabled):hover .shuffle-icon) {
    transform: none;
  }

  .fallback-actions :deep(.fallback-action--primary:not(.is-disabled):hover .el-icon) {
    transform: none;
  }

  .card-list :deep(.recipe-card:hover .card-cover .cover-img),
  .card-list :deep(.recipe-card:hover .card-cover .cover-placeholder),
  .card-list :deep(.recipe-card:focus-within .card-cover .cover-img),
  .card-list :deep(.recipe-card:focus-within .card-cover .cover-placeholder),
  .recipe-shuffle-enter-from {
    transform: none;
  }
}
</style>
