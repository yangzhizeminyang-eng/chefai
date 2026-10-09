<!-- 文件职责：反馈工单。状态 Tab（pending / processing / resolved）+ 流转按钮（开始处理 / 标记解决）。 -->
<script setup lang="ts">
/**
 * 反馈工单逻辑：按状态 Tab 切换拉取列表，流转操作（pending→processing→resolved）带确认。
 * 所有写操作前置确认，只读角色统一拦截提示。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { listFeedbacks, notifyApiError, transitionFeedback } from '@/api/admin'
import type { FeedbackStatus, FeedbackTicket } from '@/api/admin'
import { useSimpleList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { confirmAction } from '@/utils/interaction'
import { formatDate } from '@/utils/format'

const auth = useAuthStore()

/** 状态 Tab 配置 */
const TABS: { value: FeedbackStatus; label: string }[] = [
  { value: 'pending', label: '待处理' },
  { value: 'processing', label: '处理中' },
  { value: 'resolved', label: '已解决' },
]

/** 状态中文映射 */
const STATUS_LABELS: Record<FeedbackStatus, string> = {
  pending: '待处理',
  processing: '处理中',
  resolved: '已解决',
}

/** 当前激活的状态 Tab */
const activeStatus = ref<FeedbackStatus>('pending')

// 列表三态（随 Tab 切换重新拉取）
const { loading, error, items, load } = useSimpleList<FeedbackTicket>(async () =>
  (await listFeedbacks({ status: activeStatus.value })).items,
)

/**
 * Tab 切换：重置到对应状态并刷新。
 */
async function onTabChange(): Promise<void> {
  await load()
}

/**
 * 开始处理工单（pending → processing）。
 * @param row 工单行
 */
async function handleStart(row: FeedbackTicket): Promise<void> {
  if (!auth.ensureWritable()) return
  if (!await confirmAction(`确认开始处理工单 #${row.id}？`, '流转确认')) return
  try {
    await transitionFeedback(row.id, 'start')
    ElMessage.success('已开始处理')
    await load()
  } catch (e) {
    notifyApiError(e, '流转失败')
  }
}

/**
 * 标记解决工单（processing → resolved）。
 * @param row 工单行
 */
async function handleResolve(row: FeedbackTicket): Promise<void> {
  if (!auth.ensureWritable()) return
  if (!await confirmAction(`确认将工单 #${row.id} 标记为已解决？`, '流转确认')) return
  try {
    await transitionFeedback(row.id, 'resolve')
    ElMessage.success('已标记解决')
    await load()
  } catch (e) {
    notifyApiError(e, '流转失败')
  }
}

onMounted(() => {
  load()
})
</script>

<template>
  <div class="page">
    <el-card shadow="never">
      <el-tabs v-model="activeStatus" @tab-change="onTabChange">
        <el-tab-pane v-for="tab in TABS" :key="tab.value" :label="tab.label" :name="tab.value" />
      </el-tabs>

      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" class="block">
        <el-button size="small" @click="load">重试</el-button>
      </el-alert>

      <el-table v-loading="loading" :data="items" border stripe>
        <template #empty><el-empty description="暂无工单数据" /></template>
        <el-table-column prop="id" label="工单号" width="100" />
        <el-table-column prop="content" label="反馈内容" min-width="240" show-overflow-tooltip />
        <el-table-column label="类型" width="120">
          <template #default="{ row }">{{ row.type || '-' }}</template>
        </el-table-column>
        <el-table-column label="用户（脱敏）" width="160">
          <template #default="{ row }">
            <span class="mono">{{ row.user_id_hash || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'resolved' ? 'success' : row.status === 'processing' ? 'primary' : 'warning'">
              {{ STATUS_LABELS[row.status as FeedbackStatus] ?? row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'pending'" link type="primary" @click="handleStart(row)">开始处理</el-button>
            <el-button v-if="row.status === 'processing'" link type="success" @click="handleResolve(row)">标记解决</el-button>
            <span v-if="row.status === 'resolved'" class="muted">已完结</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>
