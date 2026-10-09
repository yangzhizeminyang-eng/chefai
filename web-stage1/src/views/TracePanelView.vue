<script setup lang="ts">
/**
 * 文件职责：W-06 Agent 调度可视化面板（/trace）。
 * 阶段一专属交付物：按 request_id 展示多智能体调度证据（agent_trace 落库数据）。
 * - 查询区：request_id 输入 + 查询按钮 + 「最近请求」下拉（listTraces 拉最近 20 条，支持演示场景切换）；
 *   挂载时若路由带 ?request_id=（来自 W-02「查看调度详情」入口）自动填入查询框并执行查询（M6/T3 ID 串联）；
 *   挂载时先确保匿名 ID 就绪（sessionStore.ensureAnonymousId）再拉最近列表，
 *   避免匿名 ID 懒初始化与首屏请求竞态导致列表为空（T1/L2 修复）。
 * - 概览区：request_id / 总耗时（sum duration_ms）/ 总 token（prompt+completion）/ 总成本（sum cost_cents，元=分/100 保留 4 位）；
 * - 风控判定卡：hit / category / rule_id / message_id；
 * - 一票否决大横幅：veto=true 时 el-alert error 高亮「一票否决已触发：其余 N 个节点未执行」；
 * - 节点表：状态（七态 el-tag 颜色映射）/ 耗时 / 模型 / token / 成本 / 命中规则；否决相关行加粗高亮；
 * - 三态：查询中 loading / 空（无 trace）el-empty「请先发起一次请求」/ 异常 el-alert + 重试。
 * 数据一律本地 state + 直接调 endpoints（不改动 store）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getTrace, listTraces } from '@/api/endpoints'
import type { ApiError, TraceDetail, TraceListItem, TraceSpan } from '@/api/types'
import { useSessionStore } from '@/stores/session'
import { formatCost } from '@/utils/recipe'

/** 路由（读取 ?request_id= 查询参数，W-02「查看调度详情」入口串联用） */
const route = useRoute()
/** 会话 store（挂载时先确保匿名 ID 就绪，再拉最近列表，T1/L2 竞态修复） */
const sessionStore = useSessionStore()

/* ── 查询区状态 ── */
/** 输入框中的 request_id */
const requestId = ref('')
/** 查询进行中标记 */
const loading = ref(false)
/** 查询错误（归一化 ApiError） */
const error = ref<ApiError | null>(null)
/** trace 详情（null = 尚未查到，走空态） */
const traceDetail = ref<TraceDetail | null>(null)

/* ── 最近请求列表状态 ── */
/** 最近 trace 列表（最多 20 条） */
const recentList = ref<TraceListItem[]>([])
/** 最近列表加载中标记 */
const listLoading = ref(false)
/** 最近请求下拉当前选中值（回显当前演示场景对应的 request_id） */
const recentSelected = ref('')

/**
 * 挂载初始化（T1/L2 + M6/T3 修复）：
 * 1. 先确保匿名 ID 就绪（懒获取并持久化 localStorage），再拉最近列表——
 *    避免「首屏列表请求先于匿名 ID 创建发出 → 后端无该匿名用户的 trace 记录」的竞态，
 *    该竞态此前表现为首次进入列表为空、手动刷新才加载；
 * 2. 路由带 ?request_id= 时（W-02「查看调度详情」入口进入）自动填入查询框并执行查询。
 * @returns 无
 */
onMounted(async () => {
  // ensureAnonymousId 内部已兜底（后端不可用时本地生成），不会向调用方抛出异常
  await sessionStore.ensureAnonymousId()
  void loadRecent()
  // 从推荐结果页串联进入：?request_id= 自动填入查询框（queryTrace 内回填）并查询
  const fromQuery = typeof route.query.request_id === 'string' ? route.query.request_id.trim() : ''
  if (fromQuery) void queryTrace(fromQuery)
})

/**
 * 拉取最近 trace 列表（GET /v1/trace?limit=20）。
 * @returns 无（结果写入 recentList；异常时置空列表保持页面可用）
 */
async function loadRecent(): Promise<void> {
  listLoading.value = true
  try {
    recentList.value = await listTraces(20)
  } catch {
    // 列表拉取失败属辅助功能：静默置空，不阻塞手动 request_id 查询
    recentList.value = []
  } finally {
    listLoading.value = false
  }
}

/**
 * 查询指定 request_id 的调度 trace（GET /v1/trace/{request_id}）。
 * @param id 可选显式传入的 request_id（最近列表选择时使用；缺省读输入框）
 * @returns 无（成功写 traceDetail；失败写 error 并清空详情）
 */
async function queryTrace(id?: string): Promise<void> {
  const target = (id ?? requestId.value).trim()
  if (!target) {
    ElMessage.warning('请输入 request_id')
    return
  }
  requestId.value = target
  loading.value = true
  error.value = null
  try {
    traceDetail.value = await getTrace(target)
  } catch (e) {
    traceDetail.value = null
    error.value = e as ApiError
  } finally {
    loading.value = false
  }
}

/**
 * 最近请求下拉选中：回填输入框并立即查询（演示场景切换）。
 * @param id 选中的 request_id
 * @returns 无
 */
function onRecentChange(id: string): void {
  if (id) void queryTrace(id)
}

/* ── 概览汇总（节点 span 求和；节点缺失时回退 totals） ── */
const summary = computed(() => {
  const detail = traceDetail.value
  if (!detail) return null
  const nodes = detail.nodes ?? []
  const sum = (pick: (n: TraceSpan) => number): number => nodes.reduce((acc, n) => acc + (pick(n) || 0), 0)
  const totals = detail.totals
  return {
    /** 总耗时 ms（sum duration_ms） */
    durationMs: nodes.length ? sum((n) => n.duration_ms) : 0,
    /** 总 token（prompt + completion；无节点时回退后端 totals 汇总） */
    totalTokens:
      (nodes.length ? sum((n) => n.prompt_tokens) : (totals?.prompt_tokens ?? 0)) +
      (nodes.length ? sum((n) => n.completion_tokens) : (totals?.completion_tokens ?? 0)),
    /** 总成本（分；无节点时回退后端 totals 汇总） */
    costCents: nodes.length ? sum((n) => n.cost_cents) : (totals?.cost_cents ?? 0),
  }
})

/** 一票否决是否触发 */
const isVeto = computed(() => traceDetail.value?.veto?.veto === true)

/** 一票否决相关节点数（not_executed / skipped_by_veto），用于「其余 N 个节点未执行」 */
const vetoNodeCount = computed(
  () =>
    (traceDetail.value?.nodes ?? []).filter(
      (n) => n.status === 'not_executed' || n.status === 'skipped_by_veto',
    ).length,
)

/** 一票否决横幅描述（有 reason 用 reason，否则用固定纯净返回体说明） */
const vetoDescription = computed(
  () => traceDetail.value?.veto?.reason || '输入闸门命中阻断规则，业务节点短路未执行，返回体不包含任何推荐/问答/营养内容。',
)

/**
 * ISO 时间 → 本地可读时间（最近列表展示用）。
 * @param iso ISO 8601 时间串
 * @returns 本地时间串（解析失败时原样返回）
 */
function formatTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('zh-CN', { hour12: false })
}

/**
 * 节点状态 → el-tag 类型与中文文案映射（七态；否决跳过附「未执行」语义文案）。
 * @param status 节点状态
 * @returns tag 类型与展示文案
 */
function statusMeta(status: TraceSpan['status']): {
  type: 'success' | 'warning' | 'danger' | 'info' | 'primary'
  label: string
} {
  switch (status) {
    case 'ok':
      return { type: 'success', label: '成功' }
    case 'degraded':
      return { type: 'warning', label: '降级' }
    case 'failed':
      return { type: 'danger', label: '失败' }
    case 'timeout':
      return { type: 'danger', label: '超时' }
    case 'not_executed':
      return { type: 'info', label: '未执行' }
    case 'skipped_by_veto':
      return { type: 'info', label: '未执行 · 被否决跳过' }
    case 'running':
      return { type: 'primary', label: '执行中' }
    default:
      return { type: 'info', label: String(status) }
  }
}

/**
 * 节点表行类名：一票否决相关行（not_executed / skipped_by_veto）加粗高亮。
 * @param param0 含当前行数据的上下文
 * @returns 行类名（否决相关行为 veto-row，其余空串）
 */
function vetoRowClass({ row }: { row: TraceSpan }): string {
  return row.status === 'not_executed' || row.status === 'skipped_by_veto' ? 'veto-row' : ''
}

/** 风险类别中文标签映射（与 W-05 一致；未收录编码原样展示） */
const CATEGORY_LABELS: Record<string, string> = {
  food_safety_high_risk: '食品安全高风险',
  medical_refusal: '医疗建议拒答',
  pseudoscience: '伪科学内容澄清',
  allergen_conflict: '过敏原冲突',
  special_population: '特殊人群风险',
  injection: '注入攻击拦截',
}
</script>

<template>
  <section class="page-card trace-page">
    <!-- 页头 -->
    <h1 class="page-title">Agent 调度可视化面板</h1>
    <p class="page-desc">按 request_id 查询本次请求的多智能体调度证据（节点耗时 / 模型 / token / 成本 / 风控判定）。</p>

    <!-- 查询区：request_id 输入 + 查询按钮 + 最近请求切换 -->
    <el-card class="query-card" shadow="never">
      <div class="query-row">
        <el-input
          v-model="requestId"
          class="query-input"
          placeholder="输入 request_id，如 req_20261005_a71c"
          clearable
          @keyup.enter="queryTrace()"
        />
        <el-button type="primary" :loading="loading" @click="queryTrace()">查询</el-button>
      </div>
      <div class="recent-row">
        <span class="recent-label">最近请求</span>
        <el-select
          v-model="recentSelected"
          class="recent-select"
          :loading="listLoading"
          placeholder="选择最近请求快速切换演示场景"
          @change="onRecentChange"
        >
          <el-option
            v-for="item in recentList"
            :key="item.request_id"
            :label="`${item.request_id} · ${formatTime(item.created_at)}${item.veto ? ' · 一票否决' : ''}`"
            :value="item.request_id"
          />
          <template #empty>
            <p class="recent-empty">暂无最近请求（请先在食材选择页发起一次搜索或推荐）</p>
          </template>
        </el-select>
        <el-button :loading="listLoading" @click="loadRecent()">刷新列表</el-button>
      </div>
    </el-card>

    <!-- 异常态：查询失败 + 重试 -->
    <el-alert
      v-if="error"
      class="state-alert"
      type="error"
      show-icon
      :closable="false"
      :title="`查询失败：${error.message}`"
    >
      <el-button size="small" type="primary" plain @click="queryTrace(requestId)">重试</el-button>
    </el-alert>

    <!-- 空态：尚未查询 / 查无记录 → 引导先发起一次请求 -->
    <el-empty v-else-if="!traceDetail && !loading" description="请先发起一次请求" />

    <!-- 结果区：概览 / 风控判定 / 一票否决横幅 / 节点表 -->
    <template v-else>
      <div v-loading="loading" element-loading-text="正在查询调度证据…">
        <!-- 一票否决大横幅（veto=true 时高亮） -->
        <el-alert
          v-if="isVeto"
          class="veto-banner"
          type="error"
          show-icon
          :closable="false"
          :title="`一票否决已触发：其余 ${vetoNodeCount} 个节点未执行`"
          :description="vetoDescription"
        />

        <!-- 概览区：request_id / 总耗时 / 总 token / 总成本 -->
        <el-card class="block-card" shadow="never">
          <template #header><span class="block-title">调度概览</span></template>
          <div v-if="summary" class="stat-grid">
            <div class="stat-cell">
              <span class="stat-label">request_id</span>
              <span class="stat-value mono">{{ traceDetail?.request_id }}</span>
            </div>
            <div class="stat-cell">
              <span class="stat-label">总耗时</span>
              <span class="stat-value">{{ summary.durationMs }} ms</span>
            </div>
            <div class="stat-cell">
              <span class="stat-label">总 token</span>
              <span class="stat-value">{{ summary.totalTokens }}</span>
            </div>
            <div class="stat-cell">
              <span class="stat-label">总成本</span>
              <span class="stat-value">{{ formatCost(summary.costCents) }}</span>
            </div>
          </div>
        </el-card>

        <!-- 风控判定卡：hit / category / rule_id / message_id -->
        <el-card class="block-card" shadow="never">
          <template #header><span class="block-title">风控判定</span></template>
          <el-descriptions v-if="traceDetail?.risk?.hit" :column="2" border size="small">
            <el-descriptions-item label="是否命中">{{ traceDetail.risk.hit ? '是' : '否' }}</el-descriptions-item>
            <el-descriptions-item label="类别">
              {{ CATEGORY_LABELS[traceDetail.risk.category ?? ''] ?? traceDetail.risk.category ?? '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="命中规则 ID">
              <span class="mono">{{ traceDetail.risk.rule_id || '—' }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="话术模板 ID">
              <span class="mono">{{ traceDetail.risk.message_id || '—' }}</span>
            </el-descriptions-item>
          </el-descriptions>
          <p v-else class="risk-pass-text">ℹ️ 本次请求未命中风控规则（正常放行）。</p>
        </el-card>

        <!-- 节点表：状态 / 耗时 / 模型 / token / 成本 / 命中规则；否决相关行高亮 -->
        <el-card class="block-card" shadow="never">
          <template #header>
            <span class="block-title">节点执行列表（{{ traceDetail?.nodes?.length ?? 0 }} 个）</span>
          </template>
          <el-table :data="traceDetail?.nodes ?? []" size="small" :row-class-name="vetoRowClass">
            <el-table-column prop="node_name" label="节点名" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="mono">{{ row.node_name }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="170">
              <template #default="{ row }">
                <el-tag :type="statusMeta(row.status).type" effect="light" size="small">
                  {{ statusMeta(row.status).label }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="耗时(ms)" width="95" align="right">
              <template #default="{ row }">{{ row.duration_ms }}</template>
            </el-table-column>
            <el-table-column label="模型" min-width="130" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="mono">{{ row.model_name || '—（纯规则）' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="输入 token" prop="prompt_tokens" width="100" align="right" sortable />
            <el-table-column label="输出 token" prop="completion_tokens" width="100" align="right" sortable />
            <el-table-column label="成本" width="100" align="right">
              <template #default="{ row }">{{ formatCost(row.cost_cents) }}</template>
            </el-table-column>
            <el-table-column label="命中规则" width="110">
              <template #default="{ row }">
                <span class="mono">{{ row.rule_hit || '—' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </div>
    </template>
  </section>
</template>

<style scoped>
.page-desc {
  margin: -8px 0 16px;
  font-size: var(--font-sm);
  color: var(--color-info);
}

/* ── 查询区 ── */
.query-card {
  margin-bottom: 16px;
}

.query-row {
  display: flex;
  gap: 12px;
}

.query-input {
  max-width: 420px;
}

.recent-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}

.recent-label {
  font-size: var(--font-sm);
  color: var(--color-info);
  white-space: nowrap;
}

.recent-select {
  flex: 1;
  min-width: 260px;
  max-width: 560px;
}

.recent-empty {
  margin: 0;
  padding: 12px;
  font-size: var(--font-sm);
  color: var(--color-info);
  text-align: center;
}

/* ── 状态区 ── */
.state-alert {
  margin-bottom: 16px;
}

/* ── 一票否决大横幅 ── */
.veto-banner {
  margin-bottom: 16px;
}

/* ── 分块卡片 ── */
.block-card {
  margin-bottom: 16px;
}

.block-title {
  font-size: var(--font-md);
  font-weight: 600;
}

/* 概览统计网格 */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.stat-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--color-info-bg);
}

.stat-label {
  font-size: 12px;
  color: var(--color-info);
}

.stat-value {
  font-size: var(--font-lg);
  font-weight: 600;
  word-break: break-all;
}

.mono {
  font-family: Consolas, Menlo, monospace;
}

.risk-pass-text {
  margin: 0;
  font-size: var(--font-sm);
  color: var(--color-info);
}

/* ── 一票否决相关行加粗 + 背景高亮（深浅模式经 CSS 变量自适应） ── */
:deep(tr.veto-row) {
  background-color: var(--color-warning-bg);
}

:deep(tr.veto-row > td.el-table__cell) {
  background-color: var(--color-warning-bg);
  font-weight: 600;
}

/* 窄屏降级：概览统计两列 */
@media (max-width: 860px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
