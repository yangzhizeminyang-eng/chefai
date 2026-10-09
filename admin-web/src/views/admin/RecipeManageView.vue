<!-- 文件职责：菜谱管理。筛选 + 分页表格 + 新建/编辑抽屉（食材用量行编辑 + 步骤行编辑）
     + 发布（422 逐条定位）/ 下架 / 批量导入（结果与错误明细）/ 版本回滚。 -->
<script setup lang="ts">
/**
 * 菜谱管理逻辑：列表三态检索、菜谱表单（含行编辑）、发布校验错误弹窗、导入结果展示、回滚对话框。
 * 所有写操作前置确认，只读角色统一拦截提示。
 */
import { onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules, UploadFile, UploadUserFile } from 'element-plus'
import { ElMessage } from 'element-plus'

import {
  createRecipe,
  getRecipe,
  getValidationErrors,
  importRecipes,
  listRecipes,
  notifyApiError,
  publishRecipe,
  rollbackRecipe,
  unpublishRecipe,
  updateRecipe,
} from '@/api/admin'
import type { RecipeListItem, ValidationErrorItem } from '@/api/admin'
import { usePagedList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { confirmAction } from '@/utils/interaction'
import { formatDate } from '@/utils/format'

const auth = useAuthStore()

/** 状态中文映射 */
const STATUS_LABELS: Record<string, string> = { draft: '草稿', published: '已发布' }

/** 筛选条件（关键词 / 状态） */
const filters = reactive({ keyword: '', status: '' })

// 列表分页三态
const { loading, error, items, total, page, size, load, reload, onPageChange, onSizeChange } = usePagedList<RecipeListItem>(
  (p, s) => listRecipes({
    keyword: filters.keyword.trim() || undefined,
    status: filters.status || undefined,
    page: p,
    size: s,
  }),
)

/**
 * 重置筛选条件并刷新列表。
 */
async function resetFilters(): Promise<void> {
  filters.keyword = ''
  filters.status = ''
  await reload()
}

// ==================== 新建 / 编辑抽屉 ====================

const drawerVisible = ref(false)
/** 当前编辑的菜谱 ID（0 表示新建） */
const editingId = ref(0)
/** 保存请求进行中标记 */
const saving = ref(false)
/** 表单引用（用于触发校验） */
const formRef = ref<FormInstance>()

/** 菜谱表单（基本信息 + 食材用量行 + 步骤行） */
const form = reactive({
  name: '',
  description: '',
  ingredients: [] as { name: string; amount: string; unit: string }[],
  steps: [] as { content: string }[],
})

/** 表单校验规则 */
const rules: FormRules = {
  name: [{ required: true, message: '请输入菜谱名称', trigger: 'blur' }],
}

/**
 * 重置表单为新建状态。
 */
function resetForm(): void {
  editingId.value = 0
  form.name = ''
  form.description = ''
  form.ingredients = []
  form.steps = []
  formRef.value?.clearValidate()
}

/**
 * 打开新建抽屉（只读角色拦截）。
 */
function openCreate(): void {
  if (!auth.ensureWritable()) return
  resetForm()
  drawerVisible.value = true
}

/**
 * 打开编辑抽屉：拉取详情回填食材与步骤行。
 * @param row 列表行
 */
async function openEdit(row: RecipeListItem): Promise<void> {
  if (!auth.ensureWritable()) return
  try {
    const detail = await getRecipe(row.id)
    editingId.value = row.id
    form.name = detail.name ?? ''
    form.description = detail.description ?? ''
    form.ingredients = (detail.ingredients ?? []).map((it) => ({
      name: it.name ?? '',
      amount: it.amount ?? '',
      unit: it.unit ?? '',
    }))
    form.steps = (detail.steps ?? []).map((it) => ({ content: it.content ?? '' }))
    drawerVisible.value = true
  } catch (e) {
    notifyApiError(e, '菜谱详情加载失败')
  }
}

/** 添加一行食材 */
function addIngredientRow(): void {
  form.ingredients.push({ name: '', amount: '', unit: '' })
}

/**
 * 删除指定食材行。
 * @param index 行下标
 */
function removeIngredientRow(index: number): void {
  form.ingredients.splice(index, 1)
}

/** 添加一行步骤 */
function addStepRow(): void {
  form.steps.push({ content: '' })
}

/**
 * 删除指定步骤行。
 * @param index 行下标
 */
function removeStepRow(index: number): void {
  form.steps.splice(index, 1)
}

/**
 * 保存菜谱（新建或更新）：空行过滤后提交，步骤按顺序生成 order。
 */
async function handleSave(): Promise<void> {
  const valid = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  if (!await confirmAction(editingId.value ? '确认保存菜谱修改？' : '确认创建菜谱？', '保存确认')) return
  const payload = {
    name: form.name.trim(),
    description: form.description.trim() || undefined,
    ingredients: form.ingredients
      .filter((it) => it.name.trim())
      .map((it) => ({ name: it.name.trim(), amount: it.amount.trim(), unit: it.unit.trim() || undefined })),
    steps: form.steps
      .filter((it) => it.content.trim())
      .map((it, idx) => ({ order: idx + 1, content: it.content.trim() })),
  }
  saving.value = true
  try {
    if (editingId.value) {
      await updateRecipe(editingId.value, payload)
      ElMessage.success('保存成功')
    } else {
      await createRecipe(payload)
      ElMessage.success('创建成功')
    }
    drawerVisible.value = false
    await load()
  } catch (e) {
    notifyApiError(e, '保存失败')
  } finally {
    saving.value = false
  }
}

// ==================== 发布 / 下架 ====================

/** 发布校验错误明细（422 逐条定位弹窗） */
const publishErrors = ref<ValidationErrorItem[]>([])
const publishDialogVisible = ref(false)
/** 正在发布的菜谱 ID（按钮 loading） */
const publishingId = ref(0)

/**
 * 发布菜谱：422 时解析 errors 数组并弹窗逐条展示。
 * @param row 列表行
 */
async function handlePublish(row: RecipeListItem): Promise<void> {
  if (!auth.ensureWritable()) return
  if (!await confirmAction(`确认发布菜谱「${row.name}」？后端将进行用量量化校验。`, '发布确认')) return
  publishingId.value = row.id
  try {
    await publishRecipe(row.id)
    ElMessage.success('发布成功')
    await load()
  } catch (e) {
    const errors = getValidationErrors(e)
    if (errors.length > 0) {
      publishErrors.value = errors
      publishDialogVisible.value = true
    }
    notifyApiError(e, '发布失败，请查看校验明细')
  } finally {
    publishingId.value = 0
  }
}

/**
 * 下架菜谱。
 * @param row 列表行
 */
async function handleUnpublish(row: RecipeListItem): Promise<void> {
  if (!auth.ensureWritable()) return
  if (!await confirmAction(`确认下架菜谱「${row.name}」？`, '下架确认')) return
  try {
    await unpublishRecipe(row.id)
    ElMessage.success('下架成功')
    await load()
  } catch (e) {
    notifyApiError(e, '下架失败')
  }
}

// ==================== 版本回滚 ====================

const rollbackVisible = ref(false)
/** 回滚目标菜谱行 */
const rollbackRow = ref<RecipeListItem | null>(null)
/** 目标版本号 */
const rollbackVersion = ref<number | null>(null)

/**
 * 打开回滚对话框。
 * @param row 列表行
 */
function openRollback(row: RecipeListItem): void {
  if (!auth.ensureWritable()) return
  rollbackRow.value = row
  rollbackVersion.value = null
  rollbackVisible.value = true
}

/**
 * 确认回滚到指定版本。
 */
async function handleRollback(): Promise<void> {
  if (!rollbackRow.value) return
  const version = rollbackVersion.value
  if (!version || version < 1) {
    ElMessage.warning('请输入有效的目标版本号')
    return
  }
  if (!await confirmAction(`确认将「${rollbackRow.value.name}」回滚到版本 ${version}？`, '回滚确认')) return
  try {
    await rollbackRecipe(rollbackRow.value.id, version)
    ElMessage.success('回滚成功')
    rollbackVisible.value = false
    await load()
  } catch (e) {
    notifyApiError(e, '回滚失败')
  }
}

// ==================== 批量导入 ====================

const importVisible = ref(false)
/** 导入文件格式 */
const importFormat = ref<'json' | 'csv' | 'md'>('json')
/** el-upload 文件列表回显 */
const importFileList = ref<UploadUserFile[]>([])
/** 待上传文件（取最新选择） */
const importFile = ref<File | null>(null)
/** 导入请求进行中标记 */
const importing = ref(false)
/** 导入结果（成功 / 失败 / 错误明细） */
const importResult = ref<{ imported: number; failed: number; errors: ValidationErrorItem[] } | null>(null)

/**
 * 打开批量导入对话框（只读角色拦截）。
 */
function openImport(): void {
  if (!auth.ensureWritable()) return
  importFileList.value = []
  importFile.value = null
  importResult.value = null
  importFormat.value = 'json'
  importVisible.value = true
}

/**
 * el-upload 选择文件回调（记录最新选择的文件）。
 * @param file 上传文件对象
 */
function onImportFileChange(file: UploadFile): void {
  importFile.value = (file.raw as File | undefined) ?? null
}

/**
 * el-upload 移除文件回调（清空待上传文件）。
 */
function onImportFileRemove(): void {
  importFile.value = null
}

/**
 * 提交批量导入并展示结果。
 */
async function handleImport(): Promise<void> {
  if (!importFile.value) {
    ElMessage.warning('请先选择要导入的文件')
    return
  }
  if (!await confirmAction(`确认以 ${importFormat.value.toUpperCase()} 格式导入该文件？`, '导入确认')) return
  importing.value = true
  try {
    importResult.value = await importRecipes(importFile.value, importFormat.value)
    ElMessage.success(`导入完成：成功 ${importResult.value.imported} 条，失败 ${importResult.value.failed} 条`)
    await load()
  } catch (e) {
    notifyApiError(e, '导入失败')
  } finally {
    importing.value = false
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
        <el-input
          v-model="filters.keyword"
          placeholder="按名称搜索"
          clearable
          style="width: 220px"
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-select v-model="filters.status" placeholder="状态" clearable style="width: 140px" @change="reload">
          <el-option label="全部" value="" />
          <el-option label="草稿" value="draft" />
          <el-option label="已发布" value="published" />
        </el-select>
        <el-button type="primary" @click="reload">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
        <div class="grow" />
        <el-button type="success" @click="openCreate">新建菜谱</el-button>
        <el-button type="warning" @click="openImport">批量导入</el-button>
      </div>

      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" class="block">
        <el-button size="small" @click="load">重试</el-button>
      </el-alert>

      <el-table v-loading="loading" :data="items" border stripe>
        <template #empty><el-empty description="暂无菜谱数据" /></template>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="菜谱名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'published' ? 'success' : 'info'">{{ STATUS_LABELS[row.status] ?? row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="用量量化" width="100">
          <template #default="{ row }">
            <el-tag :type="row.quantified ? 'success' : 'warning'" effect="plain">{{ row.quantified ? '已量化' : '未量化' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.status !== 'published'" link type="success" :loading="publishingId === row.id" @click="handlePublish(row)">发布</el-button>
            <el-button v-if="row.status === 'published'" link type="warning" @click="handleUnpublish(row)">下架</el-button>
            <el-button link type="danger" @click="openRollback(row)">回滚</el-button>
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

    <!-- 新建 / 编辑抽屉 -->
    <el-drawer v-model="drawerVisible" :title="editingId ? '编辑菜谱' : '新建菜谱'" size="620px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="84px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="菜谱名称" maxlength="50" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="菜谱简介（可选）" />
        </el-form-item>
        <el-form-item label="食材用量">
          <div class="rows-box">
            <el-table :data="form.ingredients" size="small" border>
              <template #empty><span class="muted">暂无食材，请点击下方按钮添加</span></template>
              <el-table-column label="食材名" min-width="130">
                <template #default="{ $index }">
                  <el-input v-model="form.ingredients[$index].name" placeholder="如：番茄" />
                </template>
              </el-table-column>
              <el-table-column label="用量" width="110">
                <template #default="{ $index }">
                  <el-input v-model="form.ingredients[$index].amount" placeholder="如：200" />
                </template>
              </el-table-column>
              <el-table-column label="单位" width="100">
                <template #default="{ $index }">
                  <el-input v-model="form.ingredients[$index].unit" placeholder="如：g" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="70">
                <template #default="{ $index }">
                  <el-button link type="danger" @click="removeIngredientRow($index)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-button size="small" class="rows-add" @click="addIngredientRow">+ 添加食材</el-button>
          </div>
        </el-form-item>
        <el-form-item label="步骤">
          <div class="rows-box">
            <el-table :data="form.steps" size="small" border>
              <template #empty><span class="muted">暂无步骤，请点击下方按钮添加</span></template>
              <el-table-column label="#" width="50">
                <template #default="{ $index }">{{ $index + 1 }}</template>
              </el-table-column>
              <el-table-column label="内容" min-width="260">
                <template #default="{ $index }">
                  <el-input v-model="form.steps[$index].content" type="textarea" :rows="2" placeholder="步骤描述" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="70">
                <template #default="{ $index }">
                  <el-button link type="danger" @click="removeStepRow($index)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-button size="small" class="rows-add" @click="addStepRow">+ 添加步骤</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="drawerVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-drawer>

    <!-- 发布 422 校验明细弹窗 -->
    <el-dialog v-model="publishDialogVisible" title="发布校验未通过（逐条定位）" width="660px">
      <el-alert type="warning" title="以下条目量化校验失败，请修正后重新发布" :closable="false" class="block" />
      <el-table :data="publishErrors" border size="small" max-height="360">
        <el-table-column label="行" width="70">
          <template #default="{ row }">{{ row.row ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="字段" width="130">
          <template #default="{ row }">{{ row.field ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="当前值" min-width="120">
          <template #default="{ row }">{{ row.value === undefined || row.value === null || row.value === '' ? '-' : String(row.value) }}</template>
        </el-table-column>
        <el-table-column label="原因" min-width="180">
          <template #default="{ row }">{{ row.reason ?? row.message ?? '-' }}</template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button type="primary" @click="publishDialogVisible = false">知道了</el-button>
      </template>
    </el-dialog>

    <!-- 版本回滚对话框 -->
    <el-dialog v-model="rollbackVisible" title="菜谱版本回滚" width="420px">
      <p v-if="rollbackRow">目标菜谱：<b>{{ rollbackRow.name }}</b></p>
      <el-input-number v-model="rollbackVersion" :min="1" placeholder="目标版本号" style="width: 200px" />
      <p class="muted">请输入要回滚到的历史版本号（to_version）。</p>
      <template #footer>
        <el-button @click="rollbackVisible = false">取消</el-button>
        <el-button type="danger" @click="handleRollback">确认回滚</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入对话框 -->
    <el-dialog v-model="importVisible" title="菜谱批量导入" width="640px" destroy-on-close>
      <el-form label-width="84px">
        <el-form-item label="文件格式">
          <el-radio-group v-model="importFormat">
            <el-radio-button value="json">JSON</el-radio-button>
            <el-radio-button value="csv">CSV</el-radio-button>
            <el-radio-button value="md">Markdown</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="文件">
          <el-upload
            v-model:file-list="importFileList"
            :auto-upload="false"
            drag
            accept=".json,.csv,.md"
            :on-change="onImportFileChange"
            :on-remove="onImportFileRemove"
          >
            <div style="padding: 12px 0">将文件拖到此处，或<em>点击选择</em></div>
            <template #tip>
              <div class="muted">建议一次上传一个文件，导入时读取最新选择的文件。</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template v-if="importResult">
        <el-descriptions :column="2" border size="small" class="block" title="导入结果">
          <el-descriptions-item label="成功导入">{{ importResult.imported }}</el-descriptions-item>
          <el-descriptions-item label="失败">{{ importResult.failed }}</el-descriptions-item>
        </el-descriptions>
        <el-table v-if="importResult.errors.length" :data="importResult.errors" border size="small" max-height="240">
          <el-table-column label="行" width="70">
            <template #default="{ row }">{{ row.row ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="字段" width="130">
            <template #default="{ row }">{{ row.field ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="原因" min-width="180">
            <template #default="{ row }">{{ row.reason ?? row.message ?? JSON.stringify(row) }}</template>
          </el-table-column>
        </el-table>
      </template>
      <template #footer>
        <el-button @click="importVisible = false">关闭</el-button>
        <el-button type="primary" :loading="importing" @click="handleImport">开始导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.rows-box {
  width: 100%;
}

.rows-add {
  margin-top: 8px;
  width: 100%;
}
</style>
