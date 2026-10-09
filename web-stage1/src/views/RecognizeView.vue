<script setup lang="ts">
/**
 * 视图职责：拍一下冰箱（图像识别，Task 9 / 路由 /recognize）。
 * 区块：① 模块开关守卫：switch.vision=false → 全页置灰说明（el-empty + 说明卡）；
 *       ② 上传区：el-upload（accept image/*，capture 兼容拍照/相册）→
 *          compressImage 前端压缩至 ≤1MB → POST /v1/vision/recognize（multipart）；
 *       ③ 识别结果：高置信默认勾选（绿色区）/ 低置信黄色区需人工勾选确认；
 *       ④ 额度显示（quota.used/limit）+ 降级提示条（degraded → 信息条）；
 *       ⑤ 确认入库：POST /v1/vision/confirm → 勾选食材加入已选（ingredients store）→ 跳 /select；
 *       ⑥ 失败/降级：错误 alert +「改为手选」按钮（跳 /select）。
 * 三态：上传前 / 识别中（动画）/ 结果与异常；深色模式全变量适配。
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Camera, Picture } from '@element-plus/icons-vue'
import type { UploadFile, UploadRawFile } from 'element-plus'
import { postVisionConfirm, postVisionRecognize } from '@/api/endpoints'
import type { ApiError, VisionRecognizeResponse } from '@/api/types'
import { useConfigStore } from '@/stores/config'
import { useIngredientsStore } from '@/stores/ingredients'
import { compressImage } from '@/utils/image'
import { MEMBER_QUOTA_LABEL } from '@/constants/copy'

/** 路由（确认入库后跳 /select、「改为手选」） */
const router = useRouter()
/** 远程开关 store（vision 开关守卫） */
const configStore = useConfigStore()
/** 食材 store（确认入库后写入已选） */
const ingredientsStore = useIngredientsStore()

/** 压缩目标：1MB */
const MAX_UPLOAD_BYTES = 1024 * 1024

/** 识别模块是否可用（开关关闭 → 全页置灰说明） */
const visionEnabled = computed(() => configStore.switches.vision !== false)

/** 识别请求进行中 */
const recognizing = ref(false)
/** 确认入库进行中 */
const confirming = ref(false)
/** 压缩中提示 */
const compressing = ref(false)
/** 识别错误（归一化 ApiError） */
const error = ref<ApiError | null>(null)
/** 识别响应（结果 + 额度 + 降级标记） */
const result = ref<VisionRecognizeResponse | null>(null)
/** 用户勾选确认的食材名（高置信默认勾选） */
const checkedNames = ref<Record<string, boolean>>({})

/** 高置信结果（默认全选） */
const highConfidence = computed(() =>
  (result.value?.recognized ?? []).filter((r) => r.confidence === 'high'),
)
/** 低置信结果（黄色区人工确认） */
const lowConfidence = computed(() =>
  (result.value?.recognized ?? []).filter((r) => r.confidence === 'low'),
)
/** 已勾选数量 */
const checkedCount = computed(
  () => Object.values(checkedNames.value).filter(Boolean).length,
)

/**
 * el-upload 自定义上传：压缩 → 识别（不走 action 真实上传）。
 * @param options element-plus 上传选项（含 file 原始对象）
 * @returns 无
 */
async function handleUpload(options: { file: UploadRawFile }): Promise<void> {
  error.value = null
  result.value = null
  checkedNames.value = {}
  compressing.value = true
  recognizing.value = true
  try {
    const compressed = await compressImage(options.file as unknown as File, MAX_UPLOAD_BYTES)
    const res = await postVisionRecognize(compressed)
    result.value = res
    // 高置信默认勾选；低置信默认不勾
    const next: Record<string, boolean> = {}
    for (const item of res.recognized ?? []) {
      next[item.name] = item.confidence === 'high'
    }
    checkedNames.value = next
    if ((res.recognized ?? []).length === 0) {
      ElMessage.info('没认出食材，换个角度再拍一张试试')
    }
  } catch (e) {
    error.value = e as ApiError
  } finally {
    compressing.value = false
    recognizing.value = false
  }
}

/**
 * el-upload 变更钩子：截获文件后走自定义上传（阻止默认行为已由 http-request 覆盖）。
 * @param file 变更文件
 * @returns 无
 */
function onFileChange(file: UploadFile): void {
  if (file.raw) void handleUpload({ file: file.raw as UploadRawFile })
}

/**
 * 确认入库：POST /v1/vision/confirm → 勾选食材加入已选 → 跳 /select。
 * @returns 无
 */
async function onConfirm(): Promise<void> {
  const names = Object.entries(checkedNames.value)
    .filter(([, checked]) => checked)
    .map(([name]) => name)
  if (names.length === 0) {
    ElMessage.warning('请至少勾选一样食材')
    return
  }
  confirming.value = true
  try {
    const res = await postVisionConfirm(names)
    // 同步写入已选（跳 /select 后可直接去推荐）
    for (const name of names) {
      const matched = ingredientsStore.list.find(
        (ing) => ing.name === name || (ing.aliases ?? []).includes(name),
      )
      if (matched && !ingredientsStore.selected[matched.id]) {
        ingredientsStore.toggle(matched)
      }
    }
    ElMessage.success(`已把 ${res.added ?? names.length} 样食材加入已选`)
    void router.push('/select')
  } catch (e) {
    ElMessage.error((e as ApiError).message || '入库失败，请重试')
  } finally {
    confirming.value = false
  }
}

/**
 * 改为手选：跳食材选择页。
 * @returns 无
 */
function goManual(): void {
  void router.push('/select')
}

/**
 * 重新拍：清空结果回到上传态。
 * @returns 无
 */
function resetAll(): void {
  result.value = null
  error.value = null
  checkedNames.value = {}
}
</script>

<template>
  <section class="page-card recognize-page" :class="{ 'recognize-page--disabled': !visionEnabled }">
    <h1 class="page-title">拍一下冰箱</h1>

    <!-- ① 开关关闭：整页置灰说明 -->
    <template v-if="!visionEnabled">
      <el-empty description="识别功能维护中" :image-size="90">
        <template #description>
          <p class="disabled-text">拍照识别食材功能暂未开放，先用手选的方式选食材吧</p>
        </template>
        <el-button type="primary" @click="goManual">改为手选食材</el-button>
      </el-empty>
    </template>

    <template v-else>
      <!-- 降级提示条 -->
      <el-alert
        v-if="result?.degraded"
        class="rec-alert"
        type="warning"
        title="识别服务繁忙，本次结果可能不够准确，建议核对后再确认入库"
        :closable="false"
        show-icon
      />

      <!-- 失败提示条 + 改为手选 -->
      <el-alert
        v-if="error"
        class="rec-alert"
        type="error"
        :title="`识别失败：${error.message}`"
        :closable="false"
        show-icon
      >
        <el-button size="small" type="primary" plain @click="goManual">改为手选</el-button>
        <el-button size="small" plain @click="resetAll">重新拍</el-button>
      </el-alert>

      <!-- ② 上传区（识别前展示） -->
      <div v-if="!result && !recognizing" class="upload-zone">
        <el-icon :size="44" class="upload-icon"><Camera /></el-icon>
        <p class="upload-hint">拍一张冰箱内部或食材摆在一起的照片，厨娘帮你认食材</p>
        <el-upload
          drag
          accept="image/*"
          :auto-upload="false"
          :show-file-list="false"
          :on-change="onFileChange"
        >
          <el-button type="primary" size="large" :icon="Picture">拍照 / 从相册选择</el-button>
          <template #tip>
            <p class="upload-tip">支持 JPG / PNG，大图会自动压缩后上传（≤1MB）</p>
          </template>
        </el-upload>
        <el-button link type="primary" class="manual-link" @click="goManual">
          拍不清？改为手选食材 →
        </el-button>
      </div>

      <!-- 识别中动画 -->
      <div v-else-if="recognizing" class="recognizing">
        <el-skeleton :rows="3" animated class="recognizing-skeleton" />
        <p class="recognizing-text">
          {{ compressing ? '正在压缩图片…' : '正在识别食材…' }}
        </p>
      </div>

      <!-- ③④ 结果区 -->
      <template v-else-if="result">
        <!-- 额度 -->
        <div class="quota-line">
          <span class="quota-text">{{ MEMBER_QUOTA_LABEL }}：{{ result.quota.used }} / {{ result.quota.limit }}</span>
          <el-button size="small" link type="primary" @click="resetAll">再拍一张</el-button>
        </div>

        <!-- 高置信（默认勾选） -->
        <div v-if="highConfidence.length > 0" class="conf-section">
          <p class="conf-label">识别到这些食材（已为你勾选）：</p>
          <div class="conf-chips">
            <el-checkbox
              v-for="item in highConfidence"
              :key="item.name"
              v-model="checkedNames[item.name]"
              class="conf-chip"
              border
            >
              {{ item.name }}
            </el-checkbox>
          </div>
        </div>

        <!-- 低置信（黄色区人工确认） -->
        <div v-if="lowConfidence.length > 0" class="conf-section conf-section--low">
          <p class="conf-label conf-label--low">这些不太确定，请你确认：</p>
          <div class="conf-chips">
            <el-checkbox
              v-for="item in lowConfidence"
              :key="item.name"
              v-model="checkedNames[item.name]"
              class="conf-chip conf-chip--low"
              border
            >
              {{ item.name }}
            </el-checkbox>
          </div>
        </div>

        <!-- 空结果 -->
        <el-empty
          v-if="(result.recognized ?? []).length === 0"
          description="没认出食材，换个角度再试一次"
          :image-size="80"
        />

        <!-- ⑤ 确认入库 -->
        <div class="confirm-bar">
          <el-button
            type="primary"
            size="large"
            :disabled="checkedCount === 0"
            :loading="confirming"
            @click="onConfirm"
          >
            确认入库（已选 {{ checkedCount }} 样）
          </el-button>
          <el-button size="large" @click="goManual">改为手选</el-button>
        </div>
      </template>
    </template>
  </section>
</template>

<style scoped>
.recognize-page--disabled {
  opacity: 0.75;
}

.disabled-text {
  margin: 8px 0 0;
  font-size: var(--font-sm);
  color: var(--color-info);
}

.rec-alert {
  margin-bottom: 14px;
}

/* ── 上传区 ── */
.upload-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 28px 16px;
  border: 1px dashed var(--color-info-border);
  border-radius: 12px;
}

.upload-icon {
  color: var(--el-color-primary);
}

.upload-hint {
  margin: 0;
  font-size: var(--font-md);
  color: var(--text-main);
  text-align: center;
}

.upload-tip {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--color-info);
}

.manual-link {
  margin-top: 4px;
}

/* ── 识别中 ── */
.recognizing {
  padding: 24px 0;
  text-align: center;
}

.recognizing-skeleton {
  max-width: 480px;
  margin: 0 auto 14px;
}

.recognizing-text {
  margin: 0;
  font-size: var(--font-md);
  color: var(--color-info);
}

/* ── 结果 ── */
.quota-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.quota-text {
  font-size: var(--font-sm);
  color: var(--color-info);
}

.conf-section {
  margin-bottom: 14px;
}

.conf-section--low {
  padding: 12px 14px;
  border: 1px solid var(--color-warning-border);
  border-radius: 10px;
  background: var(--color-warning-bg);
}

.conf-label {
  margin: 0 0 10px;
  font-size: var(--font-md);
  color: var(--text-main);
}

.conf-label--low {
  color: var(--color-warning);
  font-weight: 600;
}

.conf-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.conf-chip--low {
  --el-checkbox-checked-bg-color: var(--color-warning-bg);
}

.confirm-bar {
  display: flex;
  gap: 12px;
  margin-top: 18px;
}
</style>
