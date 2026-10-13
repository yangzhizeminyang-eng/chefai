<!--
  文件级注释：P-07 拍照识别页（pages/recommend/photo）。
  自 web-stage1/src/views/RecognizeView.vue（363 行）迁移（阶段二拆页：本页承担
  「采集 + 上传识别」，识别结果确认与入库移交 P-08 recognize.vue）：
  - 模块开关守卫：switches.vision=false → 全页置灰说明（EmptyState +「改为手选」保底）；
  - 两个入口按钮（拍照 / 相册）：均经 platform/media.chooseAndCompressImage 采集压缩
    （该函数 sourceType 同时声明 camera+album，系统弹出拍照/相册选择面板，
    页面双按钮为等价入口，语义对齐源码 el-upload「拍照 / 从相册选择」单入口）；
  - 采集成功 trackEvent('ingredient_photo_upload') → uploadRecognize 上传识别；
  - 识别成功：结果（含额度）经 storage 交接键 aicook_vision_result_v1 传递，
    页面呈现成功态（额度行 + 识别摘要），点「确认食材」进入 P-08 识别确认页；
  - PERMISSION_DENIED 错误 → PermissionGuide（scope camera）+ fallback 插槽
    「手选食材」按钮（→ RECOMMEND_SELECT，保底不阻断主链路）；
  - 用户取消（MEDIA_CANCEL）静默回空闲态；
  - 额度展示：MEMBER_QUOTA_LABEL + 识别响应 quota 字段（口径与源码一致）；
  - 离线：OfflineBar + 识别需联网提示（OFFLINE_UNCACHED_TEXT）。
  五态：空闲（上传区）/ 识别中（SkeletonPage + 耗时说明）/ 成功（结果摘要）/ 错误 /
  无权限（PermissionGuide）。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide } from '@dcloudio/uni-app'
import { MEMBER_QUOTA_LABEL, OFFLINE_UNCACHED_TEXT } from '@shared/constants'
import type { ApiError, VisionRecognizeResponse } from '@shared/types'
import { useConfigStore } from '@/stores/config'
import { chooseAndCompressImage, uploadRecognize } from '@/platform/media'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide, trackEvent } from '@/utils/track'
import { toastInfo } from '@/utils/toast'
import { set as storageSet, remove as storageRemove } from '@/utils/storage'
import { VISION_RESULT_KEY } from '@/utils/visionTransfer'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import SkeletonPage from '@/components/SkeletonPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import PermissionGuide from '@/components/PermissionGuide.vue'
import OfflineBar from '@/components/OfflineBar.vue'
import BaseButton from '@/components-base/BaseButton.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()
/** 全局网络态（离线提示条显隐 + 需联网提示） */
const network = useAppNetwork()
/** 远程开关 store（vision 开关守卫，源码语义 ①） */
const configStore = useConfigStore()

/** 页面阶段：idle 上传区 / recognizing 识别中 / success 成功 / denied 无权限 */
const stage = ref<'idle' | 'recognizing' | 'success' | 'denied'>('idle')
/** 识别错误（归一化 ApiError；PERMISSION_DENIED 单独转 denied 态） */
const error = ref<ApiError | null>(null)
/** 识别响应（成功态展示数据源：quota + recognized 摘要） */
const result = ref<VisionRecognizeResponse | null>(null)

/** 识别模块是否可用（switches.vision 未返回视为开启） */
const visionEnabled = computed(() => configStore.switches.vision !== false)

/** 识别到的食材名摘要（前 6 个 + 计数） */
const recognizedSummary = computed(() => {
  const names = (result.value?.recognized ?? []).map((r) => r.name)
  if (names.length === 0) return '未识别出食材'
  if (names.length <= 6) return names.join('、')
  return `${names.slice(0, 6).join('、')} 等 ${names.length} 样`
})

/**
 * 「改为手选食材」保底入口：跳食材选择页（主链路兜底，未授权/开关关闭均可达）。
 * @returns 无
 */
function goManual(): void {
  goRoute(ROUTES.RECOMMEND_SELECT)
}

/**
 * 采集并识别主流程：chooseAndCompressImage → uploadRecognize → 结果交接进
 * storage 交接键 → 成功态展示（额度 + 摘要），由用户点击进入识别确认页。
 * 埋点：ingredient_photo_upload（采集成功即落，口径与源码一致）。
 * @returns 无
 */
async function captureAndRecognize(): Promise<void> {
  if (stage.value === 'recognizing') return
  error.value = null
  // 离线提示：识别必须联网（离线时仍允许尝试，失败走错误态）
  if (!network.isConnected) toastInfo(OFFLINE_UNCACHED_TEXT)
  let tempFilePath = ''
  try {
    const chosen = await chooseAndCompressImage()
    tempFilePath = chosen.tempFilePath
  } catch (e) {
    const err = e as ApiError
    if (err?.code === 'MEDIA_CANCEL') return // 用户取消：静默回空闲态
    if (err?.code === 'PERMISSION_DENIED') {
      stage.value = 'denied'
      return
    }
    error.value = err
    stage.value = 'idle'
    return
  }
  // 采集成功即落埋点（口径对齐源码 handleUpload 成功路径）
  trackEvent('ingredient_photo_upload')
  stage.value = 'recognizing'
  try {
    const res = await uploadRecognize(tempFilePath)
    result.value = res
    // 结果交接：写入 storage 交接键（识别确认页读取后清除；食材名非敏感，可临时落盘）
    storageSet(VISION_RESULT_KEY, res)
    stage.value = 'success'
  } catch (e) {
    error.value = e as ApiError
    stage.value = 'idle'
  }
}

/**
 * 进入识别确认页（成功态主操作；交接数据已在 storage）。
 * @returns 无
 */
function goConfirm(): void {
  goRoute(ROUTES.RECOMMEND_RECOGNIZE)
}

/**
 * 重新拍：清空结果与交接数据回空闲态。
 * @returns 无
 */
function resetAll(): void {
  result.value = null
  error.value = null
  stage.value = 'idle'
  storageRemove(VISION_RESULT_KEY)
}

/**
 * 无权限态「去设置」回包：授权开启相机/相册后自动重试识别主流程。
 * @param authSetting 授权结果（PermissionGuide emit result）
 * @returns 无
 */
function onAuthResult(authSetting: Record<string, boolean>): void {
  const granted = Object.values(authSetting).some((v) => v === true)
  if (granted) {
    stage.value = 'idle'
    void captureAndRecognize()
  }
}

// onHide：尽力上报缓冲埋点
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <!-- 离线提示条 -->
    <OfflineBar v-if="!network.isConnected" />

    <view class="photo" :class="{ 'is-disabled-page': !visionEnabled }">
      <!-- ① 开关关闭：整页置灰说明（源码语义 ①，保底不阻断） -->
      <template v-if="!visionEnabled">
        <EmptyState
          icon="📸"
          title="识别功能维护中"
          desc="拍照识别食材功能暂未开放，先用手选的方式选食材吧"
          action-text="改为手选食材"
          @action="goManual"
        />
      </template>

      <template v-else>
        <!-- 无权限态：PermissionGuide + fallback 手选保底 -->
        <template v-if="stage === 'denied'">
          <PermissionGuide scope="camera" @result="onAuthResult">
            <template #fallback>
              <BaseButton block @click="goManual">手选食材</BaseButton>
            </template>
          </PermissionGuide>
        </template>

        <template v-else>
          <!-- 错误态：识别失败 + 重新拍 / 改为手选 -->
          <view v-if="error" class="photo__error">
            <text class="photo__error-text">识别失败：{{ error.message }}</text>
            <view class="photo__error-actions">
              <BaseButton size="sm" @click="resetAll">重新拍</BaseButton>
              <BaseButton size="sm" type="default" @click="goManual">改为手选</BaseButton>
            </view>
          </view>

          <!-- 识别中：骨架 + 真实视觉模型耗时说明（源码文案口径） -->
          <template v-if="stage === 'recognizing'">
            <SkeletonPage type="list" :rows="4" />
            <text class="photo__recognizing-text">正在识别食材…通常 3–8 秒，最长约 20 秒</text>
          </template>

          <!-- 成功态：额度行 + 识别摘要 + 进入确认（额度展示与源码 quota-line 口径一致） -->
          <template v-else-if="stage === 'success' && result">
            <view class="photo__result">
              <view class="photo__quota">
                <text class="photo__quota-text">
                  {{ MEMBER_QUOTA_LABEL }}：{{ result.quota.used }} / {{ result.quota.limit }}
                </text>
              </view>
              <view class="photo__summary">
                <text class="photo__summary-title">识别完成</text>
                <text class="photo__summary-names">{{ recognizedSummary }}</text>
              </view>
              <view class="photo__result-actions">
                <BaseButton block size="lg" @click="goConfirm">确认食材</BaseButton>
                <BaseButton block type="default" @click="resetAll">再拍一张</BaseButton>
              </view>
            </view>
          </template>

          <!-- 空闲态：上传区（双入口按钮 + 提示文案，源码 upload-zone 语义） -->
          <template v-else>
            <view class="photo__upload">
              <text class="photo__upload-icon">📷</text>
              <text class="photo__upload-hint">
                拍一张冰箱内部或食材摆在一起的照片，厨娘帮你认食材
              </text>
              <view class="photo__upload-actions">
                <BaseButton block size="lg" @click="captureAndRecognize">拍照</BaseButton>
                <BaseButton block size="lg" type="default" @click="captureAndRecognize">
                  从相册选择
                </BaseButton>
              </view>
              <text class="photo__upload-tip">
                支持 JPG / PNG，大图会自动压缩后上传
              </text>
              <view class="photo__manual-link" @click="goManual">
                <text class="photo__manual-link-text">拍不清？改为手选食材 →</text>
              </view>
            </view>
          </template>
        </template>
      </template>
    </view>
  </view>
</template>

<style scoped lang="scss">
.photo {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);

  /* 开关关闭置灰（源码 recognize-page--disabled 语义） */
  &.is-disabled-page {
    opacity: 0.75;
  }
}

.photo__error {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-md);
  margin-bottom: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--color-danger-bg);
}

.photo__error-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-danger);
  word-break: break-all;
}

.photo__error-actions {
  display: flex;
  gap: var(--space-sm);
}

.photo__recognizing-text {
  display: block;
  margin-top: var(--space-md);
  text-align: center;
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* ── 成功态 ── */
.photo__result {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.photo__quota {
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
}

.photo__quota-text {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.photo__summary {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.photo__summary-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.photo__summary-names {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-secondary);
  word-break: break-all;
}

.photo__result-actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

/* ── 空闲态上传区（源码 upload-zone 语义） ── */
.photo__upload {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-xl) var(--space-md);
  border: 2rpx dashed var(--border-color);
  border-radius: var(--radius-card);
}

.photo__upload-icon {
  font-size: 88rpx;
  line-height: 1.2;
}

.photo__upload-hint {
  font-size: var(--font-size-base);
  line-height: 1.7;
  color: var(--text-primary);
  text-align: center;
}

.photo__upload-actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  width: 100%;
}

.photo__upload-tip {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.photo__manual-link {
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
}

.photo__manual-link-text {
  font-size: var(--font-size-sm);
  color: var(--color-primary);
}
</style>
