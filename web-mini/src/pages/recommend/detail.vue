<!--
  文件级注释：P-13 菜谱详情页（W-03；pages/recommend/detail）。
  自 web-stage1/src/views/RecipeDetailView.vue（739 行）迁移，语义对齐说明：
  - onLoad options.recipe_id → endpoints.getRecipe(id)；无 recipe_id（深链兜底）→
    EmptyState + 回首页；404 → EmptyState「菜谱不存在」；加载失败 ErrorState retry；
  - 份数切换：BasePicker 1~8 份，变更后重拉 getRecipe(id, servings)（源码语义：后端按
    份数重算用量；快速变更以请求序号守卫丢弃过期响应）；
  - 结构：标题 + 封面 RecipeCover lg + 元信息（时长/份量/难度/热量）+ 过敏原警示条
    AllergenAlertBar 常驻顶部（allergens 来自详情 allergen_codes，过敏原五处生效之二）
    + 食材清单三段用量表（formatAmountText，内部复用 @shared/utils formatAmount，
    spoon 模式下 ml 类换算勺/茶匙）+ 步骤列表（amount_hint 按 scaleStepHint 份数缩放）
    + 营养入口 BaseCell（→ NUTRITION_SUMMARY + '?recipe_id='）+ 图片来源标注行
    （IMAGE_SOURCE_NOTE，RL-19）+ DisclaimerBar scene="detail"（免责六处之二）
    + 底部固定「开始烹饪」；
  - 开始烹饪链路：过敏原交集展示层预判（详情 allergen_codes ∩ 家庭档案全成员
    allergen_codes 并集——阶段一为后端 allergen_conflict 判定 + 二次确认弹窗，阶段二
    前端交集为展示层预判，最终以后端 allergen_conflict 为准；档案加载失败视为无法预判，
    直接创建会话交由后端判定）→ 有交集跳 COOK_ALLERGEN_CONFIRM + '?recipe_id='；
    无交集直接 createCookingSession（cooking store startSession 承接：会话/步骤快照/
    本地缓存一次落位）→ trackEvent('cook_start') → 跳 COOK_GUIDE + '?session_id='；
    响应仍带 allergen_conflict（预判漏网）→ 同样转过敏原确认页；
  - 详情缓存：进入成功后把步骤写入 offlineCache（saveRecipeSnapshot，供 P-15 离线）；
  - 分享：onShareAppMessage 用 platform/share.buildRecipeSharePayload（仅菜名/路径/封面，
    不携带健康画像）；onShareTimeline 返回 query 同 path；
  - 埋点：recipe_detail_view（onLoad）、cook_start（会话创建成功时）。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad, onShareAppMessage, onShareTimeline } from '@dcloudio/uni-app'
import { DISCLAIMER_SHARE, IMAGE_SOURCE_NOTE } from '@shared/constants'
import type { ApiError, RecipeDetail } from '@shared/types'
import { allergenLabel, formatAmountText, scaleStepHint } from '@shared/utils'
import { getRecipe } from '@/api/endpoints'
import { useProfileStore } from '@/stores/profile'
import { useCookingStore } from '@/stores/cooking'
import { useMeStore } from '@/stores/me'
import { saveRecipeSnapshot } from '@/utils/offlineCache'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide, trackEvent } from '@/utils/track'
import { toastError } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import { buildRecipeSharePayload, drawSharePoster } from '@/platform/share'
import AllergenAlertBar from '@/components/AllergenAlertBar.vue'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import RecipeCover from '@/components/RecipeCover.vue'
import BaseCell from '@/components-base/BaseCell.vue'
import BasePicker from '@/components-base/BasePicker.vue'
import BaseTag from '@/components-base/BaseTag.vue'
import BaseButton from '@/components-base/BaseButton.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()
/** 家庭档案 store（过敏原交集预判数据源） */
const profileStore = useProfileStore()
/** 烹饪 store（startSession：创建会话 + 步骤快照 + 本地缓存） */
const cookingStore = useCookingStore()
/** 个人中心 store（计量单位设置，DEF-09） */
const meStore = useMeStore()

/** 菜谱详情 */
const detail = ref<RecipeDetail | null>(null)
/** 详情加载中 */
const loading = ref(false)
/** 详情加载错误（code=404 → 菜谱不存在态） */
const error = ref<ApiError | null>(null)
/** 当前份数（详情加载后同步为菜谱基准份数） */
const servings = ref(1)
/** 菜谱基准份数（首次加载时的 servings，作为步骤提示缩放系数的分母；缩放变更不改动） */
const baseServings = ref(1)
/** 份数重拉进行中（内容区弱化提示） */
const scaling = ref(false)
/** 请求序号（份数快速变更时丢弃过期响应，对齐源码 reqSeq） */
let reqSeq = 0
/** 开始烹饪请求进行中 */
const starting = ref(false)

/** 是否 404（菜谱不存在） */
const isNotFound = computed(() => error.value?.code === 404)
/** 是否无 recipe_id（深链兜底空态） */
const noRecipeId = ref(false)
/** 当前菜谱 ID（onLoad 存档，404/错误重试复用） */
const recipeId = ref('')

/** 份数选择器选项（1~8，对齐源码 el-input-number min/max） */
const servingsOptions = computed(() =>
  Array.from({ length: 8 }, (_, i) => ({ label: `${i + 1} 份`, value: i + 1 })),
)

/** 计量单位展示模式（DEF-09：用户设置；未加载默认 gram） */
const unitMode = computed(() => meStore.settings?.unit ?? 'gram')

/** 难度编码 → 中文标签（对齐源码 easy/medium/hard 口径） */
const difficultyText = computed(() => {
  const d = detail.value?.difficulty
  return d === 'easy' ? '简单' : d === 'medium' ? '中等' : '较难'
})

/** 详情页过敏原中文名列表（@shared/utils allergenLabel 映射；未知编码原样） */
const allergenNames = computed(() =>
  (detail.value?.allergen_codes ?? []).map((code) => allergenLabel(code)),
)

/**
 * 步骤用量提示缩放系数（当前份数 / 菜谱基准份数；基准非法回退 1 = 不缩放）。
 * @returns 缩放系数
 */
const hintFactor = computed<number>(() => {
  if (!baseServings.value || baseServings.value < 1) return 1
  return servings.value / baseServings.value
})

/** 食材清单三段配置（key 对应 RecipeDetail 字段，对齐源码 INGREDIENT_SECTIONS） */
const INGREDIENT_SECTIONS = [
  { key: 'main_ingredients', title: '主料' },
  { key: 'side_ingredients', title: '辅料' },
  { key: 'seasoning_ingredients', title: '调味料' },
] as const

/**
 * 图片来源标注文案（RL-19）：后端提供 cover_image_source 时优先；否则有真实图时
 * 用 IMAGE_SOURCE_NOTE 常量；纯占位封面不渲染来源行。
 * @returns 标注文案；无图返回空串（不渲染）
 */
const sourceNote = computed(() => {
  if (detail.value?.cover_image_source) return `图片来源：${detail.value.cover_image_source}`
  return detail.value?.cover_image_url ? IMAGE_SOURCE_NOTE : ''
})

/**
 * 秒数转可读时长（步骤/总耗时展示，对齐源码 formatDuration）。
 * @param sec 耗时秒数（0 表示无需等待）
 * @returns 可读文案
 */
function formatDuration(sec: number): string {
  if (!sec || sec <= 0) return '—'
  if (sec < 60) return `${sec} 秒`
  return `${Math.round(sec / 60)} 分钟`
}

/**
 * 食材行用量展示（formatAmountText：spoon 模式下 ml 类片段换算勺/茶匙，
 * 内部复用 @shared/utils formatAmount；gram/milliliter 模式原样展示）。
 * @param amount 后端拼好的用量串（如「200g」「2 勺」）
 * @returns 展示文案
 */
function amountDisplay(amount: string): string {
  return formatAmountText(amount, unitMode.value)
}

/**
 * 步骤用量提示按份数缩放（M3/R3 语义：本步用量随份数变化）。
 * @param hint 原始用量提示
 * @returns 缩放后的提示文案
 */
function stepHint(hint: string | null | undefined): string {
  return scaleStepHint(hint, hintFactor.value)
}

/**
 * 拉取菜谱详情（onLoad / 404 重试共用）。
 * 成功后：同步份数基准 + 落离线快照（saveRecipeSnapshot，供 P-15 离线）。
 * @param id 菜谱 ID
 * @returns 无
 */
async function loadDetail(id: string): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const res = await getRecipe(id)
    detail.value = res
    // 同步菜谱基准份数（不触发缩放重算）；该值同时作为步骤提示缩放的分母
    servings.value = res.servings || 1
    baseServings.value = res.servings || 1
    // 详情缓存：步骤写入离线快照（fire-and-forget，失败静默不影响在线浏览）
    void saveRecipeSnapshot({
      recipe_id: res.id,
      title: res.title,
      steps: res.steps,
      base_servings: baseServings.value,
    })
  } catch (e) {
    error.value = e as ApiError
    detail.value = null
  } finally {
    loading.value = false
  }
}

/**
 * 份数变更：重拉详情（后端按份数重算用量）；快速变更以序号守卫丢弃过期响应。
 * @param val 新份数（BasePicker 回传 string | number）
 * @returns 无
 */
async function onServingsChange(val: string | number): Promise<void> {
  const next = Number(val)
  if (!detail.value || !Number.isInteger(next) || next < 1 || next > 8) return
  const id = detail.value.id
  reqSeq += 1
  const seq = reqSeq
  scaling.value = true
  try {
    const nextDetail = await getRecipe(id, next)
    if (seq !== reqSeq) return
    detail.value = nextDetail
    servings.value = nextDetail.servings || next
  } catch {
    // 重拉失败保持当前详情（份数不变），不打断浏览（对齐源码 toast 降级语义）
  } finally {
    if (seq === reqSeq) scaling.value = false
  }
}

/**
 * 营养入口 → 营养总览页（携带 recipe_id）。
 * @returns 无
 */
function goNutrition(): void {
  if (!detail.value) return
  goRoute(`${ROUTES.NUTRITION_SUMMARY}?recipe_id=${detail.value.id}`)
}

/**
 * 家庭档案全成员过敏原编码并集（去重；档案缺失返回空数组 = 无法预判）。
 * @returns 过敏原编码并集
 */
function familyAllergenCodes(): string[] {
  const set = new Set<string>()
  for (const m of profileStore.family?.members ?? []) {
    for (const code of m.allergen_codes ?? []) set.add(code)
  }
  return [...set]
}

/**
 * 过敏原交集展示层预判（⚠️ 非最终判定）：详情 allergen_codes ∩ 家庭成员过敏原并集。
 * 注释声明：本交集计算为展示层预判（决定是否先进入过敏原确认页），
 * 最终是否冲突以后端 createCookingSession 响应的 allergen_conflict 为准。
 * @returns 交集编码列表（空数组 = 预判无冲突）
 */
function intersectionWithFamily(): string[] {
  const codes = detail.value?.allergen_codes ?? []
  const familySet = new Set(familyAllergenCodes())
  return codes.filter((c) => familySet.has(c))
}

/**
 * 开始烹饪（底部固定主操作）：
 * ① 档案未加载先 loadAll()（预判数据前提；失败置 null 走无法预判分支）；
 * ② 交集非空（展示层预判）→ 跳 COOK_ALLERGEN_CONFIRM + '?recipe_id='（确认页内完成
 *    会话创建，最终以后端判定为准）；
 * ③ 无交集 → createCookingSession（cooking store startSession 承接）→ cook_start 埋点
 *    → 跳 COOK_GUIDE + '?session_id='；响应仍带 allergen_conflict（预判漏网）→
 *    同样转过敏原确认页。
 * @returns 无
 */
async function startCooking(): Promise<void> {
  if (!detail.value || starting.value) return
  starting.value = true
  try {
    // 档案懒加载：预判依赖家庭档案（失败时 family 为 null，视为无法预判）
    if (!profileStore.family) {
      await profileStore.loadAll()
    }
    // 展示层预判：有交集先确认（后端 allergen_conflict 仍为最终判定）
    if (profileStore.family && intersectionWithFamily().length > 0) {
      goRoute(`${ROUTES.COOK_ALLERGEN_CONFIRM}?recipe_id=${detail.value.id}`)
      return
    }
    // 直接创建会话（endpoints.createCookingSession 由 store 承接：会话/步骤/缓存落位）
    const session = await cookingStore.startSession(
      detail.value.id,
      servings.value,
      detail.value.steps,
      baseServings.value,
    )
    trackEvent('cook_start', { recipe_id: detail.value.id })
    if (session.allergen_conflict && session.allergen_conflict.length > 0) {
      // 预判漏网（后端判定有冲突）：转过敏原确认页二次确认
      goRoute(`${ROUTES.COOK_ALLERGEN_CONFIRM}?recipe_id=${detail.value.id}`)
      return
    }
    goRoute(`${ROUTES.COOK_GUIDE}?session_id=${session.id}`)
  } catch {
    // 创建失败：保持页面可重试（startSession 内部已写 error，此处统一 toast 提示）
    toastError('开始烹饪失败，请重试')
  } finally {
    starting.value = false
  }
}

/**
 * 404 / 无 recipe_id 的返回动作。
 * @returns 无
 */
function goHome(): void {
  goRoute(ROUTES.HOME)
}

// 转发：菜名 + 详情路径 + 封面（buildRecipeSharePayload，不含健康画像）
onShareAppMessage(() => {
  const d = detail.value
  return buildRecipeSharePayload({
    id: d?.id ?? 0,
    name: d?.title ?? 'AI 厨娘菜谱',
    cover_url: d?.cover_image_url ?? undefined,
  })
})

// 朋友圈分享：query 与 onShareAppMessage path 参数一致（recipe_id）
onShareTimeline(() => {
  const d = detail.value
  return {
    title: d?.title ?? 'AI 厨娘菜谱',
    query: d ? `recipe_id=${d.id}` : '',
    imageUrl: d?.cover_image_url ?? undefined,
  }
})

/** 分享海报保存进行中（按钮转圈/禁用） */
const posterSaving = ref(false)

/** 分享海报离屏 canvas 节点 id（与模板 <canvas canvas-id> 对应） */
const SHARE_CANVAS_ID = 'rdetail-share'

/**
 * 生成并保存分享海报（G-02 分享图免责附着）：
 * drawSharePoster 绘制（底部固定免责行传 DISCLAIMER_SHARE 共享常量）
 * → canvasToTempFilePath 导出临时图 → saveImageToPhotosAlbum 存相册。
 * 仅含菜名/封面/免责行公开信息，不携带健康画像（RL 隐私红线）。
 * @returns 无
 * @throws 不抛出（绘制失败 / 导出失败 / 相册授权拒绝均内部捕获转提示或 openSetting 引导）
 */
async function onSavePoster(): Promise<void> {
  const d = detail.value
  if (!d || posterSaving.value) return
  posterSaving.value = true
  try {
    const drawn = await drawSharePoster(
      SHARE_CANVAS_ID,
      { id: d.id, name: d.title, cover_url: d.cover_image_url ?? undefined },
      DISCLAIMER_SHARE,
    )
    if (!drawn) {
      uni.showToast({ title: '海报生成失败，请重试', icon: 'none' })
      return
    }
    const filePath = await new Promise<string>((resolve, reject) => {
      uni.canvasToTempFilePath({
        canvasId: SHARE_CANVAS_ID,
        success: (res) => resolve(res.tempFilePath),
        fail: (err) => reject(err),
      })
    })
    await new Promise<void>((resolve, reject) => {
      uni.saveImageToPhotosAlbum({
        filePath,
        success: () => resolve(),
        fail: (err) => reject(err),
      })
    })
    uni.showToast({ title: '分享图已存入相册', icon: 'success' })
  } catch (err) {
    // 相册授权被拒：弹窗引导去设置开启「添加到相册」（拒绝后重试入口不变）
    const errMsg = typeof err === 'object' && err !== null && 'errMsg' in err ? String((err as { errMsg?: string }).errMsg) : ''
    if (/auth|deny|authorize/i.test(errMsg)) {
      uni.showModal({
        title: '需要相册权限',
        content: '保存分享图需开启「添加到相册」权限，可在设置中开启',
        confirmText: '去设置',
        success: (res) => {
          if (res.confirm) uni.openSetting({})
        },
      })
    } else {
      uni.showToast({ title: '保存失败，请重试', icon: 'none' })
    }
  } finally {
    posterSaving.value = false
  }
}

// onLoad：深链兜底判定 + 详情加载 + 埋点 + 设置预取（计量单位）
onLoad((options) => {
  const rawId = typeof options?.recipe_id === 'string' ? options.recipe_id.trim() : ''
  trackEvent('recipe_detail_view', rawId ? { recipe_id: rawId } : undefined)
  if (!rawId || Number.isNaN(Number(rawId))) {
    noRecipeId.value = true
    return
  }
  recipeId.value = rawId
  void loadDetail(rawId)
  // 计量单位设置预取（失败静默，unitMode 兜底 gram）
  void meStore.loadSettings()
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

    <!-- 深链兜底：无 recipe_id → EmptyState + 回首页 -->
    <EmptyState
      v-if="noRecipeId"
      icon="🔗"
      title="缺少菜谱信息"
      desc="分享链接可能不完整，回首页重新挑选吧"
      action-text="回首页"
      @action="goHome"
    />

    <!-- 加载态：详情骨架 -->
    <template v-else-if="loading">
      <view class="rdetail">
        <SkeletonPage type="detail" :rows="6" />
      </view>
    </template>

    <!-- 空态（404）：菜谱不存在 -->
    <EmptyState
      v-else-if="isNotFound"
      icon="🍽️"
      title="菜谱不存在"
      desc="该菜谱可能已下架，回首页看看别的吧"
      action-text="回首页"
      @action="goHome"
    />

    <!-- 异常态：错误 + 重试 -->
    <view v-else-if="error" class="rdetail">
      <ErrorState kind="server" :detail="error.message" @retry="loadDetail(recipeId)" />
    </view>

    <template v-else-if="detail">
      <view class="rdetail" :class="{ 'is-scaling': scaling }">
        <!-- ① 过敏原警示条：常驻顶部（allergens 来自详情，无过敏原组件不渲染） -->
        <AllergenAlertBar :allergens="allergenNames" />

        <!-- ①.5 成品图：RecipeCover lg（无图/失败回落占位封面，绝不裂图） -->
        <RecipeCover
          class="rdetail__cover"
          :name="detail.title"
          :cover-url="detail.cover_image_url ?? ''"
          :palette-seed="String(detail.id)"
          size="lg"
        />
        <!-- 图片来源标注行（RL-19）：有真实图才渲染 -->
        <text v-if="sourceNote" class="rdetail__source-note">{{ sourceNote }}</text>

        <!-- ② 头部：菜名 + 简介 + 元信息 + 份数切换 -->
        <view class="rdetail__head">
          <text class="rdetail__title">{{ detail.title }}</text>
          <text v-if="detail.description" class="rdetail__desc">{{ detail.description }}</text>
          <view class="rdetail__meta">
            <BaseTag :text="difficultyText" kind="info" />
            <text class="rdetail__meta-item">⏱ 约 {{ detail.time_minutes }} 分钟</text>
            <text class="rdetail__meta-item">
              🔥 {{ detail.calories_kcal != null ? `${detail.calories_kcal} kcal/份` : '热量未纳入统计' }}
            </text>
          </view>
          <view class="rdetail__servings">
            <text class="rdetail__servings-label">份数</text>
            <BasePicker
              :model-value="servings"
              :options="servingsOptions"
              placeholder="选择份数"
              @update:model-value="onServingsChange"
            />
          </view>
        </view>

        <!-- ③ 食材清单三段（主料/辅料/调味）+ 用量展示 -->
        <text class="rdetail__section-title">食材清单</text>
        <text class="rdetail__amount-note">用量参照：1 勺 ≈ 15ml；用量随份数自动缩放。</text>
        <view v-for="section in INGREDIENT_SECTIONS" :key="section.key" class="rdetail__ing-section">
          <text class="rdetail__sub-title">{{ section.title }}</text>
          <view v-for="row in detail[section.key]" :key="row.name" class="rdetail__ing-row">
            <text class="rdetail__ing-name">{{ row.name }}</text>
            <text class="rdetail__ing-amount">{{ amountDisplay(row.amount) }}</text>
            <view v-if="row.allergens && row.allergens.length > 0" class="rdetail__ing-allergens">
              <BaseTag v-for="code in row.allergens" :key="code" :text="allergenLabel(code)" kind="danger" />
            </view>
          </view>
          <text v-if="detail[section.key].length === 0" class="rdetail__muted">
            暂无{{ section.title }}
          </text>
        </view>

        <!-- 设备要求 -->
        <text class="rdetail__section-title">设备要求</text>
        <view class="rdetail__equip">
          <template v-if="detail.equipment.length > 0">
            <BaseTag v-for="eq in detail.equipment" :key="eq" :text="eq" kind="neutral" />
          </template>
          <text v-else class="rdetail__muted">无特殊设备要求</text>
        </view>

        <!-- ④ 步骤列表 -->
        <text class="rdetail__section-title">做法步骤</text>
        <view v-for="step in detail.steps" :key="step.no" class="rdetail__step">
          <view class="rdetail__step-head">
            <view class="rdetail__step-no">
              <text class="rdetail__step-no-text">{{ step.no }}</text>
            </view>
            <text class="rdetail__step-duration">第 {{ step.no }} 步 · {{ formatDuration(step.duration_sec) }}</text>
          </view>
          <text class="rdetail__step-desc">{{ step.description }}</text>
          <text v-if="step.amount_hint" class="rdetail__step-hint">用量提示：{{ stepHint(step.amount_hint) }}</text>
          <text v-if="step.tips" class="rdetail__step-tip">要点：{{ step.tips }}</text>
          <text v-if="step.rescue" class="rdetail__step-tip">失败补救：{{ step.rescue }}</text>
        </view>

        <!-- 替代食材 / 小贴士 -->
        <template v-if="detail.substitutes.length > 0">
          <text class="rdetail__section-title">替代食材</text>
          <text v-for="(sub, i) in detail.substitutes" :key="i" class="rdetail__plain-line">· {{ sub }}</text>
        </template>
        <template v-if="detail.tips.length > 0">
          <text class="rdetail__section-title">小贴士</text>
          <text v-for="(tip, i) in detail.tips" :key="i" class="rdetail__plain-line">· {{ tip }}</text>
        </template>

        <!-- ⑤ 营养入口：BaseCell → 营养总览（携带 recipe_id） -->
        <view class="rdetail__nutrition">
          <BaseCell title="营养估算" desc="五大营养素与未纳入统计项" arrow @click="goNutrition" />
        </view>

        <!-- ⑥ 菜谱来源标注 -->
        <text class="rdetail__source-line">菜谱来源：{{ detail.source_label }}</text>

        <DisclaimerBar scene="detail" />
      </view>

      <!-- ⑦ 底部固定条：分享图（canvas 海报含免责行）+ 开始烹饪（starting 转圈禁用） -->
      <view class="rdetail__footer">
        <BaseButton
          class="rdetail__footer-btn rdetail__footer-btn--poster"
          size="lg"
          type="default"
          :loading="posterSaving"
          @click="onSavePoster"
        >
          分享图
        </BaseButton>
        <BaseButton
          class="rdetail__footer-btn"
          size="lg"
          :loading="starting"
          @click="startCooking"
        >
          开始烹饪
        </BaseButton>
      </view>

      <!-- 分享海报离屏画布：仅点「分享图」时绘制（drawSharePoster 含固定免责行） -->
      <canvas canvas-id="rdetail-share" class="rdetail__share-canvas" />
    </template>
  </view>
</template>

<style scoped lang="scss">
.rdetail {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
  /* 底部固定条占位 */
  padding-bottom: 180rpx;

  /* 份数重拉中弱化提示（不整页遮挡） */
  &.is-scaling {
    opacity: 0.7;
  }
}

.rdetail__cover {
  margin-top: var(--space-sm);
}

.rdetail__source-note {
  display: block;
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.rdetail__head {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-top: var(--space-md);
}

.rdetail__title {
  font-size: 40rpx;
  font-weight: 700;
  line-height: 1.4;
  color: var(--text-primary);
}

.rdetail__desc {
  font-size: var(--font-size-sm);
  line-height: 1.7;
  color: var(--text-secondary);
}

.rdetail__meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-md);
}

.rdetail__meta-item {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.rdetail__servings {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-ctrl);
  background: var(--color-info-bg);
}

.rdetail__servings-label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.rdetail__section-title {
  display: block;
  margin: var(--space-lg) 0 var(--space-sm);
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.rdetail__amount-note {
  display: block;
  margin-bottom: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.rdetail__sub-title {
  display: block;
  margin: var(--space-sm) 0;
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-secondary);
}

.rdetail__ing-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-sm);
  min-height: var(--hit-min);
  padding: var(--space-xs) 0;
  border-bottom: 1rpx solid var(--divider);
}

.rdetail__ing-name {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
}

.rdetail__ing-amount {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.rdetail__ing-allergens {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
}

.rdetail__muted {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.rdetail__equip {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-xs);
}

/* ── 步骤 ── */
.rdetail__step {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-sm) 0;
  border-bottom: 1rpx solid var(--divider);
}

.rdetail__step-head {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.rdetail__step-no {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44rpx;
  height: 44rpx;
  border-radius: var(--radius-pill);
  background: var(--color-primary);
}

.rdetail__step-no-text {
  font-size: var(--font-size-sm);
  font-weight: 700;
  color: var(--text-inverse);
}

.rdetail__step-duration {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.rdetail__step-desc {
  font-size: var(--font-size-base);
  line-height: 1.7;
  color: var(--text-primary);
}

.rdetail__step-hint {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-warning);
  word-break: break-all;
}

.rdetail__step-tip {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-tertiary);
  word-break: break-all;
}

.rdetail__plain-line {
  display: block;
  padding: var(--space-xs) 0;
  font-size: var(--font-size-sm);
  line-height: 1.7;
  color: var(--text-primary);
  word-break: break-all;
}

.rdetail__nutrition {
  margin-top: var(--space-lg);
  border-radius: var(--radius-card);
  overflow: hidden;
}

.rdetail__source-line {
  display: block;
  margin-top: var(--space-md);
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* ── 底部固定条 ── */
.rdetail__footer {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  box-sizing: border-box;
  display: flex;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--bg-card);
  border-top: 1rpx solid var(--divider);
}

.rdetail__footer-btn {
  flex: 1;
  width: auto;
}

/* 分享图次级按钮：固定窄宽，让主操作占主导 */
.rdetail__footer-btn--poster {
  flex: 0 0 200rpx;
}

/* 分享海报离屏画布：移出可视区（旧版 canvas 不支持 display:none），尺寸与绘制定版 320x420 一致 */
.rdetail__share-canvas {
  position: fixed;
  left: -9999px;
  top: 0;
  width: 320px;
  height: 420px;
}
</style>
