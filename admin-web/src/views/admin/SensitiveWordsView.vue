<!-- 文件职责：违禁词管理（与风控规则同构的简单 CRUD：列表 + 新增/编辑/删除）。 -->
<script setup lang="ts">
/**
 * 违禁词逻辑：列表三态、词表单（新增 / 编辑）、删除确认。
 * 所有写操作前置确认，只读角色统一拦截提示。
 */
import { onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

import { createSensitiveWord, deleteSensitiveWord, listSensitiveWords, notifyApiError, updateSensitiveWord } from '@/api/admin'
import type { SensitiveWord } from '@/api/admin'
import { useSimpleList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { confirmAction } from '@/utils/interaction'
import { formatDate } from '@/utils/format'

const auth = useAuthStore()

// 列表三态
const { loading, error, items, load } = useSimpleList<SensitiveWord>(async () => (await listSensitiveWords()).items)

// ==================== 新增 / 编辑 ====================

const dialogVisible = ref(false)
/** 当前编辑的违禁词 ID（0 表示新增） */
const editingId = ref(0)
/** 保存请求进行中标记 */
const saving = ref(false)
/** 表单引用（用于触发校验） */
const formRef = ref<FormInstance>()

/** 词表单 */
const form = reactive({ word: '' })

/** 表单校验规则 */
const rules: FormRules = {
  word: [{ required: true, message: '请输入违禁词', trigger: 'blur' }],
}

/**
 * 打开新增对话框（只读角色拦截）。
 */
function openCreate(): void {
  if (!auth.ensureWritable()) return
  editingId.value = 0
  form.word = ''
  dialogVisible.value = true
}

/**
 * 打开编辑对话框并回填。
 * @param row 列表行
 */
function openEdit(row: SensitiveWord): void {
  if (!auth.ensureWritable()) return
  editingId.value = row.id
  form.word = row.word
  dialogVisible.value = true
}

/**
 * 保存违禁词（新增或更新）。
 */
async function handleSave(): Promise<void> {
  const valid = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  if (!await confirmAction(editingId.value ? '确认保存违禁词修改？' : '确认新增违禁词？', '保存确认')) return
  saving.value = true
  try {
    if (editingId.value) {
      await updateSensitiveWord(editingId.value, { word: form.word.trim() })
      ElMessage.success('保存成功')
    } else {
      await createSensitiveWord({ word: form.word.trim() })
      ElMessage.success('新增成功')
    }
    dialogVisible.value = false
    await load()
  } catch (e) {
    notifyApiError(e, '保存失败')
  } finally {
    saving.value = false
  }
}

/**
 * 删除违禁词。
 * @param row 列表行
 */
async function handleDelete(row: SensitiveWord): Promise<void> {
  if (!auth.ensureWritable()) return
  if (!await confirmAction(`确认删除违禁词「${row.word}」？`, '删除确认')) return
  try {
    await deleteSensitiveWord(row.id)
    ElMessage.success('删除成功')
    await load()
  } catch (e) {
    notifyApiError(e, '删除失败')
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
        <span class="muted">违禁词用于输入与输出内容的风控过滤。</span>
        <div class="grow" />
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">新增违禁词</el-button>
      </div>

      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" class="block">
        <el-button size="small" @click="load">重试</el-button>
      </el-alert>

      <el-table v-loading="loading" :data="items" border stripe>
        <template #empty><el-empty description="暂无违禁词" /></template>
        <el-table-column prop="id" label="ID" width="90" />
        <el-table-column prop="word" label="违禁词" min-width="200">
          <template #default="{ row }"><span class="mono">{{ row.word }}</span></template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增 / 编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑违禁词' : '新增违禁词'" width="420px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="违禁词" prop="word">
          <el-input v-model="form.word" placeholder="违禁词内容" maxlength="100" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
