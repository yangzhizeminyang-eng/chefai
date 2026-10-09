<!-- 文件职责：操作日志（只读）。分页表格 + before/after JSON 对比抽屉。日志由后端自动产生，前端不做写操作。 -->
<script setup lang="ts">
/**
 * 操作日志逻辑：分页检索三态、查看抽屉展示操作人 / IP / 前后快照对比。
 */
import { ref } from 'vue'

import { listOperationLogs } from '@/api/admin'
import type { OperationLog } from '@/api/admin'
import { usePagedList } from '@/composables/useList'
import { formatDate } from '@/utils/format'

// 列表分页三态
const { loading, error, items, total, page, size, load, onPageChange, onSizeChange } = usePagedList<OperationLog>(
  (p, s) => listOperationLogs({ page: p, size: s }),
)

/** 对比抽屉显隐 */
const drawerVisible = ref(false)
/** 当前查看的日志 */
const currentLog = ref<OperationLog | null>(null)

/**
 * 打开对比抽屉。
 * @param row 日志行
 */
function openDetail(row: OperationLog): void {
  currentLog.value = row
  drawerVisible.value = true
}

/**
 * 快照 JSON 序列化（后端可能返回对象或 JSON 字符串，空值显示占位）。
 * @param value 快照原始值
 * @returns 可展示的字符串
 */
function snapshotJson(value: unknown): string {
  if (value === undefined || value === null) return '（无快照）'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
</script>

<template>
  <div class="page">
    <el-card shadow="never">
      <div class="toolbar">
        <span class="muted">操作日志由后端自动产生，本页面只读展示。</span>
        <div class="grow" />
        <el-button @click="load">刷新</el-button>
      </div>

      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" class="block">
        <el-button size="small" @click="load">重试</el-button>
      </el-alert>

      <el-table v-loading="loading" :data="items" border stripe>
        <template #empty><el-empty description="暂无操作日志" /></template>
        <el-table-column prop="id" label="ID" width="90" />
        <el-table-column prop="module" label="模块" width="140">
          <template #default="{ row }"><span class="mono">{{ row.module }}</span></template>
        </el-table-column>
        <el-table-column prop="action" label="动作" width="140">
          <template #default="{ row }"><span class="mono">{{ row.action }}</span></template>
        </el-table-column>
        <el-table-column prop="operator" label="操作人" width="130" />
        <el-table-column prop="ip" label="IP" width="140">
          <template #default="{ row }"><span class="mono">{{ row.ip || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">查看对比</el-button>
          </template>
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

    <!-- before / after JSON 对比抽屉 -->
    <el-drawer v-model="drawerVisible" title="操作快照对比" size="56%">
      <el-descriptions v-if="currentLog" :column="2" border size="small" class="block">
        <el-descriptions-item label="模块">{{ currentLog.module }}</el-descriptions-item>
        <el-descriptions-item label="动作">{{ currentLog.action }}</el-descriptions-item>
        <el-descriptions-item label="操作人">{{ currentLog.operator }}</el-descriptions-item>
        <el-descriptions-item label="IP">{{ currentLog.ip || '-' }}</el-descriptions-item>
        <el-descriptions-item label="时间" :span="2">{{ formatDate(currentLog.created_at) }}</el-descriptions-item>
      </el-descriptions>
      <div class="sub-title">变更前（before_snapshot）</div>
      <pre class="json-pre">{{ snapshotJson(currentLog?.before_snapshot) }}</pre>
      <div class="sub-title">变更后（after_snapshot）</div>
      <pre class="json-pre">{{ snapshotJson(currentLog?.after_snapshot) }}</pre>
    </el-drawer>
  </div>
</template>
