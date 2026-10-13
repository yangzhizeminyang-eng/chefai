<!--
  文件级注释：P-17 问厨娘页（烹饪过程求助，W-04 求助弹窗拆页落点）。
  自 web-stage1 CookGuideView 求助区（postCookingHelp 三态）迁移：
  - onLoad options.session_id → 会话求助链路 postCookingHelp(sessionId, question)；
  - 对话流：本页问答列表（AskChatCard 逐条呈现），记录持久化到
    cook_ask_{session_id}（返回 guide 后对话状态保留——store 不承载求助对话，
    以 storage 持久化跨页面存活，重进恢复）；
  - 求助关键词（DEF-06 十类）：与后端 _HELP_TOPICS 关键词库同源（太咸/太淡/糊锅/
    发苦/没调料/火候/溅油/太辣/腥味/粘锅），收敛为快捷提问 chips——点击即填入发送，
    后端命中关键词返回针对性常识要点（前端不重复实现回答逻辑，发问一律走后端）；
  - 风控分流（G-01 / RL-7）：
      · blocked 且话术含「医疗/医生」→ AskChatCard refuse 中性卡
        （MEDICAL_REFUSE_TEXT 常量，就医引导非警告）+ trackEvent('medical_refuse')；
      · blocked 其他 → RiskBlockModal（话术含「过敏原」按 allergen 类，否则 food）
        + trackEvent('safety_block')；
      · 发问一律走后端，前端不做风控判定（kind 归类仅影响展示色调）；
  - 429 当日次数超限 → 轻提示（对齐源码 helpState 'limit'）；
  - 加载/错误态：发送失败 ErrorState + 重试（重试上一次问题）；
  - 埋点：发送求助 trackEvent('cook_help_request')；onHide flush 缓冲。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad } from '@dcloudio/uni-app'
import { postCookingHelp } from '@/api/endpoints'
import type { ApiError } from '@shared/types'
import { MEDICAL_REFUSE_TEXT } from '@shared/constants'
import { get as storageGet, set as storageSet } from '@/utils/storage'
import { toastWarning } from '@/utils/toast'
import { trackEvent, flushOnHide } from '@/utils/track'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import AskChatCard from '@/components/AskChatCard.vue'
import RiskBlockModal from '@/components/RiskBlockModal.vue'
import ErrorState from '@/components/ErrorState.vue'
import EmptyState from '@/components/EmptyState.vue'
import BaseButton from '@/components-base/BaseButton.vue'
import BaseInput from '@/components-base/BaseInput.vue'

/** 对话记录持久化键前缀（key = cook_ask_{sessionId}，返回 guide 后状态保留） */
const ASK_LOG_PREFIX = 'cook_ask_'

/** 求助对话条目（AskChatCard 渲染数据源） */
interface AskEntry {
  /** 用户问句（溯源回显） */
  question: string
  /** 厨娘回答正文（多条回答以换行合并） */
  answer: string
  /** 是否医疗拒答态（RL-7 中性卡 + 就医引导） */
  refuse: boolean
}

/** 求助关键词表（DEF-06 十类，与后端 cooking.py _HELP_TOPICS 同源；快捷提问 chips） */
const HELP_TOPICS: readonly string[] = [
  '太咸了怎么办',
  '太淡了怎么办',
  '糊锅了怎么办',
  '炒出来发苦',
  '调料没有了怎么替代',
  '火候怎么判断',
  '溅油烫到了怎么办',
  '太辣了怎么中和',
  '腥味重怎么去',
  '粘锅了怎么办',
]

/** 医疗类话术识别关键词（blocked 响应未回传 kind，按话术关键字归类；仅影响展示分流） */
const MEDICAL_HINTS: readonly string[] = ['医疗', '医生', '就医', '诊断']

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 路由注入的会话 ID（求助接口路径参数；空 = 从引导页外进入的兜底态） */
const sessionId = ref('')

/** 求助对话列表（持久化恢复，倒序展示为对话流） */
const entries = ref<AskEntry[]>([])

/** 输入区内容（v-model） */
const question = ref('')

/** 发送请求进行中（防重复 asking） */
const asking = ref(false)

/** 发送失败标记（ErrorState + 重试上一次问题） */
const sendError = ref<ApiError | null>(null)

/** 最近一次尝试发送的问题（重试落点） */
const lastQuestion = ref('')

/** 风控拦截弹窗可见性（RiskBlockModal；文案随 kind） */
const riskVisible = ref(false)

/** 风控拦截类型（food / allergen / medical；按后端话术关键字归类） */
const riskKind = ref<'food' | 'allergen' | 'medical'>('food')

/** 风控拦截补充说明（后端 message） */
const riskDetail = ref('')

/** 对话持久化键 */
const logKey = computed(() => `${ASK_LOG_PREFIX}${sessionId.value || 'local'}`)

/**
 * 持久化对话记录（每次变更后同步落盘，返回 guide 再进状态保留）。
 * @returns 无
 * @throws 不抛出（storage 内部静默降级）
 */
function persistEntries(): void {
  storageSet(logKey.value, entries.value)
}

/**
 * 快捷 chips 点击：填入对应求助关键词并发送（对齐「点击即问」快捷体验）。
 * @param topic 关键词话术
 * @returns 无
 */
function onQuickTopic(topic: string): void {
  question.value = topic
  void sendQuestion()
}

/**
 * 发送求助（函数）：空输入守卫 → 防重复 → postCookingHelp → 三态分流呈现。
 * - 正常 answers：多条以换行合并，AskChatCard 逐条呈现；
 * - blocked：话术含医疗关键词 → refuse 中性卡 + medical_refuse 埋点；
 *   其余 → RiskBlockModal + safety_block 埋点；
 * - 429：当日次数超限轻提示；其余错误 → ErrorState 重试。
 * @returns 无
 * @throws 不抛出（错误收敛为页面三态，不向外抛）
 */
async function sendQuestion(): Promise<void> {
  const text = question.value.trim()
  if (!text) {
    toastWarning('请输入问题')
    return
  }
  if (asking.value) return
  if (!sessionId.value) {
    toastWarning('未关联烹饪会话，请从烹饪引导页进入')
    return
  }
  asking.value = true
  sendError.value = null
  lastQuestion.value = text
  // 发送求助埋点（cook_help_request）
  trackEvent('cook_help_request', { session_id: sessionId.value })
  try {
    const res = await postCookingHelp(sessionId.value, text)
    if ('blocked' in res && res.blocked) {
      const message = res.message ?? res.title ?? ''
      const isMedical = MEDICAL_HINTS.some((k) => message.includes(k))
      if (isMedical) {
        // RL-7 医疗拒答：中性卡 + MEDICAL_REFUSE_TEXT 常量（安全类埋点立即 flush）
        entries.value = [
          ...entries.value,
          { question: text, answer: MEDICAL_REFUSE_TEXT, refuse: true },
        ]
        trackEvent('medical_refuse', { session_id: sessionId.value })
      } else {
        // G-01 一票否决：拦截弹窗（话术含过敏原按 allergen 类，其余 food 类）
        riskKind.value = message.includes('过敏原') ? 'allergen' : 'food'
        riskDetail.value = message
        riskVisible.value = true
        trackEvent('safety_block', { session_id: sessionId.value })
      }
      question.value = ''
      persistEntries()
      return
    }
    // 正常回答：多条要点换行合并（后端 answers 每条为一句可执行要点）
    const answers = 'answers' in res ? (res.answers ?? []) : []
    entries.value = [
      ...entries.value,
      { question: text, answer: answers.join('\n') || '这个问题厨娘暂时答不上来，试试换一种问法', refuse: false },
    ]
    question.value = ''
    persistEntries()
  } catch (e) {
    const err = e as ApiError
    if (err.code === 429) {
      // 429 当日次数超限：轻提示（对齐源码 helpState 'limit' 文案语义）
      toastWarning('今日求助次数已达上限，明天再来问吧')
    } else {
      // 其余错误：ErrorState + 重试上一次问题
      sendError.value = err
    }
  } finally {
    asking.value = false
  }
}

/**
 * 错误态重试：重发上一次问题。
 * @returns 无
 */
function retrySend(): void {
  sendError.value = null
  if (lastQuestion.value) {
    question.value = lastQuestion.value
    void sendQuestion()
  }
}

/**
 * 关闭风控拦截弹窗。
 * @returns 无
 */
function onRiskClose(): void {
  riskVisible.value = false
}

/**
 * onLoad：解析 session_id 并恢复持久化对话记录。
 * @param options 页面参数（session_id）
 * @returns 无
 * @throws 不抛出
 */
onLoad((options) => {
  sessionId.value = options?.session_id ? decodeURIComponent(options.session_id) : ''
  const cached = storageGet<AskEntry[]>(logKey.value, [])
  entries.value = Array.isArray(cached) ? cached : []
})

// 页面隐匿时尽力上报缓冲埋点（统一页面约定；medical_refuse/safety_block 已即时 flush）
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <view class="ask">
      <!-- 会话缺失兜底：求助链路依赖烹饪会话 -->
      <EmptyState
        v-if="!sessionId"
        icon="👩‍🍳"
        title="未关联烹饪会话"
        desc="请从烹饪引导页进入问厨娘，才能结合当前步骤提问"
      />

      <template v-else>
        <!-- 对话流：AskChatCard 逐条呈现（refuse 中性卡 / 正常卡） -->
        <view v-if="entries.length > 0" class="ask__list">
          <AskChatCard
            v-for="(entry, idx) in entries"
            :key="idx"
            :question="entry.question"
            :answer="entry.answer"
            :refuse="entry.refuse"
          />
        </view>
        <EmptyState
          v-else-if="!sendError"
          icon="💬"
          title="做菜遇到问题？问问厨娘"
          desc="例如「太咸了怎么办」「糊锅了怎么补救」，也可以点下方常见问题直接提问"
        />

        <!-- 发送失败：错误态 + 重试 -->
        <ErrorState v-if="sendError" kind="server" detail="求助发送失败，请重试" @retry="retrySend" />

        <!-- 快捷求助关键词（DEF-06 十类，与后端关键词库同源；点击即问） -->
        <view class="ask__chips">
          <view
            v-for="topic in HELP_TOPICS"
            :key="topic"
            class="ask__chip"
            :class="{ 'is-disabled': asking }"
            @click="onQuickTopic(topic)"
          >
            {{ topic }}
          </view>
        </view>

        <!-- 输入区：BaseInput + 发送（防重复 asking） -->
        <view class="ask__composer">
          <view class="ask__input">
            <BaseInput
              v-model="question"
              type="text"
              placeholder="输入你的问题，如：太咸了怎么办"
              :maxlength="100"
              :disabled="asking"
            />
          </view>
          <BaseButton :loading="asking" @click="sendQuestion">发送</BaseButton>
        </view>
      </template>

      <!-- G-01 风控拦截弹窗（非医疗类） -->
      <RiskBlockModal :visible="riskVisible" :kind="riskKind" :detail="riskDetail" @close="onRiskClose" />
    </view>
  </view>
</template>

<style scoped lang="scss">
.ask {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-md);
  padding-bottom: calc(var(--space-xl) + env(safe-area-inset-bottom));
}

/* 对话流 */
.ask__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* 快捷求助关键词 */
.ask__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.ask__chip {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--hit-min);
  padding: 0 var(--space-md);
  border-radius: 999rpx;
  border: 1rpx solid var(--border-color);
  background: var(--bg-card);
  font-size: var(--font-size-sm);
  color: var(--text-primary);

  &.is-disabled {
    opacity: 0.5;
    pointer-events: none;
  }
}

/* 输入区 */
.ask__composer {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.ask__input {
  flex: 1;
  min-width: 0;
}
</style>
