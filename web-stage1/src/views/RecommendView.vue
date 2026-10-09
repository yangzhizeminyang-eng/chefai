<script setup lang="ts">
/**
 * 视图职责：W-02 推荐结果列表页（对齐 UI 清单 W-02 行与架构文档 §9.2 响应示例）。
 * 区块：① 食材摘要（可编辑 → 返回 W-01）+「显示被我过滤掉的菜」开关
 *       ② 三档分组（✅现在就能做 / 🛒差1–2样 / 💡需要多买几样）
 *       ③ 推荐卡片（菜名/耗时/难度/热量/覆盖率/缺失食材/设备标注）
 *       ④ 「为什么推荐给你」（rank_reasons 弹层）
 *       ⑤ 被过滤清单/计数（双模式）+ 部分失败说明条 + 不足 8 条如实说明 + 免责小字。
 * 三态：加载 = 骨架屏 +「正在为你挑选…」；空 = 「放宽到差 1–2 样」/「补充食材」；异常 = el-alert + 重试。
 */
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { RecommendResultItem } from '@/api/types'
import { useIngredientsStore } from '@/stores/ingredients'
import { useRecommendStore } from '@/stores/recommend'
import { coveragePercent, groupResults } from '@/utils/recipe'
import DisclaimerBar from '@/components/DisclaimerBar.vue'

/** 路由（卡片跳详情 / 编辑食材回 W-01 / 阻断跳 W-05） */
const router = useRouter()
/** 推荐 store：三档结果 / 加载态 / 过滤数据 / trace */
const recommendStore = useRecommendStore()
/** 食材 store（已选数量校验） */
const ingredientsStore = useIngredientsStore()

/** 三档分组定义（顺序即展示顺序） */
const GROUPS = [
  { level: 'can_cook_now', title: '✅ 现在就能做' },
  { level: 'missing_1_2', title: '🛒 差 1–2 样' },
  { level: 'need_more', title: '💡 需要多买几样' },
] as const

/** 难度编码 → 中文标签（契约 difficulty: easy/medium/hard） */
const DIFFICULTY_LABELS: Record<RecommendResultItem['difficulty'], string> = {
  easy: '简单',
  medium: '中等',
  hard: '较难',
}

/** 三档分组结果（复用 utils/recipe.groupResults；未知 match_level 条目不落入任何档） */
const grouped = computed(() => {
  const buckets = groupResults(recommendStore.results)
  return GROUPS.map((g) => ({ ...g, items: buckets[g.level] }))
})

/** 被过滤计数摘要（计数模式文案；total=0 返回空串） */
const filteredSummary = computed(() => {
  const f = recommendStore.filtered
  const total = (f.allergen ?? 0) + (f.dietary_restriction ?? 0) + (f.difficulty ?? 0)
  if (total === 0) return ''
  return `共过滤 ${total} 道：过敏原 ${f.allergen ?? 0} 道 / 忌口 ${f.dietary_restriction ?? 0} 道 / 难度 ${f.difficulty ?? 0} 道`
})

/** 不足 8 条如实说明（不为凑数填充低质推荐） */
const insufficientNotice = computed(() => {
  const n = recommendStore.results.length
  if (n === 0 || n >= 8) return ''
  return `本次为你匹配到 ${n} 道菜谱（推荐上限 8 道）：现有食材组合有限，宁缺毋滥，不为凑数填充低质推荐。`
})

/**
 * 难度编码转中文标签。
 * @param d 难度编码
 * @returns 中文标签
 */
function difficultyLabel(d: RecommendResultItem['difficulty']): string {
  return DIFFICULTY_LABELS[d]
}

/**
 * 卡片点击 → 菜谱详情 W-03。
 * @param recipeId 菜谱 ID
 * @returns 无
 */
function goDetail(recipeId: number): void {
  void router.push(`/recipe/${recipeId}`)
}

/**
 * 进入页面即发起推荐（store 内部按请求指纹防重复；响应为短路体时跳 W-05）。
 * @returns 无
 */
async function initialFetch(): Promise<void> {
  await recommendStore.fetchRecommend()
  if (recommendStore.blockedPayload) void router.push('/blocked')
}

/**
 * 「显示被我过滤掉的菜」开关切换：强制重发请求（开关状态已并入请求 options）。
 * @returns 无
 */
async function onFilterSwitchChange(): Promise<void> {
  await recommendStore.fetchRecommend(true)
  if (recommendStore.blockedPayload) void router.push('/blocked')
}

/**
 * 空态按钮「放宽到差 1–2 样」：打开被过滤展示开关并强制重发，被过滤菜谱带「已过滤」标记列出。
 * @returns 无
 */
async function relaxFilter(): Promise<void> {
  recommendStore.showFilteredItems = true
  ElMessage.info('已放宽展示：被过滤的菜谱将带「已过滤」标记列出')
  await recommendStore.fetchRecommend(true)
  if (recommendStore.blockedPayload) void router.push('/blocked')
}

/**
 * 空态按钮「补充食材」：返回 W-01。
 * @returns 无
 */
function goSelect(): void {
  void router.push('/select')
}

/**
 * 异常重试：强制重发推荐请求。
 * @returns 无
 */
function retry(): void {
  void recommendStore.fetchRecommend(true)
}

// 挂载即拉取推荐
onMounted(() => {
  void initialFetch()
})
</script>

<template>
  <section class="page-card recommend-page">
    <h1 class="page-title">为你挑选的菜谱</h1>

    <!-- ① 食材摘要（可编辑） + 被过滤展示开关 -->
    <div class="summary-bar">
      <div class="summary-ingredients">
        <span class="summary-label">已用食材：</span>
        <el-tag v-for="name in recommendStore.usedIngredients" :key="name" size="small">
          {{ name }}
        </el-tag>
        <el-button link type="primary" size="small" @click="goSelect">编辑食材</el-button>
      </div>
      <div class="summary-switch">
        <span class="switch-label">显示被我过滤掉的菜</span>
        <el-switch v-model="recommendStore.showFilteredItems" @change="onFilterSwitchChange" />
      </div>
    </div>

    <!-- 其他态：部分 Agent 失败 → 顶部说明条 -->
    <el-alert
      v-if="recommendStore.partialNotice"
      type="warning"
      title="本次部分内容未能生成"
      :description="recommendStore.partialNotice"
      :closable="false"
      show-icon
    />

    <!-- 其他态：后端附加提示（notice） -->
    <el-alert
      v-if="recommendStore.notice"
      type="info"
      :title="recommendStore.notice"
      :closable="false"
      show-icon
    />

    <!-- 异常态：错误 + 重试 -->
    <el-alert
      v-if="recommendStore.error"
      type="error"
      :title="recommendStore.error.message"
      :closable="false"
      show-icon
    >
      <el-button size="small" type="primary" plain @click="retry">重试</el-button>
    </el-alert>

    <!-- 加载态：骨架屏 + 正在为你挑选 -->
    <div v-if="recommendStore.loading" class="loading-block">
      <el-skeleton :rows="5" animated />
      <p class="loading-text">正在为你挑选…</p>
    </div>

    <template v-else-if="!recommendStore.error">
      <!-- 空态：无匹配 → 说明原因 + 两个行动按钮 -->
      <el-empty
        v-if="recommendStore.results.length === 0"
        description="现有食材暂时匹配不到合适的菜"
      >
        <div class="empty-actions">
          <el-button type="primary" @click="relaxFilter">放宽到差 1–2 样</el-button>
          <el-button @click="goSelect">补充食材</el-button>
        </div>
      </el-empty>

      <template v-else>
        <!-- 其他态：不足 8 条如实说明 -->
        <el-alert
          v-if="insufficientNotice"
          type="info"
          :title="insufficientNotice"
          :closable="false"
          show-icon
        />

        <!-- 被过滤菜谱区（开关打开时）：清单模式 / 计数模式双支持 -->
        <template v-if="recommendStore.showFilteredItems">
          <el-divider class="filtered-divider">被过滤的菜谱（默认不会出现在推荐中）</el-divider>
          <template v-if="recommendStore.filteredItems.length > 0">
            <div
              v-for="f in recommendStore.filteredItems"
              :key="f.recipe_id"
              class="filtered-item"
              role="button"
              @click="goDetail(f.recipe_id)"
            >
              <span class="filtered-title">{{ f.title }}</span>
              <el-tag type="danger" size="small" effect="plain">已过滤</el-tag>
              <span class="filtered-reason">{{ f.filter_reasons.join('；') }}</span>
            </div>
          </template>
          <p v-else-if="filteredSummary" class="filtered-summary">{{ filteredSummary }}</p>
          <p v-else class="filtered-summary">当前没有被过滤的菜谱</p>
        </template>

        <!-- ② 三档分组渲染 -->
        <div v-for="group in grouped" :key="group.level" class="group-section">
          <template v-if="group.items.length > 0">
            <el-divider class="group-divider">
              <span class="group-title">
                {{ group.title }}
                <el-badge :value="group.items.length" type="primary" class="group-badge" />
              </span>
            </el-divider>

            <!-- ③ 推荐卡片 -->
            <div class="card-list">
              <div
                v-for="item in group.items"
                :key="item.recipe_id"
                class="recipe-card"
                role="button"
                @click="goDetail(item.recipe_id)"
              >
                <div class="card-head">
                  <span class="card-title">{{ item.title }}</span>
                  <!-- ④ 为什么推荐给你：rank_reasons 弹层 -->
                  <el-popover placement="top" :width="320" trigger="hover">
                    <template #reference>
                      <el-button link type="primary" size="small" @click.stop>
                        为什么推荐给你
                      </el-button>
                    </template>
                    <ul class="reason-list">
                      <li v-for="(reason, i) in item.rank_reasons" :key="i">{{ reason }}</li>
                    </ul>
                  </el-popover>
                </div>
                <div class="card-meta">
                  <span>⏱ {{ item.time_minutes }} 分钟</span>
                  <span>🍳 {{ difficultyLabel(item.difficulty) }}</span>
                  <span>
                    🔥 {{ item.calories_kcal != null ? `${item.calories_kcal} kcal/份` : '热量未纳入统计' }}
                  </span>
                  <span>📦 覆盖率 {{ coveragePercent(item.covered_ingredients, item.missing_ingredients) }}%</span>
                </div>
                <div v-if="item.missing_ingredients.length > 0 || item.required_equipment.length > 0" class="card-tags">
                  <el-tag
                    v-for="m in item.missing_ingredients"
                    :key="`miss-${m}`"
                    type="warning"
                    size="small"
                  >
                    缺 {{ m }}
                  </el-tag>
                  <el-tag
                    v-for="eq in item.required_equipment"
                    :key="`eq-${eq}`"
                    type="info"
                    size="small"
                  >
                    需要 {{ eq }} 设备
                  </el-tag>
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- 调度取证线索：trace id（W-06 面板查询用） -->
        <p class="trace-hint">Agent 调度 trace：{{ recommendStore.traceId || '—' }}</p>
      </template>
    </template>

    <!-- 页面级免责条（G-02） -->
    <DisclaimerBar variant="default" />
  </section>
</template>

<style scoped>
.recommend-page {
  padding-bottom: 28px;
}

.summary-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 8px;
  background: var(--color-info-bg);
  border: 1px solid var(--color-info-border);
}

.summary-ingredients {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.summary-label {
  font-size: var(--font-sm);
  color: var(--color-info);
}

.summary-switch {
  display: flex;
  align-items: center;
  gap: 8px;
}

.switch-label {
  font-size: var(--font-sm);
  color: var(--color-info);
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

.empty-actions {
  display: flex;
  gap: 12px;
}

.filtered-divider {
  margin: 20px 0 12px;
}

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

.card-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}

.recipe-card {
  padding: 14px 16px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
  background: var(--card-bg);
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.recipe-card:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.card-title {
  font-size: var(--font-lg);
  font-weight: 600;
  color: var(--text-main);
}

.reason-list {
  margin: 0;
  padding-left: 18px;
  font-size: var(--font-sm);
  line-height: 1.8;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 10px;
  font-size: var(--font-sm);
  color: var(--text-main);
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.filtered-item {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 12px;
  margin-bottom: 8px;
  border-radius: 8px;
  border: 1px dashed var(--color-danger-border);
  cursor: pointer;
}

.filtered-title {
  font-size: var(--font-md);
  color: var(--text-main);
}

.filtered-reason {
  font-size: var(--font-sm);
  color: var(--color-info);
}

.filtered-summary {
  font-size: var(--font-sm);
  color: var(--color-info);
}

.trace-hint {
  margin-top: 20px;
  font-size: 12px;
  color: var(--color-info);
}
</style>
