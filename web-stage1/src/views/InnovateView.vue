<script setup lang="ts">
/**
 * 视图职责：AI 创新菜页（Task 9 / 路由 /innovate）。
 * 区块：① 顶部固定警示条「AI 创新·未经人工审核」；
 *       ② 食材输入（复用食材库多选 + 自定义输入）；
 *       ③ 生成按钮 → precheck（命中拦截展示拦截话术卡）→ 提交异步生成 job 并轮询
 *          （加载动画「已提交生成任务，正在基于食材性质与搭配规则创新…完成后自动
 *          展示（通常 10–60 秒）」，链路见 stores/innovation.generate）；
 *       ④ 结果卡：菜名 / 量化用量清单 / 步骤 / 创新依据（搭配规则 + 食性标注）/
 *          营养（缺失灰字）/ 强制声明；采纳（adopt → toast → 入「我的创新菜」）；
 *          复用（reuse → 弹确认后展示详情可再采纳）；评分反馈（el-rate + 评论）；
 *       ⑤ 页内 Tab「我的创新菜」列表（点开复用/评分）。
 * 三态：加载 = 生成动画；空 = 引导；异常 = el-alert；深色模式全变量适配。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Plus } from '@element-plus/icons-vue'
import { useInnovationStore } from '@/stores/innovation'
import { useIngredientsStore } from '@/stores/ingredients'
import type { ApiError, InnovationRecipe } from '@/api/types'

/** 创新 store */
const innovationStore = useInnovationStore()
/** 食材 store（复用分类与列表） */
const ingredientsStore = useIngredientsStore()

/** 页内 Tab：create 创作 / mine 我的创新菜 */
const activeTab = ref<'create' | 'mine'>('create')

/* ── 食材输入 ── */

/** 已选食材名列表（来自食材库点选） */
const pickedNames = computed(() => ingredientsStore.selectedList.map((s) => s.name))
/** 自定义输入缓冲 */
const customInput = ref('')
/** 自定义食材名（不在食材库里的） */
const customNames = ref<string[]>([])

/** 全部食材名（库选 + 自定义） */
const allNames = computed(() => [...pickedNames.value, ...customNames.value])

/**
 * 添加自定义食材（去重）。
 * @returns 无
 */
function addCustom(): void {
  const text = customInput.value.trim()
  if (!text) return
  if (!allNames.value.includes(text)) {
    customNames.value = [...customNames.value, text]
  }
  customInput.value = ''
}

/**
 * 移除自定义食材。
 * @param name 食材名
 * @returns 无
 */
function removeCustom(name: string): void {
  customNames.value = customNames.value.filter((n) => n !== name)
}

/* ── 生成链路 ── */

/** 结果是否被拦截（展示拦截话术卡） */
const blockedInfo = computed(() => {
  const pre = innovationStore.precheck
  return pre?.blocked ? { rule_id: pre.rule_id, message: pre.message } : null
})

/**
 * 点击「生成创新菜」：校验至少 1 样食材 → store.generate（precheck → generate）。
 * @returns 无
 */
async function onGenerate(): Promise<void> {
  if (allNames.value.length === 0) {
    ElMessage.warning('请至少选择或输入 1 样食材')
    return
  }
  await innovationStore.generate(allNames.value)
  if (innovationStore.current) {
    ElMessage.success('创新菜已生成，记得做完美食回来评分')
  }
}

/* ── 采纳 / 复用 / 评分 ── */

/**
 * 采纳当前创新菜（adopt → toast → 入「我的创新菜」）。
 * @returns 无
 */
async function onAdopt(): Promise<void> {
  try {
    const ok = await innovationStore.adopt()
    if (ok) ElMessage.success('已采纳，可在「我的创新菜」中查看')
  } catch (e) {
    ElMessage.error((e as ApiError).message || '采纳失败，请重试')
  }
}

/**
 * 复用创新菜（reuse → 结果置为当前展示）。
 * @param id 创新菜谱 ID
 * @returns 无
 */
async function onReuse(id: number): Promise<void> {
  const ok = await innovationStore.reuse(id)
  if (ok) {
    activeTab.value = 'create'
    ElMessage.success('已载入这道创新菜，可查看详情或直接采纳')
  } else if (innovationStore.error) {
    ElMessage.error(innovationStore.error.message)
  }
}

/** 评分弹窗可见性 */
const ratingVisible = ref(false)
/** 评分目标（null = 当前结果） */
const ratingTarget = ref<InnovationRecipe | null>(null)
/** 评分值 */
const ratingValue = ref(0)
/** 评论 */
const ratingComment = ref('')
/** 评分提交中 */
const ratingSubmitting = ref(false)

/**
 * 打开评分弹窗（默认对当前结果）。
 * @param recipe 目标创新菜（缺省取 current）
 * @returns 无
 */
function openRating(recipe?: InnovationRecipe): void {
  ratingTarget.value = recipe ?? innovationStore.current
  ratingValue.value = 0
  ratingComment.value = ''
  if (!ratingTarget.value) {
    ElMessage.info('请先生成或选择一道创新菜')
    return
  }
  ratingVisible.value = true
}

/**
 * 提交评分反馈。
 * @returns 无
 */
async function onRatingSubmit(): Promise<void> {
  if (!ratingTarget.value || ratingValue.value === 0) {
    ElMessage.warning('请先打分（1~5 星）')
    return
  }
  ratingSubmitting.value = true
  try {
    await innovationStore.sendFeedback(ratingTarget.value.id, ratingValue.value, ratingComment.value.trim() || undefined)
    ElMessage.success('感谢你的反馈')
    ratingVisible.value = false
  } catch (e) {
    ElMessage.error((e as ApiError).message || '提交失败，请重试')
  } finally {
    ratingSubmitting.value = false
  }
}

/* ── 展示辅助 ── */

/**
 * 营养值展示（null → 「未纳入统计」）。
 * @param label 营养名
 * @param value 数值
 * @param unit 单位
 * @returns 展示文案
 */
function nutritionText(label: string, value: number | null, unit: string): string {
  return value == null ? `${label}：未纳入统计` : `${label}：${value}${unit}`
}

/**
 * 步骤耗时格式化。
 * @param sec 耗时秒数
 * @returns 文案
 */
function stepDuration(sec: number): string {
  if (!sec || sec <= 0) return ''
  return sec < 60 ? `${sec} 秒` : `约 ${Math.round(sec / 60)} 分钟`
}

/** 是否已采纳当前结果（用于按钮态） */
const isCurrentAdopted = computed(() =>
  innovationStore.current ? innovationStore.myRecipes.some((r) => r.id === innovationStore.current?.id) : false,
)

// 挂载：预拉食材库（点选用）
onMounted(() => {
  if (ingredientsStore.list.length === 0) {
    void ingredientsStore.loadIngredients()
  }
})
</script>

<template>
  <section class="page-card innovate-page">
    <h1 class="page-title">AI 创新一下</h1>

    <!-- ① 顶部固定警示条 -->
    <el-alert
      class="innovate-warning"
      type="warning"
      title="AI 创新·未经人工审核"
      description="以下菜谱由 AI 根据食材搭配规则生成，未经人工审核，仅供参考；请遵循基本烹饪安全常识，过敏食材请自行核对。"
      :closable="false"
      show-icon
    />

    <el-tabs v-model="activeTab" class="innovate-tabs">
      <!-- ═══ Tab1 创作 ═══ -->
      <el-tab-pane label="创作" name="create">
        <!-- ② 食材输入 -->
        <div class="pick-section">
          <p class="pick-label">用手边的食材（点选或输入）：</p>
          <div class="pick-grid">
            <button
              v-for="ing in ingredientsStore.list.slice(0, 24)"
              :key="ing.id"
              type="button"
              class="pick-chip"
              :class="{ 'pick-chip--active': !!ingredientsStore.selected[ing.id] }"
              @click="ingredientsStore.toggle(ing)"
            >
              {{ ing.name }}
            </button>
          </div>
          <div class="custom-row">
            <el-input
              v-model="customInput"
              maxlength="20"
              placeholder="食材库里没有？直接输入，如：鱼腥草"
              @keyup.enter="addCustom"
            />
            <el-button :icon="Plus" @click="addCustom">添加</el-button>
          </div>
          <div v-if="customNames.length > 0" class="custom-tags">
            <el-tag v-for="n in customNames" :key="n" closable @close="removeCustom(n)">{{ n }}</el-tag>
          </div>
        </div>

        <!-- ③ 生成按钮 + 动画 -->
        <div class="generate-bar">
          <el-button
            type="primary"
            size="large"
            :icon="MagicStick"
            :loading="innovationStore.generating"
            :disabled="allNames.length === 0"
            @click="onGenerate"
          >
            生成创新菜（{{ allNames.length }} 样食材）
          </el-button>
        </div>

        <div v-if="innovationStore.generating" class="generating">
          <el-skeleton :rows="4" animated class="generating-skeleton" />
          <p class="generating-text">已提交生成任务，正在基于食材性质与搭配规则创新…完成后自动展示（通常 10–60 秒）</p>
        </div>

        <!-- 异常 -->
        <el-alert
          v-else-if="innovationStore.error"
          class="innovate-alert"
          type="error"
          :title="innovationStore.error.message"
          :closable="false"
          show-icon
        >
          <el-button size="small" type="primary" plain @click="onGenerate">重试</el-button>
        </el-alert>

        <!-- 拦截话术卡 -->
        <div v-else-if="blockedInfo" class="blocked-card">
          <p class="blocked-title">这组食材暂时不能创新</p>
          <p class="blocked-message">{{ blockedInfo.message || '食材组合未通过安全预检' }}</p>
          <p v-if="blockedInfo.rule_id" class="blocked-rule">规则编号：{{ blockedInfo.rule_id }}</p>
        </div>

        <!-- ④ 结果卡 -->
        <div v-else-if="innovationStore.current" class="result-card">
          <div class="result-head">
            <h2 class="result-name">{{ innovationStore.current.name }}</h2>
            <el-tag type="warning" size="small">AI 创新</el-tag>
          </div>

          <!-- 用量清单 -->
          <div class="result-section">
            <h3 class="result-sub">用量清单</h3>
            <ul class="ing-list">
              <li v-for="(ing, i) in innovationStore.current.ingredients" :key="i" class="ing-row">
                <span>{{ ing.name }}</span>
                <span class="ing-amount">{{ ing.amount }}{{ ing.unit }}</span>
              </li>
            </ul>
          </div>

          <!-- 步骤 -->
          <div class="result-section">
            <h3 class="result-sub">步骤</h3>
            <ol class="step-list">
              <li v-for="s in innovationStore.current.steps" :key="s.no" class="step-row">
                <p class="step-desc">{{ s.description }}</p>
                <p v-if="stepDuration(s.duration_sec)" class="step-duration">⏱ {{ stepDuration(s.duration_sec) }}</p>
                <p v-if="s.tips" class="step-tips">要点：{{ s.tips }}</p>
              </li>
            </ol>
          </div>

          <!-- 创新依据 -->
          <div class="result-section">
            <h3 class="result-sub">创新依据</h3>
            <ul v-if="innovationStore.current.basis.pairings.length > 0" class="basis-list">
              <li v-for="(p, i) in innovationStore.current.basis.pairings" :key="i" class="basis-row">
                <el-tag size="small" class="basis-tag">{{ p.relation }}</el-tag>
                <span class="basis-text"><strong>{{ p.a }} × {{ p.b }}</strong>：{{ p.rationale }}</span>
              </li>
            </ul>
            <ul v-if="innovationStore.current.basis.properties.length > 0" class="basis-list">
              <li v-for="(pr, i) in innovationStore.current.basis.properties" :key="`p${i}`" class="basis-row">
                <el-tag size="small" type="warning" class="basis-tag">{{ pr.name }}</el-tag>
                <span class="basis-text">{{ pr.note }}</span>
              </li>
            </ul>
          </div>

          <!-- 营养（缺失灰字） -->
          <div class="result-section">
            <h3 class="result-sub">营养估算</h3>
            <div class="nutri-line">
              <span :class="{ 'me-muted': innovationStore.current.nutrition.kcal == null }">
                {{ nutritionText('热量', innovationStore.current.nutrition.kcal, ' kcal') }}
              </span>
              <span :class="{ 'me-muted': innovationStore.current.nutrition.protein == null }">
                {{ nutritionText('蛋白质', innovationStore.current.nutrition.protein, 'g') }}
              </span>
              <span :class="{ 'me-muted': innovationStore.current.nutrition.fat == null }">
                {{ nutritionText('脂肪', innovationStore.current.nutrition.fat, 'g') }}
              </span>
              <span :class="{ 'me-muted': innovationStore.current.nutrition.carb == null }">
                {{ nutritionText('碳水', innovationStore.current.nutrition.carb, 'g') }}
              </span>
            </div>
            <p v-if="innovationStore.current.nutrition.excluded.length > 0" class="excluded-note">
              未纳入统计：{{ innovationStore.current.nutrition.excluded.join('、') }}
            </p>
          </div>

          <!-- 强制声明 -->
          <div class="result-disclaimer">{{ innovationStore.current.disclaimer }}</div>

          <!-- 采纳 / 复用 / 评分 -->
          <div class="result-actions">
            <el-button
              type="primary"
              :disabled="isCurrentAdopted"
              @click="onAdopt"
            >
              {{ isCurrentAdopted ? '已采纳' : '采纳这道菜' }}
            </el-button>
            <el-button @click="openRating()">为它评分</el-button>
          </div>
        </div>

        <!-- 空态 -->
        <el-empty
          v-else
          description="选几样手边食材，让厨娘帮你组合出新菜"
          :image-size="80"
        />
      </el-tab-pane>

      <!-- ═══ Tab2 我的创新菜 ═══ -->
      <el-tab-pane label="我的创新菜" name="mine">
        <el-empty
          v-if="innovationStore.myRecipes.length === 0"
          description="还没有采纳的创新菜，去「创作」生成一道吧"
        />
        <div v-else class="mine-list">
          <div v-for="r in innovationStore.myRecipes" :key="r.id" class="mine-item">
            <div class="mine-main">
              <span class="mine-name">{{ r.name }}</span>
              <span class="mine-meta">{{ r.ingredients.length }} 样食材 · {{ r.steps.length }} 步</span>
            </div>
            <div class="mine-actions">
              <el-button size="small" type="primary" plain @click="onReuse(r.id)">复用</el-button>
              <el-button size="small" @click="openRating(r)">评分</el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 评分弹窗 -->
    <el-dialog v-model="ratingVisible" title="为创新菜评分" width="400px" align-center>
      <div class="rating-body">
        <p class="rating-name">{{ ratingTarget?.name }}</p>
        <el-rate v-model="ratingValue" :max="5" show-text :texts="['很难吃', '一般', '还行', '不错', '惊艳']" />
        <el-input
          v-model="ratingComment"
          type="textarea"
          :rows="3"
          maxlength="200"
          placeholder="说说哪里好（或不好），可选"
          class="rating-comment"
        />
      </div>
      <template #footer>
        <el-button @click="ratingVisible = false">取消</el-button>
        <el-button type="primary" :loading="ratingSubmitting" @click="onRatingSubmit">提交</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.innovate-warning {
  margin-bottom: 14px;
}

.innovate-alert {
  margin: 14px 0;
}

/* ── 食材点选 ── */
.pick-section {
  margin-bottom: 16px;
}

.pick-label {
  margin: 0 0 10px;
  font-size: var(--font-md);
  color: var(--text-main);
}

.pick-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.pick-chip {
  padding: 6px 14px;
  border: 1px solid var(--color-info-border);
  border-radius: 16px;
  background: var(--card-bg);
  color: var(--text-main);
  font-size: var(--font-sm);
  cursor: pointer;
}

.pick-chip--active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}

.custom-row {
  display: flex;
  gap: 8px;
  max-width: 420px;
  margin-bottom: 8px;
}

.custom-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* ── 生成 ── */
.generate-bar {
  margin-bottom: 16px;
}

.generating {
  padding: 20px 0;
  text-align: center;
}

.generating-skeleton {
  max-width: 560px;
  margin: 0 auto 14px;
}

.generating-text {
  margin: 0;
  font-size: var(--font-md);
  color: var(--color-info);
}

/* ── 拦截卡 ── */
.blocked-card {
  padding: 18px;
  border: 1px solid var(--color-danger-border);
  border-radius: 10px;
  background: var(--color-danger-bg);
}

.blocked-title {
  margin: 0 0 8px;
  font-size: var(--font-md);
  font-weight: 700;
  color: var(--color-danger);
}

.blocked-message {
  margin: 0 0 6px;
  font-size: var(--font-sm);
  line-height: 1.7;
  color: var(--text-main);
}

.blocked-rule {
  margin: 0;
  font-size: var(--font-sm);
  color: var(--color-info);
}

/* ── 结果卡 ── */
.result-card {
  padding: 18px;
  border: 1px solid var(--color-info-border);
  border-radius: 12px;
}

.result-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.result-name {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--text-main);
}

.result-section {
  margin-bottom: 16px;
}

.result-sub {
  margin: 0 0 8px;
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
}

.ing-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.ing-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px dashed var(--color-info-border);
  font-size: var(--font-sm);
  color: var(--text-main);
}

.ing-amount {
  color: var(--color-info);
}

.step-list {
  margin: 0;
  padding-left: 20px;
}

.step-row {
  margin-bottom: 10px;
}

.step-desc {
  margin: 0;
  font-size: var(--font-sm);
  line-height: 1.7;
  color: var(--text-main);
}

.step-duration {
  margin: 2px 0;
  font-size: var(--font-sm);
  color: var(--color-info);
}

.step-tips {
  margin: 2px 0 0;
  font-size: var(--font-sm);
  color: var(--color-warning);
}

.basis-list {
  margin: 0 0 8px;
  padding: 0;
  list-style: none;
}

.basis-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 6px;
}

.basis-tag {
  flex-shrink: 0;
}

.basis-text {
  font-size: var(--font-sm);
  line-height: 1.7;
  color: var(--text-main);
}

.nutri-line {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: var(--font-sm);
  color: var(--text-main);
}

.me-muted {
  color: var(--color-info);
}

.excluded-note {
  margin: 8px 0 0;
  font-size: var(--font-sm);
  color: var(--color-info);
}

.result-disclaimer {
  padding: 10px 12px;
  margin-bottom: 14px;
  border-radius: 8px;
  background: var(--color-info-bg);
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-info);
}

.result-actions {
  display: flex;
  gap: 10px;
}

/* ── 我的创新菜 ── */
.mine-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mine-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
}

.mine-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.mine-name {
  font-weight: 600;
  color: var(--text-main);
}

.mine-meta {
  font-size: var(--font-sm);
  color: var(--color-info);
}

.mine-actions {
  flex-shrink: 0;
  display: flex;
  gap: 8px;
}

/* ── 评分弹窗 ── */
.rating-body {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}

.rating-name {
  margin: 0;
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
}

.rating-comment {
  width: 100%;
}
</style>
