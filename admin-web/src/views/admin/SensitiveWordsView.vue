<!-- 文件职责：违禁词管理（remote_config 词表全量模型：word + replacement + category，无行 ID）。 -->
<script setup lang="ts">
/**
 * 违禁词逻辑（对齐后端真实契约）：
 * - 词表存 remote_config 'output_sensitive_words'（JSONB 数组），无按行 ID；
 * - 列表 = GET {words, version, active_source, builtin_rules}；
 * - 新增 = POST 追加（重复 409）；删除 = DELETE ?word=；编辑 = 以 PUT 全量替换实现
 *   （按 word 定位替换 replacement/category，前端整体提交）；
 * - active_source='builtin' 表示当前生效的是代码内置表，自定义词表为空。
 * 所有写操作前置确认，只读角色统一拦截提示。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

import {
  createSensitiveWord,
  deleteSensitiveWord,
  listSensitiveWords,
  notifyApiError,
  replaceSensitiveWords,
} from '@/api/admin'
import type { SensitiveWordEntry } from '@/api/admin'
import { useSimpleList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { confirmAction } from '@/utils/interaction'

const auth = useAuthStore()

/** 词表查询响应（words 之外的元信息） */
const state = reactive({ version: 0, active_source: 'builtin', builtin_rules: 0 })

// 列表三态
const { loading, error, items, load } = useSimpleList<SensitiveWordEntry>(async () => {
  const res = await listSensitiveWords()
  state.version = res.version
  state.active_source = res.active_source
  state.builtin_rules = res.builtin_rules
  return res.words
})

/** 当前生效来源说明 */
const sourceText = computed(() =>
  state.active_source === 'remote_config'
    ? `自定义词表生效（version ${state.version}）`
    : `代码内置词表生效（共 ${state.builtin_rules} 条），自定义词表为空`,
)

// ==================== 新增 ====================

const dialogVisible = ref(false)
/** 保存请求进行中标记 */
const saving = ref(false)
/** 表单引用（用于触发校验） */
const formRef = ref<FormInstance>()

/** 词条表单（replacement 必填：命中后输出的合规替换文本） */
const form = reactive({ word: '', replacement: '', category: 'custom' })

/** 表单校验规则 */
const rules: FormRules = {
  word: [{ required: true, message: '请输入违禁词', trigger: 'blur' }],
  replacement: [{ required: true, message: '请输入替换文本（命中后输出）', trigger: 'blur' }],
}

/**
 * 打开新增对话框（只读角色拦截）。
 */
function openCreate(): void {
  if (!auth.ensureWritable()) return
  form.word = ''
  form.replacement = ''
  form.category = 'custom'
  dialogVisible.value = true
}

/**
 * 追加违禁词（重复时后端 409）。
 */
async function handleCreate(): Promise<void> {
  const valid = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  if (!await confirmAction(`确认新增违禁词「${form.word.trim()}」？`, '保存确认')) return
  saving.value = true
  try {
    await createSensitiveWord({
      word: form.word.trim(),
      replacement: form.replacement.trim(),
      category: form.category.trim() || 'custom',
    })
    ElMessage.success('新增成功')
    dialogVisible.value = false
    await load()
  } catch (e) {
    notifyApiError(e, '新增失败')
  } finally {
    saving.value = false
  }
}

// ==================== 编辑（全量替换实现） ====================

const editVisible = ref(false)
/** 当前编辑的原词（编辑不可改词本身，仅改替换文本/类别） */
const editingWord = ref('')
/** 编辑表单 */
const editForm = reactive({ replacement: '', category: '' })
const editFormRef = ref<FormInstance>()
/** 编辑保存中标记 */
const editSaving = ref(false)

/**
 * 打开编辑对话框并回填（词本身作为定位键不可改）。
 * @param row 列表行
 */
function openEdit(row: SensitiveWordEntry): void {
  if (!auth.ensureWritable()) return
  editingWord.value = row.word
  editForm.replacement = row.replacement
  editForm.category = row.category
  editVisible.value = true
}

/**
 * 保存编辑：按 word 定位替换后 PUT 全量词表。
 */
async function handleEditSave(): Promise<void> {
  const valid = await editFormRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  const next = (items.value as SensitiveWordEntry[]).map((it) =>
    it.word === editingWord.value
      ? { ...it, replacement: editForm.replacement.trim(), category: editForm.category.trim() || 'custom' }
      : it,
  )
  if (!await confirmAction(`确认保存「${editingWord.value}」的修改（全量替换词表）？`, '保存确认')) return
  editSaving.value = true
  try {
    await replaceSensitiveWords(next)
    ElMessage.success('保存成功')
    editVisible.value = false
    await load()
  } catch (e) {
    notifyApiError(e, '保存失败')
  } finally {
    editSaving.value = false
  }
}

// ==================== 删除 ====================

/**
 * 删除违禁词（DELETE ?word=）。
 * @param row 列表行
 */
async function handleDelete(row: SensitiveWordEntry): Promise<void> {
  if (!auth.ensureWritable()) return
  if (!await confirmAction(`确认删除违禁词「${row.word}」？`, '删除确认')) return
  try {
    await deleteSensitiveWord(row.word)
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
        <span class="muted">输出敏感词表：命中后按替换文本脱敏输出（word + replacement + category，无行 ID）。</span>
        <div class="grow" />
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">新增违禁词</el-button>
      </div>

      <el-alert
        type="info"
        :title="sourceText"
        :closable="false"
        class="block"
        description="自定义词表为空时，Agent 输出脱敏自动回退代码内置表；新增任一词条后即切换为自定义词表生效。"
      />

      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" class="block">
        <el-button size="small" @click="load">重试</el-button>
      </el-alert>

      <el-table v-loading="loading" :data="items" border stripe>
        <template #empty><el-empty description="暂无自定义违禁词（当前内置词表生效）" /></template>
        <el-table-column prop="word" label="违禁词" min-width="180">
          <template #default="{ row }"><span class="mono">{{ row.word }}</span></template>
        </el-table-column>
        <el-table-column prop="replacement" label="替换文本" min-width="200">
          <template #default="{ row }"><span class="mono">{{ row.replacement }}</span></template>
        </el-table-column>
        <el-table-column prop="category" label="类别" width="140">
          <template #default="{ row }">
            <el-tag type="warning">{{ row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增对话框 -->
    <el-dialog v-model="dialogVisible" title="新增违禁词" width="460px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="违禁词" prop="word">
          <el-input v-model="form.word" placeholder="违规词内容" maxlength="50" />
        </el-form-item>
        <el-form-item label="替换文本" prop="replacement">
          <el-input v-model="form.replacement" placeholder="命中后输出的合规替换文本" maxlength="100" />
        </el-form-item>
        <el-form-item label="类别">
          <el-input v-model="form.category" placeholder="缺省 custom" maxlength="30" style="width: 220px" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleCreate">保存</el-button>
      </template>
    </el-dialog>

    <!-- 编辑对话框 -->
    <el-dialog v-model="editVisible" :title="`编辑违禁词：${editingWord}`" width="460px" destroy-on-close>
      <el-form ref="editFormRef" :model="editForm" :rules="rules" label-width="90px">
        <el-form-item label="违禁词">
          <el-input :model-value="editingWord" disabled />
        </el-form-item>
        <el-form-item label="替换文本" prop="replacement">
          <el-input v-model="editForm.replacement" placeholder="命中后输出的合规替换文本" maxlength="100" />
        </el-form-item>
        <el-form-item label="类别">
          <el-input v-model="editForm.category" maxlength="30" style="width: 220px" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="handleEditSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
