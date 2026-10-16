<!-- 文件职责：风控规则管理。规则表格（编码/类别/阶段/等级/阻断/启停 switch+确认）+ 新增/编辑（trigger_condition JSON 编辑）+ 按操作日志回滚。 -->
<script setup lang="ts">
/**
 * 风控规则逻辑（对齐后端真实契约）：
 * - 列表三态、启停（body {enabled}，确认 + 接口）、规则表单、回滚（选择操作日志）；
 * - 表单字段：rule_code / category(五类枚举) / stage_scope(input/output/both) /
 *   trigger_condition(JSONB：keywords/groups/regex) / response_message_id / block /
 *   risk_level(critical/high/medium) / evidence_ref / version / enabled。
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
import type { OperationLog, RiskCategory, RiskLevel, RiskRule, RiskStage } from '@/api/admin'
import { useSimpleList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { confirmAction } from '@/utils/interaction'
import { formatDate } from '@/utils/format'

const auth = useAuthStore()

/** 类别枚举选项（对齐 risk_rule.category CHECK 五类） */
const CATEGORY_OPTIONS: Array<{ value: RiskCategory; label: string }> = [
  { value: 'food_safety_high_risk', label: '食品安全高风险' },
  { value: 'special_population', label: '特殊人群' },
  { value: 'medical_refusal', label: '医疗拒绝' },
  { value: 'pseudoscience', label: '伪科学' },
  { value: 'output_ban', label: '输出违禁' },
]

/** 类别中文映射 */
const CATEGORY_LABELS: Record<string, string> = Object.fromEntries(
  CATEGORY_OPTIONS.map((o) => [o.value, o.label]),
)

/** 阶段枚举选项 */
const STAGE_OPTIONS: Array<{ value: RiskStage; label: string }> = [
  { value: 'input', label: '输入侧' },
  { value: 'output', label: '输出侧' },
  { value: 'both', label: '双侧' },
]

/** 风险等级选项 */
const LEVEL_OPTIONS: Array<{ value: RiskLevel; label: string }> = [
  { value: 'critical', label: 'critical' },
  { value: 'high', label: 'high' },
  { value: 'medium', label: 'medium' },
]

/** 等级标签颜色 */
const LEVEL_TAG_TYPES: Record<string, string> = { critical: 'danger', high: 'warning', medium: 'info' }

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

/** 规则表单（trigger_condition 以 JSON 文本编辑，提交时 parse） */
const form = reactive<{
  rule_code: string
  category: RiskCategory
  stage_scope: RiskStage
  triggerText: string
  response_message_id: string
  block: boolean
  risk_level: RiskLevel
  evidence_ref: string
  version: string
  enabled: boolean
}>({
  rule_code: '',
  category: 'food_safety_high_risk',
  stage_scope: 'input',
  triggerText: '{\n  "keywords": []\n}',
  response_message_id: '',
  block: true,
  risk_level: 'high',
  evidence_ref: '',
  version: 'v1',
  enabled: true,
})

/** 表单校验规则 */
const rules: FormRules = {
  rule_code: [{ required: true, message: '请输入规则编码（如 FS-901）', trigger: 'blur' }],
  category: [{ required: true, message: '请选择类别', trigger: 'change' }],
  stage_scope: [{ required: true, message: '请选择阶段', trigger: 'change' }],
  risk_level: [{ required: true, message: '请选择风险等级', trigger: 'change' }],
  version: [{ required: true, message: '请输入版本号', trigger: 'blur' }],
}

/**
 * 解析 trigger_condition JSON 文本；非法返回 null 并提示。
 */
function parseTrigger(): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(form.triggerText) as unknown
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      ElMessage.error('触发条件必须是 JSON 对象（如 {"keywords": ["生豆芽"]}）')
      return null
    }
    return parsed as Record<string, unknown>
  } catch {
    ElMessage.error('触发条件 JSON 格式不合法')
    return null
  }
}

/**
 * 打开新增对话框（只读角色拦截）。
 */
function openCreate(): void {
  if (!auth.ensureWritable()) return
  editingId.value = 0
  form.rule_code = ''
  form.category = 'food_safety_high_risk'
  form.stage_scope = 'input'
  form.triggerText = '{\n  "keywords": []\n}'
  form.response_message_id = ''
  form.block = true
  form.risk_level = 'high'
  form.evidence_ref = ''
  form.version = 'v1'
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
  form.rule_code = row.rule_code
  form.category = row.category
  form.stage_scope = row.stage_scope
  form.triggerText = JSON.stringify(row.trigger_condition ?? {}, null, 2)
  form.response_message_id = row.response_message_id ?? ''
  form.block = Boolean(row.block)
  form.risk_level = row.risk_level
  form.evidence_ref = row.evidence_ref ?? ''
  form.version = row.version
  form.enabled = Boolean(row.enabled)
  dialogVisible.value = true
}

/**
 * 保存规则（新增或更新）。编辑时 rule_code/category/stage_scope/version 由后端忽略，
 * 仅 trigger_condition/block/risk_level/response_message_id/evidence_ref/enabled 可变。
 */
async function handleSave(): Promise<void> {
  const valid = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  const trigger = parseTrigger()
  if (trigger === null) return
  if (!await confirmAction(editingId.value ? '确认保存规则修改？' : '确认新增规则？', '保存确认')) return
  saving.value = true
  try {
    if (editingId.value) {
      await updateRiskRule(editingId.value, {
        rule_code: form.rule_code.trim(),
        category: form.category,
        stage_scope: form.stage_scope,
        trigger_condition: trigger,
        response_message_id: form.response_message_id.trim() || undefined,
        block: form.block,
        risk_level: form.risk_level,
        evidence_ref: form.evidence_ref.trim() || undefined,
        version: form.version.trim(),
        enabled: form.enabled,
      })
      ElMessage.success('保存成功')
    } else {
      await createRiskRule({
        rule_code: form.rule_code.trim(),
        category: form.category,
        stage_scope: form.stage_scope,
        trigger_condition: trigger,
        response_message_id: form.response_message_id.trim() || undefined,
        block: form.block,
        risk_level: form.risk_level,
        evidence_ref: form.evidence_ref.trim() || undefined,
        version: form.version.trim(),
        enabled: form.enabled,
      })
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
    await toggleRiskRule(row.id, !row.enabled)
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
        <span class="muted">风控规则在输入/输出双侧拦截，启用后即时热更新生效。</span>
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
        <el-table-column prop="rule_code" label="规则编码" width="130" />
        <el-table-column label="类别" width="140">
          <template #default="{ row }">
            <el-tag>{{ CATEGORY_LABELS[row.category] ?? row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="阶段" width="90">
          <template #default="{ row }">
            {{ STAGE_OPTIONS.find((o) => o.value === row.stage_scope)?.label ?? row.stage_scope }}
          </template>
        </el-table-column>
        <el-table-column label="触发条件" min-width="220" show-overflow-tooltip>
          <template #default="{ row }"><span class="mono">{{ JSON.stringify(row.trigger_condition) }}</span></template>
        </el-table-column>
        <el-table-column label="等级" width="100">
          <template #default="{ row }">
            <el-tag :type="LEVEL_TAG_TYPES[row.risk_level] ?? 'info'">{{ row.risk_level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="阻断" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.block" type="danger">一票否决</el-tag>
            <span v-else class="muted">提示</span>
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="80" />
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled" :before-change="() => handleToggle(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增 / 编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑规则' : '新增规则'" width="600px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="规则编码" prop="rule_code">
          <el-input v-model="form.rule_code" :disabled="!!editingId" placeholder="如 FS-901（创建后不可改）" />
        </el-form-item>
        <el-form-item label="类别" prop="category">
          <el-select v-model="form.category" style="width: 100%">
            <el-option v-for="opt in CATEGORY_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="阶段" prop="stage_scope">
          <el-select v-model="form.stage_scope" style="width: 100%">
            <el-option v-for="opt in STAGE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="触发条件" prop="triggerText">
          <el-input v-model="form.triggerText" type="textarea" :rows="5" placeholder='JSON 对象，如 {"keywords": ["生豆芽"], "groups": [...]}' />
        </el-form-item>
        <el-form-item label="风险等级" prop="risk_level">
          <el-select v-model="form.risk_level" style="width: 100%">
            <el-option v-for="opt in LEVEL_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="一票否决">
          <el-switch v-model="form.block" active-text="命中即阻断" inactive-text="仅提示" />
        </el-form-item>
        <el-form-item label="话术模板 ID">
          <el-input v-model="form.response_message_id" placeholder="命中时的话术模板 ID（可选）" />
        </el-form-item>
        <el-form-item label="证据引用">
          <el-input v-model="form.evidence_ref" placeholder="依据来源（可选，如 GB 2761）" />
        </el-form-item>
        <el-form-item label="版本" prop="version">
          <el-input v-model="form.version" :disabled="!!editingId" placeholder="如 v1（创建后不可改）" style="width: 160px" />
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
