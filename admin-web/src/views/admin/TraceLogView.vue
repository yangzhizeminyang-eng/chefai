<!-- 文件职责：Agent 调用日志。时间范围 / 节点 / 状态 / 规则命中四维筛选 + 分页表格（脱敏 user_id_hash）+ 展开行查看节点详情。 -->
<script setup lang="ts">
/**
 * Agent 日志逻辑：四维筛选条件管理、分页检索、展开行 JSON 详情展示。
 */
import { onMounted, reactive } from 'vue'

import { listTraceLogs } from '@/api/admin'
import type { TraceLogItem } from '@/api/admin'
import { usePagedList } from '@/composables/useList'
import { formatDate } from '@/utils/format'

/** Agent 节点选项（与远程开关的五大能力对齐） */
const NODE_OPTIONS = [
  { value: 'recommend', label: '推荐' },
  { value: 'vision', label: '视觉识别' },
  { value: 'qa', label: '智能问答' },
  { value: 'payment', label: '支付' },
  { value: 'innovation', label: '创新' },
]

/** 节点中文映射 */
const NODE_LABELS: Record<string, string> = {
  recommend: '推荐',
  vision: '视觉识别',
  qa: '智能问答',
  payment: '支付',
  innovation: '创新',
}

/** 四维筛选条件（时间范围为 el-date-picker 的 datetimerange 值） */
const filters = reactive({
  timeRange: null as [Date, Date] | null,
  nodeName: '',
  status: '',
  ruleHit: '',
})

// 列表分页三态
const { loading, error, items, total, page, size, load, reload, onPageChange, onSizeChange } = usePagedList<TraceLogItem>(
  (p, s) => {
    const range = filters.timeRange
    return listTraceLogs({
      start: range?.[0]?.toISOString(),
      end: range?.[1]?.toISOString(),
      node_name: filters.nodeName || undefined,
      status: filters.status || undefined,
      rule_hit: filters.ruleHit.trim() || undefined,
      page: p,
      size: s,
    })
  },
)

/**
 * 重置筛选条件并刷新列表。
 */
async function resetFilters(): Promise<void> {
  filters.timeRange = null
  filters.nodeName = ''
  filters.status = ''
  filters.ruleHit = ''
  await reload()
}

/**
 * 展开行详情 JSON 序列化（优先取 nodes 字段，缺失时展示整行）。
 * @param row 日志行
 * @returns 格式化 JSON 字符串
 */
function detailJson(row: TraceLogItem): string {
  const detail = row.nodes ?? row
  try {
    return JSON.stringify(detail, null, 2)
  } catch {
    return String(detail)
  }
}

onMounted(() => {
  load()
})
</script>

<template>
  <div class="page">
    <el-card shadow="never">
      <div class="toolbar">
        <el-date-picker
          v-model="filters.timeRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          style="width: 360px"
        />
        <el-select v-model="filters.nodeName" placeholder="节点" clearable style="width: 140px">
          <el-option label="全部节点" value="" />
          <el-option v-for="opt in NODE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
        <el-select v-model="filters.status" placeholder="状态" clearable style="width: 130px">
          <el-option label="全部状态" value="" />
          <el-option label="成功" value="success" />
          <el-option label="失败" value="error" />
        </el-select>
        <el-input v-model="filters.ruleHit" placeholder="规则命中（ID / 关键词）" clearable style="width: 200px" @keyup.enter="reload" />
        <el-button type="primary" @click="reload">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>

      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" class="block">
        <el-button size="small" @click="load">重试</el-button>
      </el-alert>

      <el-table v-loading="loading" :data="items" border stripe>
        <template #empty><el-empty description="暂无日志数据" /></template>
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand-box">
              <div class="sub-title">节点详情</div>
              <pre class="json-pre">{{ detailJson(row) }}</pre>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="ID" width="90" />
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="用户（脱敏）" width="160">
          <template #default="{ row }">
            <span class="mono">{{ row.user_id_hash || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="节点" width="110">
          <template #default="{ row }">{{ NODE_LABELS[row.node_name] ?? row.node_name ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'error' ? 'danger' : 'success'">{{ row.status === 'error' ? '失败' : '成功' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="规则命中" width="130">
          <template #default="{ row }">
            <el-tag v-if="row.rule_hit" type="warning" size="small">{{ row.rule_hit }}</el-tag>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="耗时(ms)" width="100">
          <template #default="{ row }">{{ row.duration_ms ?? '-' }}</template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          :current-page="page"
          :page-size="size"
          :page-sizes="[10, 20, 50, 100]"
          @current-change="onPageChange"
          @size-change="onSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.expand-box {
  padding: 8px 16px 8px 48px;
}
</style>
