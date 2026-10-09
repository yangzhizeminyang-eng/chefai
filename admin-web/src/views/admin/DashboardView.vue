<!-- 文件职责：数据看板。左侧成本看板（按日 token / 请求 / 费用 + 合计），右侧风控告警（按日拦截数 + 规则命中排行）。 -->
<script setup lang="ts">
/**
 * 看板逻辑：并行拉取成本与风控两路数据，各自维护加载 / 错误 / 空三态。
 */
import { computed, onMounted, ref } from 'vue'

import { getDashboardCost, getDashboardRisk, getErrorMessage } from '@/api/admin'
import type { CostDay, RiskDay, RiskRuleStat } from '@/api/admin'
import { formatDate, formatNumber, formatYuan } from '@/utils/format'

// —— 成本看板 ——
const costLoading = ref(false)
const costError = ref('')
const costDays = ref<CostDay[]>([])

/** 成本合计（token / 请求 / 费用分） */
const costTotal = computed<{ tokens: number; requests: number; cost: number }>(() => {
  return costDays.value.reduce(
    (acc, day) => ({
      tokens: acc.tokens + (day.tokens ?? 0),
      requests: acc.requests + (day.requests ?? 0),
      cost: acc.cost + (day.cost_cents ?? 0),
    }),
    { tokens: 0, requests: 0, cost: 0 },
  )
})

// —— 风控告警看板 ——
const riskLoading = ref(false)
const riskError = ref('')
const riskDays = ref<RiskDay[]>([])

/** 按规则聚合的命中排行（跨天累加后降序） */
const ruleRank = computed<RiskRuleStat[]>(() => {
  const map = new Map<string, number>()
  for (const day of riskDays.value) {
    for (const stat of day.by_rule ?? []) {
      map.set(stat.rule_id, (map.get(stat.rule_id) ?? 0) + (stat.count ?? 0))
    }
  }
  return Array.from(map.entries())
    .map(([rule_id, count]) => ({ rule_id, count }))
    .sort((a, b) => b.count - a.count)
})

/** 规则命中最多次数（用于进度条比例基准） */
const maxRuleCount = computed<number>(() => ruleRank.value[0]?.count ?? 0)

/**
 * 计算规则命中占比百分比。
 * @param count 命中次数
 * @returns 0-100 的整数百分比
 */
function rulePercent(count: number): number {
  if (maxRuleCount.value <= 0) return 0
  return Math.min(100, Math.round((count / maxRuleCount.value) * 100))
}

/**
 * 计算按日拦截率展示文案。
 * @param row 风控按日数据
 * @returns 形如 "12.5%" 的文案；总数为 0 时返回 "-"
 */
function blockedRate(row: RiskDay): string {
  const total = row.total ?? 0
  if (total <= 0) return '-'
  return `${(((row.blocked ?? 0) / total) * 100).toFixed(1)}%`
}

/**
 * 加载成本看板数据。
 */
async function loadCost(): Promise<void> {
  costLoading.value = true
  costError.value = ''
  try {
    costDays.value = (await getDashboardCost()).days
  } catch (e) {
    costError.value = getErrorMessage(e, '成本看板加载失败')
    costDays.value = []
  } finally {
    costLoading.value = false
  }
}

/**
 * 加载风控告警看板数据。
 */
async function loadRisk(): Promise<void> {
  riskLoading.value = true
  riskError.value = ''
  try {
    riskDays.value = (await getDashboardRisk()).days
  } catch (e) {
    riskError.value = getErrorMessage(e, '风控看板加载失败')
    riskDays.value = []
  } finally {
    riskLoading.value = false
  }
}

onMounted(() => {
  loadCost()
  loadRisk()
})
</script>

<template>
  <div class="page">
    <el-row :gutter="16">
      <!-- 成本看板 -->
      <el-col :xs="24" :lg="12">
        <el-card shadow="never" class="block">
          <template #header><b>成本看板（按日）</b></template>
          <el-alert v-if="costError" type="error" :title="costError" show-icon :closable="false" class="block">
            <el-button size="small" @click="loadCost">重试</el-button>
          </el-alert>
          <el-table v-loading="costLoading" :data="costDays" border stripe size="small" max-height="420">
            <template #empty><el-empty description="暂无成本数据" /></template>
            <el-table-column label="日期" min-width="110">
              <template #default="{ row }">{{ formatDate(row.date, 'YYYY-MM-DD') }}</template>
            </el-table-column>
            <el-table-column label="Token 用量" min-width="110">
              <template #default="{ row }">{{ formatNumber(row.tokens) }}</template>
            </el-table-column>
            <el-table-column label="请求数" min-width="90">
              <template #default="{ row }">{{ formatNumber(row.requests) }}</template>
            </el-table-column>
            <el-table-column label="费用" min-width="100">
              <template #default="{ row }">{{ formatYuan(row.cost_cents) }}</template>
            </el-table-column>
          </el-table>
          <el-descriptions :column="3" border size="small" class="summary">
            <el-descriptions-item label="Token 合计">{{ formatNumber(costTotal.tokens) }}</el-descriptions-item>
            <el-descriptions-item label="请求合计">{{ formatNumber(costTotal.requests) }}</el-descriptions-item>
            <el-descriptions-item label="费用合计">{{ formatYuan(costTotal.cost) }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <!-- 风控告警 -->
      <el-col :xs="24" :lg="12">
        <el-card shadow="never" class="block">
          <template #header><b>风控告警（按日）</b></template>
          <el-alert v-if="riskError" type="error" :title="riskError" show-icon :closable="false" class="block">
            <el-button size="small" @click="loadRisk">重试</el-button>
          </el-alert>
          <el-table v-loading="riskLoading" :data="riskDays" border stripe size="small" max-height="260">
            <template #empty><el-empty description="暂无风控数据" /></template>
            <el-table-column label="日期" min-width="110">
              <template #default="{ row }">{{ formatDate(row.date, 'YYYY-MM-DD') }}</template>
            </el-table-column>
            <el-table-column label="总调用" min-width="90">
              <template #default="{ row }">{{ formatNumber(row.total) }}</template>
            </el-table-column>
            <el-table-column label="拦截数" min-width="90">
              <template #default="{ row }">{{ formatNumber(row.blocked) }}</template>
            </el-table-column>
            <el-table-column label="拦截率" min-width="90">
              <template #default="{ row }">{{ blockedRate(row) }}</template>
            </el-table-column>
          </el-table>
          <div class="sub-title">规则命中排行（按日聚合）</div>
          <el-table :data="ruleRank" border size="small" max-height="220">
            <template #empty><el-empty description="暂无规则命中记录" /></template>
            <el-table-column label="规则 ID" min-width="150">
              <template #default="{ row }"><span class="mono">{{ row.rule_id }}</span></template>
            </el-table-column>
            <el-table-column label="命中次数" width="100">
              <template #default="{ row }">{{ formatNumber(row.count) }}</template>
            </el-table-column>
            <el-table-column label="占比" min-width="140">
              <template #default="{ row }">
                <el-progress :percentage="rulePercent(row.count)" :stroke-width="8" />
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.summary {
  margin-top: 16px;
}
</style>
