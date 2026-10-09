<!-- 文件职责：风控规则管理。规则表格（类型 / 模式 / 启停 switch+确认）+ 新增/编辑 + 按操作日志回滚（应用 before_snapshot）。 -->
<script setup lang="ts">
/**
 * 风控规则逻辑：规则列表三态、启停（确认 + 接口）、规则表单、回滚（选择操作日志）。
 * 所有写操作前置确认，只读角色统一拦截提示。
 */
import { onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

import {
  createRiskRule,
  listOperationLogs,
  listRiskRules,
  notifyApiError,
  rollbackRiskRules,
  toggleRiskRule,
  updateRiskRule,
} from '@/api/admin'
import type { OperationLog, RiskRule, RiskRulePayload } from '@/api/admin'
import { useSimpleList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { confirmAction } from '@/utils/interaction'
import { formatDate } from '@/utils/format'

const auth = useAuthStore()

/** 规则类型选项（允许自定义输入） */
const RULE_TYPE_OPTIONS = [
  { value: 'keyword', label: '关键词' },
  { value: 'regex', label: '正则表达式' },
  { value: 'user_blacklist', label: '用户黑名单' },
]

/** 规则类型中文映射 */
const RULE_TYPE_LABELS: Record<string, string> = {
  keyword: '关键词',
  regex: '正则表达式',
  user_blacklist: '用户黑名单',
}

// 列表三态
const { loading, error, items, load } = useSimpleList<RiskRule>(async () => (await listRiskRules()).items)

// ==================== 新增 / 编辑 ====================

const dialogVisible = ref(false)
/** 当前编辑的规则 ID（0 表示新增） */
const editingId = ref(0)
/** 保存请求进行中标记 */
const saving = ref(false)
/** 表单引用（用于触发校验） */
const formRef = ref<FormInstance>()

/** 规则表单（表单层面字段必填，提交时 message_id 为空才转 undefined） */
const form = reactive<{ rule_type: string; pattern: string; message_id: string; enabled: boolean }>({
  rule_type: 'keyword',
  pattern: '',
  message_id: '',
  enabled: true,
})

/** 表单校验规则 */
const rules: FormRules = {
  rule_type: [{ required: true, message: '请选择或输入规则类型', trigger: 'change' }],
  pattern: [{ required: true, message: '请输入匹配模式', trigger: 'blur' }],
}

/**
 * 打开新增对话框（只读角色拦截）。
 */
function openCreate(): void {
  if (!auth.ensureWritable()) return
  editingId.value = 0
  form.rule_type = 'keyword'
  form.pattern = ''
  form.message_id = ''
  form.enabled = true
  dialogVisible.value = true
}

/**
 * 打开编辑对话框并回填。
 * @param row 列表行
 */
function openEdit(row: RiskRule): void {
  if (!auth.ensureWritable()) return
  editingId.value = row.id
  form.rule_type = row.rule_type
  form.pattern = row.pattern
  form.message_id = row.message_id ?? ''
  form.enabled = Boolean(row.enabled)
  dialogVisible.value = true
}

/**
 * 保存规则（新增或更新）。
 */
async function handleSave(): Promise<void> {
  const valid = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  if (!await confirmAction(editingId.value ? '确认保存规则修改？' : '确认新增规则？', '保存确认')) return
  const payload: RiskRulePayload = {
    rule_type: form.rule_type.trim(),
    pattern: form.pattern.trim(),
    message_id: form.message_id.trim() || undefined,
    enabled: form.enabled,
  }
  saving.value = true
  try {
    if (editingId.value) {
      await updateRiskRule(editingId.value, payload)
      ElMessage.success('保存成功')
    } else {
      await createRiskRule(payload)
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
 * 启停规则（带确认，供 el-switch :before-change 调用）。
 * @param row 列表行
 * @returns 允许切换返回 true
 */
async function handleToggle(row: RiskRule): Promise<boolean> {
  if (!auth.ensureWritable()) return false
  if (!await confirmAction(`确认${row.enabled ? '停用' : '启用'}该规则？`, '启停确认')) return false
  try {
    await toggleRiskRule(row.id)
    row.enabled = !row.enabled
    return true
  } catch (e) {
    notifyApiError(e, '规则启停失败')
    return false
  }
}

// ==================== 回滚（选择操作日志） ====================

const rollbackVisible = ref(false)
/** 可选的操作日志列表 */
const rollbackLogs = ref<OperationLog[]>([])
/** 日志加载中标记 */
const rollbackLoading = ref(false)
/** 当前选中的日志 */
const selectedLog = ref<OperationLog | null>(null)
/** 回滚请求进行中标记 */
const rollbacking = ref(false)

/**
 * 打开回滚对话框（只读角色拦截）并拉取最近操作日志。
 */
function openRollback(): void {
  if (!auth.ensureWritable()) return
  selectedLog.value = null
  rollbackVisible.value = true
  loadRollbackLogs()
}

/**
 * 拉取最近操作日志供选择。
 */
async function loadRollbackLogs(): Promise<void> {
  rollbackLoading.value = true
  try {
    rollbackLogs.value = (await listOperationLogs({ page: 1, size: 20 })).items
  } catch (e) {
    rollbackLogs.value = []
    notifyApiError(e, '操作日志加载失败')
  } finally {
    rollbackLoading.value = false
  }
}

/**
 * 确认按所选日志的变更前快照（before_snapshot）回滚。
 */
async function handleRollback(): Promise<void> {
  if (!selectedLog.value) {
    ElMessage.warning('请先选择一条操作日志')
    return
  }
  if (!await confirmAction('确认按所选日志的变更前快照回滚风控规则？', '回滚确认')) return
  rollbacking.value = true
  try {
    await rollbackRiskRules(selectedLog.value.id)
    ElMessage.success('回滚成功')
    rollbackVisible.value = false
    await load()
  } catch (e) {
    notifyApiError(e, '回滚失败')
  } finally {
    rollbacking.value = false
  }
}

/**
 * 记录日志表格当前选中行。
 * @param row 选中行（可能为 null）
 */
function onLogCurrentChange(row: OperationLog | null): void {
  selectedLog.value = row
}

onMounted(() => {
  load()
})
</script>

<template>
  <div class="page">
    <el-card shadow="never">
      <div class="toolbar">
        <span class="muted">命中规则用于 Agent 输出风控拦截，启停即时生效。</span>
        <div class="grow" />
        <el-button type="warning" @click="openRollback">按操作日志回滚</el-button>
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">新增规则</el-button>
      </div>

      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" class="block">
        <el-button size="small" @click="load">重试</el-button>
      </el-alert>

      <el-table v-loading="loading" :data="items" border stripe>
        <template #empty><el-empty description="暂无风控规则" /></template>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag>{{ RULE_TYPE_LABELS[row.rule_type] ?? row.rule_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="pattern" label="匹配模式" min-width="200" show-overflow-tooltip>
          <template #default="{ row }"><span class="mono">{{ row.pattern }}</span></template>
        </el-table-column>
        <el-table-column label="提示消息 ID" width="140">
          <template #default="{ row }">{{ row.message_id || '-' }}</template>
        </el-table-column>
        <el-table-column label="启用" width="100">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled" :before-change="() => handleToggle(row)" />
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增 / 编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑规则' : '新增规则'" width="520px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="规则类型" prop="rule_type">
          <el-select v-model="form.rule_type" filterable allow-create default-first-option style="width: 100%">
            <el-option v-for="opt in RULE_TYPE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="匹配模式" prop="pattern">
          <el-input v-model="form.pattern" type="textarea" :rows="3" placeholder="关键词或正则表达式" />
        </el-form-item>
        <el-form-item label="提示消息 ID">
          <el-input v-model="form.message_id" placeholder="命中时的提示消息 ID（可选）" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 按操作日志回滚对话框 -->
    <el-dialog v-model="rollbackVisible" title="按操作日志回滚风控规则" width="720px" destroy-on-close>
      <el-alert type="info" title="回滚将应用所选操作日志的变更前快照（before_snapshot），请谨慎选择。" :closable="false" class="block" />
      <el-table
        v-loading="rollbackLoading"
        :data="rollbackLogs"
        border
        size="small"
        max-height="320"
        highlight-current-row
        @current-change="onLogCurrentChange"
      >
        <template #empty><el-empty description="暂无操作日志" /></template>
        <el-table-column prop="id" label="日志 ID" width="90" />
        <el-table-column prop="module" label="模块" width="120" />
        <el-table-column prop="action" label="动作" width="120" />
        <el-table-column prop="operator" label="操作人" width="120" />
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="rollbackVisible = false">取消</el-button>
        <el-button type="danger" :loading="rollbacking" @click="handleRollback">确认回滚</el-button>
      </template>
    </el-dialog>
  </div>
</template>
