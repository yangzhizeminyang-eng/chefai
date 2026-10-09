<script setup lang="ts">
/**
 * 视图职责：W-03 菜谱详情页（对齐 UI 清单 W-03 行）。
 * 区块：① 过敏原警示条（G-03，allergen_codes 非空时置顶）② 头部（菜名/菜系/难度/耗时/份数）
 *       ③ 份数缩放（1~8，变更后重拉详情与营养，用量与营养同步重算）
 *       ④ 食材清单三段（主料/辅料/调味，量化值 + 勺参照）⑤ 过敏原标注 ⑥ 设备要求
 *       ⑦ 步骤列表（el-timeline：描述+时长+要点+失败补救折叠）⑧ 替代食材 ⑨ 小贴士
 *       ⑩ 营养入口（五大数值 + per_serving + excluded_items + 估算值标注；
 *          L4-1 去重后不再单独渲染免责条，估算口径说明由后端 estimate_note 承担）
 *       ⑪ 来源标注 ⑫ 底部固定条（免责 + 开始做菜，冲突时二次确认；
 *          L4-1 去重：免责声明全页仅此 1 处渲染）。
 * 三态：加载 = 详情骨架屏；异常 = el-alert + 重试（404 → 「菜谱不存在」）；空态仅 404 场景。
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getNutrition, getRecipe } from '@/api/endpoints'
import type { ApiError, NutritionResult, RecipeDetail, RecipeIngredientItem } from '@/api/types'
import { useCookingStore } from '@/stores/cooking'
import { scaleStepHint } from '@/utils/scaling'
import AllergenAlertBar from '@/components/AllergenAlertBar.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'

/** 路由（取 :id 与跳转烹饪页） */
const route = useRoute()
const router = useRouter()
/** 烹饪 store：创建会话并快照步骤（W-04 数据源） */
const cookingStore = useCookingStore()

/** 菜谱详情 */
const detail = ref<RecipeDetail | null>(null)
/** 详情加载中 */
const loading = ref(false)
/** 详情加载错误（code=404 → 菜谱不存在态） */
const error = ref<ApiError | null>(null)
/** 当前份数（初值 1，详情加载后同步为菜谱基准份数） */
const servings = ref(1)
/** 菜谱基准份数（首次加载时的 servings，作为步骤提示缩放系数的分母；缩放变更不改动） */
const baseServings = ref(1)
/** 份数缩放重算进行中（内容区 v-loading，不整页遮挡） */
const scaling = ref(false)
/** 请求序号（份数快速变更时丢弃过期响应） */
let reqSeq = 0

/** 营养估算结果 */
const nutrition = ref<NutritionResult | null>(null)
/** 营养加载中 */
const nutritionLoading = ref(false)
/** 营养加载错误 */
const nutritionError = ref<ApiError | null>(null)
/** 营养区展开标记 */
const showNutrition = ref(false)

/** 开始做菜请求进行中 */
const starting = ref(false)
/** 过敏原冲突二次确认弹窗可见性 */
const conflictVisible = ref(false)
/** 冲突说明文本 */
const conflictText = ref('')
/** 待跳转的会话 ID（冲突确认后使用） */
const pendingSessionId = ref('')

/** GB 7718 八类致敏原编码 → 中文名映射 */
const ALLERGEN_NAMES: Record<string, string> = {
  gluten: '含麸质',
  crustacean: '甲壳类',
  fish: '鱼类',
  egg: '蛋类',
  peanut: '花生',
  soybean: '大豆',
  milk: '乳制品',
  nuts: '坚果',
}

/** 详情页过敏原中文名列表（未知编码原样展示） */
const allergenNames = computed(() =>
  (detail.value?.allergen_codes ?? []).map((code) => ALLERGEN_NAMES[code] ?? code),
)

/** 是否 404（菜谱不存在） */
const isNotFound = computed(() => error.value?.code === 404)

/** 三段食材清单配置（key 对应 RecipeDetail 字段） */
const INGREDIENT_SECTIONS = [
  { key: 'main_ingredients', title: '主料' },
  { key: 'side_ingredients', title: '辅料' },
  { key: 'seasoning_ingredients', title: '调味料' },
] as const

/**
 * 步骤用量提示缩放系数（当前份数 / 菜谱基准份数）。
 * 食材表用量由后端按同一比例缩放，步骤文本提示在前端按同系数缩放保持一致。
 * @returns 缩放系数（基准份数非法时回退 1 = 不缩放）
 */
const hintFactor = computed<number>(() => {
  if (!baseServings.value || baseServings.value < 1) return 1
  return servings.value / baseServings.value
})

/**
 * 营养区按份数合计热量文案（单份 × 份数，与头部 kcal/份 同源换算）。
 * @returns 形如「约 920 kcal」；无合计数据时返回「—」
 */
const totalKcalText = computed<string>(() => {
  const total = nutrition.value?.total?.kcal
  return total != null ? `约 ${total} kcal` : '—'
})

/**
 * 难度编码转中文标签。
 * @param d 难度编码
 * @returns 中文标签
 */
function difficultyLabel(d: RecipeDetail['difficulty']): string {
  return d === 'easy' ? '简单' : d === 'medium' ? '中等' : '较难'
}

/**
 * 秒数转可读时长（步骤/总耗时展示）。
 * @param sec 耗时秒数（0 表示无需等待）
 * @returns 可读文案
 */
function formatDuration(sec: number): string {
  if (!sec || sec <= 0) return '—'
  if (sec < 60) return `${sec} 秒`
  return `${Math.round(sec / 60)} 分钟`
}

/**
 * 致敏原编码转中文名（未知编码原样返回）。
 * @param code 致敏原编码
 * @returns 中文名
 */
function allergenName(code: string): string {
  return ALLERGEN_NAMES[code] ?? code
}

/**
 * 拉取菜谱详情（首次进入 / 路由参数变化）。
 * @returns 无
 */
async function loadDetail(): Promise<void> {
  const id = route.params.id as string
  if (!id) return
  loading.value = true
  error.value = null
  try {
    detail.value = await getRecipe(id)
    // 同步菜谱基准份数（不触发缩放重算）；该值同时作为步骤提示缩放的分母
    servings.value = detail.value.servings || 1
    baseServings.value = detail.value.servings || 1
  } catch (e) {
    error.value = e as ApiError
    detail.value = null
  } finally {
    loading.value = false
  }
}

/**
 * 份数变更：并行重拉详情（用量重算）与营养估算（营养同步重算）。
 * 快速变更时以序号守卫，丢弃过期响应。
 * @param val 新份数（1~8）
 * @returns 无
 */
async function onServingsChange(val: number | undefined): Promise<void> {
  if (!detail.value || val == null || val < 1) return
  const id = detail.value.id
  reqSeq += 1
  const seq = reqSeq
  scaling.value = true
  try {
    const nextDetail = await getRecipe(id, val)
    if (seq !== reqSeq) return
    detail.value = nextDetail
    servings.value = nextDetail.servings || val
    // 营养区已展开过（或正展开）则同步重算；未展开过保持懒加载
    if (showNutrition.value || nutrition.value || nutritionError.value) {
      nutrition.value = null
      nutritionError.value = null
      nutritionLoading.value = true
      try {
        nutrition.value = await getNutrition(id, val)
      } catch (e) {
        nutritionError.value = e as ApiError
      } finally {
        nutritionLoading.value = false
      }
    }
  } catch (e) {
    if (seq !== reqSeq) return
    ElMessage.error((e as ApiError).message)
  } finally {
    if (seq === reqSeq) scaling.value = false
  }
}

/**
 * 展开/收起营养区（首次展开时懒加载营养估算）。
 * @returns 无
 */
async function toggleNutrition(): Promise<void> {
  showNutrition.value = !showNutrition.value
  if (showNutrition.value && !nutrition.value && detail.value) {
    nutritionLoading.value = true
    nutritionError.value = null
    try {
      nutrition.value = await getNutrition(detail.value.id, servings.value)
    } catch (e) {
      nutritionError.value = e as ApiError
    } finally {
      nutritionLoading.value = false
    }
  }
}

/**
 * 营养单项值渲染：null → 「未纳入统计」（不按 0 计）。
 * @param v 数值或 null
 * @param unit 单位
 * @returns 展示文案
 */
function nutritionText(v: number | null, unit: string): string {
  return v != null ? `${v} ${unit}` : '未纳入统计'
}

/**
 * 步骤用量提示按份数缩放（M3/R3 修复：本步用量随份数响应式变化）。
 * @param step 步骤对象
 * @returns 缩放后的用量提示；无提示返回空串
 */
function stepHint(step: RecipeDetail['steps'][number]): string {
  return scaleStepHint(step.amount_hint, hintFactor.value)
}

/**
 * 点击「开始做菜」：创建烹饪会话（后端做过敏原冲突检查）；
 * 有冲突（allergen_conflict 非空）→ 弹二次确认；无冲突 → 直接进 W-04。
 * @returns 无
 */
async function startCooking(): Promise<void> {
  if (!detail.value || starting.value) return
  starting.value = true
  try {
    const session = await cookingStore.startSession(
      detail.value.id,
      servings.value,
      detail.value.steps,
      baseServings.value,
    )
    if (session.allergen_conflict && session.allergen_conflict.length > 0) {
      // 阶段一预期无档案无冲突；若返回冲突则二次确认
      conflictText.value = session.allergen_conflict.join('、')
      pendingSessionId.value = session.id
      conflictVisible.value = true
    } else {
      void router.push(`/cook/${session.id}`)
    }
  } catch (e) {
    ElMessage.error((e as ApiError).message)
  } finally {
    starting.value = false
  }
}

/**
 * 冲突二次确认「仍要继续」：进入已创建的会话。
 * @returns 无
 */
function confirmStartAnyway(): void {
  conflictVisible.value = false
  if (pendingSessionId.value) void router.push(`/cook/${pendingSessionId.value}`)
}

/**
 * 404 / 异常后的返回动作：回推荐列表。
 * @returns 无
 */
function goBack(): void {
  void router.push('/recommend')
}

// 路由参数变化（含首次进入）时重新拉取详情
watch(
  () => route.params.id,
  () => {
    void loadDetail()
  },
  { immediate: true },
)
</script>

<template>
  <section class="page-card detail-page">
    <!-- 加载态：详情骨架屏 -->
    <el-skeleton v-if="loading" :rows="8" animated />

    <!-- 空态（404）：菜谱不存在 -->
    <el-empty v-else-if="isNotFound" description="菜谱不存在">
      <el-button type="primary" @click="goBack">返回推荐</el-button>
    </el-empty>

    <!-- 异常态：错误 + 重试 -->
    <el-alert
      v-else-if="error"
      type="error"
      :title="error.message"
      :closable="false"
      show-icon
    >
      <el-button size="small" type="primary" plain @click="loadDetail">重试</el-button>
    </el-alert>

    <template v-else-if="detail">
      <!-- ① 过敏原警示条（G-03，置顶） -->
      <AllergenAlertBar :allergens="allergenNames" :conflict="false" />

      <!-- ② 头部：菜名 + 难度 + 耗时 + 份数缩放 -->
      <div class="detail-head">
        <div class="head-info">
          <h2 class="recipe-title">{{ detail.title }}</h2>
          <p v-if="detail.description" class="recipe-desc">{{ detail.description }}</p>
          <div class="head-meta">
            <el-tag size="small">{{ difficultyLabel(detail.difficulty) }}</el-tag>
            <span>⏱ 约 {{ detail.time_minutes }} 分钟</span>
            <span>🔥 {{ detail.calories_kcal != null ? `${detail.calories_kcal} kcal/份` : '热量未纳入统计' }}</span>
          </div>
        </div>
        <!-- ③ 份数缩放：1~8，变更后重拉详情与营养 -->
        <div class="servings-box" v-loading="scaling">
          <span class="servings-label">份数</span>
          <el-input-number
            v-model="servings"
            :min="1"
            :max="8"
            :step="1"
            step-strictly
            @change="onServingsChange"
          />
        </div>
      </div>

      <el-divider />

      <!-- ④ 食材清单三段（主料/辅料/调味）+ 勺参照 -->
      <h3 class="section-title">食材清单</h3>
      <p class="amount-note">用量参照：1 勺 ≈ 15ml；用量随份数自动缩放。</p>
      <div v-for="section in INGREDIENT_SECTIONS" :key="section.key" class="ingredient-section">
        <h4 class="sub-title">{{ section.title }}</h4>
        <el-table
          :data="detail[section.key] as RecipeIngredientItem[]"
          size="small"
          :empty-text="`暂无${section.title}`"
        >
          <el-table-column prop="name" label="名称" min-width="120" />
          <el-table-column prop="amount" label="用量" min-width="120" />
          <el-table-column label="致敏原标注" min-width="180">
            <template #default="{ row }">
              <template v-if="row.allergens && row.allergens.length > 0">
                <el-tag
                  v-for="code in row.allergens"
                  :key="code"
                  type="danger"
                  size="small"
                  effect="plain"
                >
                  {{ allergenName(code) }}
                </el-tag>
              </template>
              <!-- 致敏原字段缺失（未标注）→ 待核实；空数组 → 无 -->
              <span v-else-if="row.allergens == null" class="muted">该食材致敏原信息待核实</span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- ⑥ 设备要求（阶段一无用户设备档案，全部列出标注） -->
      <h3 class="section-title">设备要求</h3>
      <p class="equip-line">
        <template v-if="detail.equipment.length > 0">
          本菜谱需要：
          <el-tag v-for="eq in detail.equipment" :key="eq" type="info" size="small" class="equip-tag">
            {{ eq }}
          </el-tag>
        </template>
        <span v-else class="muted">无特殊设备要求</span>
      </p>

      <el-divider />

      <!-- ⑦ 步骤列表 -->
      <h3 class="section-title">做法步骤</h3>
      <el-timeline class="step-timeline">
        <el-timeline-item
          v-for="step in detail.steps"
          :key="step.no"
          :timestamp="`第 ${step.no} 步 · ${formatDuration(step.duration_sec)}`"
          placement="top"
        >
          <p class="step-desc">{{ step.description }}</p>
          <p v-if="step.amount_hint" class="step-hint">用量提示：{{ stepHint(step) }}</p>
          <!-- 要点 / 失败补救折叠 -->
          <el-collapse v-if="step.tips || step.rescue" class="step-collapse">
            <el-collapse-item title="新手要点 / 失败补救" :name="step.no">
              <p v-if="step.tips" class="step-tip-line">要点：{{ step.tips }}</p>
              <p v-if="step.rescue" class="step-tip-line">失败补救：{{ step.rescue }}</p>
            </el-collapse-item>
          </el-collapse>
        </el-timeline-item>
      </el-timeline>

      <!-- ⑧ 替代食材 -->
      <template v-if="detail.substitutes.length > 0">
        <h3 class="section-title">替代食材</h3>
        <ul class="plain-list">
          <li v-for="(sub, i) in detail.substitutes" :key="i">{{ sub }}</li>
        </ul>
      </template>

      <!-- ⑨ 小贴士 -->
      <template v-if="detail.tips.length > 0">
        <h3 class="section-title">小贴士</h3>
        <ul class="plain-list">
          <li v-for="(tip, i) in detail.tips" :key="i">{{ tip }}</li>
        </ul>
      </template>

      <el-divider />

      <!-- ⑩ 营养入口：展开显示营养区 -->
      <div class="nutrition-section">
        <el-button :type="showNutrition ? 'default' : 'primary'" plain @click="toggleNutrition">
          营养估算{{ showNutrition ? '（收起）' : '' }}
        </el-button>
        <div v-if="showNutrition" class="nutrition-body">
          <template v-if="nutrition">
            <div class="nutrition-grid">
              <div class="n-item">
                <span class="n-value">{{ nutritionText(nutrition.kcal, 'kcal') }}</span>
                <span class="n-label">热量</span>
              </div>
              <div class="n-item">
                <span class="n-value">{{ nutritionText(nutrition.protein, 'g') }}</span>
                <span class="n-label">蛋白质</span>
              </div>
              <div class="n-item">
                <span class="n-value">{{ nutritionText(nutrition.fat, 'g') }}</span>
                <span class="n-label">脂肪</span>
              </div>
              <div class="n-item">
                <span class="n-value">{{ nutritionText(nutrition.carbs, 'g') }}</span>
                <span class="n-label">碳水</span>
              </div>
              <div class="n-item">
                <span class="n-value">{{ nutritionText(nutrition.sodium, 'mg') }}</span>
                <span class="n-label">钠</span>
              </div>
            </div>
            <!-- 口径统一（M5/R4/S9）：全部为「每份」口径，与头部 kcal/份 同源；
                 按份数合计单独标注，换算 = 单份 × 份数 -->
            <p class="n-serving">
              单份 {{ nutrition.kcal != null ? `${nutrition.kcal} kcal` : '未纳入统计' }} ·
              按 {{ nutrition.per_serving }} 份合计 {{ totalKcalText }}
            </p>
            <!-- 未纳入统计项（缺失数据不按 0 计） -->
            <el-alert
              v-if="nutrition.excluded_items.length > 0"
              type="warning"
              :title="`以下食材未纳入统计：${nutrition.excluded_items.join('、')}`"
              :closable="false"
              show-icon
            />
            <p class="n-note">{{ nutrition.estimate_note }}</p>
            <!-- L4-1 去重：营养区原独立的 DisclaimerBar（nutrition 档）已移除，
                 估算口径说明由后端 estimate_note 承担，全页免责统一收敛至底部固定条 1 处 -->
          </template>
          <el-alert
            v-else-if="nutritionError"
            type="error"
            :title="nutritionError.message"
            :closable="false"
            show-icon
          />
          <el-skeleton v-else-if="nutritionLoading" :rows="2" animated />
        </div>
      </div>

      <!-- ⑪ 来源标注 -->
      <p class="source-line">菜谱来源：{{ detail.source_label }}</p>
    </template>

    <!-- L4-1 去重：原页面级 DisclaimerBar（default 档）已移除，
         免责声明全页仅保留下方底部固定条 1 处（原最主要位置，用户决策前必见） -->
  </section>

  <!-- ⑫ 底部固定条：免责 + 开始做菜（L4-1 去重后免责声明全页唯一渲染点） -->
  <div v-if="detail && !isNotFound" class="detail-footer">
    <div class="footer-inner">
      <!-- 页面唯一免责条（G-02 default 档）：置于开始做菜按钮旁，用户发起烹饪前必见 -->
      <DisclaimerBar variant="default" class="footer-disclaimer" />
      <el-button type="primary" size="large" class="footer-btn" :loading="starting" @click="startCooking">
        开始做菜
      </el-button>
    </div>
  </div>

  <!-- 过敏原冲突二次确认（阶段一预期不触发） -->
  <el-dialog v-model="conflictVisible" title="过敏原冲突提醒" width="440px" align-center>
    <p>该菜谱与登记的过敏原冲突：{{ conflictText }}</p>
    <p class="muted">请以实际食材包装标签为准。</p>
    <template #footer>
      <el-button @click="conflictVisible = false">取消</el-button>
      <el-button type="danger" @click="confirmStartAnyway">仍要继续</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.detail-page {
  padding-bottom: 24px;
}

.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 14px;
}

.recipe-title {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-main);
}

.recipe-desc {
  margin: 0 0 10px;
  font-size: var(--font-sm);
  color: var(--color-info);
  line-height: 1.7;
}

.head-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  font-size: var(--font-sm);
  color: var(--text-main);
}

.servings-box {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  border-radius: 8px;
  background: var(--color-info-bg);
  border: 1px solid var(--color-info-border);
}

.servings-label {
  font-size: var(--font-md);
  color: var(--text-main);
}

.section-title {
  margin: 18px 0 10px;
  font-size: var(--font-lg);
  font-weight: 600;
  color: var(--text-main);
}

.sub-title {
  margin: 12px 0 6px;
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
}

.amount-note {
  margin: 0 0 8px;
  font-size: var(--font-sm);
  color: var(--color-info);
}

.ingredient-section {
  margin-bottom: 8px;
}

.muted {
  color: var(--color-info);
  font-size: var(--font-sm);
}

.equip-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  font-size: var(--font-md);
  color: var(--text-main);
}

.equip-tag {
  margin-right: 4px;
}

.step-timeline {
  padding-left: 4px;
}

.step-desc {
  margin: 0 0 6px;
  font-size: var(--font-md);
  line-height: 1.7;
  color: var(--text-main);
}

.step-hint {
  margin: 0 0 6px;
  font-size: var(--font-sm);
  color: var(--color-warning);
}

.step-collapse {
  margin-top: 4px;
}

.step-tip-line {
  margin: 4px 0;
  font-size: var(--font-sm);
  color: var(--color-info);
  line-height: 1.7;
}

.plain-list {
  margin: 0;
  padding-left: 20px;
  font-size: var(--font-md);
  line-height: 1.9;
  color: var(--text-main);
}

.nutrition-section {
  margin-bottom: 12px;
}

.nutrition-body {
  margin-top: 12px;
}

.nutrition-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.n-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 8px;
  border-radius: 8px;
  background: var(--color-info-bg);
  border: 1px solid var(--color-info-border);
}

.n-value {
  font-size: var(--font-lg);
  font-weight: 700;
  color: var(--text-main);
}

.n-label {
  font-size: var(--font-sm);
  color: var(--color-info);
}

.n-serving {
  margin: 8px 0;
  font-size: var(--font-sm);
  color: var(--color-info);
}

.n-note {
  margin: 8px 0;
  font-size: var(--font-sm);
  color: var(--color-warning);
}

.source-line {
  margin: 16px 0 0;
  font-size: var(--font-sm);
  color: var(--color-info);
}

/* ── 底部固定条 ── */
.detail-footer {
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
  padding: 8px 16px;
}

.footer-disclaimer {
  flex: 1;
  min-width: 0;
}

.footer-btn {
  flex-shrink: 0;
  min-width: 140px;
  min-height: 44px;
  font-size: var(--font-md);
}
</style>
