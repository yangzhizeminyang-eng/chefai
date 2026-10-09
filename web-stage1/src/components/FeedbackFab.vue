<script setup lang="ts">
/**
 * 组件职责：全局反馈入口（右下角固定 FAB）+ 意见反馈弹窗。
 * - FAB 固定于视口右下角（所有页面可见），点击打开反馈弹窗；
 * - 弹窗：类型单选（bug / 建议 / 其他）+ 文字内容（≥5 字校验）；
 * - 提交成功展示回执号 + 「24 小时内回复」承诺说明；
 * - 监听全局自定义事件 `aicook:open-feedback`（个人中心「反馈」宫格入口复用本弹窗）。
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound } from '@element-plus/icons-vue'
import { useMeStore } from '@/stores/me'
import type { ApiError } from '@/api/types'

/** 个人中心等外部入口打开弹窗的自定义事件名（与 MeView 约定一致） */
const OPEN_FEEDBACK_EVENT = 'aicook:open-feedback'

/** 反馈内容最大长度（与后端 /v1/feedback 上限一致，超限提交会被 400 拒绝） */
const FEEDBACK_MAX_LENGTH = 500

/** 个人中心 store（submitFeedback 动作） */
const meStore = useMeStore()

/** 弹窗可见性 */
const visible = ref(false)
/** 反馈类型 */
const type = ref<'bug' | 'suggestion' | 'other'>('suggestion')
/** 反馈内容 */
const content = ref('')
/** 提交中 */
const submitting = ref(false)
/** 提交成功后的回执号（非空时弹窗切到成功态） */
const receiptNo = ref('')

/** 类型选项（el-radio-group） */
const TYPE_OPTIONS: Array<{ value: 'bug' | 'suggestion' | 'other'; label: string }> = [
  { value: 'bug', label: '问题反馈' },
  { value: 'suggestion', label: '功能建议' },
  { value: 'other', label: '其他' },
]

/**
 * 打开弹窗（重置为空白表单态）。
 * @returns 无
 */
function open(): void {
  content.value = ''
  type.value = 'suggestion'
  receiptNo.value = ''
  visible.value = true
}

/**
 * 提交反馈：走 me store；成功后切成功态展示回执号。
 * - 空内容（trim 后为空）：warning 提示，不发请求、弹窗不关（修复 M4 空提交静默无响应）；
 * - 内容不足 5 字：warning 提示补充描述；
 * - 提交前统一 slice(0, FEEDBACK_MAX_LENGTH) 兜底（修复 H5 超限入库：
 *   textarea maxlength 仅约束手动输入，程序化赋值仍可能超后端 500 字上限）。
 * @returns 无
 * @throws 不向外抛出（接口异常已就地转为错误 toast）
 */
async function onSubmit(): Promise<void> {
  const text = content.value.trim()
  if (!text) {
    ElMessage.warning('请填写反馈内容')
    return
  }
  if (text.length < 5) {
    ElMessage.warning('请至少输入 5 个字，方便我们定位问题')
    return
  }
  submitting.value = true
  try {
    receiptNo.value = await meStore.submitFeedback(text.slice(0, FEEDBACK_MAX_LENGTH), type.value)
  } catch (e) {
    ElMessage.error((e as ApiError).message || '提交失败，请稍后重试')
  } finally {
    submitting.value = false
  }
}

// 挂载：监听全局打开事件（外部入口复用本弹窗）；卸载时移除
onMounted(() => {
  window.addEventListener(OPEN_FEEDBACK_EVENT, open as EventListener)
})
onBeforeUnmount(() => {
  window.removeEventListener(OPEN_FEEDBACK_EVENT, open as EventListener)
})
</script>

<template>
  <!-- 右下角固定反馈 FAB（全页面可见） -->
  <el-button
    class="feedback-fab"
    type="primary"
    circle
    size="large"
    aria-label="意见反馈"
    title="意见反馈"
    @click="open"
  >
    <el-icon :size="22"><ChatDotRound /></el-icon>
  </el-button>

  <!-- 意见反馈弹窗：表单态 / 成功态二段 -->
  <el-dialog v-model="visible" title="意见反馈" width="440px" align-center>
    <!-- 表单态 -->
    <div v-if="!receiptNo">
      <el-form label-position="top">
        <el-form-item label="反馈类型">
          <el-radio-group v-model="type">
            <el-radio-button v-for="opt in TYPE_OPTIONS" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="反馈内容">
          <el-input
            v-model="content"
            type="textarea"
            :rows="5"
            :maxlength="FEEDBACK_MAX_LENGTH"
            show-word-limit
            placeholder="描述你遇到的问题或建议（至少 5 个字）"
          />
        </el-form-item>
      </el-form>
    </div>

    <!-- 成功态：回执号 + 24h 承诺 -->
    <el-result v-else icon="success" title="反馈已提交" sub-title="我们会在 24 小时内回复你">
      <template #extra>
        <p class="feedback-receipt">回执编号：{{ receiptNo }}</p>
      </template>
    </el-result>

    <template #footer>
      <template v-if="!receiptNo">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">提交</el-button>
      </template>
      <el-button v-else type="primary" @click="visible = false">好的</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.feedback-fab {
  position: fixed;
  right: 20px;
  bottom: 24px;
  z-index: 60;
  width: 52px;
  height: 52px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.18);
}

.feedback-receipt {
  margin: 0 0 12px;
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
}
</style>
