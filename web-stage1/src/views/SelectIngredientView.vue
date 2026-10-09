<script setup lang="ts">
/**
 * 视图职责：W-01 食材选择页（手选简版，对齐 UI 清单 W-01 行）。
 * 区块：① 顶部搜索框（食材过滤 + 回车走统一 ask 消费链路 stores/ask.submitQuestion；
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
import type { Ingredient } from '@/api/types'
import { useIngredientsStore } from '@/stores/ingredients'
import { useAskStore } from '@/stores/ask'
import { useConfigStore } from '@/stores/config'
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

// 挂载：回填首页降级搜索词（?q=，触发本地过滤与防抖远程搜索），并拉取全量食材
onMounted(() => {
  const q = typeof route.query.q === 'string' ? route.query.q.trim() : ''
  if (q) keyword.value = q
  void ingredientsStore.loadIngredients()
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
  padding-bottom: 72px;
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

.category-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 18px;
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
  border: 1px solid var(--color-info-border);
  border-radius: 8px;
  background: var(--card-bg);
  color: var(--text-main);
  font-size: var(--font-md);
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease;
}

.ing-card:hover {
  border-color: var(--el-color-primary);
}

.ing-card--selected {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  font-weight: 600;
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
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  background: var(--card-bg);
  border-top: 1px solid var(--color-info-border);
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.06);
}

.footer-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  max-width: var(--page-max-width);
  margin: 0 auto;
  padding: 10px 16px;
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
  font-size: var(--font-md);
}
</style>
