<!--
  文件级注释：P-34 意见反馈页（pages/member 分包）。
  - 表单语义自 web-stage1 FeedbackFab 反馈弹窗迁移：类型单选（bug 问题反馈 /
    suggestion 功能建议 / other 其他，枚举与文案对齐源码 TYPE_OPTIONS）+ 内容多行输入；
  - 本地校验：trim 后非空 + 最少 10 字（阶段二口径，较源码 5 字更严）；
    提交前 slice(0, 500) 兜底（对齐源码 FEEDBACK_MAX_LENGTH，防程序化赋值超后端上限）；
  - 提交 → me.submitFeedback（POST /v1/feedback）→ 成功 trackEvent('feedback_submit')
    + toast + 成功态展示回执号与 24 小时回复承诺 → 可「再填一条」清空重填；
  - 反馈详情：页面参数携带 id 时（onLoad options.id）调 getFeedbackDetail(id)
    展示处理状态 / 回执号 / 提交时间（契约无回复内容字段，状态含 pending/processing/resolved）；
  - 入口说明：全局 FeedbackFab 组件仅 emit click，页面跳转由宿主页承接
    （主包「我的」页已挂 BaseCell 意见反馈入口 → 本页）；
  - 三态：SkeletonPage / ErrorState（重试）/ 离线提示条；onHide flush 埋点。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad, onShow } from '@dcloudio/uni-app'
import type { ApiError, FeedbackDetailResponse } from '@shared/types'
import { getFeedbackDetail } from '@/api/endpoints'
import { useMeStore } from '@/stores/me'
import { trackEvent, flushOnHide } from '@/utils/track'
import { toastSuccess, toastWarning, toastError } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import ErrorState from '@/components/ErrorState.vue'
import BasePicker from '@/components-base/BasePicker.vue'
import BaseInput from '@/components-base/BaseInput.vue'
import BaseButton from '@/components-base/BaseButton.vue'
import BaseTag from '@/components-base/BaseTag.vue'

/** 反馈内容上限（对齐源码 FEEDBACK_MAX_LENGTH，与后端 /v1/feedback 校验一致） */
const FEEDBACK_MAX_LENGTH = 500

/** 反馈内容最少字数（阶段二口径：本地校验最少 10 字） */
const FEEDBACK_MIN_LENGTH = 10

/** 反馈类型枚举（对齐后端契约 bug / suggestion / other） */
type FeedbackType = 'bug' | 'suggestion' | 'other'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 个人中心 store（submitFeedback） */
const me = useMeStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 页面模式：detail 详情查看（options.id 携带时）/ form 反馈表单（缺省） */
const mode = ref<'form' | 'detail'>('form')

/** 详情查询目标反馈 ID */
const detailId = ref(0)

/** 反馈详情（详情模式数据） */
const detail = ref<FeedbackDetailResponse | null>(null)

/** 详情加载中 / 加载错误 */
const detailLoading = ref(false)
const detailError = ref<ApiError | null>(null)

/** 反馈类型（缺省 suggestion，对齐源码 open() 重置口径） */
const type = ref<FeedbackType>('suggestion')

/** 反馈内容 */
const content = ref('')

/** 提交中（防连点） */
const submitting = ref(false)

/** 提交成功后的回执号（非空时切成功态） */
const receiptNo = ref('')

/** 类型选项（label 对齐源码 TYPE_OPTIONS 文案） */
const TYPE_OPTIONS: Array<{ label: string; value: string }> = [
  { label: '问题反馈', value: 'bug' },
  { label: '功能建议', value: 'suggestion' },
  { label: '其他', value: 'other' },
]

/** 处理状态 → 中文徽标映射（契约 status 为自由串，未知值原样透传） */
const STATUS_TEXT: Record<string, string> = {
  pending: '待处理',
  processing: '处理中',
  resolved: '已解决',
}

/** 详情状态徽标文案 */
const detailStatusText = computed(() =>
  detail.value ? (STATUS_TEXT[detail.value.status] ?? detail.value.status) : '',
)

/**
 * 类型选择变更（仅更新缓冲）。
 * @param value 新类型枚举值
 * @returns 无
 */
function onTypeChange(value: string | number): void {
  type.value = value as FeedbackType
}

/**
 * 提交反馈：本地校验（非空 + ≥10 字）→ me.submitFeedback（POST /v1/feedback）
 * → 成功埋点 feedback_submit + toast + 成功态（回执号 + 24h 承诺）；失败就地转错误 toast。
 * @returns 无
 * @throws 不向外抛出（接口异常已就地提示）
 */
async function onSubmit(): Promise<void> {
  const text = content.value.trim()
  if (!text) {
    toastWarning('请填写反馈内容')
    return
  }
  if (text.length < FEEDBACK_MIN_LENGTH) {
    toastWarning('请至少输入 10 个字，方便我们定位问题')
    return
  }
  submitting.value = true
  try {
    receiptNo.value = await me.submitFeedback(text.slice(0, FEEDBACK_MAX_LENGTH), type.value)
    trackEvent('feedback_submit', { feedback_type: type.value })
    toastSuccess('反馈已提交')
    content.value = ''
  } catch (e) {
    toastError((e as ApiError).message || '提交失败，请稍后重试')
  } finally {
    submitting.value = false
  }
}

/**
 * 成功态 → 再填一条：清空回执号回到表单态。
 * @returns 无
 */
function writeAnother(): void {
  receiptNo.value = ''
  content.value = ''
  type.value = 'suggestion'
}

/**
 * 拉取反馈详情（getFeedbackDetail）。
 * @param id 反馈 ID
 * @returns 无
 * @throws 不抛出（失败写入 detailError 三态）
 */
async function loadDetail(id: number): Promise<void> {
  detailLoading.value = true
  detailError.value = null
  try {
    detail.value = await getFeedbackDetail(id)
  } catch (e) {
    detailError.value = e as ApiError
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

/**
 * 时间格式化（YYYY-MM-DD HH:mm）。
 * @param iso ISO 8601 时间串
 * @returns 格式化文案；非法输入原样返回
 */
function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// onLoad：解析页面参数（id → 详情模式）
onLoad((options) => {
  const id = Number(options?.id ?? 0)
  if (Number.isFinite(id) && id > 0) {
    mode.value = 'detail'
    detailId.value = id
  }
})

// onShow：详情模式拉取详情（表单模式无数据请求）
onShow(() => {
  if (mode.value === 'detail') {
    void loadDetail(detailId.value)
  }
})

// onHide：尽力上报缓冲埋点
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <!-- 离线提示条 -->
    <OfflineBar v-if="!network.isConnected" />

    <view class="feedback">
      <!-- ═══ 详情模式（options.id 携带时） ═══ -->
      <template v-if="mode === 'detail'">
        <SkeletonPage v-if="detailLoading" type="detail" :rows="3" />

        <ErrorState v-else-if="detailError" kind="server" @retry="loadDetail(detailId)" />

        <view v-else-if="detail" class="feedback__detail">
          <view class="feedback__detail-card">
            <view class="feedback__detail-row">
              <text class="feedback__detail-label">处理状态</text>
              <BaseTag :text="detailStatusText" :kind="detail.status === 'resolved' ? 'primary' : 'info'" />
            </view>
            <view class="feedback__detail-row">
              <text class="feedback__detail-label">回执编号</text>
              <text class="feedback__detail-value">{{ detail.receipt_no }}</text>
            </view>
            <view class="feedback__detail-row">
              <text class="feedback__detail-label">提交时间</text>
              <text class="feedback__detail-value">{{ formatTime(detail.created_at) }}</text>
            </view>
          </view>
          <view class="feedback__hint">
            <text class="feedback__hint-text">我们会在 24 小时内回复你</text>
          </view>
        </view>
      </template>

      <!-- ═══ 表单模式（缺省） ═══ -->
      <template v-else>
        <!-- 成功态：回执号 + 承诺说明 -->
        <view v-if="receiptNo" class="feedback__success">
          <text class="feedback__success-icon">✅</text>
          <text class="feedback__success-title">反馈已提交</text>
          <text class="feedback__success-sub">我们会在 24 小时内回复你</text>
          <text class="feedback__success-receipt">回执编号：{{ receiptNo }}</text>
          <BaseButton class="feedback__success-btn" type="default" block @click="writeAnother">
            再填一条
          </BaseButton>
        </view>

        <!-- 表单态 -->
        <template v-else>
          <view class="feedback__field">
            <text class="feedback__label">反馈类型</text>
            <BasePicker
              :model-value="type"
              :options="TYPE_OPTIONS"
              placeholder="选择反馈类型"
              @update:model-value="onTypeChange"
            />
          </view>

          <view class="feedback__field">
            <text class="feedback__label">反馈内容（至少 10 个字）</text>
            <BaseInput
              v-model="content"
              type="textarea"
              placeholder="描述你遇到的问题或建议（至少 10 个字）"
              :maxlength="FEEDBACK_MAX_LENGTH"
            />
          </view>

          <BaseButton class="feedback__submit" block :loading="submitting" @click="onSubmit">
            提交
          </BaseButton>
        </template>
      </template>
    </view>
  </view>
</template>

<style scoped lang="scss">
.feedback {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md) var(--space-md) var(--space-xl);
}

.feedback__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  margin-bottom: var(--space-lg);
}

.feedback__label {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.feedback__submit {
  margin-top: var(--space-xs);
}

/* ── 成功态 ── */
.feedback__success {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-xl) var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
}

.feedback__success-icon {
  font-size: 80rpx;
  line-height: 1.2;
}

.feedback__success-title {
  margin-top: var(--space-xs);
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.feedback__success-sub {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.feedback__success-receipt {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-primary);
}

.feedback__success-btn {
  margin-top: var(--space-md);
}

/* ── 详情 ── */
.feedback__detail-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-lg) var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
}

.feedback__detail-row {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.feedback__detail-label {
  flex-shrink: 0;
  width: 160rpx;
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.feedback__detail-value {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-base);
  color: var(--text-primary);
  word-break: break-all;
}

.feedback__hint {
  padding: var(--space-sm) var(--space-md);
  margin-top: var(--space-lg);
  border-radius: var(--radius-card);
  background: var(--color-info-bg);
}

.feedback__hint-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-secondary);
}
</style>
