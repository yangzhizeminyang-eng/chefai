<!--
  文件级注释：P-14 过敏原二次确认页（过敏原五处生效之四，M4 烹饪闭环安全闸）。
  自 web-stage1 烹饪发起语义迁移：进入烹饪前对「菜谱过敏原 × 家庭档案过敏原」做
  展示层预判并强制二次确认（预判仅供提示，最终以后端 createCookingSession 的
  allergen_conflict 判定为准——后端才是安全判定权威，前端预判不阻断「用户确认后继续」）。
  - onLoad options：recipe_id（必填）+ servings（可选，缺省取菜谱基准份数）；
  - 冲突计算（展示层预判）：
      ① code 级：detail.allergen_codes（GB 7718 八类）∩ 各成员 allergen_codes 并集；
      ② 文本级：成员 custom_allergens（八类之外自由文本）对菜谱食材名做包含匹配；
  - 「已知晓，继续烹饪」：storage 记忆 allergen_conflict_ack={recipe_id:true}
    （供 P-13 入口侧判断免二次弹本页；重新进入本页仍会确认，属展示层冗余保险）→
    createCookingSession（后端权威判定）→ rememberSessionRecipe（断点续做反查映射）→
    trackEvent('cook_start') → goRoute(COOK_GUIDE?session_id=)；
  - 「返回修改」：navigateBack 回上一页（推荐列表 / 菜谱详情）；
  - 五态：详情拉取中 SkeletonPage / 失败 ErrorState 重试 / 无冲突兜底提示（本页
    正常仅在有冲突时被 P-13 打开，无冲突到达视为兜底场景仍可继续）。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad } from '@dcloudio/uni-app'
import { createCookingSession, getRecipe } from '@/api/endpoints'
import type { ApiError, RecipeDetail } from '@shared/types'
import { useProfileStore } from '@/stores/profile'
import { rememberSessionRecipe } from '@/utils/offlineCache'
import { get as storageGet, set as storageSet } from '@/utils/storage'
import { goRoute, ROUTES } from '@/utils/routes'
import { toastError, toastWarning } from '@/utils/toast'
import { trackEvent, flushOnHide } from '@/utils/track'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import AllergenAlertBar from '@/components/AllergenAlertBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import ErrorState from '@/components/ErrorState.vue'
import BaseButton from '@/components-base/BaseButton.vue'

/** GB 7718 八类致敏原 code → 中文标签（对齐 profile/member-edit 选项口径，展示层专用） */
const ALLERGEN_LABELS: Record<string, string> = {
  gluten: '麸质',
  crustacean: '甲壳类',
  fish: '鱼类',
  egg: '蛋类',
  peanut: '花生',
  soybean: '大豆',
  milk: '乳制品',
  nuts: '坚果',
}

/** 过敏原确认记忆键（会话级确认标记：{ [recipe_id]: true }，供 P-13 入口侧免重复弹本页） */
const ACK_KEY = 'allergen_conflict_ack'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 家庭档案 store（family.members 过敏原档案数据源） */
const profile = useProfileStore()

/** 页面参数：菜谱 ID（onLoad 注入；null = 参数缺失错误态） */
const recipeId = ref<number | null>(null)
/** 页面参数：目标份数（可选；缺省取菜谱基准份数） */
const servings = ref<number | null>(null)

/** 菜谱详情（拉取成功后写入） */
const detail = ref<RecipeDetail | null>(null)
/** 加载中标记（SkeletonPage 数据源） */
const loading = ref(false)
/** 加载错误（归一化 ApiError；非空走 ErrorState） */
const error = ref<ApiError | null>(null)

/** 创建会话请求进行中（防连点） */
const creating = ref(false)

/** 冲突过敏原展示列表（code 级交集 + 自定义文本命中，预判语义见文件头注释） */
const conflictAllergens = ref<string[]>([])

/** 是否存在冲突（决定警示条与说明文案） */
const hasConflict = computed(() => conflictAllergens.value.length > 0)

/**
 * 归一化菜谱食材名列表（主料 + 辅料 + 调味料，供自定义过敏原文本包含匹配）。
 * @param d 菜谱详情
 * @returns 食材名数组（去空）
 */
function collectIngredientNames(d: RecipeDetail): string[] {
  return [...d.main_ingredients, ...d.side_ingredients, ...d.seasoning_ingredients]
    .map((item) => item.name ?? '')
    .filter((n) => n.length > 0)
}

/**
 * 计算「菜谱过敏原 × 家庭成员过敏原」展示层预判交集（函数）。
 * ① code 级：菜谱 allergen_codes 与全部成员 allergen_codes 并集的交集，转中文标签；
 * ② 文本级：成员 custom_allergens 文本被任一食材名包含（或反过来包含）即命中，
 *    保留用户原文展示。
 * @param d 菜谱详情（allergen_codes + 食材清单）
 * @returns 冲突过敏原展示文案数组（如 ['蛋类', '芒果']）
 * @throws 不抛出（family 未加载按空档案处理，交由后端判定兜底）
 */
function computeConflicts(d: RecipeDetail): string[] {
  const members = profile.family?.members ?? []
  if (members.length === 0) return []
  const result: string[] = []
  // ① code 级交集（八类，去重保序）
  const memberCodes = new Set<string>()
  for (const m of members) for (const c of m.allergen_codes ?? []) memberCodes.add(c)
  const seen = new Set<string>()
  for (const code of d.allergen_codes ?? []) {
    if (memberCodes.has(code) && !seen.has(code)) {
      seen.add(code)
      result.push(ALLERGEN_LABELS[code] ?? code)
    }
  }
  // ② 自定义过敏原文本 × 食材名包含匹配（八类之外，如「芒果」）
  const names = collectIngredientNames(d)
  for (const m of members) {
    for (const custom of m.custom_allergens ?? []) {
      const text = (custom ?? '').trim()
      if (!text) continue
      const hit = names.some((n) => n.includes(text) || text.includes(n))
      if (hit && !result.includes(text)) result.push(text)
    }
  }
  return result
}

/**
 * 拉取菜谱详情并计算过敏原冲突预判（函数）。
 * 家庭档案未加载时先拉档案（loadAll 内部已 ensureAnonymousId 前置）。
 * @returns 无
 * @throws 不抛出（错误写入 error 三态，页面走 ErrorState）
 */
async function load(): Promise<void> {
  if (recipeId.value == null) return
  loading.value = true
  error.value = null
  try {
    // 家庭档案就绪（NEW-01：请求前置匿名 ID；loadAll 三段并行，任一失败互不影响）
    if (!profile.family) await profile.loadAll()
    const d = await getRecipe(recipeId.value)
    detail.value = d
    if (servings.value == null && d.servings) servings.value = d.servings
    conflictAllergens.value = computeConflicts(d)
  } catch (e) {
    error.value = e as ApiError
  } finally {
    loading.value = false
  }
}

/**
 * 写过敏原确认记忆（allergen_conflict_ack 追加本菜谱标记，供入口侧免重复弹本页）。
 * @param rid 菜谱 ID
 * @returns 无
 * @throws 不抛出（storage 写失败静默，仅影响下次免确认体验）
 */
function rememberAck(rid: number): void {
  try {
    const prev = storageGet<Record<string, boolean>>(ACK_KEY, {}) ?? {}
    storageSet(ACK_KEY, { ...prev, [String(rid)]: true })
  } catch {
    // 静默：确认记忆失败不阻断烹饪流程
  }
}

/**
 * 「已知晓，继续烹饪」：写确认记忆 → 创建烹饪会话（后端权威过敏原判定）→
 * 写会话→菜谱映射（断点续做反查）→ 埋 cook_start → 跳烹饪引导页。
 * @returns 无
 * @throws 不抛出（创建失败 toast 提示，停留本页可重试）
 */
async function onProceed(): Promise<void> {
  if (recipeId.value == null || creating.value) return
  creating.value = true
  try {
    // 展示层确认记忆（可重进需再确认的场景由入口侧结合 P-13 逻辑决定）
    rememberAck(recipeId.value)
    // 份数兜底：参数未传时取菜谱基准份数（保证 createCookingSession 契约必填）
    const targetServings = servings.value && servings.value >= 1 ? servings.value : (detail.value?.servings ?? 1)
    const session = await createCookingSession({ recipe_id: recipeId.value, servings: targetServings })
    // 会话 → 菜谱映射（断点续做恢复失败时反查离线快照用，fire-and-forget）
    rememberSessionRecipe(session.id, recipeId.value)
    trackEvent('cook_start', { recipe_id: recipeId.value, servings: targetServings })
    goRoute(`${ROUTES.COOK_GUIDE}?session_id=${encodeURIComponent(session.id)}`)
  } catch (e) {
    const err = e as ApiError
    // 后端过敏原拦截（403/422 等）按业务文案提示；其余走归一化 message
    toastError(err.message || '创建烹饪会话失败，请重试')
  } finally {
    creating.value = false
  }
}

/**
 * 「返回修改」：返回上一页（推荐列表 / 菜谱详情），不创建会话。
 * @returns 无
 * @throws 不抛出（无栈可弹时系统自忽略）
 */
function onBack(): void {
  uni.navigateBack({ fail: () => {} })
}

/**
 * onLoad：解析 recipe_id / servings 参数并启动加载。
 * @param options 页面参数（recipe_id 必填，servings 可选）
 * @returns 无
 * @throws 不抛出（参数缺失停留错误态，页面提供返回按钮兜底）
 */
onLoad((options) => {
  const rawId = Number(options?.recipe_id)
  recipeId.value = Number.isFinite(rawId) && rawId > 0 ? rawId : null
  const rawServings = Number(options?.servings)
  servings.value = Number.isFinite(rawServings) && rawServings >= 1 ? rawServings : null
  if (recipeId.value == null) {
    toastWarning('缺少菜谱参数，请从菜谱页重新进入')
    return
  }
  void load()
})

// 页面隐匿时尽力上报缓冲埋点（统一页面约定）
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <!-- 加载态：详情拉取中骨架屏 -->
    <SkeletonPage v-if="loading" />

    <!-- 错误态：详情拉取失败，可重试 -->
    <ErrorState
      v-else-if="error"
      kind="server"
      detail="菜谱信息拉取失败，无法进行过敏原比对"
      @retry="load"
    />

    <!-- 参数缺失兜底态 -->
    <view v-else-if="recipeId == null" class="allergen-confirm">
      <text class="allergen-confirm__hint">缺少菜谱参数，请从菜谱页重新进入</text>
      <BaseButton block @click="onBack">返回</BaseButton>
    </view>

    <!-- 主流程：冲突展示 + 双按钮 -->
    <view v-else class="allergen-confirm">
      <!-- 过敏原警示条（冲突过敏原；空数组组件不渲染） -->
      <AllergenAlertBar :allergens="conflictAllergens" />

      <!-- 说明区 -->
      <view class="allergen-confirm__card">
        <text class="allergen-confirm__title">{{
          hasConflict ? '以下食材与您的过敏原档案存在冲突' : '未发现与家庭档案冲突的过敏原'
        }}</text>
        <text class="allergen-confirm__desc">
          {{
            hasConflict
              ? '为保障安全，请确认是否继续烹饪；如成员出现不适请立即停止食用。最终判定以后端创建会话时的检查结果为准。'
              : '家庭档案中未匹配到与本菜谱相关的过敏原，可放心继续。最终判定以后端创建会话时的检查结果为准。'
          }}
        </text>
      </view>

      <!-- 操作区：大热区双按钮 -->
      <view class="allergen-confirm__actions">
        <BaseButton block size="lg" :loading="creating" @click="onProceed">已知晓，继续烹饪</BaseButton>
        <BaseButton block size="lg" type="default" :disabled="creating" @click="onBack">返回修改</BaseButton>
      </view>
    </view>
  </view>
</template>

<style scoped lang="scss">
.allergen-confirm {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-md);
  padding-bottom: calc(var(--space-xl) + env(safe-area-inset-bottom));
}

.allergen-confirm__card {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  border: 1rpx solid var(--border-color);
}

.allergen-confirm__title {
  font-size: var(--font-size-md);
  font-weight: 600;
  line-height: 1.5;
  color: var(--text-primary);
}

.allergen-confirm__desc {
  font-size: var(--font-size-sm);
  line-height: 1.7;
  color: var(--text-secondary);
}

.allergen-confirm__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-top: var(--space-md);
}

.allergen-confirm__hint {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}
</style>
