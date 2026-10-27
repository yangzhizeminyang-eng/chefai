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
import { useIngredientsStore } from '@/stores/ingredients'
import { fetchDayMenu } from '@/api/dayMenu'
import type { RecommendResultItem } from '@/api/types'
import { decideHomeSearchRoute } from '@/utils/searchRouting'
import { selectFeaturedRecipes } from '@/utils/homeRecommendations'
import { toastInfo } from '@/utils/toast'
import { ArrowRight, Clock, CoffeeCup, Plus, Refresh, Search, WarningFilled } from '@element-plus/icons-vue'
import AskChatCard from '@/components/AskChatCard.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import RecipeCover from '@/components/RecipeCover.vue'

/** 路由（入口跳转 / 拦截页跳转） */
const router = useRouter()
/** 首页聚合 store */
const homeStore = useHomeStore()
/** 远程开关 store（AI 创新入口置灰用） */
const configStore = useConfigStore()
/** 统一 ask 消费 store（空输入提示 / 意图分流 / chat 态 / asking 标记） */
const askStore = useAskStore()
/** 当前会话已选择的食材（展示真实状态，不伪造预置食材） */
const ingredientsStore = useIngredientsStore()

/** 首页展示的真实今日推荐，主数据仍由 /today 页面完整呈现 */
const featuredRecipes = ref<RecommendResultItem[]>([])
const featuredLoading = ref(false)
const featuredError = ref(false)

/** 搜索关键词（回车提问语义，同 W-01 约定） */
const keyword = ref('')
const alternateHeadline = ref(false)

const homeTitle = computed(() =>
  alternateHeadline.value ? '今天想犒劳自己什么？' : '今天想用这些食材做什么？',
)

const showRecipeSteam = computed(
  () => featuredRecipes.value[0]?.title.includes('蚝油生菜') && Boolean(featuredRecipes.value[0]?.cover_image_url),
)

/** AI 创新入口是否可用（switches.innovation 未返回时默认放开） */
const innovationEnabled = computed(() => configStore.switches.innovation !== false)

/** 问答模块是否可用（§5.8：switch.qa=false → 搜索框降级为菜名/食材名精确搜索） */
const qaEnabled = computed(() => configStore.switches.qa !== false)

/** 搜索框占位文案（问答开关关闭时如实降级说明，§5.8 问答模块） */
const searchPlaceholder = computed(() =>
  qaEnabled.value ? '想吃什么或有什么食材？回车问厨娘' : '问答维护中：输入食材名，回车去精确搜索',
)

/** 已选食材列表，点击「去挑选」可在食材页继续编辑 */
const selectedIngredients = computed(() => ingredientsStore.selectedList)

/** 首页轻量展示首道安全过滤后的今日推荐；完整列表和换一换仍在 /today */
async function loadFeaturedRecipe(): Promise<void> {
  featuredLoading.value = true
  featuredError.value = false
  try {
    const response = await fetchDayMenu()
    featuredRecipes.value = selectFeaturedRecipes(response.results)
  } catch {
    featuredError.value = true
    featuredRecipes.value = []
  } finally {
    featuredLoading.value = false
  }
}

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
  void Promise.all([homeStore.load(), loadFeaturedRecipe()])
})
</script>

<template>
  <section class="home-page" aria-labelledby="home-title">
    <header class="home-heading">
      <div class="home-heading__copy">
        <p class="home-greeting">为家常的每一餐</p>
        <h1 id="home-title">{{ homeTitle }}</h1>
        <button
          class="home-title-switch"
          type="button"
          :aria-pressed="alternateHeadline"
          @click="alternateHeadline = !alternateHeadline"
        >
          <el-icon aria-hidden="true"><CoffeeCup /></el-icon>
          {{ alternateHeadline ? '换回食材灵感' : '换个问法' }}
        </button>
      </div>
      <div class="home-heading__search">
        <el-input
          v-model="keyword"
          class="home-search"
          clearable
          :placeholder="searchPlaceholder"
          @keyup.enter="onSearchEnter"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
          <template #append>
            <el-button :loading="askStore.asking" @click="onSearchEnter">
              {{ qaEnabled ? '问厨娘' : '搜索' }}
            </el-button>
          </template>
        </el-input>
      </div>
    </header>

    <AskChatCard class="home-chat" />

    <div class="home-alerts">
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

      <el-alert
        v-if="homeStore.data && !homeStore.hasProfile"
        class="home-alert"
        type="warning"
        title="还没有建立家庭档案，建好后推荐会更懂你（过敏原 / 口味 / 厨艺）"
        :closable="false"
        show-icon
      >
        <el-button size="small" type="warning" plain @click="router.push('/profile')">去建档</el-button>
      </el-alert>

      <article
        v-if="homeStore.hasUnfinished"
        class="resume-card"
        role="link"
        tabindex="0"
        @click="router.push(`/cook/${homeStore.data?.unfinished_session?.session_id}`)"
        @keydown.enter="router.push(`/cook/${homeStore.data?.unfinished_session?.session_id}`)"
      >
        <span class="aside-label">继续烹饪</span>
        <strong>{{ homeStore.data?.unfinished_session?.recipe_name }}</strong>
        <span class="resume-progress">
          第 {{ homeStore.data?.unfinished_session?.current_step }} 步，共 {{ homeStore.data?.unfinished_session?.total_steps }} 步
        </span>
        <span class="aside-action">回到这道菜 <el-icon><ArrowRight /></el-icon></span>
      </article>

      <el-alert
        v-if="showExpiryAlert"
        class="expiry-alert"
        type="warning"
        :title="expiryText"
        show-icon
        @close="dismissExpiry"
      >
        <p class="expiry-note">到期信息仅作提醒，不代表食材是否可食用</p>
        <el-button size="small" text @click="router.push('/inventory')">查看库存</el-button>
      </el-alert>
    </div>

    <div class="home-layout">
      <div class="home-primary">
        <section class="ingredient-section" aria-labelledby="ingredient-title">
          <div class="section-heading">
            <div>
              <h2 id="ingredient-title">手边的食材</h2>
              <p>从冰箱现有的东西开始</p>
            </div>
            <el-button class="text-action" text @click="router.push('/select')">
              {{ selectedIngredients.length ? '编辑食材' : '添加食材' }}
              <el-icon><ArrowRight /></el-icon>
            </el-button>
          </div>
          <TransitionGroup v-if="selectedIngredients.length" name="ingredient" tag="div" class="ingredient-list">
            <span v-for="item in selectedIngredients" :key="item.id" class="ingredient-chip">
              {{ item.name }}
            </span>
            <button
              key="add-more"
              class="ingredient-add"
              type="button"
              aria-label="添加更多食材"
              title="添加更多食材"
              @click="router.push('/select')"
            >
              <el-icon><Plus /></el-icon>
            </button>
          </TransitionGroup>
          <button v-else class="ingredient-empty" type="button" @click="router.push('/select')">
            <span class="ingredient-empty__icon"><el-icon><Plus /></el-icon></span>
            <span>选择几样手边食材，看看能做什么</span>
            <el-icon class="ingredient-empty__arrow"><ArrowRight /></el-icon>
          </button>
          <div v-if="selectedIngredients.length" class="ingredient-cta">
            <span>已选 {{ selectedIngredients.length }} 样</span>
            <el-button type="primary" @click="router.push('/recommend')">
              <span>按这些食材推荐</span><el-icon><ArrowRight /></el-icon>
            </el-button>
          </div>
        </section>

        <section class="recommend-section" aria-labelledby="recommend-title">
          <div class="section-heading section-heading--recommend">
            <div>
              <h2 id="recommend-title">今日灵感</h2>
              <p>按家庭档案过滤后的菜谱推荐</p>
            </div>
            <el-button class="text-action" text @click="router.push('/today')">
              看更多 <el-icon><ArrowRight /></el-icon>
            </el-button>
          </div>

          <div v-if="featuredLoading" class="featured-loading" aria-label="正在加载今日推荐">
            <el-skeleton animated :rows="4" />
          </div>
          <div
            v-else-if="featuredRecipes.length"
            class="featured-recipes"
            :class="{ 'featured-recipes--two': featuredRecipes.length === 2, 'featured-recipes--one': featuredRecipes.length === 1 }"
          >
            <article
              v-for="(recipe, index) in featuredRecipes"
              :key="recipe.recipe_id"
              class="featured-recipe"
            >
              <button
                class="featured-recipe__image"
                type="button"
                :aria-label="`查看菜谱：${recipe.title}`"
                @click="router.push(`/recipe/${recipe.recipe_id}`)"
              >
                <RecipeCover :src="recipe.cover_image_url" :title="recipe.title" :recipe-id="recipe.recipe_id" />
                <span v-if="index === 0 && showRecipeSteam" class="recipe-steam" aria-hidden="true"><i></i><i></i><i></i></span>
              </button>
              <div class="featured-recipe__body">
                <div class="featured-recipe__heading">
                  <h3>{{ recipe.title }}</h3>
                  <el-popover placement="top" :width="280" trigger="click">
                    <template #reference>
                      <el-button class="featured-recipe__reason" text @click.stop>推荐理由</el-button>
                    </template>
                    <ul class="featured-recipe__reason-list">
                      <li v-for="(reason, reasonIndex) in recipe.rank_reasons" :key="reasonIndex">{{ reason }}</li>
                    </ul>
                  </el-popover>
                </div>
                <div class="featured-recipe__meta">
                  <span class="recipe-meta-item"><el-icon><Clock /></el-icon>{{ recipe.time_minutes }} 分钟</span>
                  <span class="recipe-meta-item">{{ recipe.difficulty === 'easy' ? '简单' : recipe.difficulty === 'medium' ? '适中' : '较难' }}</span>
                  <span v-if="recipe.calories_kcal != null" class="recipe-meta-item">{{ recipe.calories_kcal }} kcal/份</span>
                </div>
                <div v-if="recipe.missing_ingredients.length || recipe.required_equipment.length" class="featured-recipe__tags">
                  <span
                    v-for="ingredient in recipe.missing_ingredients.slice(0, 2)"
                    :key="`missing-${ingredient}`"
                    class="featured-recipe__tag"
                  >需要 {{ ingredient }}</span>
                  <span
                    v-for="equipment in recipe.required_equipment.slice(0, 2)"
                    :key="`equipment-${equipment}`"
                    class="featured-recipe__tag"
                  >需要 {{ equipment }} 设备</span>
                  <span
                    v-if="recipe.missing_ingredients.length > 2"
                    class="featured-recipe__tag featured-recipe__tag--muted"
                  >另需 {{ recipe.missing_ingredients.length - 2 }} 样</span>
                </div>
                <div class="featured-recipe__footer">
                  <el-button type="primary" @click="router.push(`/recipe/${recipe.recipe_id}`)">
                    看做法 <el-icon><ArrowRight /></el-icon>
                  </el-button>
                </div>
              </div>
            </article>
          </div>
          <div v-else class="featured-empty">
            <p>{{ featuredError ? '今日推荐暂时没有加载出来。' : '暂时没有合适的推荐，试着换个入口看看。' }}</p>
            <el-button v-if="featuredError" text @click="loadFeaturedRecipe">
              <el-icon><Refresh /></el-icon>重试
            </el-button>
            <el-button v-else text @click="router.push('/today')">打开今日推荐 <el-icon><ArrowRight /></el-icon></el-button>
          </div>
        </section>

        <section class="quick-links" aria-label="更多厨房功能">
          <button type="button" @click="goEntry(entries[0]!)">今天吃什么 <el-icon><ArrowRight /></el-icon></button>
          <button type="button" @click="goEntry(entries[1]!)">拍照识别 <el-icon><ArrowRight /></el-icon></button>
          <button type="button" @click="goEntry(entries[2]!)">时令推荐 <el-icon><ArrowRight /></el-icon></button>
          <button type="button" @click="goEntry(entries[3]!)">饮食目标 <el-icon><ArrowRight /></el-icon></button>
          <button type="button" @click="goEntry(entries[4]!)">库存清单 <el-icon><ArrowRight /></el-icon></button>
          <button type="button" @click="goEntry(entries[5]!)">AI 创新菜 <el-icon><ArrowRight /></el-icon></button>
        </section>
      </div>

      <aside class="home-aside" aria-label="厨房提醒">
        <button
          class="seasonal-link"
          type="button"
          @click="goEntry(entries[2]!)"
        >
          <!-- 实色底衬容器：文字落在不透明深绿底上（对比 ≥12:1），
               axe color-contrast 可自动判定（原图片+渐变背景为 incomplete） -->
          <span class="seasonal-link__copy">
            <span>顺着时令做饭</span>
            <strong>看看当季食材</strong>
          </span>
          <el-icon><ArrowRight /></el-icon>
        </button>

        <div class="safety-note">
          <el-icon class="safety-note__mark" aria-hidden="true"><WarningFilled /></el-icon>
          <p>过敏原和食品安全提示会优先于推荐结果。食材临期信息仅作提醒。</p>
        </div>
        <DisclaimerBar variant="default" />
      </aside>
    </div>
  </section>
</template>

<style scoped>
.home-page {
  --home-content-inset: clamp(32px, 3.4vw, 64px);
  --home-ink: var(--text-main);
  --home-muted: color-mix(in srgb, var(--text-muted) 82%, var(--text-main));
  --home-line: var(--color-info-border);
  --home-paper: var(--page-bg);
  display: grid;
  grid-template-columns: minmax(0, 1.22fr) minmax(400px, 0.78fr);
  grid-template-rows: auto auto auto 1fr;
  min-height: 100dvh;
  max-width: none;
  margin: 0;
  color: var(--home-ink);
}

.home-heading {
  grid-column: 1;
  grid-row: 1;
  display: block;
  max-width: 900px;
  padding: 54px 40px 22px var(--home-content-inset);
}

.home-greeting {
  margin: 0 0 12px;
  color: var(--accent-deep);
  font-size: 13px;
  font-weight: 700;
}

.home-heading h1 {
  max-width: 600px;
  margin: 0;
  color: var(--home-ink);
  font-family: 'Noto Serif SC', 'Songti SC', Georgia, serif;
  font-size: 43px;
  font-weight: 600;
  line-height: 1.28;
  text-wrap: balance;
}

.home-title-switch {
  display: inline-flex;
  min-height: 36px;
  align-items: center;
  gap: 7px;
  margin-top: 10px;
  padding: 0;
  color: var(--accent-deep);
  border: 0;
  background: transparent;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: color 180ms ease;
}

.home-title-switch:hover { color: var(--accent-deep); }
.home-title-switch:focus-visible { outline: 2px solid var(--accent-deep); outline-offset: 3px; }

.home-heading__search {
  width: min(680px, 100%);
  margin-top: 22px;
}

.home-search :deep(.el-input__wrapper) {
  min-height: 48px;
  padding-left: 14px;
  border-radius: 10px 0 0 10px;
  background: var(--card-bg);
  box-shadow: 0 0 0 1px var(--home-line) inset;
}

.home-search :deep(.el-input-group__append) {
  padding: 0;
  border: 0;
  border-left: 0;
  border-radius: 0 10px 10px 0;
  background: var(--accent-deep);
  box-shadow: none;
}

.home-search :deep(.el-input-group__append .el-button) {
  min-height: 48px;
  padding: 0 20px;
  color: var(--text-on-accent);
  border: 0;
  border-radius: 0 10px 10px 0;
  background: var(--accent-deep);
}

.home-chat {
  max-width: 700px;
  grid-column: 1;
  grid-row: 2;
  margin: 0 44px 12px var(--home-content-inset);
}

.home-alerts {
  grid-column: 1;
  grid-row: 3;
  display: grid;
  gap: 10px;
  max-width: 900px;
  padding: 0 44px 0 var(--home-content-inset);
}

.home-alert {
  margin: 0;
}

.home-alert :deep(.el-alert__title) { color: var(--color-warning); }
.home-alert :deep(.el-button--warning) { color: var(--color-warning); border-color: var(--color-warning-border); }

.home-layout {
  display: contents;
}

.home-primary,
.home-aside {
  min-width: 0;
}

.home-primary {
  grid-column: 1;
  grid-row: 4;
  max-width: 900px;
  padding: 12px 44px 40px var(--home-content-inset);
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 17px;
}

.section-heading h2 {
  margin: 0;
  color: var(--home-ink);
  font-family: 'Noto Serif SC', 'Songti SC', Georgia, serif;
  font-size: 23px;
  font-weight: 600;
}

.section-heading p {
  margin: 6px 0 0;
  color: var(--home-muted);
  font-size: 13px;
}

.text-action {
  gap: 5px;
  color: var(--accent-deep) !important;
  font-size: 13px;
  font-weight: 650;
}

.ingredient-section {
  padding-bottom: 27px;
  border-bottom: 1px solid var(--home-line);
}

.ingredient-list {
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  align-items: center;
}

.ingredient-enter-active,
.ingredient-leave-active,
.ingredient-move {
  transition: opacity 180ms ease, transform 220ms cubic-bezier(0.2, 0.8, 0.2, 1);
}

.ingredient-enter-from,
.ingredient-leave-to {
  opacity: 0;
  transform: scale(0.94) translateY(3px);
}


.ingredient-chip {
  display: inline-flex;
  min-height: 38px;
  align-items: center;
  padding: 0 14px;
  color: var(--home-ink);
  border: 1px solid var(--home-line);
  border-radius: 8px;
  background: color-mix(in srgb, var(--card-bg) 62%, transparent);
  font-size: 13px;
}

.ingredient-add,
.ingredient-empty {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-deep);
  border: 1px dashed #abb8a9;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  transition: background-color 160ms ease, border-color 160ms ease, transform 160ms ease;
}

.ingredient-add {
  width: 38px;
  height: 38px;
  font-size: 16px;
}

.ingredient-empty {
  width: 100%;
  min-height: 64px;
  justify-content: flex-start;
  gap: 13px;
  padding: 10px 14px;
  color: var(--home-muted);
  border-style: solid;
  border-color: var(--home-line);
  font-size: 13px;
  text-align: left;
}

.ingredient-empty__icon {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  color: var(--accent-deep);
  border-radius: 50%;
  background: var(--accent-soft);
  font-size: 17px;
}

.ingredient-empty__arrow {
  margin-left: auto;
}

.ingredient-add:hover,
.ingredient-empty:hover {
  border-color: var(--accent-deep);
  background: var(--accent-soft);
}

.ingredient-cta {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 16px;
  margin-top: 15px;
  color: var(--home-muted);
  font-size: 12px;
}

.featured-recipe__footer :deep(.el-button) {
  min-height: 40px;
  gap: 8px;
  padding: 0 14px;
  color: var(--text-on-accent);
  border: 0;
  border-radius: 9px;
  background: var(--accent-deep);
}

.ingredient-cta :deep(.el-button) {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  gap: 8px;
  padding: 0 24px;
  color: var(--text-on-accent);
  border: 0;
  border-radius: 10px;
  background: var(--accent-deep);
  box-shadow: 0 4px 12px rgba(45, 78, 56, 0.2);
  transition: transform 160ms ease, box-shadow 160ms ease, background-color 160ms ease;
}

.ingredient-cta :deep(.el-button:not(.is-disabled):hover) {
  background: color-mix(in srgb, var(--accent-deep) 92%, white);
  box-shadow: 0 7px 16px rgba(45, 78, 56, 0.25);
}

.ingredient-cta :deep(.el-button:focus-visible) {
  outline: 2px solid var(--accent-deep);
  outline-offset: 3px;
}

.recommend-section {
  padding-top: 29px;
}

.section-heading--recommend {
  margin-bottom: 15px;
}

.featured-recipes {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: stretch;
  gap: 12px;
}

.featured-recipes--one { grid-template-columns: minmax(0, 1fr); }
.featured-recipes--two { grid-template-columns: repeat(2, minmax(0, 1fr)); }

.featured-recipe {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 12px 14px 14px;
  border: 1px solid var(--home-line);
  border-radius: 10px;
  background: var(--surface-raised);
  transition: border-color 180ms ease, box-shadow 180ms ease;
}

.featured-recipe:hover,
.featured-recipe:focus-within {
  border-color: var(--accent-deep);
  box-shadow: 0 7px 18px rgba(36, 72, 58, 0.1);
}

.featured-recipe__image {
  position: relative;
  display: block;
  width: 100%;
  min-width: 0;
  padding: 0;
  overflow: hidden;
  border: 0;
  border-radius: 8px;
  background: var(--home-paper);
  cursor: pointer;
  text-align: left;
}

.recipe-steam {
  position: absolute;
  right: 16%;
  bottom: 20%;
  display: flex;
  gap: 9px;
  width: 48px;
  height: 40px;
  pointer-events: none;
}

.recipe-steam i {
  width: 8px;
  height: 25px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.66);
  filter: blur(4px);
  opacity: 0;
  animation: recipe-steam-rise 3s ease-in-out infinite;
}

.recipe-steam i:nth-child(2) { animation-delay: 700ms; }
.recipe-steam i:nth-child(3) { animation-delay: 1400ms; }

@keyframes recipe-steam-rise {
  0% { opacity: 0; transform: translateY(12px) scaleX(0.7); }
  28% { opacity: 0.55; }
  100% { opacity: 0; transform: translateY(-15px) scaleX(1.25); }
}

.featured-recipe__image :deep(.recipe-cover) {
  aspect-ratio: 16 / 9;
  border-radius: 8px;
  transition: transform 320ms cubic-bezier(0.16, 1, 0.3, 1);
}

.featured-recipe__image:hover :deep(.recipe-cover) {
  transform: scale(1.015);
}

.featured-recipe__body {
  display: flex;
  flex-direction: column;
  gap: 9px;
  flex: 1;
  padding: 11px 2px 0;
}

.featured-recipe__heading,
.featured-recipe__meta,
.featured-recipe__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.featured-recipe__heading h3 {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--home-ink);
  font-family: 'Noto Serif SC', 'Songti SC', Georgia, serif;
  font-size: 19px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.featured-recipe__reason :deep(.el-button) {
  min-height: 30px;
  padding: 0;
  color: var(--accent-deep);
  font-size: 12px;
  white-space: nowrap;
}

.featured-recipe__reason-list {
  margin: 0;
  padding-left: 18px;
  color: var(--home-ink);
  font-size: 13px;
  line-height: 1.7;
}

.recipe-meta-item {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 4px;
  color: var(--home-muted);
  font-size: 11px;
  white-space: nowrap;
}

.featured-recipe__tags {
  display: flex;
  min-height: 27px;
  flex-wrap: wrap;
  align-content: flex-start;
  gap: 5px;
}

.featured-recipe__tag {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  min-height: 24px;
  padding: 2px 7px;
  overflow: hidden;
  /* 加深至 --text-muted 55% + --text-main 45%：浅色 ~5.9:1 / 深色 ~8.7:1，
     修复 10px 小字在 --surface-soft 底上 4.38 < 4.5 的 color-contrast 违规 */
  color: color-mix(in srgb, var(--text-muted) 55%, var(--text-main));
  border: 1px solid var(--home-line);
  border-radius: 5px;
  background: var(--surface-soft);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.featured-recipe__tag--muted {
  color: var(--accent-deep);
  background: var(--accent-soft);
}

.featured-recipe__footer {
  justify-content: flex-end;
  margin-top: auto;
  padding-top: 3px;
}

.featured-loading,
.featured-empty {
  min-height: 220px;
  padding: 28px;
  border: 1px solid var(--home-line);
  border-radius: 8px;
  background: var(--card-bg);
}

.featured-empty {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  color: var(--home-muted);
  font-size: 13px;
}

.home-aside {
  display: flex;
  grid-column: 2;
  grid-row: 1 / span 4;
  flex-direction: column;
  align-items: stretch;
  gap: 0;
  min-width: 0;
  padding: 0;
}

.seasonal-link {
  position: relative;
  display: flex;
  min-height: 560px;
  height: 100dvh;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-end;
  gap: 0;
  padding: 28px 0 0;
  color: #fffdf6;
  border: 0;
  border-radius: 0;
  background-color: var(--page-bg);
  background-image:
    linear-gradient(90deg, var(--page-bg) 0, color-mix(in srgb, var(--page-bg) 82%, transparent) 72px, transparent 220px),
    linear-gradient(270deg, var(--page-bg) 0, color-mix(in srgb, var(--page-bg) 78%, transparent) 8px, transparent 28px),
    linear-gradient(0deg, rgba(0, 0, 0, 0.42), transparent 42%),
    url('/images/kitchen-prep-reference.jpg');
  background-position: 0 0, 100% 0, 0 0, 54% center;
  background-size: auto, auto, auto, cover;
  text-align: left;
  cursor: pointer;
  transition: filter 180ms ease;
}

.seasonal-link:hover {
  filter: brightness(1.04);
}

.seasonal-link__copy {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 26px 32px 30px;
}

.seasonal-link span {
  color: rgba(255, 253, 246, 0.9);
  font-size: 12px;
}

.seasonal-link strong {
  color: #fffdf6;
  font-family: 'Noto Serif SC', 'Songti SC', Georgia, serif;
  font-size: 24px;
  font-weight: 600;
  text-shadow: 0 1px 12px rgba(0, 0, 0, 0.3);
}

.seasonal-link .el-icon {
  position: absolute;
  right: 20px;
  bottom: 33px;
  flex: 0 0 auto;
  color: #fffdf6;
  font-size: 21px;
  filter: drop-shadow(0 1px 8px rgba(0, 0, 0, 0.32));
}

.resume-card {
  display: grid;
  gap: 9px;
  padding: 14px 16px;
  border: 1px solid var(--home-line);
  border-radius: 8px;
  background: var(--surface-raised);
  cursor: pointer;
}

.home-alerts .resume-card {
  grid-template-columns: auto 1fr auto auto;
  align-items: center;
  gap: 8px 14px;
}

.home-alerts .resume-card .aside-label { grid-column: 1; }
.home-alerts .resume-card strong { grid-column: 2; }
.home-alerts .resume-progress { grid-column: 3; }
.home-alerts .resume-card .aside-action { grid-column: 4; white-space: nowrap; }

.resume-card:focus-visible {
  outline: 2px solid var(--accent-deep);
  outline-offset: 4px;
}

.aside-label {
  color: var(--accent-deep);
  font-size: 12px;
  font-weight: 700;
}

.resume-card strong {
  color: var(--home-ink);
  font-family: 'Noto Serif SC', 'Songti SC', Georgia, serif;
  font-size: 18px;
}

.resume-progress {
  color: var(--home-muted);
  font-size: 12px;
}

.aside-action {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--accent-deep);
  font-size: 12px;
  font-weight: 650;
}

.expiry-alert {
  align-items: flex-start;
}

.home-alerts .expiry-alert { width: 100%; }

.expiry-note {
  margin: 2px 0 7px;
  color: var(--color-warning);
  font-size: 12px;
  line-height: 1.5;
}

.safety-note {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px 0;
  border-top: 1px solid var(--home-line);
  color: var(--home-muted);
}

.safety-note__mark {
  display: inline-flex;
  width: 20px;
  height: 20px;
  flex: 0 0 auto;
  color: var(--color-warning);
  font-size: 17px;
}

.safety-note p {
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
}

.home-aside :deep(.disclaimer-bar) {
  padding: 11px 0 0;
  border-top: 1px solid var(--home-line);
  font-size: 11px;
  color: color-mix(in srgb, var(--home-muted) 65%, var(--home-ink));
}

.quick-links {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 29px;
  border-top: 1px solid var(--home-line);
  border-bottom: 1px solid var(--home-line);
}

.quick-links button {
  display: flex;
  min-height: 48px;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 12px;
  color: var(--home-ink);
  border: 0;
  background: transparent;
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.quick-links button:nth-child(n + 4) {
  border-top: 1px solid var(--home-line);
}

.quick-links button:hover {
  color: var(--accent-deep);
  background: rgba(255, 255, 255, 0.35);
}

.home-page button:not(.seasonal-link):not(.featured-recipe__image),
.home-page :deep(.el-button) {
  border-radius: 8px;
  transition: transform 160ms ease, color 160ms ease, background-color 160ms ease, border-color 160ms ease;
}

.home-page button:not(.seasonal-link):not(.featured-recipe__image):hover:not(:disabled),
.home-page :deep(.el-button:not(.is-disabled):hover) {
  transform: translateY(-2px);
}

.home-page .home-search :deep(.el-input-group__append .el-button) {
  border-radius: 0 10px 10px 0;
}

.home-page .home-search :deep(.el-input-group__append .el-button:not(.is-disabled):hover) {
  transform: none;
}

.home-page .home-primary .ingredient-cta :deep(.el-button) {
  border-radius: 10px;
  transition: transform 160ms ease, box-shadow 160ms ease, background-color 160ms ease;
}

.quick-links button:focus-visible,
.ingredient-add:focus-visible,
.ingredient-empty:focus-visible,
.seasonal-link:focus-visible,
.featured-recipe__image:focus-visible {
  outline: 2px solid var(--accent-deep);
  outline-offset: 3px;
}

@media (max-width: 1100px) {
  .home-page {
    --home-content-inset: 32px;
    grid-template-columns: minmax(0, 1fr);
  }

  .home-heading,
  .home-primary {
    padding-right: 32px;
    padding-left: var(--home-content-inset);
  }

  .home-heading h1 {
    font-size: 39px;
  }

  .home-chat { margin-right: 32px; margin-left: var(--home-content-inset); }
  .home-alerts { padding-right: 32px; padding-left: var(--home-content-inset); }
  .home-aside {
    grid-column: 1;
    grid-row: 5;
    padding: 0 32px 28px;
  }

  .home-alerts .resume-card {
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .home-alerts .resume-card strong { grid-column: 2; }
  .home-alerts .resume-progress { grid-column: 2; }
  .home-alerts .resume-card .aside-action { grid-column: 3; grid-row: 1 / span 2; }

  .featured-recipes { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .featured-recipes--two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .seasonal-link {
    min-height: 420px;
    height: 68dvh;
    max-height: 680px;
    background-image:
      linear-gradient(0deg, rgba(0, 0, 0, 0.42), transparent 42%),
      url('/images/kitchen-prep-reference.jpg');
    background-position: 0 0, 54% center;
    background-size: auto, cover;
  }
}

@media (max-width: 760px) {
  .home-page {
    --home-content-inset: 22px;
    display: block;
    min-height: 0;
  }

  .home-heading { padding: 32px 22px 20px; }
  .home-heading h1 { max-width: 520px; font-size: 36px; }
  .home-heading__search { width: 100%; margin-top: 20px; }
  .home-chat { margin: 0 22px 14px; }
  .home-alerts { padding: 0 22px; }

  .home-alerts .resume-card {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 7px 12px;
  }

  .home-alerts .resume-card .aside-label { grid-column: 1; }
  .home-alerts .resume-card strong { grid-column: 1 / -1; }
  .home-alerts .resume-progress { grid-column: 1; }
  .home-alerts .resume-card .aside-action { grid-column: 2; grid-row: 3; }

  .home-layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
    padding-top: 0;
  }

  .home-primary {
    grid-column: auto;
    grid-row: auto;
    padding: 18px 22px 20px;
  }

  .featured-recipes,
  .featured-recipes--two,
  .featured-recipes--one {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto;
  }

  .home-aside {
    grid-column: auto;
    grid-row: auto;
    display: flex;
    gap: 18px;
    padding: 0 22px 30px;
  }

  .seasonal-link {
    width: 100%;
    min-height: 460px;
    height: 76dvh;
    max-height: 720px;
  }

  .home-aside :deep(.disclaimer-bar),
  .safety-note {
    grid-column: 1 / -1;
  }
}

@media (max-width: 520px) {
  .home-page { --home-content-inset: 18px; }
  .home-heading { padding: 27px var(--home-content-inset) 18px; }
  .home-heading h1 { font-size: 32px; }
  .desktop-break {
    display: none;
  }

  .home-chat { margin-right: 18px; margin-left: var(--home-content-inset); }
  .home-alerts { padding-right: 18px; padding-left: var(--home-content-inset); }
  .home-primary { padding-right: 18px; padding-left: var(--home-content-inset); }
  .home-aside { padding-right: 18px; padding-left: 18px; }
  .seasonal-link { min-height: 420px; height: 72dvh; }
  .seasonal-link__copy { padding: 24px 22px 28px; }
  .seasonal-link strong { font-size: 22px; }

  .section-heading h2 {
    font-size: 21px;
  }

  .featured-recipe__image :deep(.recipe-cover) {
    aspect-ratio: 16 / 9;
  }

  .featured-recipe__body {
    gap: 9px;
    padding: 10px 2px 0;
  }

  .featured-recipe__heading h3 {
    font-size: 18px;
  }

  .featured-empty {
    min-height: 130px;
    align-items: flex-start;
    flex-direction: column;
  }

  .quick-links {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .quick-links button:nth-child(n + 3) {
    border-top: 1px solid var(--home-line);
  }

  .ingredient-cta {
    flex-wrap: wrap;
    gap: 10px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .home-page *,
  .home-page *::before,
  .home-page *::after {
    scroll-behavior: auto;
    transition-duration: 0.01ms !important;
    animation: none !important;
  }
}

</style>
