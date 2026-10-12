<script setup lang="ts">
/**
 * 视图职责：时令吃什么页（/seasonal，对齐 spec「首页双入口重构」方案 B）。
 * 区块：① 标题「时令吃什么」+ 月份副标题（month 取服务端响应，未加载时不显示月份数字）；
 *       ② 未建档黄条（同 HomeView：homeStore.data && !homeStore.hasProfile → 去建档引导，不阻断浏览）；
 *       ③ 合规说明条（RL-3 红线，固定文案一字不改：当季信息仅为食材供应参考，
 *          不代表食材品质或营养优劣）；
 *       ④ 当季食材区（el-tag 多选：点选/取消 + 全选/清空，选中集合为不可变 Set 纯函数维护）；
 *       ⑤ 主操作「用这些去推荐」（选中 ≥1 才可用）：把选中食材预置进 ingredientsStore
 *          已选集合（复用 SelectIngredientView 同款 toggle 写入方法与 {id, name} 结构，
 *          数量档由推荐请求统一映射默认档 enough），随后跳 /recommend（已预置不再被
 *          无食材守卫拦截）；
 *       ⑥ 当季菜谱区（el-divider + RecipeCard 栅格，show-coverage=false——当季菜谱
 *          无覆盖率语义；菜谱空但食材非空时轻提示不报错）；
 *       ⑦ 兜底「看看全部食材库」→ /select。
 * 三态：加载 = 骨架屏；异常 = el-alert + 重试；数据缺失（后端降级 ingredients 为空，
 * HTTP 恒 200）= el-empty「当月时令数据待补充」+ 兜底入口，不留白不报错。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchSeasonal } from '@/api/seasonal'
import type { SeasonalIngredient, SeasonalResponse } from '@/api/seasonal'
import type { ApiError } from '@/api/types'
import { useIngredientsStore } from '@/stores/ingredients'
import { useHomeStore } from '@/stores/home'
import { seasonalSubtitle, toggleSeasonalId } from '@/utils/seasonal'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import RecipeCard from '@/components/RecipeCard.vue'

/** 路由（转推荐跳 /recommend、兜底跳 /select、黄条跳 /profile） */
const router = useRouter()
/** 已选食材 store：转推荐时把选中当季食材预置进已选集合（复用 toggle 写入方法） */
const ingredientsStore = useIngredientsStore()
/** 首页聚合 store：未建档黄条数据源（条件用法同 HomeView，只读复用） */
const homeStore = useHomeStore()

/** 时令响应数据（null = 未加载/降级前） */
const seasonal = ref<SeasonalResponse | null>(null)
/** 时令数据加载中标记 */
const loading = ref(false)
/** 时令数据加载错误（归一化 ApiError，null 表示无错） */
const error = ref<ApiError | null>(null)
/** 已选中的当季食材 ID 集合（不可变更新，增删走 toggleSeasonalId 纯函数） */
const selectedIds = ref(new Set<number>())
/** 「用这些去推荐」请求/跳转进行中标记（按钮 loading 态） */
const going = ref(false)

/** 月份副标题：month 来自服务端，未加载/异常时不显示月份数字（纯函数生成） */
const subtitle = computed(() => seasonalSubtitle(seasonal.value?.month))

/** 数据缺失判定：请求成功但后端降级无当季数据（!error 且 ingredients 为空） */
const noData = computed(() => !error.value && (seasonal.value?.ingredients.length ?? 0) === 0)

/**
 * 点击当季食材标签：切换选中态（不可变替换 ref 值保证响应式触发）。
 * @param ing 被点击的当季食材
 * @returns 无
 */
function toggleSelect(ing: SeasonalIngredient): void {
  selectedIds.value = toggleSeasonalId(selectedIds.value, ing.id)
}

/**
 * 全选：把全部当季食材 ID 一次性加入选中集合。
 * @returns 无
 */
function selectAll(): void {
  selectedIds.value = new Set((seasonal.value?.ingredients ?? []).map((i) => i.id))
}

/**
 * 清空：重置选中集合为空。
 * @returns 无
 */
function clearSelection(): void {
  selectedIds.value = new Set()
}

/**
 * 主操作「用这些去推荐」：把选中食材预置进 ingredientsStore 已选集合后跳 /recommend。
 * 写入严格复用 SelectIngredientView 的 toggle 方法（结构 {id, name}，已存在的不重复
 * 加入也不取消——仅对「本页新选中且尚不在已选集合」的食材触发加入侧 toggle），
 * quantity_level 不在此处指定，由推荐请求统一映射默认档 enough。
 * @returns 无
 */
async function goRecommend(): Promise<void> {
  if (selectedIds.value.size === 0 || going.value) return
  going.value = true
  try {
    for (const ing of seasonal.value?.ingredients ?? []) {
      if (selectedIds.value.has(ing.id) && !ingredientsStore.selected[ing.id]) {
        ingredientsStore.toggle({ id: ing.id, name: ing.name, category: ing.category })
      }
    }
    // 已预置 ≥1 样食材，/recommend 的无食材守卫不会拦截
    await router.push('/recommend')
  } finally {
    going.value = false
  }
}

/**
 * 兜底入口「看看全部食材库」：跳食材选择页 W-01。
 * @returns 无
 */
function goSelect(): void {
  void router.push('/select')
}

/**
 * 拉取当月时令数据（维护三态；失败不清空已有数据仅置 error 供重试）。
 * @returns 无
 */
async function loadSeasonal(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    seasonal.value = await fetchSeasonal()
  } catch (e) {
    error.value = e as ApiError
  } finally {
    loading.value = false
  }
}

// 挂载：拉取时令数据；home 聚合未就绪（直达/刷新进入）时补拉一次，
// 保证未建档黄条条件（homeStore.data && !homeStore.hasProfile）可正常判定
onMounted(() => {
  void loadSeasonal()
  if (!homeStore.data) void homeStore.load()
})
</script>

<template>
  <section class="page-card seasonal-page">
    <h1 class="page-title">时令吃什么</h1>
    <p class="seasonal-subtitle">{{ subtitle }}</p>

    <!-- ② 未建档黄条（同 HomeView 条件：聚合数据已加载且未建档；不阻断浏览） -->
    <el-alert
      v-if="homeStore.data && !homeStore.hasProfile"
      class="seasonal-alert"
      type="warning"
      title="还没有建立家庭档案，建好后推荐会更懂你（过敏原 / 口味 / 厨艺）"
      :closable="false"
      show-icon
    >
      <el-button size="small" type="warning" plain @click="router.push('/profile')">
        去建档
      </el-button>
    </el-alert>

    <!-- ③ 合规说明条（RL-3 红线，固定文案一字不改） -->
    <el-alert
      class="seasonal-alert"
      type="info"
      title="当季信息仅为食材供应参考，不代表食材品质或营养优劣"
      :closable="false"
      show-icon
    />

    <!-- 异常态：加载失败 + 重试 -->
    <el-alert
      v-if="error"
      class="seasonal-alert"
      type="error"
      :title="error.message"
      :closable="false"
      show-icon
    >
      <el-button size="small" type="primary" plain @click="loadSeasonal">重试</el-button>
    </el-alert>

    <!-- 加载态：食材标签区 + 菜谱卡栅格骨架 -->
    <template v-if="loading">
      <div class="tag-skeleton">
        <el-skeleton :rows="2" animated />
      </div>
      <div class="card-list">
        <div v-for="n in 4" :key="n" class="card-skeleton">
          <el-skeleton :rows="3" animated />
        </div>
      </div>
    </template>

    <!-- 数据缺失态：后端降级（无当季映射/异常）→ 空态兜底，不留白不报错 -->
    <el-empty v-else-if="noData" description="当月时令数据待补充">
      <el-button type="primary" @click="goSelect">看看全部食材库</el-button>
    </el-empty>

    <!-- ④⑤⑥ 正常态：当季食材区 + 主操作 + 当季菜谱区 -->
    <template v-else>
      <!-- 当季食材区：区标题 + 全选/清空 + 可多选标签 -->
      <div class="seasonal-toolbar">
        <span class="section-title">当季食材</span>
        <span class="toolbar-actions">
          <el-button link type="primary" size="small" @click="selectAll">全选</el-button>
          <el-button link size="small" @click="clearSelection">清空</el-button>
        </span>
      </div>
      <div class="seasonal-tags">
        <el-tag
          v-for="ing in seasonal?.ingredients ?? []"
          :key="ing.id"
          class="seasonal-tag"
          :type="selectedIds.has(ing.id) ? 'primary' : 'info'"
          :effect="selectedIds.has(ing.id) ? 'dark' : 'plain'"
          @click="toggleSelect(ing)"
        >
          {{ ing.name }}
        </el-tag>
      </div>

      <!-- 主操作：选中 ≥1 才可用；点击预置已选集合并跳推荐（请求/跳转中 loading） -->
      <el-button
        class="go-recommend-btn"
        type="primary"
        size="large"
        :disabled="selectedIds.size === 0"
        :loading="going"
        @click="goRecommend"
      >
        {{ going ? '正在跳转推荐…' : `用这些去推荐${selectedIds.size > 0 ? `（已选 ${selectedIds.size} 样）` : ''}` }}
      </el-button>

      <!-- ⑥ 当季菜谱区：硬过滤后的 ≤8 道当季菜（无覆盖率语义，卡片隐藏覆盖率列） -->
      <el-divider class="recipe-divider">当季菜谱</el-divider>
      <template v-if="(seasonal?.recipes ?? []).length > 0">
        <div class="card-list">
          <RecipeCard
            v-for="item in seasonal?.recipes ?? []"
            :key="item.recipe_id"
            :item="item"
            :show-coverage="false"
          />
        </div>
      </template>
      <!-- 菜谱空但食材非空：轻提示不报错，食材区与主操作照常可用 -->
      <p v-else class="recipe-empty-hint">当季菜谱暂时为空</p>

      <!-- ⑦ 兜底入口 -->
      <div class="seasonal-footer">
        <el-button link type="primary" @click="goSelect">看看全部食材库</el-button>
      </div>
    </template>

    <!-- 页面级免责条（G-02） -->
    <DisclaimerBar variant="default" />
  </section>
</template>

<style scoped>
/* ── 副标题（月份来自服务端，未加载时无月份数字） ── */
.seasonal-subtitle {
  margin: -6px 0 14px;
  font-size: var(--font-md);
  color: var(--color-info);
}

.seasonal-alert {
  margin-bottom: 14px;
}

/* ── 加载骨架 ── */
.tag-skeleton {
  margin-bottom: 18px;
}

.card-skeleton {
  padding: 14px 16px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
  background: var(--card-bg);
}

/* ── ④ 当季食材区 ── */
.seasonal-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.section-title {
  font-size: var(--font-lg);
  font-weight: 600;
  color: var(--text-main);
}

.toolbar-actions {
  display: flex;
  align-items: center;
}

.seasonal-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}

/* 标签可点选：手型光标 + 悬停描边提示可交互 */
.seasonal-tag {
  padding: 6px 14px;
  font-size: var(--font-md);
  cursor: pointer;
  user-select: none;
  transition:
    border-color 0.15s ease,
    background-color 0.15s ease;
}

.seasonal-tag:hover {
  border-color: var(--el-color-primary);
}

/* ── ⑤ 主操作 ── */
.go-recommend-btn {
  min-width: 200px;
  min-height: 44px;
}

/* ── ⑥ 当季菜谱区（栅格口径与 RecommendView .card-list 一致） ── */
.recipe-divider {
  margin: 22px 0 14px;
}

.card-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}

.recipe-empty-hint {
  margin: 4px 0 0;
  font-size: var(--font-sm);
  color: var(--color-info);
}

/* ── ⑦ 兜底入口 ── */
.seasonal-footer {
  margin-top: 20px;
  text-align: center;
}
</style>
