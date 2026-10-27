<script setup lang="ts">
/**
 * 文件职责：W-05 风控拦截页（/blocked）。
 * 承载一票否决短路结果（G-01 风控拦截，阶段一核心证据）：
 * - 数据源：recommend store 的 blockedPayload（BlockedResponse，不含 results/candidates/nutrition）；
 * - 三类视觉强度（G-01）：食品安全类红色危险（默认）/ 医疗拒答类中性蓝信息 / 伪科学类橙色科普；
 * - 页面顶部大标识 + 副条「本次请求未生成任何内容」必须醒目体现；
 * - 主体三块卡片：⛔ 风险说明 / ✅ 正确做法 / 🏥 已食用处置建议（含「请及时就医」加粗）；
 * - 元信息：命中规则 / 类别 / 风险等级 / 依据 / 请求 ID；
 * - 底部：DisclaimerBar（G-02）+「我认为这是误判」弹窗（阶段一无后台工单，仅本地提示）；
 * - 兜底：blockedPayload 为空（守卫已回 /select）再显示 el-empty「无拦截数据」+ 返回按钮。
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useRecommendStore } from '@/stores/recommend'
import type { RiskDetail } from '@/api/types'
import DisclaimerBar from '@/components/DisclaimerBar.vue'

/** 推荐 store：blockedPayload 为本页唯一数据源 */
const recommendStore = useRecommendStore()
/** 路由实例：兜底空态的返回按钮跳转 */
const router = useRouter()

/** 拦截短路响应体（null 时走兜底空态） */
const payload = computed(() => recommendStore.blockedPayload)
/** 风险详情（三块卡片与元信息的数据源） */
const risk = computed<RiskDetail | null>(() => payload.value?.risk ?? null)

/** 视觉主题键：medical_refusal → 中性蓝 / pseudoscience → 橙色科普 / 其余 → 红色危险 */
const themeKey = computed<'danger' | 'info' | 'warning'>(() => {
  const category = risk.value?.category ?? ''
  if (category === 'medical_refusal') return 'info'
  if (category === 'pseudoscience') return 'warning'
  return 'danger'
})

/** 页面顶部大标识文案（按类别切换视觉强度：医疗拒答不使用惊悚视觉） */
const header = computed(() => {
  if (themeKey.value === 'info') {
    return {
      icon: 'ℹ️',
      title: '本产品不做医疗建议',
      subtitle: '本次请求未生成任何内容；健康相关问题请咨询执业医师或临床营养师',
    }
  }
  if (themeKey.value === 'warning') {
    return {
      icon: '⚠️',
      title: '本次请求已被安全拦截',
      subtitle: '本次请求未生成任何内容；以下为科学认知澄清，请理性参考',
    }
  }
  return {
    icon: '⛔',
    title: '本次请求已被安全拦截',
    subtitle: '本次请求未生成任何内容',
  }
})

/** 风险类别中文标签映射（未收录的编码原样展示） */
const CATEGORY_LABELS: Record<string, string> = {
  food_safety_high_risk: '食品安全高风险',
  medical_refusal: '医疗建议拒答',
  pseudoscience: '伪科学内容澄清',
  allergen_conflict: '过敏原冲突',
  special_population: '特殊人群风险',
  injection: '注入攻击拦截',
}

/** 类别中文标签（兜底原样展示编码） */
const categoryLabel = computed(() => {
  const category = risk.value?.category ?? ''
  return CATEGORY_LABELS[category] ?? category
})

/**
 * 风险等级 → el-tag 类型映射（critical 红 / high 红 / medium 橙 / 其余灰蓝）。
 * @returns el-tag 的 type 值
 */
const riskLevelTagType = computed<'danger' | 'warning' | 'info'>(() => {
  const level = (risk.value?.risk_level ?? '').toLowerCase()
  if (level === 'critical' || level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  return 'info'
})

/**
 * 将已食用处置建议按「请及时就医」拆分为三段，实现关键词加粗（不使用 v-html，避免注入）。
 * @returns before 前段 / strong 强调段 / after 后段
 */
const adviceParts = computed(() => {
  const text = risk.value?.after_consumption_advice ?? ''
  const keyword = '请及时就医'
  const idx = text.indexOf(keyword)
  if (idx === -1) return { before: text, strong: '', after: '' }
  return { before: text.slice(0, idx), strong: keyword, after: text.slice(idx + keyword.length) }
})

/** 处置建议中是否含「请及时就医」（决定是否渲染拆分结构） */
const hasAdviceKeyword = computed(() => adviceParts.value.strong !== '')

/* ── 误判申诉（阶段一无后台工单，仅前端演示） ── */
/** 申诉弹窗可见性 */
const appealVisible = ref(false)
/** 申诉描述（一句话） */
const appealText = ref('')
/** 是否已提交过申诉（提交后页面留一行本地确认文案） */
const appealSubmitted = ref(false)

/**
 * 提交误判申诉：关闭弹窗、清空输入并本地提示（不调后台）。
 * @returns 无
 */
function submitAppeal(): void {
  appealVisible.value = false
  appealSubmitted.value = true
  appealText.value = ''
  ElMessage.success('已记录，我们会尽快复核')
}

/**
 * 返回食材选择页（兜底空态按钮）。
 * @returns 无
 */
function backToSelect(): void {
  void router.push('/select')
}
</script>

<template>
  <section class="page-card blocked-page" :class="`theme-${themeKey}`">
    <!-- 主内容：拦截短路响应存在时渲染（守卫已保证；再兜底空态） -->
    <template v-if="payload && risk">
      <!-- 顶部大标识：图标 + 标题 + 副条（副条固定体现「本次请求未生成任何内容」） -->
      <div class="block-banner">
        <span class="banner-icon" aria-hidden="true">{{ header.icon }}</span>
        <div class="banner-text">
          <h1 class="banner-title">{{ header.title }}</h1>
          <p class="banner-subtitle">{{ header.subtitle }}</p>
        </div>
      </div>

      <!-- 元信息行：命中规则 / 类别 / 风险等级 / 依据 / 请求 ID（供 W-06 面板交叉取证） -->
      <div class="meta-row">
        <span class="meta-item">
          <span class="meta-label">命中规则</span>
          <span class="meta-value mono">{{ risk.rule_code }}</span>
        </span>
        <span class="meta-item">
          <span class="meta-label">类别</span>
          <span class="meta-value">{{ categoryLabel }}</span>
        </span>
        <span class="meta-item">
          <span class="meta-label">风险等级</span>
          <el-tag :type="riskLevelTagType" effect="light">{{ risk.risk_level }}</el-tag>
        </span>
        <span v-if="risk.evidence_ref?.length" class="meta-item">
          <span class="meta-label">依据</span>
          <span class="meta-value mono">{{ risk.evidence_ref.join('；') }}</span>
        </span>
        <span class="meta-item">
          <span class="meta-label">请求 ID</span>
          <span class="meta-value mono">{{ payload.request_id }}</span>
        </span>
      </div>

      <!-- ① 风险/拒答/澄清说明（红色危险 / 中性蓝 / 橙色科普随主题切换，图标+文字不依赖颜色） -->
      <el-card class="card risk-card" shadow="never">
        <template #header>
          <span class="card-title">{{ header.icon }} {{ themeKey === 'info' ? '拒答说明' : themeKey === 'warning' ? '澄清说明' : '风险说明' }}</span>
        </template>
        <p class="risk-title-text">{{ risk.title }}</p>
        <p class="card-body">{{ risk.body }}</p>
      </el-card>

      <!-- ② 正确做法 / 建议（绿色对钩图标 + 文字） -->
      <el-card class="card correct-card" shadow="never">
        <template #header>
          <span class="card-title">✅ {{ themeKey === 'info' ? '建议做法' : themeKey === 'warning' ? '正确认知' : '正确做法' }}</span>
        </template>
        <p class="card-body">{{ risk.correct_action }}</p>
      </el-card>

      <!-- ③ 已食用处置建议（含「请及时就医」加粗；医疗拒答等无建议内容时整卡隐藏） -->
      <el-card v-if="risk.after_consumption_advice" class="card advice-card" shadow="never">
        <template #header>
          <span class="card-title">🏥 {{ themeKey === 'info' ? '如有不适的处置建议' : '已食用处置建议' }}</span>
        </template>
        <p class="card-body">
          <template v-if="hasAdviceKeyword">
            {{ adviceParts.before }}<strong class="advice-strong">{{ adviceParts.strong }}</strong>{{ adviceParts.after }}
          </template>
          <template v-else>{{ risk.after_consumption_advice }}</template>
        </p>
      </el-card>

      <!-- 申诉提交后的本地确认文案 -->
      <p v-if="appealSubmitted" class="appeal-done">✅ 你的申诉已记录，我们会尽快复核。</p>

      <!-- 底部操作：误判入口（阶段一仅本地提示） -->
      <div class="footer-row">
        <el-button type="primary" plain @click="appealVisible = true">我认为这是误判</el-button>
      </div>

      <!-- 免责声明条（G-02：拦截页固定附着） -->
      <DisclaimerBar variant="default" />
    </template>

    <!-- 兜底空态：blockedPayload 意外为空（守卫已回 /select，此为再兜底） -->
    <el-empty v-else description="无拦截数据">
      <el-button type="primary" @click="backToSelect">返回食材选择</el-button>
    </el-empty>

    <!-- 误判申诉弹窗：收集一句描述，提交后仅本地提示（阶段一无后台工单） -->
    <el-dialog v-model="appealVisible" title="误判申诉" width="480px">
      <p class="dialog-tip">请用一句话描述你认为误判的原因（必填），我们会人工复核：</p>
      <el-input
        v-model="appealText"
        type="textarea"
        :rows="3"
        maxlength="200"
        show-word-limit
        placeholder="例如：我使用的木耳是干制品并已充分高温烹煮……"
      />
      <template #footer>
        <el-button @click="appealVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!appealText.trim()" @click="submitAppeal">提交</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
/* ── 顶部大标识（三类视觉强度：danger 红 / info 中性蓝 / warning 橙） ── */
.block-banner {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 18px 20px;
  border: 1px solid var(--color-danger-border);
  border-radius: 10px;
  background: var(--color-danger-bg);
}

.banner-icon {
  font-size: 40px;
  line-height: 1.2;
}

.banner-title {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 700;
  color: var(--color-danger);
}

.banner-subtitle {
  margin: 0;
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
}

/* 医疗拒答：中性蓝色信息样式（不使用惊悚视觉） */
.theme-info .block-banner {
  border-color: var(--color-info-border);
  background: var(--color-info-bg);
}

.theme-info .banner-title {
  color: var(--color-info);
}

/* 伪科学：橙色科普样式 */
.theme-warning .block-banner {
  border-color: var(--color-warning-border);
  background: var(--color-warning-bg);
}

.theme-warning .banner-title {
  color: var(--color-warning);
}

/* ── 元信息行 ── */
.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  padding: 12px 4px 0;
  font-size: var(--font-sm);
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.meta-label {
  color: var(--color-info);
}

.meta-value {
  color: var(--text-main);
  font-weight: 600;
}

.mono {
  font-family: Consolas, Menlo, monospace;
}

/* ── 三块内容卡 ── */
.card {
  margin-top: 16px;
}

.card-title {
  font-size: var(--font-md);
  font-weight: 600;
}

.risk-title-text {
  margin: 0 0 8px;
  font-size: var(--font-md);
  font-weight: 600;
}

.card-body {
  margin: 0;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ① 风险说明卡：主题色左边条强调（图标+文字承载语义，不依赖颜色） */
.risk-card {
  border-left: 4px solid var(--color-danger);
}

.theme-info .risk-card {
  border-left-color: var(--color-info);
}

.theme-warning .risk-card {
  border-left-color: var(--color-warning);
}

/* ③ 处置建议卡：就医关键词加粗强调 */
.advice-strong {
  color: var(--color-danger);
  font-weight: 700;
}

.theme-info .advice-strong {
  color: var(--text-main);
}

/* ── 底部：申诉入口 + 免责条 ── */
.appeal-done {
  margin: 16px 0 0;
  font-size: var(--font-sm);
  color: var(--color-info);
}

.footer-row {
  display: flex;
  justify-content: flex-start;
  margin: 20px 0 12px;
}

.dialog-tip {
  margin: 0 0 12px;
  font-size: var(--font-sm);
  color: var(--color-info);
}
</style>
