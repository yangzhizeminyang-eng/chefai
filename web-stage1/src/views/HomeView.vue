<script setup lang="ts">
/**
 * 视图职责：首页（Task 9 / 路由 /）。
 * 区块：① 顶部搜索框（回车调 POST /v1/ask，命中一票否决写入 recommend store 后跳 W-05）；
 *       ② 未建档黄条（el-alert warning → 跳 /profile 建档引导）；
 *       ③ 「继续上次的菜」卡（未完成会话 → /cook/{sessionId} 断点续做）；
 *       ④ 临期提醒条（el-alert 可关闭，localStorage aicook_expiry_dismissed_{date} 当日不再显示）；
 *       ⑤ 六大入口卡（今天吃什么 / 拍一下冰箱 / 时令吃什么 / 饮食目标 / 我的冰箱 / AI 创新一下；
 *          innovation 受 switches.innovation 控制，关闭时置灰 + 说明）；
 *       ⑥ 底部常驻免责小字（DisclaimerBar）。
 * 三态：加载 = 骨架卡；空/数据缺失 = 入口卡照常展示（入口不依赖聚合接口）；异常 = 顶部 el-alert + 重试。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { postAsk } from '@/api/endpoints'
import type { ApiError } from '@/api/types'
import { useHomeStore } from '@/stores/home'
import { useConfigStore } from '@/stores/config'
import { useRecommendStore } from '@/stores/recommend'
import DisclaimerBar from '@/components/DisclaimerBar.vue'

/** 路由（入口跳转 / 拦截页跳转） */
const router = useRouter()
/** 首页聚合 store */
const homeStore = useHomeStore()
/** 远程开关 store（AI 创新入口置灰用） */
const configStore = useConfigStore()
/** 推荐 store（ask 命中阻断时写入 blockedPayload，W-05 数据源） */
const recommendStore = useRecommendStore()

/** 搜索关键词（回车提问语义，同 W-01 约定） */
const keyword = ref('')
/** ask 请求进行中 */
const asking = ref(false)

/** 提问意图判定正则（与 SelectIngredientView 同源：疑问词/问号/长文本视为提问） */
const QUESTION_PATTERN = /[?？]|吗|呢|怎么|怎样|如何|什么|哪些|多少|能不能|可不可以|行不行|可以|推荐/

/** AI 创新入口是否可用（switches.innovation 未返回时默认放开） */
const innovationEnabled = computed(() => configStore.switches.innovation !== false)

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
 * 搜索框回车：非空且像提问时调 POST /v1/ask。
 * - 命中一票否决 → 写入 recommend store 后跳 W-05；
 * - 受限问答 → 弹窗展示；搜索/推荐意图 → 引导去推荐页。
 * @returns 无
 */
async function onSearchEnter(): Promise<void> {
  const text = keyword.value.trim()
  if (!text || asking.value) return
  if (!QUESTION_PATTERN.test(text) && text.length <= 4) {
    // 短且无疑问词 → 引导去食材选择页搜索
    void router.push('/select')
    return
  }
  asking.value = true
  try {
    const res = await postAsk(text)
    if (res.blocked) {
      recommendStore.blockedPayload = res.blocked
      recommendStore.traceId = res.blocked.trace_id || res.trace_id
      void router.push('/blocked')
      return
    }
    if (res.intent === 'free_qa' && res.answer) {
      ElMessage.success('厨娘已准备好回答')
      void router.push({ path: '/select', query: { q: text } })
      return
    }
    void router.push('/recommend')
  } catch (e) {
    ElMessage.error((e as ApiError).message)
  } finally {
    asking.value = false
  }
}

/** 六大入口卡配置（enabled 动态判定，避免静态数据写死开关） */
const entries = computed(() => [
  {
    key: 'cooking',
    icon: '🍚',
    title: '今天吃什么',
    desc: '选食材，三档推荐',
    to: '/select',
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
    desc: '应季食材优先推荐',
    to: '/select?seasonal=1',
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
    ElMessage.info(entry.disabledTip)
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

    <!-- ① 顶部搜索框：回车提问 -->
    <el-input
      v-model="keyword"
      class="home-search"
      size="large"
      clearable
      placeholder="想吃什么或有什么食材？回车问厨娘"
      :suffix-icon="undefined"
      @keyup.enter="onSearchEnter"
    >
      <template #append>
        <el-button :loading="asking" @click="onSearchEnter">问厨娘</el-button>
      </template>
    </el-input>

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

    <!-- ④ 临期提醒条（可关闭，当日记忆） -->
    <el-alert
      v-if="showExpiryAlert"
      class="home-alert"
      type="warning"
      :title="expiryText"
      show-icon
      @close="dismissExpiry"
    >
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

.home-alert {
  margin-bottom: 14px;
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
