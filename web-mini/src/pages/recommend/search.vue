<!--
  文件级注释：P-12 搜索/提问页（pages/recommend/search）——对话流重构版。
  交互语义（对齐用户预期"AI 厨娘正常回答交流的一个过程"）：
  - 消息流：用户消息（右侧气泡）/ AI 回答（左侧气泡；医疗拒答为中性样式）/ 菜谱结果
    （左侧卡片列表，来自 ask 意图路由 recipe_search）按时间线纵向排列，
    scroll-into-view 自动滚动到最新消息；
  - 输入区：底部 fixed 常驻（input + 发送按钮 + safe-area），发送后清空可连续追问，
    形成"提问 → 回答 → 追问"的交流过程（历史消息保留在会话内）；
  - 提交链路：本页直调 postAsk（绕过 ask store 的跳转副作用——store 保留供他处用），
    响应经 resolveAskAction 纯函数分流：
    ① blocked → RiskBlockModal（RL-1：阻断态弹窗承接，不渲染业务内容）+
       对话流内插入说明消息；
    ② recipe_search（recipe_ids 非空）→ 并行 getRecipe 拉详情 →
       recipeDetailToAskItem 映射 → 对话流内嵌菜谱卡片列表（点击进详情，不跳页）；
       ids 为空 → 对话流插入 NO_RECIPE_ANSWER 兜底回答 + search_no_result 埋点；
    ③ chat（free_qa 等）→ 对话流插入 answer（MEDICAL_REFUSE_TEXT 命中 →
       拒答中性样式 + medical_refuse 埋点）；
    ④ 失败 → 对话流插入统一降级文案（ASK_FAILED_MESSAGE），不 toast 打断；
  - 空输入守卫（isBlankQuestion）；?q= 深链自动执行（语音页等入口携 q 跳入）；
  - 历史搜索：消息流为空时展示（storage 本地 aicook_search_history_v1 ≤10 条，非敏感）；
  - 五态：发送中（输入行 loading）/ 错误（对话流内呈现）/ 离线（OfflineBar）。
-->
<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { onHide, onLoad } from '@dcloudio/uni-app'
import { MEDICAL_REFUSE_TEXT } from '@shared/constants'
import {
  NO_RECIPE_ANSWER,
  isBlankQuestion,
  recipeDetailToAskItem,
  resolveAskAction,
} from '@shared/utils'
import type { RecipeDetail } from '@shared/types'
import { getRecipe, postAsk } from '@/api/endpoints'
import { ASK_FAILED_MESSAGE } from '@/stores/ask'
import { useConfigStore } from '@/stores/config'
import { useRecommendStore } from '@/stores/recommend'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide, trackEvent } from '@/utils/track'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import { get as storageGet, set as storageSet } from '@/utils/storage'
import RiskBlockModal from '@/components/RiskBlockModal.vue'
import OfflineBar from '@/components/OfflineBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import RecipeCard, { type RecipeCardLike } from '@/components/RecipeCard.vue'
import BaseButton from '@/components-base/BaseButton.vue'
import BaseInput from '@/components-base/BaseInput.vue'

/** 历史搜索持久化键（本地非敏感：搜索词；≤10 条 LRU） */
const SEARCH_HISTORY_KEY = 'aicook_search_history_v1'

/** 历史条数上限 */
const HISTORY_LIMIT = 10

/** 对话流消息（kind 判别联合渲染：user 右侧 / ai 左侧 / recipes 卡片组） */
interface ChatMsg {
  /** 消息自增 id（scroll-into-view 锚点） */
  id: number
  /** 用户消息 */
  kind: 'user' | 'ai' | 'recipes'
  /** 文本内容（user / ai 用） */
  text?: string
  /** AI 拒答标记（true → 中性拒答样式，RL-7） */
  refuse?: boolean
  /** 菜谱卡片列表（recipes 用） */
  items?: RecipeCardLike[]
  /** 触发本组结果的问题（recipes 头部回显） */
  q?: string
}

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()
/** 远程开关 store（qa 开关降级守卫，§5.8） */
const configStore = useConfigStore()
/** 推荐 store（ask blocked 兜底读取 blockedPayload） */
const recommendStore = useRecommendStore()

/** 对话流消息列表（会话内累计，形成交流过程） */
const messages = ref<ChatMsg[]>([])
/** 消息自增序列（消息 id 生成器） */
let seq = 0
/** 输入框绑定值 */
const keyword = ref('')
/** 请求进行中（发送按钮 loading 与防重复提交） */
const sending = ref(false)
/** 历史搜索词（新→旧；消息流为空时展示） */
const history = ref<string[]>([])
/** scroll-view 滚动锚点（最新消息 id，发送后滚动到底） */
const scrollInto = ref('')

/** 问答模块是否可用（switches.qa 未返回视为开启） */
const qaEnabled = computed(() => configStore.switches.qa !== false)

/** ask blocked 兜底：本页以弹窗承接（RL-1：blockedPayload 存在即展示） */
const blockVisible = computed(() => !!recommendStore.blockedPayload)

/** 拦截弹窗 kind 映射（medical_refusal → medical / allergen_conflict → allergen / 其余 food） */
const blockKind = computed<'food' | 'allergen' | 'medical'>(() => {
  const category = recommendStore.blockedPayload?.risk?.category ?? ''
  if (category === 'medical_refusal') return 'medical'
  if (category === 'allergen_conflict') return 'allergen'
  return 'food'
})

/** 拦截弹窗补充说明（后端 risk.body 直出） */
const blockDetail = computed(() => recommendStore.blockedPayload?.risk?.body ?? '')

/**
 * 追加一条消息并滚动到该消息（nextTick 等 DOM 更新后设置 scroll-into-view）。
 * @param msg 消息体（id 由本函数分配）
 * @returns 分配后的消息 id
 */
function pushMsg(msg: Omit<ChatMsg, 'id'>): number {
  seq += 1
  const withId: ChatMsg = { id: seq, ...msg }
  messages.value.push(withId)
  void nextTick(() => {
    scrollInto.value = `msg-${seq}`
  })
  return seq
}

/**
 * 保存历史搜索词（新→旧去重，LRU ≤10 条；storage 失败静默）。
 * @param t 搜索词（已 trim）
 * @returns 无
 */
function saveHistory(t: string): void {
  const next = [t, ...history.value.filter((h) => h !== t)].slice(0, HISTORY_LIMIT)
  history.value = next
  try {
    storageSet(SEARCH_HISTORY_KEY, next)
  } catch {
    // 历史写入失败静默：非敏感增强数据，不阻断交流
  }
}

/**
 * 菜谱详情 → RecipeCard 数据适配（recipeDetailToAskItem 产物 → 卡片条目）。
 * @param r 推荐结果条目（来自 recipeDetailToAskItem 映射）
 * @returns 卡片条目
 */
function toCardItem(r: ReturnType<typeof recipeDetailToAskItem>): RecipeCardLike {
  return {
    id: String(r.recipe_id),
    name: r.title,
    total_time: r.time_minutes,
    difficulty: r.difficulty,
  }
}

/**
 * 发送消息（交流主链路）：user 气泡 → postAsk → resolveAskAction 分流 → AI 气泡 /
 * 菜谱卡片组 / 风控弹窗；失败在对话流内呈现统一降级文案（不 toast 打断交流）。
 * @returns 无
 * @throws 不向外抛出（请求与详情拉取失败均在对话流内收敛）
 */
async function send(): Promise<void> {
  const t = keyword.value.trim()
  if (isBlankQuestion(t) || sending.value) return
  if (!qaEnabled.value) {
    pushMsg({ kind: 'ai', text: '问答功能维护中，稍后再来问问厨娘吧' })
    return
  }
  // 用户消息入流 + 清空输入 + 历史 LRU
  pushMsg({ kind: 'user', text: t })
  keyword.value = ''
  saveHistory(t)
  sending.value = true
  try {
    const res = await postAsk(t)
    const action = resolveAskAction(res)
    if (action.type === 'blocked') {
      // 命中风控一票否决（G-01）：写 W-05 数据源，弹窗承接（对话流插入中性说明）
      const recommendStore2 = useRecommendStore()
      recommendStore2.blockedPayload = action.payload
      recommendStore2.traceId = action.payload.trace_id || res.trace_id
      trackEvent('safety_block')
      pushMsg({ kind: 'ai', text: '该请求未通过安全检查，未生成任何内容', refuse: true })
      return
    }
    if (action.type === 'recipe_search') {
      // 搜索命中：并行拉详情（上限 8 条防长列表），失败的条目静默剔除
      const details = await Promise.all(
        action.recipeIds.slice(0, 8).map((id) => getRecipe(id).catch(() => null)),
      )
      const items = details
        .filter((d): d is RecipeDetail => d !== null)
        .map((d) => toCardItem(recipeDetailToAskItem(d, t)))
      if (items.length === 0) {
        trackEvent('search_no_result')
        pushMsg({ kind: 'ai', text: NO_RECIPE_ANSWER })
        return
      }
      pushMsg({ kind: 'recipes', items, q: t })
      return
    }
    // chat / 其他意图：AI 回答气泡（医疗拒答 → 中性样式 + medical_refuse 埋点）
    const refuse = action.answer.includes(MEDICAL_REFUSE_TEXT)
    if (refuse) trackEvent('medical_refuse')
    pushMsg({ kind: 'ai', text: action.answer, refuse })
  } catch {
    // 统一降级：对话流内呈现（交流不打断，用户可重试追问）
    pushMsg({ kind: 'ai', text: ASK_FAILED_MESSAGE })
  } finally {
    sending.value = false
  }
}

/**
 * 历史词点击：回填输入框并立即执行搜索。
 * @param t 历史搜索词
 * @returns 无
 */
function useHistory(t: string): void {
  keyword.value = t
  void send()
}

/**
 * 结果卡片点击 → 菜谱详情（携带 recipe_id）+ recommend_click 埋点。
 * @param card 被点击卡片
 * @returns 无
 */
function goDetail(card: RecipeCardLike): void {
  trackEvent('recommend_click', { recipe_id: card.id })
  goRoute(`${ROUTES.RECIPE_DETAIL}?recipe_id=${card.id}`)
}

/**
 * 关闭拦截弹窗：清空 blockedPayload 后留在本页（RL-1 阻断态显式确认）。
 * @returns 无
 */
function closeBlocked(): void {
  recommendStore.blockedPayload = null
}

// onLoad：消费 ?q=（语音页等入口携 q 跳入，回填并自动执行）；恢复历史搜索
onLoad((options) => {
  try {
    const saved = storageGet<string[]>(SEARCH_HISTORY_KEY, [])
    if (Array.isArray(saved)) history.value = saved
  } catch {
    // 历史读取失败静默：非敏感增强数据
  }
  const q = (options as { q?: string } | undefined)?.q
  if (q && q.trim()) {
    keyword.value = q.trim()
    void send()
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

    <!-- 消息流（scroll-view：scroll-into-view 锚点滚到最新消息） -->
    <scroll-view
      class="chat__scroll"
      scroll-y
      :scroll-into-view="scrollInto"
      scroll-with-animation
    >
      <!-- 空会话：欢迎语 + 历史搜索（有则展示） -->
      <view v-if="messages.length === 0" class="chat__welcome">
        <text class="chat__welcome-title">你好，我是 AI 厨娘 👩‍🍳</text>
        <text class="chat__welcome-desc">问我"晚上吃点清淡的有什么推荐"，或直接说食材让我帮你找菜谱</text>
        <view v-if="history.length > 0" class="chat__history">
          <text class="chat__history-title">最近搜索</text>
          <view class="chat__history-chips">
            <view
              v-for="h in history"
              :key="h"
              class="chat__history-chip"
              @click="useHistory(h)"
            >
              {{ h }}
            </view>
          </view>
        </view>
        <EmptyState
          v-if="!qaEnabled"
          icon="💬"
          title="问答功能维护中"
          desc="稍后再来问问厨娘吧"
        />
      </view>

      <!-- 消息列表 -->
      <view
        v-for="msg in messages"
        :id="`msg-${msg.id}`"
        :key="msg.id"
        class="chat__row"
        :class="{ 'chat__row--user': msg.kind === 'user' }"
      >
        <!-- 用户消息：右侧主色气泡 -->
        <view v-if="msg.kind === 'user'" class="chat__bubble chat__bubble--user">
          {{ msg.text }}
        </view>

        <!-- 菜谱结果组：问题回显 + 卡片列表（点击进详情，不跳页） -->
        <view v-else-if="msg.kind === 'recipes'" class="chat__recipes">
          <view v-if="msg.q" class="chat__recipes-q">为你找到与「{{ msg.q }}」相关的菜谱</view>
          <view class="chat__recipes-list">
            <RecipeCard
              v-for="r in msg.items ?? []"
              :key="r.id"
              :item="r"
              @click="goDetail(r)"
            />
          </view>
        </view>

        <!-- AI 回答：左侧气泡（医疗拒答 → 中性样式 RL-7） -->
        <view
          v-else
          class="chat__bubble chat__bubble--ai"
          :class="{ 'chat__bubble--refuse': msg.refuse }"
        >
          {{ msg.text }}
        </view>
      </view>
      <view class="chat__scroll-pad" />
    </scroll-view>

    <!-- 底部输入区（fixed + safe-area）：发送中 loading 文案 -->
    <view class="chat__input-bar">
      <view class="chat__input-wrap">
        <BaseInput
          v-model="keyword"
          placeholder="问问厨娘，或说说你想吃的"
          :maxlength="200"
          @confirm="send"
        />
      </view>
      <BaseButton
        type="primary"
        size="sm"
        :disabled="sending"
        @click="send"
      >
        {{ sending ? '…' : '发送' }}
      </BaseButton>
    </view>

    <!-- 底部免责条（G-02） -->
    <DisclaimerBar scene="detail" />

    <!-- 风控拦截弹窗（G-01：blocked 弹窗承接，RL-1 不渲染业务内容） -->
    <RiskBlockModal
      :visible="blockVisible"
      :kind="blockKind"
      :detail="blockDetail"
      @close="closeBlocked"
    />
  </view>
</template>

<style scoped lang="scss">
.page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

/* 消息流滚动区：flex 占据剩余高度（底部输入区固定） */
.chat__scroll {
  flex: 1;
  min-height: 0;
  box-sizing: border-box;
  padding: var(--space-md);
}

.chat__scroll-pad {
  height: calc(var(--space-lg) + env(safe-area-inset-bottom));
}

/* 空会话欢迎区 */
.chat__welcome {
  padding: var(--space-xl) var(--space-md) 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.chat__welcome-title {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.chat__welcome-desc {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
  line-height: 1.7;
}

.chat__history {
  margin-top: var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.chat__history-title {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.chat__history-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
}

.chat__history-chip {
  box-sizing: border-box;
  min-height: var(--hit-min);
  padding: 0 var(--space-md);
  display: flex;
  align-items: center;
  border: 1rpx solid var(--border-color);
  border-radius: var(--radius-pill);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

/* 消息行：user 靠右，其余靠左 */
.chat__row {
  margin-bottom: var(--space-md);
  display: flex;
  justify-content: flex-start;

  &--user {
    justify-content: flex-end;
  }
}

/* 气泡通用 */
.chat__bubble {
  box-sizing: border-box;
  max-width: 80%;
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-card);
  font-size: var(--font-size-base);
  line-height: 1.7;
  word-break: break-all;
}

/* 用户气泡：主色实底 */
.chat__bubble--user {
  background: var(--color-primary);
  color: var(--text-inverse);
}

/* AI 气泡：卡片底色 */
.chat__bubble--ai {
  background: var(--bg-card);
  color: var(--text-primary);
  box-shadow: var(--shadow-card);
}

/* 医疗拒答：中性样式（RL-7：视觉不警示、就医引导语义已含在文案） */
.chat__bubble--refuse {
  background: var(--color-info-bg);
  color: var(--text-primary);
}

/* 菜谱结果组 */
.chat__recipes {
  box-sizing: border-box;
  width: 92%;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.chat__recipes-q {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.chat__recipes-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

/* 底部输入区：fixed 常驻 + safe-area */
.chat__input-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  box-sizing: border-box;
  padding: var(--space-sm) var(--space-md);
  padding-bottom: calc(var(--space-sm) + env(safe-area-inset-bottom));
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  background: var(--bg-page);
  border-top: 1rpx solid var(--divider);
}

.chat__input-wrap {
  flex: 1;
  min-width: 0;
}
</style>
