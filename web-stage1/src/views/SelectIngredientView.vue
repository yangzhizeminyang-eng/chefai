<script setup lang="ts">
/**
 * 视图职责：W-01 食材选择页（手选简版，对齐 UI 清单 W-01 行）。
 * 区块：⓪ 菜谱搜索结果条（DEF-02：消费 ?q=，先调 GET /v1/recipes?q= 菜谱搜索，
 *          命中 ≥1 条 → 顶部呈现「找到 N 道含「q」的菜谱」结果条（可点进详情、
 *          可关闭、可展开全部），同时保留食材页正常功能；
 *          未命中菜谱 → 回退食材名定位（关键词过滤到该食材，若命中）；
 *          双双未命中 → 既有「试试更宽泛的关键词」空态，不新增空态；
 *          q 消费完成后 router.replace 清理 query，避免刷新重复触发）
 *       ① 顶部搜索框（食材过滤 + 回车走统一 ask 消费链路 stores/ask.submitQuestion；
 *          空输入单条提示、提问与过滤 if/else 互斥，杜绝多路 toast 同时触发；
 *          chat 回答就地展示 AskChatCard；recipe_search 落推荐态跳 W-02；blocked 跳 W-05）
 *       ② 分类栏（全部 + 10 类，映射 store categories）
 *       ③ 食材网格（点选高亮 / 再点取消）
 *       ④ 底部固定操作条「已选 N 样 + 去推荐」。
 * 三态：加载 = 网格骨架屏；空 = 「试试更宽泛的关键词」；异常 = el-alert + 重试；
 *       未选食材点「去推荐」→ toastWarning「请先选择至少 1 样食材」（仅手选路径触发）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Check } from '@element-plus/icons-vue'
import type { Ingredient, RecipeSearchItem } from '@/api/types'
import { getRecipes } from '@/api/endpoints'
import { useIngredientsStore } from '@/stores/ingredients'
import { useAskStore } from '@/stores/ask'
import { useConfigStore } from '@/stores/config'
import { classifyQueryResult } from '@/utils/searchRouting'
import { toastInfo, toastWarning } from '@/utils/toast'
import AskChatCard from '@/components/AskChatCard.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'

/** 路由（跳转 /recommend、/blocked 用；读 ?q= 回填首页降级搜索词） */
const route = useRoute()
const router = useRouter()
/** 食材 store：分类 / 列表三态 / 已选 */
const ingredientsStore = useIngredientsStore()
/** 统一 ask 消费 store（空输入提示 / 意图分流 / chat 态） */
const askStore = useAskStore()
/** 远程开关 store（qa 开关闭守卫，§5.8 问答模块） */
const configStore = useConfigStore()

/** 问答模块是否可用（switch.qa=false → 回车提问分支降级为本地精确过滤） */
const qaEnabled = computed(() => configStore.switches.qa !== false)

/** 搜索关键词（即时过滤 + 回车提问双语义） */
const keyword = ref('')
/** 当前激活分类（'' = 全部） */
const activeCategory = ref('')
/** 后端搜索防抖定时器 */
let searchTimer: ReturnType<typeof setTimeout> | null = null

/** 提问意图判定正则：含疑问词/问号等视为「提问」而非纯过滤 */
const QUESTION_PATTERN = /[?？]|吗|呢|怎么|怎样|如何|什么|哪些|多少|能不能|可不可以|行不行|可以|推荐/

/** 菜谱结果条展示关键词（qBarKeyword = 消费的 ?q=） */
const qBarKeyword = ref('')
/** 菜谱结果条条目（默认首页搜索 3 条，展开后拉更多） */
const recipeHits = ref<RecipeSearchItem[]>([])
/** 菜谱搜索总命中数 */
const recipeTotal = ref(0)
/** 是否展示菜谱结果条（用户手动关闭后不再出现） */
const showRecipeBar = ref(false)
/** 结果条是否已展开（展开后拉取 page_size=20） */
const barExpanded = ref(false)

/** 底部已选摘要：最多展示前 6 个食材名 */
const selectedPreview = computed(() => {
  const names = ingredientsStore.selectedList.map((s) => s.name)
  if (names.length <= 6) return names.join('、')
  return `${names.slice(0, 6).join('、')} 等 ${names.length} 样`
})

/**
 * 本地可见列表：在 store.list 基础上做关键词即时过滤（名称 + 别名，忽略大小写）。
 * @returns 过滤后的食材数组
 */
const visibleList = computed<Ingredient[]>(() => {
  const t = keyword.value.trim().toLowerCase()
  if (!t) return ingredientsStore.list
  return ingredientsStore.list.filter((ing) => {
    if (ing.name.toLowerCase().includes(t)) return true
    return (ing.aliases ?? []).some((a) => a.toLowerCase().includes(t))
  })
})

/**
 * 判断输入文本是否像食材名（命中当前列表的名称或别名，双向包含）。
 * @param text 用户输入
 * @returns 是否命中食材
 */
function matchesIngredientText(text: string): boolean {
  const t = text.trim()
  if (!t) return false
  return ingredientsStore.list.some((ing) => {
    if (ing.name === t || ing.name.includes(t) || t.includes(ing.name)) return true
    return (ing.aliases ?? []).some((a) => a === t || a.includes(t) || t.includes(a))
  })
}

/**
 * 按当前分类 + 关键词重新拉取食材列表（后端含别名搜索）。
 * @returns 无
 */
function reloadList(): void {
  void ingredientsStore.loadIngredients(
    activeCategory.value || undefined,
    keyword.value.trim() || undefined,
  )
}

/**
 * 搜索框回车：三分支 if/else 互斥（修复 M1/N5 三路 toast 同时弹出）。
 * - 空输入 → 交由 ask store 出单条「请输入内容」提示，不发请求、不触发其他分支；
 * - 命中本地食材名/别名 → 纯过滤（过滤已随输入即时完成，不发请求、无 toast）；
 * - 含疑问词或长度 > 4 且非食材名 → 统一 ask 消费链路（stores/ask.submitQuestion）：
 *   blocked 跳 W-05 / recipe_search 落推荐态跳 W-02 / chat 就地展示 / 失败单一降级；
 *   qa 开关关闭（§5.8 问答模块）→ 降级为本地食材名精确过滤并单条说明，不发起 ask。
 * 分支互斥保证每次回车至多一条提示；ask 成功后页面跳转离开，
 * 不再同时出现「请先选择至少 1 样食材」守卫提示与「试试更宽泛的关键词」空态。
 * @returns 无
 */
function onSearchEnter(): void {
  const text = keyword.value.trim()
  // 分支 1（空输入）：单条提示即返回，绝不继续触发过滤/ask 分支
  if (!text) {
    void askStore.submitQuestion(text)
    return
  }
  const ingredientish = matchesIngredientText(text)
  // 分支 2（纯过滤意图）：静默完成，无提示
  if (ingredientish) {
    return
  }
  // 分支 3（提问意图）：qa 关闭时降级为本地精确过滤（即时过滤已随输入生效）
  if (!qaEnabled.value) {
    toastInfo('问答功能维护中，仅支持食材名精确搜索')
    return
  }
  if (QUESTION_PATTERN.test(text) || text.length > 4) {
    void askStore.submitQuestion(text)
  }
}

/**
 * 空态行动：清空关键词与分类回到全量列表（§5.3 空态必须图标 + 文案 + 下一步行动按钮）。
 * @returns 无
 */
function resetSearch(): void {
  keyword.value = ''
  activeCategory.value = ''
}

/**
 * 点击「去推荐」：未选食材给单条警示（grouping 防堆叠），已选则跳 W-02 手选推荐。
 * @returns 无
 */
function goRecommend(): void {
  if (ingredientsStore.selectedCount === 0) {
    toastWarning('请先选择至少 1 样食材')
    return
  }
  void router.push('/recommend')
}

/**
 * 消费路由 ?q= 查询词（DEF-02：首页短菜名/降级搜索跳转带来的查询词不再丢失）。
 * 流程：先保证食材库就绪 → 调 GET /v1/recipes?q= 菜谱搜索 → 按 classifyQueryResult 分类：
 * - 命中菜谱 → 顶部呈现结果条（最多 3 条 + 展开全部），关键词置空保留食材页全量功能；
 * - 未命中菜谱但命中食材 → 回退食材名定位（关键词过滤到该食材，防抖远程搜索照常）；
 * - 双双未命中 → 关键词照常回填，走既有「试试更宽泛的关键词」空态（不新增空态）。
 * 处理完成后 router.replace 清理 q（不重挂组件），避免刷新重复触发搜索。
 * @param q 查询词（空串时仅加载食材库，不做搜索）
 * @returns 无
 */
async function consumeQueryQ(q: string): Promise<void> {
  // 食材库先就绪（回退定位判定依赖全量列表）
  if (!ingredientsStore.list.length) {
    await ingredientsStore.loadIngredients()
  }
  if (!q) return
  let hits: RecipeSearchItem[] = []
  let total = 0
  try {
    const res = await getRecipes({ q, page: 1, page_size: 3 })
    hits = res.items ?? []
    total = res.total ?? hits.length
  } catch {
    // 菜谱搜索失败：按未命中处理回退食材定位，不阻塞食材页主功能
    hits = []
  }
  const kind = classifyQueryResult(hits, q, ingredientsStore.list)
  if (kind === 'recipes') {
    // 命中菜谱：顶部结果条；关键词保持为空，食材网格保留全量可选
    qBarKeyword.value = q
    recipeHits.value = hits
    recipeTotal.value = total
    barExpanded.value = false
    showRecipeBar.value = true
  } else {
    // 回退食材名定位（ingredient 过滤命中 / none 走既有空态）
    keyword.value = q
  }
  // q 已消费：清理 query，防止刷新后重复触发搜索
  const clearedQuery = { ...route.query }
  delete clearedQuery.q
  void router.replace({ query: clearedQuery })
}

/**
 * 展开菜谱结果条：拉取更多命中条目（page_size=20，失败保持当前 3 条）。
 * @returns 无
 */
async function expandRecipeHits(): Promise<void> {
  barExpanded.value = true
  try {
    const res = await getRecipes({ q: qBarKeyword.value, page: 1, page_size: 20 })
    recipeHits.value = res.items ?? []
  } catch {
    // 展开失败保持当前条目，不打断浏览
  }
}

/**
 * 关闭菜谱结果条（用户手动交互后可关闭，本次停留不再出现）。
 * @returns 无
 */
function closeRecipeBar(): void {
  showRecipeBar.value = false
}

// 关键词变化：400ms 防抖后走后端搜索（含别名匹配）；清空则按当前分类重拉
watch(keyword, (val) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    void ingredientsStore.loadIngredients(
      activeCategory.value || undefined,
      val.trim() || undefined,
    )
  }, 400)
})

// 分类切换：立即按新分类 + 当前关键词重拉
watch(activeCategory, () => {
  reloadList()
})

// 挂载：消费首页跳转带来的 ?q=（先搜菜谱、再回退食材定位），并拉取全量食材
onMounted(() => {
  const q = typeof route.query.q === 'string' ? route.query.q.trim() : ''
  void consumeQueryQ(q)
})
</script>

<template>
  <section class="page-card select-page">
    <h1 class="page-title">今天吃什么？先选食材</h1>

    <!-- ① 搜索框：过滤 + 回车提问双语义 -->
    <el-input
      v-model="keyword"
      class="search-input"
      size="large"
      clearable
      placeholder="搜索食材，或直接输入问题回车"
      @keyup.enter="onSearchEnter"
    />

    <!-- ⓪ 菜谱搜索结果条（DEF-02）：?q= 命中菜谱时顶部呈现，可点进详情、可关闭、可展开 -->
    <div v-if="showRecipeBar" class="q-recipe-bar">
      <div class="q-bar-head">
        <span class="q-bar-title">找到 {{ recipeTotal }} 道含「{{ qBarKeyword }}」的菜谱</span>
        <el-button link size="small" @click="closeRecipeBar">关闭</el-button>
      </div>
      <div class="q-bar-list">
        <button
          v-for="r in recipeHits"
          :key="r.id"
          type="button"
          class="q-bar-item"
          @click="router.push(`/recipe/${r.id}`)"
        >
          {{ r.title }}
        </button>
        <el-button
          v-if="!barExpanded && recipeTotal > recipeHits.length"
          link
          size="small"
          type="primary"
          @click="expandRecipeHits"
        >
          查看全部 {{ recipeTotal }} 道
        </el-button>
      </div>
    </div>

    <!-- chat 就地展示卡：受限问答结果（含问句回显与免责小字），无内容不渲染 -->
    <AskChatCard class="select-chat" />

    <!-- ② 分类栏：全部 + 十类 -->
    <div class="category-bar">
      <el-check-tag :checked="activeCategory === ''" @change="activeCategory = ''">全部</el-check-tag>
      <el-check-tag
        v-for="cat in ingredientsStore.categories"
        :key="cat.code"
        :checked="activeCategory === cat.code"
        @change="activeCategory = cat.code"
      >
        {{ cat.label }}
      </el-check-tag>
    </div>

    <!-- 异常态：列表加载失败 + 重试 -->
    <el-alert
      v-if="ingredientsStore.error"
      type="error"
      :title="ingredientsStore.error.message"
      :closable="false"
      show-icon
    >
      <el-button size="small" type="primary" plain @click="reloadList">重试</el-button>
    </el-alert>

    <template v-else>
      <!-- 加载态：网格骨架屏 -->
      <div v-if="ingredientsStore.loading" class="ing-grid">
        <div v-for="n in 12" :key="n" class="ing-card ing-card--skeleton">
          <el-skeleton :rows="1" animated />
        </div>
      </div>

      <!-- 空态：搜索无结果（§5.3 空态必须含下一步行动按钮） -->
      <el-empty v-else-if="visibleList.length === 0" description="试试更宽泛的关键词">
        <el-button type="primary" size="small" @click="resetSearch">查看全部食材</el-button>
      </el-empty>

      <!-- ③ 食材网格：点选高亮 / 再点取消 -->
      <div v-else class="ing-grid">
        <button
          v-for="ing in visibleList"
          :key="ing.id"
          type="button"
          class="ing-card"
          :class="{ 'ing-card--selected': !!ingredientsStore.selected[ing.id] }"
          @click="ingredientsStore.toggle(ing)"
        >
          <span class="ing-name">{{ ing.name }}</span>
          <el-icon v-if="ingredientsStore.selected[ing.id]" class="ing-check" :size="16">
            <Check />
          </el-icon>
        </button>
      </div>
    </template>

    <!-- 页面级免责条（G-02） -->
    <DisclaimerBar variant="default" />
  </section>

  <!-- ④ 底部固定操作条：已选 N 样 + 去推荐 -->
  <div class="select-footer">
    <div class="footer-inner">
      <div class="footer-info">
        <span class="footer-count">已选 {{ ingredientsStore.selectedCount }} 样</span>
        <span v-if="selectedPreview" class="footer-names">{{ selectedPreview }}</span>
        <el-button
          v-if="ingredientsStore.selectedCount > 0"
          link
          size="small"
          @click="ingredientsStore.clear()"
        >
          清空
        </el-button>
      </div>
      <el-button type="primary" size="large" class="footer-btn" @click="goRecommend">
        去推荐
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.select-page {
  padding: 0 0 96px;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.search-input {
  max-width: 560px;
  margin-bottom: 14px;
}

/* ── chat 结果卡（AskChatCard）与搜索框间距 ── */
.select-chat {
  max-width: 560px;
  margin-bottom: 14px;
}

/* ── 菜谱搜索结果条（DEF-02）── */
.q-recipe-bar {
  max-width: 560px;
  margin-bottom: 14px;
  padding: 10px 14px;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 10px;
  background: var(--el-color-primary-light-9);
}

.q-bar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.q-bar-title {
  font-size: var(--font-sm);
  font-weight: 600;
  color: var(--text-main);
}

.q-bar-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.q-bar-item {
  padding: 4px 12px;
  border: 1px solid var(--el-color-primary-light-5);
  border-radius: 999px;
  background: var(--card-bg);
  color: var(--el-color-primary);
  font-size: var(--font-sm);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.q-bar-item:hover {
  background: var(--el-color-primary-light-8);
}

.category-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 20px;
  margin: 2px 0 20px;
  border-bottom: 1px solid var(--sidebar-line);
}

.category-bar :deep(.el-check-tag) {
  padding: 7px 2px 9px;
  border: 0;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  background: transparent;
  color: var(--text-muted);
  font-size: var(--font-sm);
  line-height: 1.4;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.category-bar :deep(.el-check-tag:hover) {
  color: var(--text-main);
}

.category-bar :deep(.el-check-tag.is-checked) {
  border-bottom-color: var(--accent-deep);
  background: transparent;
  color: var(--accent-deep);
  font-weight: 600;
}

.ing-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(108px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.ing-card {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 48px;
  padding: 10px 8px;
  border: 1px solid var(--sidebar-line);
  border-radius: 8px;
  background: transparent;
  color: var(--text-main);
  font-size: var(--font-md);
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.ing-card:hover {
  border-color: var(--line-strong);
  background: var(--surface-hover);
}

.ing-card--selected {
  border-color: var(--el-color-primary);
  background: var(--sidebar-active);
  font-weight: 600;
}

.ing-card--selected:hover {
  border-color: var(--el-color-primary);
  background: var(--sidebar-active);
}

.ing-card:focus-visible {
  outline: 2px solid var(--accent-deep);
  outline-offset: 2px;
}

.ing-card--skeleton {
  cursor: default;
}

.ing-check {
  position: absolute;
  top: 6px;
  right: 6px;
  color: var(--el-color-primary);
}

/* ── 底部固定操作条 ── */
.select-footer {
  position: fixed;
  left: var(--sidebar-width);
  right: 0;
  bottom: 0;
  z-index: 20;
  background: var(--page-bg);
  border-top: 1px solid var(--sidebar-line);
}

.footer-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  max-width: 1520px;
  margin: 0 auto;
  padding: 12px clamp(24px, 4vw, 72px);
}

.footer-info {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.footer-count {
  flex-shrink: 0;
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--el-color-primary);
}

.footer-names {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-sm);
  color: var(--color-info);
}

.footer-btn {
  min-width: 132px;
  min-height: 44px;
  border-radius: 10px;
  box-shadow: 0 3px 10px rgba(36, 72, 58, 0.14);
  font-size: var(--font-md);
}

.footer-btn:hover {
  box-shadow: 0 4px 12px rgba(36, 72, 58, 0.2);
}

@media (max-width: 900px) {
  .select-footer {
    left: 0;
  }

  .footer-inner {
    padding-right: 24px;
    padding-left: 24px;
  }
}

@media (max-width: 560px) {
  .select-page {
    padding-bottom: 88px;
  }

  .category-bar {
    column-gap: 16px;
  }

  .footer-inner {
    gap: 10px;
    padding: 10px 18px;
  }

  .footer-info {
    gap: 7px;
  }

  .footer-names {
    max-width: 36vw;
  }

  .footer-btn {
    min-width: 104px;
    padding-right: 14px;
    padding-left: 14px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .category-bar :deep(.el-check-tag),
  .ing-card {
    transition: none;
  }
}
</style>
