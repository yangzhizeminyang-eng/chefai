<script setup lang="ts">
/**
 * 视图职责：首页（Task 9 / 路由 /）。
 * 区块：① 顶部搜索框（回车走统一 ask 消费链路 stores/ask.submitQuestion：
 *          空输入单条提示；blocked 跳 W-05；recipe_search 落推荐态跳 W-02；
 *          chat 就地展示结果卡 AskChatCard；
 *          DEF-02：短且无疑问词的菜名/食材名搜索不再丢词，携带 q=原始输入 跳 /select）；
 *       ② 未建档黄条（el-alert warning → 跳 /profile 建档引导）；
 *       ③ 「继续上次的菜」卡（未完成会话 → /cook/{sessionId} 断点续做）；
 *       ④ 临期提醒条（el-alert 可关闭，localStorage aicook_expiry_dismissed_{date} 当日不再显示；
 *          条内固定说明「到期信息仅作提醒，不代表食材是否可食用」，RL-3 不做可食性判定）；
 *       ⑤ 六大入口卡（今天吃什么 / 拍一下冰箱 / 时令吃什么 / 饮食目标 / 我的冰箱 / AI 创新一下；
 *          innovation 受 switches.innovation 控制，关闭时置灰 + 说明）；
 *       ⑥ 底部常驻免责小字（DisclaimerBar）。
 * 三态：加载 = 骨架卡；空/数据缺失 = 入口卡照常展示（入口不依赖聚合接口）；异常 = 顶部 el-alert + 重试。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useHomeStore } from '@/stores/home'
import { useConfigStore } from '@/stores/config'
import { useAskStore } from '@/stores/ask'
import { decideHomeSearchRoute } from '@/utils/searchRouting'
import { toastInfo } from '@/utils/toast'
import AskChatCard from '@/components/AskChatCard.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'

/** 路由（入口跳转 / 拦截页跳转） */
const router = useRouter()
/** 首页聚合 store */
const homeStore = useHomeStore()
/** 远程开关 store（AI 创新入口置灰用） */
const configStore = useConfigStore()
/** 统一 ask 消费 store（空输入提示 / 意图分流 / chat 态 / asking 标记） */
const askStore = useAskStore()

/** 搜索关键词（回车提问语义，同 W-01 约定） */
const keyword = ref('')

/** AI 创新入口是否可用（switches.innovation 未返回时默认放开） */
const innovationEnabled = computed(() => configStore.switches.innovation !== false)

/** 问答模块是否可用（§5.8：switch.qa=false → 搜索框降级为菜名/食材名精确搜索） */
const qaEnabled = computed(() => configStore.switches.qa !== false)

/** 搜索框占位文案（问答开关关闭时如实降级说明，§5.8 问答模块） */
const searchPlaceholder = computed(() =>
  qaEnabled.value ? '想吃什么或有什么食材？回车问厨娘' : '问答维护中：输入食材名，回车去精确搜索',
)

/** 临期提醒是否已被今日关闭（localStorage 当日记忆） */
const expiryDismissed = ref(false)

/** 今日日期键（YYYY-MM-DD，本地时区） */
function todayKey(): string {
  const d = new Date()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

/** 临期提醒展示条件：有临期数据且今日未被关闭 */
const showExpiryAlert = computed(
  () => (homeStore.data?.expiring?.length ?? 0) > 0 && !expiryDismissed.value,
)

/** 临期提醒文案（首条 + 其余计数） */
const expiryText = computed(() => {
  const list = homeStore.data?.expiring ?? []
  const first = list[0]
  if (!first) return ''
  const head = `${first.ingredient_name} ${first.days_left < 0 ? '已过期' : `还剩 ${first.days_left} 天`}`
  return list.length > 1 ? `${head} 等 ${list.length} 样食材临近到期` : `${head}，注意及时食用`
})

/**
 * 关闭临期提醒：写 localStorage aicook_expiry_dismissed_{date}，当日不再显示。
 * @returns 无
 */
function dismissExpiry(): void {
  expiryDismissed.value = true
  try {
    localStorage.setItem(`aicook_expiry_dismissed_${todayKey()}`, '1')
  } catch {
    // 持久化失败仅影响当日记忆，不阻塞
  }
}

/**
 * 搜索框回车：按分流决策执行（纯函数 decideHomeSearchRoute 承载判定，便于单测）。
 * - 空输入 → 单条「请输入内容」提示（store 内守卫），不发请求（修复 A1 静默无响应）；
 * - qa 开关关闭（§5.8 问答模块）→ 降级为食材名精确搜索：跳食材选择页并回填关键词；
 * - 短且无疑问词（DEF-02 修复）→ 携带 q=原始输入 跳 /select：菜名搜索意图不丢词，
 *   选择页先搜菜谱、再回退食材定位；
 * - 其余 → submitQuestion：blocked 跳 W-05 / recipe_search 落推荐态跳 W-02 /
 *   chat 就地展示（AskChatCard）/ 失败单一降级 toast（修复 H2 闭环断裂）。
 * @returns 无
 */
function onSearchEnter(): void {
  const text = keyword.value.trim()
  const decision = decideHomeSearchRoute(text, qaEnabled.value)
  // 空输入：交给 store 统一出单条提示（文案单点维护），不跳转不发请求
  if (decision === 'emptyHint' || decision === 'ask') {
    void askStore.submitQuestion(text)
    return
  }
  // 问答开关关闭（§5.8）：不走 ask，降级为食材名精确搜索（/select 页本地+远程搜索）
  if (decision === 'selectDegraded') {
    toastInfo('问答功能维护中，已切换为食材名精确搜索')
  }
  // selectShort / selectDegraded 均携带 q 跳转（DEF-02：短菜名如「宫保鸡丁」不再丢词）
  void router.push({ path: '/select', query: { q: text } })
}

/** 六大入口卡配置（enabled 动态判定，避免静态数据写死开关） */
const entries = computed(() => [
  {
    key: 'cooking',
    icon: '🍚',
    title: '今天吃什么',
    desc: '没想好？先看这几道',
    to: '/today',
    enabled: homeStore.data?.entries.cooking ?? true,
    disabledTip: '推荐功能维护中',
  },
  {
    key: 'vision',
    icon: '📸',
    title: '拍一下冰箱',
    desc: '拍照识别食材',
    to: '/recognize',
    enabled: homeStore.data?.entries.vision ?? true,
    disabledTip: '识别功能维护中',
  },
  {
    key: 'seasonal',
    icon: '🍂',
    title: '时令吃什么',
    desc: '当季食材与应季菜谱',
    to: '/seasonal',
    enabled: homeStore.data?.entries.seasonal ?? true,
    disabledTip: '时令功能维护中',
  },
  {
    key: 'goal',
    icon: '🎯',
    title: '饮食目标',
    desc: '建档定制推荐',
    to: '/profile',
    enabled: homeStore.data?.entries.goal ?? true,
    disabledTip: '档案功能维护中',
  },
  {
    key: 'fridge',
    icon: '🧊',
    title: '我的冰箱',
    desc: '库存管理与购物清单',
    to: '/inventory',
    enabled: homeStore.data?.entries.fridge ?? true,
    disabledTip: '库存功能维护中',
  },
  {
    key: 'innovation',
    icon: '✨',
    title: 'AI 创新一下',
    desc: '按手边食材出新菜',
    to: '/innovate',
    enabled: innovationEnabled.value && (homeStore.data?.entries.innovation ?? true),
    disabledTip: 'AI 创新功能暂未开放',
  },
])

/**
 * 点击入口卡：禁用态提示，可用态跳转目标路由。
 * @param entry 入口卡对象
 * @returns 无
 */
function goEntry(entry: { to: string; enabled: boolean; disabledTip: string }): void {
  if (!entry.enabled) {
    toastInfo(entry.disabledTip)
    return
  }
  void router.push(entry.to)
}

/**
 * 重试首页聚合数据。
 * @returns 无
 */
function retry(): void {
  void homeStore.load()
}

// 挂载：读取当日关闭记忆 + 拉取聚合数据
onMounted(() => {
  try {
    expiryDismissed.value = localStorage.getItem(`aicook_expiry_dismissed_${todayKey()}`) === '1'
  } catch {
    expiryDismissed.value = false
  }
  void homeStore.load()
})
</script>

<template>
  <section class="page-card home-page">
    <h1 class="page-title">今天想吃什么？</h1>

    <!-- ① 顶部搜索框：回车提问（统一 ask 消费链路；qa 关闭时降级为精确搜索入口） -->
    <el-input
      v-model="keyword"
      class="home-search"
      size="large"
      clearable
      :placeholder="searchPlaceholder"
      :suffix-icon="undefined"
      @keyup.enter="onSearchEnter"
    >
      <template #append>
        <el-button :loading="askStore.asking" @click="onSearchEnter">
          {{ qaEnabled ? '问厨娘' : '搜索' }}
        </el-button>
      </template>
    </el-input>

    <!-- chat 就地展示卡：受限问答结果（含问句回显与免责小字），无内容不渲染 -->
    <AskChatCard class="home-chat" />

    <!-- 异常态：聚合数据加载失败（入口卡仍可用） -->
    <el-alert
      v-if="homeStore.error"
      class="home-alert"
      type="error"
      :title="`首页信息加载失败：${homeStore.error.message}`"
      :closable="false"
      show-icon
    >
      <el-button size="small" type="primary" plain @click="retry">重试</el-button>
    </el-alert>

    <!-- ② 未建档黄条（聚合数据未返回时不误报） -->
    <el-alert
      v-if="homeStore.data && !homeStore.hasProfile"
      class="home-alert"
      type="warning"
      title="还没有建立家庭档案，建好后推荐会更懂你（过敏原 / 口味 / 厨艺）"
      :closable="false"
      show-icon
    >
      <el-button size="small" type="warning" plain @click="router.push('/profile')">
        去建档
      </el-button>
    </el-alert>

    <!-- ③ 继续上次的菜 -->
    <div
      v-if="homeStore.hasUnfinished"
      class="resume-card"
      role="button"
      @click="router.push(`/cook/${homeStore.data?.unfinished_session?.session_id}`)"
    >
      <span class="resume-icon">🍳</span>
      <div class="resume-info">
        <p class="resume-title">继续上次的菜：{{ homeStore.data?.unfinished_session?.recipe_name }}</p>
        <p class="resume-sub">
          进度：第 {{ homeStore.data?.unfinished_session?.current_step }} 步 /
          共 {{ homeStore.data?.unfinished_session?.total_steps }} 步
        </p>
      </div>
      <el-button type="primary">继续做</el-button>
    </div>

    <!-- ④ 临期提醒条（可关闭，当日记忆；条内固定说明：到期信息仅提醒，不作可食性判定，RL-3） -->
    <el-alert
      v-if="showExpiryAlert"
      class="home-alert"
      type="warning"
      :title="expiryText"
      show-icon
      @close="dismissExpiry"
    >
      <p class="expiry-note">到期信息仅作提醒，不代表食材是否可食用</p>
      <el-button size="small" plain @click="router.push('/inventory')">去查看冰箱</el-button>
    </el-alert>

    <!-- 加载态：入口卡骨架 -->
    <div v-if="homeStore.loading" class="entry-grid">
      <div v-for="n in 6" :key="n" class="entry-card">
        <el-skeleton :rows="2" animated />
      </div>
    </div>

    <!-- ⑤ 六大入口卡 -->
    <div v-else class="entry-grid">
      <button
        v-for="entry in entries"
        :key="entry.key"
        type="button"
        class="entry-card"
        :class="{ 'entry-card--disabled': !entry.enabled }"
        @click="goEntry(entry)"
      >
        <span class="entry-icon">{{ entry.icon }}</span>
        <span class="entry-title">{{ entry.title }}</span>
        <span class="entry-desc">{{ entry.enabled ? entry.desc : '暂不可用' }}</span>
      </button>
    </div>

    <!-- ⑥ 底部常驻免责小字 -->
    <DisclaimerBar variant="default" />
  </section>
</template>

<style scoped>
.home-search {
  max-width: 560px;
  margin-bottom: 16px;
}

/* ── chat 结果卡（AskChatCard）与搜索框间距 ── */
.home-chat {
  max-width: 560px;
  margin-bottom: 16px;
}

.home-alert {
  margin-bottom: 14px;
}

/* ── 临期条固定说明（RL-3：仅提醒，不作可食性判定） ── */
.expiry-note {
  margin: 0 0 6px;
  font-size: var(--font-sm);
  color: var(--color-info);
}

/* ── 继续上次的菜卡 ── */
.resume-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 18px;
  margin-bottom: 16px;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 10px;
  background: var(--el-color-primary-light-9);
  cursor: pointer;
}

.resume-icon {
  font-size: 30px;
}

.resume-info {
  flex: 1;
  min-width: 0;
}

.resume-title {
  margin: 0 0 4px;
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
}

.resume-sub {
  margin: 0;
  font-size: var(--font-sm);
  color: var(--color-info);
}

/* ── 入口卡网格 ── */
.entry-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.entry-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 18px 16px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
  background: var(--card-bg);
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    transform 0.15s ease;
}

.entry-card:hover {
  border-color: var(--el-color-primary);
  transform: translateY(-2px);
}

.entry-card--disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.entry-card--disabled:hover {
  border-color: var(--color-info-border);
  transform: none;
}

.entry-icon {
  font-size: 28px;
}

.entry-title {
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
}

.entry-desc {
  font-size: var(--font-sm);
  color: var(--color-info);
}
</style>
