<!--
  文件级注释：P-08 识别确认页（pages/recommend/recognize）。
  自 web-stage1/src/views/RecognizeView.vue 结果确认区迁移（阶段二拆页：数据来自
  P-07 photo.vue 经 storage 交接键 aicook_vision_result_v1 传入的识别响应）：
  - 结果编辑（本地编辑，不下发）：高置信默认勾选 / 低置信默认不勾（源码语义），
    chip 点击翻转勾选；支持手动「添加食材」（本地补录）与单条删除；
  - degraded=true → 顶部 DegradedBar（DEGRADED_BAR_TEXT）+ 源码降级警示文案
    （「识别服务繁忙…建议核对后再确认入库」）；degraded 不另设扣额话术（源码无此文案，
    额度行如实展示 quota）；
  - 额度行：MEMBER_QUOTA_LABEL + 响应 quota 字段（口径与源码 quota-line 一致）；
  - 🔴 RL-5 确认入库：必须人工点击「确认无误」才调 endpoints.postVisionConfirm(names)，
    无默认确认、不可跳过（无勾选时按钮禁用）；确认成功 trackEvent('ingredient_recognize_result')，
    勾选食材并入 ingredients store 已选（按名称/别名匹配食材库，对齐源码 onConfirm 语义：
    仅能匹配到食材库的条目进入本地已选；未收录条目已由后端 confirm 入库）；
  - 成功后引导跳推荐列表（已选 ≥1，推荐页守卫放行，主链路不阻断）；
  - 确认失败：错误提示 + 保留页面可重试（ErrorState 语义内联）；
  - 空态：无交接数据（直达深链 / 交接丢失）→ EmptyState 兜底回拍照/手选。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad } from '@dcloudio/uni-app'
import { MEMBER_QUOTA_LABEL, DEGRADED_BAR_TEXT } from '@shared/constants'
import type { VisionRecognizeResponse } from '@shared/types'
import { postVisionConfirm } from '@/api/endpoints'
import { useIngredientsStore } from '@/stores/ingredients'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide, trackEvent } from '@/utils/track'
import { toastSuccess, toastWarning, toastError } from '@/utils/toast'
import { get as storageGet, remove as storageRemove } from '@/utils/storage'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import { VISION_RESULT_KEY } from '@/utils/visionTransfer'
import DegradedBar from '@/components/DegradedBar.vue'
import EmptyState from '@/components/EmptyState.vue'
import OfflineBar from '@/components/OfflineBar.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import BaseButton from '@/components-base/BaseButton.vue'
import BaseInput from '@/components-base/BaseInput.vue'

/** 本地可编辑的识别条目（confidence 为 manual 表示用户手动补录） */
interface EditableItem {
  /** 食材名 */
  name: string
  /** 是否勾选（确认入库以勾选集为准） */
  checked: boolean
  /** 置信度（high 默认勾选 / low 需人工确认 / manual 手动补录） */
  confidence: 'high' | 'low' | 'manual'
}

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()
/** 食材 store（确认入库后写入已选） */
const ingredientsStore = useIngredientsStore()

/** 是否有有效交接数据（无 → 空态兜底） */
const hasResult = ref(false)
/** 是否降级（响应 degraded，顶部降级提示条） */
const degraded = ref(false)
/** 额度快照（响应 quota） */
const quota = ref<{ used: number; limit: number } | null>(null)
/** 本地可编辑条目列表 */
const items = ref<EditableItem[]>([])
/** 手动补录输入框内容 */
const manualName = ref('')
/** 确认入库请求进行中 */
const confirming = ref(false)
/** 确认入库错误文案（非空时页面内联错误态 + 可重试） */
const confirmError = ref('')

/** 已勾选条目 */
const checkedItems = computed(() => items.value.filter((it) => it.checked))
/** 已勾选数量 */
const checkedCount = computed(() => checkedItems.value.length)

/** 带原索引的条目视图（分组渲染用，避免模板里 indexOf 反查） */
interface IndexedItem {
  /** 条目 */
  item: EditableItem
  /** 原列表索引（toggle/remove 定位用） */
  index: number
}

/** 高置信条目（已为你勾选） */
const highEntries = computed<IndexedItem[]>(() =>
  items.value.map((item, index) => ({ item, index })).filter((e) => e.item.confidence === 'high'),
)
/** 低置信条目（需人工确认） */
const lowEntries = computed<IndexedItem[]>(() =>
  items.value.map((item, index) => ({ item, index })).filter((e) => e.item.confidence === 'low'),
)
/** 手动补录条目 */
const manualEntries = computed<IndexedItem[]>(() =>
  items.value.map((item, index) => ({ item, index })).filter((e) => e.item.confidence === 'manual'),
)

/**
 * 从响应初始化编辑列表：高置信默认勾选、低置信默认不勾（源码 handleUpload 语义）。
 * @param res 识别响应
 * @returns 无
 */
function initFromResponse(res: VisionRecognizeResponse): void {
  items.value = (res.recognized ?? []).map((r) => ({
    name: r.name,
    checked: r.confidence === 'high',
    confidence: r.confidence,
  }))
  degraded.value = res.degraded === true
  quota.value = res.quota ?? null
  hasResult.value = true
}

/**
 * chip 点击：翻转该条目勾选态（人工确认语义：勾选集 = 确认入库集合）。
 * @param index 条目在列表中的索引
 * @returns 无
 */
function toggleItem(index: number): void {
  const item = items.value[index]
  if (item) item.checked = !item.checked
}

/**
 * 删除条目：从本地编辑列表移除（不涉及后端）。
 * @param index 条目在列表中的索引
 * @returns 无
 */
function removeItem(index: number): void {
  items.value.splice(index, 1)
}

/**
 * 添加食材（本地补录）：输入非空且不与现有条目重名时追加，默认勾选。
 * @returns 无
 */
function addManual(): void {
  const name = manualName.value.trim()
  if (!name) {
    toastWarning('请输入食材名')
    return
  }
  if (items.value.some((it) => it.name === name)) {
    toastWarning('该食材已在列表中')
    return
  }
  items.value.push({ name, checked: true, confidence: 'manual' })
  manualName.value = ''
}

/**
 * 🔴 RL-5 确认入库：人工点击「确认无误」触发（无默认确认、不可跳过）。
 * postVisionConfirm(勾选名列表) → 成功后勾选食材并入 ingredients store 已选
 * （按名称/别名匹配食材库，对齐源码 onConfirm）→ 埋点 → 引导跳推荐列表。
 * @returns 无
 */
async function onConfirm(): Promise<void> {
  if (checkedCount.value === 0) {
    toastWarning('请至少勾选一样食材')
    return
  }
  if (confirming.value) return
  confirming.value = true
  confirmError.value = ''
  const names = checkedItems.value.map((it) => it.name)
  try {
    const res = await postVisionConfirm(names)
    // 勾选食材并入本地已选（名称/别名匹配，匹配不到的不进本地集合——源码语义）
    if (!ingredientsStore.list.length) {
      await ingredientsStore.loadIngredients()
    }
    for (const name of names) {
      const matched = ingredientsStore.list.find(
        (ing) => ing.name === name || (ing.aliases ?? []).includes(name),
      )
      if (matched && !ingredientsStore.selected[matched.id]) {
        ingredientsStore.toggle(matched)
      }
    }
    // 确认成功埋点（源码无识别正确性 correct 上报，不落 ingredient_recognize_correct）
    trackEvent('ingredient_recognize_result', { count: res.added ?? names.length })
    toastSuccess(`已把 ${res.added ?? names.length} 样食材加入已选`)
    // 交接数据已消费：清除，防止重进残留旧结果
    storageRemove(VISION_RESULT_KEY)
    // 引导跳推荐列表（已选 ≥1，推荐页守卫放行）
    goRoute(ROUTES.RECOMMEND_LIST)
  } catch (e) {
    confirmError.value = (e as { message?: string })?.message || '入库失败，请重试'
    toastError(confirmError.value)
  } finally {
    confirming.value = false
  }
}

/**
 * 重试确认（确认失败后的重试入口，复用 onConfirm 链路）。
 * @returns 无
 */
function retryConfirm(): void {
  void onConfirm()
}

/**
 * 空态行动：回拍照识别页重新采集。
 * @returns 无
 */
function goPhoto(): void {
  goRoute(ROUTES.RECOMMEND_PHOTO)
}

/**
 * 空态保底：改手选食材。
 * @returns 无
 */
function goManual(): void {
  goRoute(ROUTES.RECOMMEND_SELECT)
}

// onLoad：读取交接数据初始化（无数据 → 空态兜底）
onLoad(() => {
  const handoff = storageGet<VisionRecognizeResponse>(VISION_RESULT_KEY)
  if (handoff && typeof handoff === 'object' && Array.isArray(handoff.recognized)) {
    initFromResponse(handoff)
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

    <view class="recognize">
      <!-- 空态：无识别结果（交接丢失 / 直达深链） -->
      <EmptyState
        v-if="!hasResult"
        icon="🔍"
        title="没有识别结果"
        desc="先拍一张冰箱照片，或直接手选食材"
        action-text="去拍照识别"
        @action="goPhoto"
      >
        <!-- EmptyState 无次按钮位，保底入口单列 -->
      </EmptyState>
      <view v-if="!hasResult" class="recognize__manual-link" @click="goManual">
        <text class="recognize__manual-link-text">改为手选食材 →</text>
      </view>

      <template v-else>
        <!-- 降级提示条（degraded=true）：DEGRADED_BAR_TEXT 常量收口 -->
        <DegradedBar v-if="degraded" :text="DEGRADED_BAR_TEXT" />
        <!-- 降级补充警示（源码 degraded alert 文案口径） -->
        <view v-if="degraded" class="recognize__degraded-tip">
          <text class="recognize__degraded-tip-text">
            识别服务繁忙，本次结果可能不够准确，建议核对后再确认入库
          </text>
        </view>

        <!-- 额度行（MEMBER_QUOTA_LABEL 常量收口，口径与源码一致） -->
        <view v-if="quota" class="recognize__quota">
          <text class="recognize__quota-text">
            {{ MEMBER_QUOTA_LABEL }}：{{ quota.used }} / {{ quota.limit }}
          </text>
        </view>

        <!-- 高置信区（已为你勾选，可取消） -->
        <view v-if="highEntries.length > 0" class="recognize__section">
          <text class="recognize__section-title">识别到这些食材（已为你勾选）：</text>
          <view class="recognize__chips">
            <view
              v-for="e in highEntries"
              :key="e.item.name"
              class="recognize__chip"
              :class="{ 'is-active': e.item.checked }"
              @click="toggleItem(e.index)"
            >
              <text class="recognize__chip-name">{{ e.item.name }}</text>
              <text v-if="e.item.checked" class="recognize__chip-check">✓</text>
              <text class="recognize__chip-remove" @click.stop="removeItem(e.index)">×</text>
            </view>
          </view>
        </view>

        <!-- 低置信区（需人工确认） -->
        <view v-if="lowEntries.length > 0" class="recognize__section">
          <text class="recognize__section-title is-warning">这些不太确定，请你确认：</text>
          <view class="recognize__chips">
            <view
              v-for="e in lowEntries"
              :key="e.item.name"
              class="recognize__chip"
              :class="{ 'is-active': e.item.checked }"
              @click="toggleItem(e.index)"
            >
              <text class="recognize__chip-name">{{ e.item.name }}</text>
              <text v-if="e.item.checked" class="recognize__chip-check">✓</text>
              <text class="recognize__chip-remove" @click.stop="removeItem(e.index)">×</text>
            </view>
          </view>
        </view>

        <!-- 手动补录区（本地编辑） -->
        <view v-if="manualEntries.length > 0" class="recognize__section">
          <text class="recognize__section-title">手动添加：</text>
          <view class="recognize__chips">
            <view
              v-for="e in manualEntries"
              :key="e.item.name"
              class="recognize__chip is-active"
              @click="toggleItem(e.index)"
            >
              <text class="recognize__chip-name">{{ e.item.name }}</text>
              <text v-if="e.item.checked" class="recognize__chip-check">✓</text>
              <text class="recognize__chip-remove" @click.stop="removeItem(e.index)">×</text>
            </view>
          </view>
        </view>

        <!-- 添加食材输入行 -->
        <view class="recognize__add">
          <BaseInput v-model="manualName" class="recognize__add-input" placeholder="没认出来？手动补一个食材名" />
          <BaseButton size="md" type="default" @click="addManual">添加</BaseButton>
        </view>

        <!-- 空结果提示：全部删光后如实提示（可继续补录） -->
        <text v-if="items.length === 0" class="recognize__empty-tip">
          识别条目已清空，可手动添加或返回重新拍照
        </text>

        <!-- 确认失败错误态（内联 + 重试） -->
        <view v-if="confirmError" class="recognize__error">
          <text class="recognize__error-text">{{ confirmError }}</text>
          <view class="recognize__error-retry" @click="retryConfirm">
            <text class="recognize__error-retry-text">重试</text>
          </view>
        </view>

        <!-- 🔴 RL-5 确认入库：必须人工点击，无默认确认；无勾选禁用 -->
        <view class="recognize__confirm">
          <BaseButton
            block
            size="lg"
            :loading="confirming"
            :disabled="checkedCount === 0"
            @click="onConfirm"
          >
            确认无误（已选 {{ checkedCount }} 样）
          </BaseButton>
          <BaseButton block type="default" @click="goPhoto">重新拍照</BaseButton>
        </view>

        <DisclaimerBar scene="detail" />
      </template>
    </view>
  </view>
</template>

<style scoped lang="scss">
.recognize {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
}

.recognize__manual-link {
  display: flex;
  justify-content: center;
  min-height: var(--hit-min);
  align-items: center;
}

.recognize__manual-link-text {
  font-size: var(--font-size-sm);
  color: var(--color-primary);
}

.recognize__degraded-tip {
  margin-top: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-ctrl);
  background: var(--color-warning-bg);
}

.recognize__degraded-tip-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-warning);
  word-break: break-all;
}

.recognize__quota {
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
  margin-top: var(--space-sm);
}

.recognize__quota-text {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.recognize__section {
  margin-top: var(--space-md);
}

.recognize__section-title {
  display: block;
  margin-bottom: var(--space-sm);
  font-size: var(--font-size-base);
  color: var(--text-primary);

  &.is-warning {
    color: var(--color-warning);
    font-weight: 600;
  }
}

.recognize__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

/* chip：热区 ≥88rpx，选中主色描边 + ✓；× 删除热区独立（stop 冒泡） */
.recognize__chip {
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  gap: 8rpx;
  min-height: var(--hit-min);
  padding: 0 var(--space-md);
  border: 2rpx solid var(--border-color);
  border-radius: var(--radius-pill);
  background: var(--bg-card);

  &.is-active {
    border-color: var(--color-primary);
    background: var(--color-primary-weak);
  }
}

.recognize__chip-name {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
}

.recognize__chip-check {
  font-size: var(--font-size-sm);
  font-weight: 700;
  color: var(--color-primary);
}

.recognize__chip-remove {
  padding: 0 6rpx;
  font-size: var(--font-size-base);
  color: var(--text-tertiary);
}

.recognize__add {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-top: var(--space-md);
}

.recognize__add-input {
  flex: 1;
  min-width: 0;
}

.recognize__empty-tip {
  display: block;
  margin-top: var(--space-md);
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.recognize__error {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-top: var(--space-md);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-ctrl);
  background: var(--color-danger-bg);
}

.recognize__error-text {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-sm);
  color: var(--color-danger);
  word-break: break-all;
}

.recognize__error-retry {
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
  padding: 0 var(--space-sm);
}

.recognize__error-retry-text {
  font-size: var(--font-size-sm);
  color: var(--color-primary);
}

.recognize__confirm {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-top: var(--space-lg);
}
</style>
