<!-- 文件职责：营养数据维护。按食材搜索（下拉）→ 加载 per100g 营养字段 → 编辑保存（data_source 必填）。 -->
<script setup lang="ts">
/**
 * 营养数据逻辑：食材下拉选择、营养数据加载（404 视为未录入）、表单校验保存。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

import { getApiStatus, getErrorMessage, getNutrition, listIngredients, notifyApiError, updateNutrition } from '@/api/admin'
import type { Ingredient, NutritionInfo } from '@/api/admin'
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

/** 营养数据表单（per100g + 数据来源） */
const form = reactive<NutritionInfo>({
  kcal: null,
  protein: null,
  fat: null,
  carb: null,
  sodium: null,
  data_source: '',
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
    ingredientOptions.value = (await listIngredients({ size: 500 })).items
  } catch (e) {
    notifyApiError(e, '食材列表加载失败')
  } finally {
    optionsLoading.value = false
  }
}

/**
 * 选中食材后拉取其营养数据；404 视为未录入，表单置空提示录入。
 */
async function handleSelect(): Promise<void> {
  if (!selectedId.value) {
    loaded.value = false
    return
  }
  loading.value = true
  loadError.value = ''
  try {
    const info = await getNutrition(selectedId.value)
    form.kcal = info.kcal ?? null
    form.protein = info.protein ?? null
    form.fat = info.fat ?? null
    form.carb = info.carb ?? null
    form.sodium = info.sodium ?? null
    form.data_source = info.data_source ?? ''
    loaded.value = true
  } catch (e) {
    if (getApiStatus(e) === 404) {
      form.kcal = null
      form.protein = null
      form.fat = null
      form.carb = null
      form.sodium = null
      form.data_source = ''
      loaded.value = true
      ElMessage.info('该食材暂无营养数据，请录入')
    } else {
      loadError.value = getErrorMessage(e, '营养数据加载失败')
      loaded.value = false
      notifyApiError(e, '营养数据加载失败')
    }
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
    await updateNutrition(selectedId.value, { ...form, data_source: form.data_source.trim() })
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
        <el-form-item label="热量 kcal">
          <el-input-number v-model="form.kcal" :min="0" :precision="1" controls-position="right" placeholder="每100g" />
        </el-form-item>
        <el-form-item label="蛋白质 g">
          <el-input-number v-model="form.protein" :min="0" :precision="1" controls-position="right" placeholder="每100g" />
        </el-form-item>
        <el-form-item label="脂肪 g">
          <el-input-number v-model="form.fat" :min="0" :precision="1" controls-position="right" placeholder="每100g" />
        </el-form-item>
        <el-form-item label="碳水 g">
          <el-input-number v-model="form.carb" :min="0" :precision="1" controls-position="right" placeholder="每100g" />
        </el-form-item>
        <el-form-item label="钠 mg">
          <el-input-number v-model="form.sodium" :min="0" :precision="1" controls-position="right" placeholder="每100g" />
        </el-form-item>
        <el-form-item label="数据来源" prop="data_source">
          <el-input v-model="form.data_source" placeholder="必填，如 USDA / 中国食物成分表" style="width: 320px" />
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
