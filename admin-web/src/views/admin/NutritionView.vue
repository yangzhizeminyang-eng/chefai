<!-- 文件职责：营养数据维护。按食材搜索（下拉）→ 加载嵌套结构 nutrition 字段 → 编辑保存（data_source 必填）。 -->
<script setup lang="ts">
/**
 * 营养数据逻辑：食材下拉选择、营养数据加载（nutrition=null 视为未录入）、表单校验保存。
 * 后端契约：GET/PUT /admin/v1/nutrition/{id}，字段 kcal_100g/protein_g/fat_g/carbs_g/sodium_mg
 * + data_source（必填）+ source_license。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

import { getNutrition, getErrorMessage, listAllIngredients, notifyApiError, updateNutrition } from '@/api/admin'
import type { Ingredient, NutritionPayload } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'
import { confirmAction } from '@/utils/interaction'

const auth = useAuthStore()

/** 食材下拉选项源数据 */
const ingredientOptions = ref<Ingredient[]>([])
/** 选项加载中标记 */
const optionsLoading = ref(false)
/** 选中的食材 ID */
const selectedId = ref<number | null>(null)

/** 营养数据加载中标记 */
const loading = ref(false)
/** 是否已加载到营养数据（控制表单显隐） */
const loaded = ref(false)
/** 加载错误文案 */
const loadError = ref('')
/** 保存请求进行中标记 */
const saving = ref(false)
/** 表单引用（用于触发校验） */
const formRef = ref<FormInstance>()

/** 营养数据表单（per100g + 数据来源，字段名对齐后端 ingredient_nutrition 列） */
const form = reactive<NutritionPayload>({
  kcal_100g: null,
  protein_g: null,
  fat_g: null,
  carbs_g: null,
  sodium_mg: null,
  data_source: '',
  source_license: 'admin_manual',
})

/** 表单校验规则（data_source 必填） */
const rules: FormRules = {
  data_source: [{ required: true, message: '数据来源必填（如 USDA / 中国食物成分表）', trigger: 'blur' }],
}

/** 下拉选项（label 为食材名称） */
const options = computed<{ value: number; label: string }[]>(() =>
  ingredientOptions.value.map((it) => ({ value: it.id, label: it.name })),
)

/** 当前选中食材名称（保存确认文案用） */
const selectedName = computed<string>(() => ingredientOptions.value.find((it) => it.id === selectedId.value)?.name ?? '')

/**
 * 加载食材下拉选项。
 */
async function loadOptions(): Promise<void> {
  optionsLoading.value = true
  try {
    ingredientOptions.value = await listAllIngredients()
  } catch (e) {
    notifyApiError(e, '食材列表加载失败')
  } finally {
    optionsLoading.value = false
  }
}

/**
 * 选中食材后拉取其营养数据（嵌套 {ingredient_id, nutrition}）；
 * nutrition=null 视为未录入，表单置空提示录入。
 */
async function handleSelect(): Promise<void> {
  if (!selectedId.value) {
    loaded.value = false
    return
  }
  loading.value = true
  loadError.value = ''
  try {
    const res = await getNutrition(selectedId.value)
    const n = res.nutrition
    form.kcal_100g = n?.kcal_100g ?? null
    form.protein_g = n?.protein_g ?? null
    form.fat_g = n?.fat_g ?? null
    form.carbs_g = n?.carbs_g ?? null
    form.sodium_mg = n?.sodium_mg ?? null
    form.data_source = n?.data_source ?? ''
    form.source_license = n?.source_license || 'admin_manual'
    loaded.value = true
    if (!n) ElMessage.info('该食材暂无营养数据，请录入')
  } catch (e) {
    loadError.value = getErrorMessage(e, '营养数据加载失败')
    loaded.value = false
    notifyApiError(e, '营养数据加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 重试加载当前食材的营养数据。
 */
function retryLoad(): void {
  handleSelect()
}

/**
 * 保存营养数据（data_source 校验通过 + 确认后提交）。
 */
async function handleSave(): Promise<void> {
  if (!selectedId.value) return
  const valid = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  if (!await confirmAction(`确认保存「${selectedName.value}」的营养数据？`, '保存确认')) return
  saving.value = true
  try {
    await updateNutrition(selectedId.value, {
      kcal_100g: form.kcal_100g,
      protein_g: form.protein_g,
      fat_g: form.fat_g,
      carbs_g: form.carbs_g,
      sodium_mg: form.sodium_mg,
      data_source: form.data_source.trim(),
      source_license: form.source_license.trim() || 'admin_manual',
    })
    ElMessage.success('保存成功')
  } catch (e) {
    notifyApiError(e, '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadOptions()
})
</script>

<template>
  <div class="page">
    <el-card shadow="never">
      <div class="toolbar">
        <el-select
          v-model="selectedId"
          filterable
          :loading="optionsLoading"
          placeholder="搜索并选择食材"
          style="width: 280px"
          @change="handleSelect"
        >
          <el-option v-for="opt in options" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
        <span v-if="selectedName" class="muted">当前食材：{{ selectedName }}</span>
      </div>

      <el-alert v-if="loadError" type="error" :title="loadError" show-icon :closable="false" class="block">
        <el-button size="small" @click="retryLoad">重试</el-button>
      </el-alert>

      <div v-if="!selectedId" class="empty-wrap">
        <el-empty description="请先选择食材" />
      </div>
      <div v-else-if="loading" v-loading="loading" class="empty-wrap loading-wrap" />

      <el-form v-else-if="loaded" ref="formRef" :model="form" :rules="rules" label-width="110px" class="nutrition-form">
        <el-form-item label="热量 kcal/100g">
          <el-input-number v-model="form.kcal_100g" :min="0" :precision="1" controls-position="right" placeholder="每100g" />
        </el-form-item>
        <el-form-item label="蛋白质 g">
          <el-input-number v-model="form.protein_g" :min="0" :precision="1" controls-position="right" placeholder="每100g" />
        </el-form-item>
        <el-form-item label="脂肪 g">
          <el-input-number v-model="form.fat_g" :min="0" :precision="1" controls-position="right" placeholder="每100g" />
        </el-form-item>
        <el-form-item label="碳水 g">
          <el-input-number v-model="form.carbs_g" :min="0" :precision="1" controls-position="right" placeholder="每100g" />
        </el-form-item>
        <el-form-item label="钠 mg">
          <el-input-number v-model="form.sodium_mg" :min="0" :precision="1" controls-position="right" placeholder="每100g" />
        </el-form-item>
        <el-form-item label="数据来源" prop="data_source">
          <el-input v-model="form.data_source" placeholder="必填，如 USDA / 中国食物成分表" style="width: 320px" />
        </el-form-item>
        <el-form-item label="来源许可">
          <el-input v-model="form.source_license" placeholder="缺省 admin_manual" style="width: 320px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" :disabled="auth.isReadonly" @click="handleSave">保存</el-button>
          <span class="muted tip">{{ auth.isReadonly ? '只读角色无法保存' : '' }}</span>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.empty-wrap {
  padding: 24px 0;
}

.loading-wrap {
  min-height: 200px;
}

.nutrition-form {
  max-width: 520px;
  padding-top: 8px;
}

.tip {
  margin-left: 12px;
}
</style>
