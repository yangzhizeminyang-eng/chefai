<!-- 文件职责：食材库管理。列表（客户端搜索）+ 新增/编辑（致敏原多选 + verified 开关）+ 别名管理 + 删除。 -->
<script setup lang="ts">
/**
 * 食材库逻辑：列表三态、食材表单（致敏原代码多选可自定义）、别名弹窗增删。
 * 所有写操作前置确认，只读角色统一拦截提示。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

import {
  addAlias,
  createIngredient,
  deleteAlias,
  deleteIngredient,
  getErrorMessage,
  listAliases,
  listAllIngredients,
  notifyApiError,
  updateIngredient,
} from '@/api/admin'
import type { Ingredient, IngredientAlias } from '@/api/admin'
import { useSimpleList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { confirmAction } from '@/utils/interaction'

const auth = useAuthStore()

/** 常见致敏原代码建议项（支持自由输入自定义代码） */
const ALLERGEN_OPTIONS = ['milk', 'egg', 'fish', 'shellfish', 'nut', 'peanut', 'wheat', 'soy', 'sesame']

/** 客户端搜索关键词（按名称 / 分类过滤） */
const keyword = ref('')

// 列表三态
const { loading, error, items, load } = useSimpleList<Ingredient>(async () => (await listAllIngredients()))

/** 按关键词过滤后的食材列表 */
const filteredItems = computed<Ingredient[]>(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return items.value
  return items.value.filter(
    (it) => it.name.toLowerCase().includes(kw) || (it.category ?? '').toLowerCase().includes(kw),
  )
})

// ==================== 新增 / 编辑 ====================

const dialogVisible = ref(false)
/** 当前编辑的食材 ID（0 表示新增） */
const editingId = ref(0)
/** 保存请求进行中标记 */
const saving = ref(false)
/** 表单引用（用于触发校验） */
const formRef = ref<FormInstance>()

/** 食材表单（含致敏原多选与认证开关） */
const form = reactive<{ name: string; category: string; allergen_codes: string[]; verified: boolean }>({
  name: '',
  category: '',
  allergen_codes: [],
  verified: false,
})

/** 表单校验规则 */
const rules: FormRules = {
  name: [{ required: true, message: '请输入食材名称', trigger: 'blur' }],
}

/**
 * 打开新增对话框（只读角色拦截）。
 */
function openCreate(): void {
  if (!auth.ensureWritable()) return
  editingId.value = 0
  form.name = ''
  form.category = ''
  form.allergen_codes = []
  form.verified = false
  dialogVisible.value = true
}

/**
 * 打开编辑对话框并回填。
 * @param row 列表行
 */
function openEdit(row: Ingredient): void {
  if (!auth.ensureWritable()) return
  editingId.value = row.id
  form.name = row.name
  form.category = row.category ?? ''
  form.allergen_codes = [...(row.allergen_codes ?? [])]
  form.verified = Boolean(row.verified)
  dialogVisible.value = true
}

/**
 * 保存食材（新增或更新）。
 */
async function handleSave(): Promise<void> {
  const valid = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  if (!await confirmAction(editingId.value ? '确认保存食材修改？' : '确认新增食材？', '保存确认')) return
  const payload = {
    name: form.name.trim(),
    category: form.category.trim() || undefined,
    allergen_codes: form.allergen_codes,
    verified: form.verified,
  }
  saving.value = true
  try {
    if (editingId.value) {
      await updateIngredient(editingId.value, payload)
      ElMessage.success('保存成功')
    } else {
      await createIngredient(payload)
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
 * 删除食材。
 * @param row 列表行
 */
async function handleDelete(row: Ingredient): Promise<void> {
  if (!auth.ensureWritable()) return
  if (!await confirmAction(`确认删除食材「${row.name}」？删除后不可恢复。`, '删除确认')) return
  try {
    await deleteIngredient(row.id)
    ElMessage.success('删除成功')
    await load()
  } catch (e) {
    notifyApiError(e, '删除失败')
  }
}

// ==================== 别名管理 ====================

const aliasVisible = ref(false)
/** 当前维护别名的食材 */
const aliasIngredient = ref<Ingredient | null>(null)
/** 别名列表 */
const aliasList = ref<IngredientAlias[]>([])
/** 别名加载中标记 */
const aliasLoading = ref(false)
/** 新别名输入 */
const aliasInput = ref('')
/** 别名添加进行中标记 */
const aliasSaving = ref(false)

/**
 * 打开别名管理弹窗并加载别名。
 * @param row 列表行
 */
function openAlias(row: Ingredient): void {
  aliasIngredient.value = row
  aliasInput.value = ''
  aliasVisible.value = true
  loadAlias()
}

/**
 * 加载当前食材的别名列表。
 */
async function loadAlias(): Promise<void> {
  if (!aliasIngredient.value) return
  aliasLoading.value = true
  try {
    aliasList.value = await listAliases(aliasIngredient.value.id)
  } catch (e) {
    aliasList.value = []
    notifyApiError(e, '别名加载失败')
  } finally {
    aliasLoading.value = false
  }
}

/**
 * 添加别名（带确认）。
 */
async function handleAddAlias(): Promise<void> {
  if (!aliasIngredient.value) return
  const alias = aliasInput.value.trim()
  if (!alias) {
    ElMessage.warning('请输入别名')
    return
  }
  if (!auth.ensureWritable()) return
  if (!await confirmAction(`确认为「${aliasIngredient.value.name}」添加别名「${alias}」？`, '添加确认')) return
  aliasSaving.value = true
  try {
    await addAlias(aliasIngredient.value.id, alias)
    aliasInput.value = ''
    await loadAlias()
  } catch (e) {
    notifyApiError(e, '别名添加失败')
  } finally {
    aliasSaving.value = false
  }
}

/**
 * 删除别名（带确认）。
 * @param item 别名项
 */
async function handleDeleteAlias(item: IngredientAlias): Promise<void> {
  if (!aliasIngredient.value) return
  const aliasId = item.id ?? item.alias_id
  if (aliasId === undefined) {
    ElMessage.error('该别名缺少 ID，无法删除')
    return
  }
  if (!auth.ensureWritable()) return
  if (!await confirmAction(`确认删除别名「${item.alias}」？`, '删除确认')) return
  try {
    await deleteAlias(aliasIngredient.value.id, aliasId)
    await loadAlias()
  } catch (e) {
    notifyApiError(e, '别名删除失败')
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
        <el-input v-model="keyword" placeholder="搜索名称 / 分类" clearable style="width: 220px" />
        <el-button @click="load">刷新</el-button>
        <div class="grow" />
        <el-button type="primary" @click="openCreate">新增食材</el-button>
      </div>

      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" class="block">
        <el-button size="small" @click="load">重试</el-button>
      </el-alert>

      <el-table v-loading="loading" :data="filteredItems" border stripe>
        <template #empty><el-empty description="暂无食材数据" /></template>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="食材名称" min-width="140" />
        <el-table-column prop="category" label="分类" width="120">
          <template #default="{ row }">{{ row.category || '-' }}</template>
        </el-table-column>
        <el-table-column label="致敏原" min-width="200">
          <template #default="{ row }">
            <template v-if="row.allergen_codes?.length">
              <el-tag v-for="code in row.allergen_codes" :key="code" size="small" type="warning" class="allergen-tag">{{ code }}</el-tag>
            </template>
            <span v-else class="muted">无</span>
          </template>
        </el-table-column>
        <el-table-column label="认证状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.verified ? 'success' : 'info'" effect="plain">{{ row.verified ? '已认证' : '未认证' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="success" @click="openAlias(row)">别名</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增 / 编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑食材' : '新增食材'" width="480px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="食材名称" prop="name">
          <el-input v-model="form.name" placeholder="食材名称" maxlength="50" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="form.category" placeholder="如：蔬菜 / 肉类（可选）" />
        </el-form-item>
        <el-form-item label="致敏原">
          <el-select
            v-model="form.allergen_codes"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入致敏原代码"
            style="width: 100%"
          >
            <el-option v-for="code in ALLERGEN_OPTIONS" :key="code" :label="code" :value="code" />
          </el-select>
        </el-form-item>
        <el-form-item label="已认证">
          <el-switch v-model="form.verified" active-text="已认证" inactive-text="未认证" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 别名管理弹窗 -->
    <el-dialog v-model="aliasVisible" :title="`别名管理 - ${aliasIngredient?.name ?? ''}`" width="460px" destroy-on-close>
      <div v-loading="aliasLoading">
        <div class="alias-box">
          <template v-if="aliasList.length">
            <el-tag
              v-for="item in aliasList"
              :key="item.id ?? item.alias_id ?? item.alias"
              closable
              class="alias-tag"
              @close="handleDeleteAlias(item)"
            >
              {{ item.alias }}
            </el-tag>
          </template>
          <span v-else class="muted">暂无别名</span>
        </div>
        <div class="alias-add">
          <el-input v-model="aliasInput" placeholder="输入新别名" clearable @keyup.enter="handleAddAlias" />
          <el-button type="primary" :loading="aliasSaving" @click="handleAddAlias">添加</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="aliasVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.allergen-tag {
  margin-right: 6px;
  margin-bottom: 4px;
}

.alias-box {
  min-height: 60px;
  padding: 10px;
  border: 1px dashed var(--el-border-color);
  border-radius: 4px;
  margin-bottom: 12px;
}

.alias-tag {
  margin: 0 8px 8px 0;
}

.alias-add {
  display: flex;
  gap: 8px;
}
</style>
