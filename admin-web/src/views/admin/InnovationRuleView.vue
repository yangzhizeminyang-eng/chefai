<!-- 文件职责：创新规则库。风味搭配规则 CRUD（食材 ID 下拉搜索 + 关系 recommend/conflict/taboo + rationale 必填 + 技法建议 + 权重 + 专家签字标记）。 -->
<script setup lang="ts">
/**
 * 创新规则逻辑（对齐后端真实契约 flavor_pairing_rule）：
 * - 列表三态、规则表单（食材按 ID 提交 / 关系三枚举 / rationale 必填 / 技法建议 / 权重 0~9.99 / 专家签字）、删除确认；
 * - 编辑时食材对与关系不可改（后端 PairingRuleUpdate 不含这三项），仅改技法/依据/权重/签字。
 * 所有写操作前置确认，只读角色统一拦截提示。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

import {
  createInnovationRule,
  deleteInnovationRule,
  listAllIngredients,
  listInnovationRules,
  notifyApiError,
  updateInnovationRule,
} from '@/api/admin'
import type { Ingredient, InnovationRule, PairingRelation } from '@/api/admin'
import { useSimpleList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { confirmAction } from '@/utils/interaction'

const auth = useAuthStore()

/** 关系三选配置（对齐 flavor_pairing_rule.relation CHECK） */
const RELATION_OPTIONS: { value: PairingRelation; label: string; tag: 'success' | 'danger' | 'warning' }[] = [
  { value: 'recommend', label: '推荐搭配', tag: 'success' },
  { value: 'conflict', label: '风味冲突', tag: 'danger' },
  { value: 'taboo', label: '忌配', tag: 'warning' },
]

/** 关系中文映射 */
const RELATION_LABELS: Record<string, string> = {
  recommend: '推荐搭配',
  conflict: '风味冲突',
  taboo: '忌配',
}

// 列表三态
const { loading, error, items, load } = useSimpleList<InnovationRule>(async () => (await listInnovationRules()).items)

/** 食材下拉选项源数据 */
const ingredientOptions = ref<Ingredient[]>([])
/** 食材 ID → 名称映射（列表展示） */
const ingredientNameById = computed<Map<number, string>>(() =>
  new Map(ingredientOptions.value.map((it) => [it.id, it.name])),
)
/** 下拉选项（value 为食材 ID，label 为名称） */
const ingredientSelectOptions = computed<{ value: number; label: string }[]>(() =>
  ingredientOptions.value.map((it) => ({ value: it.id, label: it.name })),
)

/**
 * 加载食材下拉选项（新增 / 编辑对话框与列表名称映射共用）。
 */
async function loadIngredientOptions(): Promise<void> {
  try {
    ingredientOptions.value = await listAllIngredients()
  } catch (e) {
    notifyApiError(e, '食材列表加载失败')
  }
}

/** 按 ID 取食材名（未知 ID 兜底显示 #id） */
function ingName(id: number): string {
  return ingredientNameById.value.get(id) ?? `#${id}`
}

// ==================== 新增 / 编辑 ====================

const dialogVisible = ref(false)
/** 当前编辑的规则 ID（0 表示新增） */
const editingId = ref(0)
/** 保存请求进行中标记 */
const saving = ref(false)
/** 表单引用（用于触发校验） */
const formRef = ref<FormInstance>()

/** 规则表单（编辑时食材对与关系禁用） */
const form = reactive<{
  ingredient_a_id: number | null
  ingredient_b_id: number | null
  relation: PairingRelation
  technique_suggestion: string
  rationale: string
  weight: number
  signed_by_expert: boolean
}>({
  ingredient_a_id: null,
  ingredient_b_id: null,
  relation: 'recommend',
  technique_suggestion: '',
  rationale: '',
  weight: 1,
  signed_by_expert: false,
})

/** 表单校验规则（rationale 必填：烹饪学依据） */
const rules: FormRules = {
  ingredient_a_id: [{ required: true, message: '请选择食材 A', trigger: 'change' }],
  ingredient_b_id: [{ required: true, message: '请选择食材 B', trigger: 'change' }],
  relation: [{ required: true, message: '请选择搭配关系', trigger: 'change' }],
  rationale: [
    { required: true, message: '请输入搭配依据（烹饪学表述）', trigger: 'blur' },
    { max: 255, message: '搭配依据不超过 255 字', trigger: 'blur' },
  ],
  weight: [{ required: true, message: '请填写权重（0~9.99）', trigger: 'blur' }],
}

/**
 * 打开新增对话框（只读角色拦截）。
 */
function openCreate(): void {
  if (!auth.ensureWritable()) return
  editingId.value = 0
  form.ingredient_a_id = null
  form.ingredient_b_id = null
  form.relation = 'recommend'
  form.technique_suggestion = ''
  form.rationale = ''
  form.weight = 1
  form.signed_by_expert = false
  dialogVisible.value = true
}

/**
 * 打开编辑对话框并回填（食材对与关系锁定）。
 * @param row 列表行
 */
function openEdit(row: InnovationRule): void {
  if (!auth.ensureWritable()) return
  editingId.value = row.id
  form.ingredient_a_id = row.ingredient_a_id
  form.ingredient_b_id = row.ingredient_b_id
  form.relation = row.relation
  form.technique_suggestion = row.technique_suggestion ?? ''
  form.rationale = row.rationale
  form.weight = row.weight
  form.signed_by_expert = Boolean(row.signed_by_expert)
  dialogVisible.value = true
}

/**
 * 保存规则（新增或更新）。
 */
async function handleSave(): Promise<void> {
  const valid = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  if (form.ingredient_a_id === form.ingredient_b_id) {
    ElMessage.warning('食材 A 与食材 B 不能相同')
    return
  }
  if (form.weight < 0 || form.weight > 9.99) {
    ElMessage.warning('权重取值 0 ~ 9.99')
    return
  }
  const relationLabel = RELATION_LABELS[form.relation]
  if (!await confirmAction(
    editingId.value
      ? '确认保存规则修改？'
      : `确认新增搭配规则「${ingName(form.ingredient_a_id!)} × ${ingName(form.ingredient_b_id!)}（${relationLabel}）」？`,
    '保存确认',
  )) return
  saving.value = true
  try {
    if (editingId.value) {
      await updateInnovationRule(editingId.value, {
        ingredient_a_id: form.ingredient_a_id!,
        ingredient_b_id: form.ingredient_b_id!,
        relation: form.relation,
        technique_suggestion: form.technique_suggestion.trim() || undefined,
        rationale: form.rationale.trim(),
        weight: form.weight,
        signed_by_expert: form.signed_by_expert,
      })
      ElMessage.success('保存成功')
    } else {
      await createInnovationRule({
        ingredient_a_id: form.ingredient_a_id!,
        ingredient_b_id: form.ingredient_b_id!,
        relation: form.relation,
        technique_suggestion: form.technique_suggestion.trim() || undefined,
        rationale: form.rationale.trim(),
        weight: form.weight,
        signed_by_expert: form.signed_by_expert,
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
 * 删除规则。
 * @param row 列表行
 */
async function handleDelete(row: InnovationRule): Promise<void> {
  if (!auth.ensureWritable()) return
  if (!await confirmAction(`确认删除规则「${ingName(row.ingredient_a_id)} × ${ingName(row.ingredient_b_id)}」？`, '删除确认')) return
  try {
    await deleteInnovationRule(row.id)
    ElMessage.success('删除成功')
    await load()
  } catch (e) {
    notifyApiError(e, '删除失败')
  }
}

onMounted(() => {
  load()
  loadIngredientOptions()
})
</script>

<template>
  <div class="page">
    <el-card shadow="never">
      <div class="toolbar">
        <span class="muted">风味搭配规则（flavor_pairing_rule）用于创新菜生成约束；搭配依据（rationale）必填。</span>
        <div class="grow" />
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">新增规则</el-button>
      </div>

      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" class="block">
        <el-button size="small" @click="load">重试</el-button>
      </el-alert>

      <el-table v-loading="loading" :data="items" border stripe>
        <template #empty><el-empty description="暂无搭配规则" /></template>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="食材 A" min-width="120">
          <template #default="{ row }">{{ ingName(row.ingredient_a_id) }}</template>
        </el-table-column>
        <el-table-column label="食材 B" min-width="120">
          <template #default="{ row }">{{ ingName(row.ingredient_b_id) }}</template>
        </el-table-column>
        <el-table-column label="关系" width="110">
          <template #default="{ row }">
            <el-tag :type="RELATION_OPTIONS.find((it) => it.value === row.relation)?.tag ?? 'info'">
              {{ RELATION_LABELS[row.relation] ?? row.relation }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="technique_suggestion" label="技法建议" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.technique_suggestion || '-' }}</template>
        </el-table-column>
        <el-table-column prop="rationale" label="搭配依据" min-width="200" show-overflow-tooltip />
        <el-table-column prop="weight" label="权重" width="80" />
        <el-table-column label="专家签字" width="100">
          <template #default="{ row }">
            <el-tag :type="row.signed_by_expert ? 'success' : 'info'" effect="plain">
              {{ row.signed_by_expert ? '已签字' : '未签字' }}
            </el-tag>
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

    <!-- 新增 / 编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑搭配规则' : '新增搭配规则'" width="560px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="食材 A" prop="ingredient_a_id">
          <el-select
            v-model="form.ingredient_a_id"
            filterable
            :disabled="!!editingId"
            placeholder="搜索选择食材"
            style="width: 100%"
          >
            <el-option v-for="opt in ingredientSelectOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="食材 B" prop="ingredient_b_id">
          <el-select
            v-model="form.ingredient_b_id"
            filterable
            :disabled="!!editingId"
            placeholder="搜索选择食材"
            style="width: 100%"
          >
            <el-option v-for="opt in ingredientSelectOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="关系" prop="relation">
          <el-radio-group v-model="form.relation" :disabled="!!editingId">
            <el-radio v-for="opt in RELATION_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="搭配依据" prop="rationale">
          <el-input v-model="form.rationale" type="textarea" :rows="2" placeholder="烹饪学表述，如「姜辣素与鱼肉蛋白同烹去腥提鲜」" maxlength="255" show-word-limit />
        </el-form-item>
        <el-form-item label="技法建议">
          <el-input v-model="form.technique_suggestion" placeholder="如「先煎后炖」（可选）" maxlength="128" />
        </el-form-item>
        <el-form-item label="权重">
          <el-input-number v-model="form.weight" :min="0" :max="9.99" :step="0.5" :precision="2" controls-position="right" />
        </el-form-item>
        <el-form-item label="专家签字">
          <el-switch v-model="form.signed_by_expert" active-text="已签字" inactive-text="未签字" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
