<!-- 文件职责：创新菜巡检。创新菜列表（状态 tag + 筛选）+ 巡检（结果 JSON 展示）+ 下架（status → removed）。 -->
<script setup lang="ts">
/**
 * 创新菜巡检逻辑：按状态筛选列表三态、巡检（结果弹窗展示）、下架确认。
 * 所有写操作前置确认，只读角色统一拦截提示。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { inspectInnovationRecipe, listInnovationRecipes, notifyApiError, removeInnovationRecipe } from '@/api/admin'
import type { InnovationRecipe } from '@/api/admin'
import { useSimpleList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { confirmAction } from '@/utils/interaction'
import { formatDate } from '@/utils/format'

const auth = useAuthStore()

/** 状态筛选选项 */
const STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'published', label: '已发布' },
  { value: 'removed', label: '已下架' },
]

/** 状态中文与 tag 映射 */
const STATUS_META: Record<string, { label: string; type: 'success' | 'info' | 'warning' | 'primary' }> = {
  draft: { label: '草稿', type: 'warning' },
  published: { label: '已发布', type: 'success' },
  removed: { label: '已下架', type: 'info' },
}

/** 状态筛选值（空字符串表示全部） */
const status = ref('')

// 列表三态
const { loading, error, items, load } = useSimpleList<InnovationRecipe>(async () =>
  (await listInnovationRecipes({ status: status.value || undefined })).items,
)

// ==================== 巡检 / 下架 ====================

/** 巡检结果弹窗显隐 */
const inspectVisible = ref(false)
/** 巡检结果文本（JSON 格式化） */
const inspectResult = ref('')
/** 正在巡检的创新菜 ID（按钮 loading） */
const inspectingId = ref(0)

/**
 * 执行巡检：结果以 JSON 弹窗展示（无结构化返回时给出完成提示）。
 * @param row 创新菜行
 */
async function handleInspect(row: InnovationRecipe): Promise<void> {
  if (!auth.ensureWritable()) return
  if (!await confirmAction(`确认对创新菜「${row.name}」执行巡检？`, '巡检确认')) return
  inspectingId.value = row.id
  try {
    const result = await inspectInnovationRecipe(row.id)
    inspectResult.value = result === undefined || result === null
      ? '巡检完成：后端无结构化返回'
      : JSON.stringify(result, null, 2)
    inspectVisible.value = true
    await load()
  } catch (e) {
    notifyApiError(e, '巡检失败')
  } finally {
    inspectingId.value = 0
  }
}

/**
 * 下架创新菜（status → removed）。
 * @param row 创新菜行
 */
async function handleRemove(row: InnovationRecipe): Promise<void> {
  if (!auth.ensureWritable()) return
  if (!await confirmAction(`确认下架创新菜「${row.name}」？`, '下架确认')) return
  try {
    await removeInnovationRecipe(row.id)
    ElMessage.success('下架成功')
    await load()
  } catch (e) {
    notifyApiError(e, '下架失败')
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
        <el-select v-model="status" placeholder="状态" clearable style="width: 150px" @change="load">
          <el-option label="全部" value="" />
          <el-option v-for="opt in STATUS_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
        <div class="grow" />
        <el-button @click="load">刷新</el-button>
      </div>

      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" class="block">
        <el-button size="small" @click="load">重试</el-button>
      </el-alert>

      <el-table v-loading="loading" :data="items" border stripe>
        <template #empty><el-empty description="暂无创新菜数据" /></template>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="创新菜名称" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="STATUS_META[row.status]?.type ?? 'info'">{{ STATUS_META[row.status]?.label ?? row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="最近巡检" width="180">
          <template #default="{ row }">{{ formatDate(row.last_inspected_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" :loading="inspectingId === row.id" @click="handleInspect(row)">巡检</el-button>
            <el-button v-if="row.status !== 'removed'" link type="danger" @click="handleRemove(row)">下架</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 巡检结果弹窗 -->
    <el-dialog v-model="inspectVisible" title="巡检结果" width="640px">
      <pre class="json-pre">{{ inspectResult }}</pre>
      <template #footer>
        <el-button type="primary" @click="inspectVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>
