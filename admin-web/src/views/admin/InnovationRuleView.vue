<!-- 文件职责：创新规则库。风味搭配规则 CRUD（食材两下拉搜索 + 关系三选 + 权重 + 专家签字标记）。 -->
<script setup lang="ts">
/**
 * 创新规则逻辑：搭配规则列表三态、规则表单（食材下拉 / 关系三选 / 权重 / 专家签字）、删除确认。
 * 所有写操作前置确认，只读角色统一拦截提示。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

import {
  createInnovationRule,
  deleteInnovationRule,
  listIngredients,
  listInnovationRules,
  notifyApiError,
  updateInnovationRule,
} from '@/api/admin'
import type { Ingredient, InnovationRule, PairingRelation } from '@/api/admin'
import { useSimpleList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { confirmAction } from '@/utils/interaction'
import { formatDate } from '@/utils/format'

const auth = useAuthStore()

/** 关系三选配置 */
const RELATION_OPTIONS: { value: PairingRelation; label: string; tag: 'success' | 'danger' | 'warning' }[] = [
  { value: 'pair', label: '协同搭配', tag: 'success' },
  { value: 'conflict', label: '风味冲突', tag: 'danger' },
  { value: 'replace', label: '可替代', tag: 'warning' },
]

/** 关系中文映射 */
const RELATION_LABELS: Record<string, string> = {
  pair: '协同搭配',
  conflict: '风味冲突',
  replace: '可替代',
}

// 列表三态
const { loading, error, items, load } = useSimpleList<InnovationRule>(async () => (await listInnovationRules()).items)

/** 食材下拉选项源数据 */
const ingredientOptions = ref<Ingredient[]>([])
/** 下拉选项（label 为食材名称） */
const ingredientSelectOptions = computed<{ value: string; label: string }[]>(() =>
  ingredientOptions.value.map((it) => ({ value: it.name, label: it.name })),
)

/**
 * 加载食材下拉选项（新增 / 编辑对话框使用）。
 */
async function loadIngredientOptions(): Promise<void> {
  try {
    ingredientOptions.value = (await listIngredients({ size: 500 })).items
  } catch (e) {
    notifyApiError(e, '食材列表加载失败')
  }
}

// ==================== 新增 / 编辑 ====================

const dialogVisible = ref(false)
/** 当前编辑的规则 ID（0 表示新增） */
const editingId = ref(0)
/** 保存请求进行中标记 */
const saving = ref(false)
/** 表单引用（用于触发校验） */
const formRef = ref<FormInstance>()

/** 规则表单 */
const form = reactive<{ ingredient_a: string; ingredient_b: string; relation: PairingRelation; weight: number; signed_by_expert: boolean }>({
  ingredient_a: '',
  ingredient_b: '',
  relation: 'pair',
  weight: 5,
  signed_by_expert: false,
})

/** 表单校验规则 */
const rules: FormRules = {
  ingredient_a: [{ required: true, message: '请选择食材 A', trigger: 'change' }],
  ingredient_b: [{ required: true, message: '请选择食材 B', trigger: 'change' }],
  relation: [{ required: true, message: '请选择搭配关系', trigger: 'change' }],
}

/**
 * 打开新增对话框（只读角色拦截）。
 */
function openCreate(): void {
  if (!auth.ensureWritable()) return
  editingId.value = 0
  form.ingredient_a = ''
  form.ingredient_b = ''
  form.relation = 'pair'
  form.weight = 5
  form.signed_by_expert = false
  dialogVisible.value = true
}

/**
 * 打开编辑对话框并回填。
 * @param row 列表行
 */
function openEdit(row: InnovationRule): void {
  if (!auth.ensureWritable()) return
  editingId.value = row.id
  form.ingredient_a = row.ingredient_a
  form.ingredient_b = row.ingredient_b
  form.relation = row.relation
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
  if (!await confirmAction(editingId.value ? '确认保存规则修改？' : '确认新增搭配规则？', '保存确认')) return
  const payload = {
    ingredient_a: form.ingredient_a.trim(),
    ingredient_b: form.ingredient_b.trim(),
    relation: form.relation,
    weight: form.weight,
    signed_by_expert: form.signed_by_expert,
  }
  saving.value = true
  try {
    if (editingId.value) {
      await updateInnovationRule(editingId.value, payload)
      ElMessage.success('保存成功')
    } else {
      await createInnovationRule(payload)
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
  if (!await confirmAction(`确认删除规则「${row.ingredient_a} × ${row.ingredient_b}」？`, '删除确认')) return
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
        <span class="muted">风味搭配规则（flavor_pairing_rule）用于创新菜生成约束，支持专家签字标记。</span>
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
        <el-table-column prop="ingredient_a" label="食材 A" min-width="120" />
        <el-table-column prop="ingredient_b" label="食材 B" min-width="120" />
        <el-table-column label="关系" width="110">
          <template #default="{ row }">
            <el-tag :type="RELATION_OPTIONS.find((it) => it.value === row.relation)?.tag ?? 'info'">
              {{ RELATION_LABELS[row.relation] ?? row.relation }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="weight" label="权重" width="90" />
        <el-table-column label="专家签字" width="110">
          <template #default="{ row }">
            <el-tag :type="row.signed_by_expert ? 'success' : 'info'" effect="plain">
              {{ row.signed_by_expert ? '已签字' : '未签字' }}
            </el-tag>
          </template>
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
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑搭配规则' : '新增搭配规则'" width="500px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="食材 A" prop="ingredient_a">
          <el-select v-model="form.ingredient_a" filterable placeholder="搜索选择食材" style="width: 100%">
            <el-option v-for="opt in ingredientSelectOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="食材 B" prop="ingredient_b">
          <el-select v-model="form.ingredient_b" filterable placeholder="搜索选择食材" style="width: 100%">
            <el-option v-for="opt in ingredientSelectOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="关系" prop="relation">
          <el-radio-group v-model="form.relation">
            <el-radio v-for="opt in RELATION_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="权重">
          <el-input-number v-model="form.weight" :min="0" :max="10" :step="0.5" controls-position="right" />
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
