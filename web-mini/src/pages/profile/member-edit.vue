<!--
  文件级注释：P-03 家庭成员编辑页（新增 / 编辑双模式，onLoad options.id 区分）。
  - 表单字段对齐 FamilyMember 契约：姓名（必填）/ 关系（BasePicker）/ GB 7718 八类过敏原
    多选 / 自定义过敏原（输入添加 + 标签可删）/ 暂无已知过敏原（互斥清空）/
    口味三档（辣咸甜，各 0~2）/ 忌口（预置 + 自定义）/ 特殊饮食 6 类 / 特殊人群 5 类；
  - RL-14 PIPL 单独同意：首次填写过敏原（allergen_codes 或 custom_allergens 非空）且
    未同意 → 跳 P-00b CONSENT?scene=allergen；监听 uni.$on('aicook:consent-sensitive')
    同意后续跑保存；返回无事件（暂不同意 / 中途退出）→ 中断并提示；
    未填过敏原直接保存；
  - 保存调 profile.addMember / updateMember（内部 ensureAnonReady 防孤儿用户）；异常 toast。
-->
<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import type { ApiError, FamilyMember } from '@shared/types'
import { useProfileStore } from '@/stores/profile'
import { ROUTES } from '@/utils/routes'
import { flushOnHide } from '@/utils/track'
import { toastSuccess, toastWarning, toastInfo, toastError } from '@/utils/toast'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import BaseInput from '@/components-base/BaseInput.vue'
import BasePicker from '@/components-base/BasePicker.vue'
import BaseButton from '@/components-base/BaseButton.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 档案 store（sensitiveConsented / addMember / updateMember / saving） */
const profile = useProfileStore()

/* ── 选项常量（对齐 web-stage1 ProfileView 与后端白名单） ── */

/** GB 7718 八类致敏原选项（code + 中文标签） */
const ALLERGEN_OPTIONS: Array<{ code: string; label: string }> = [
  { code: 'gluten', label: '麸质' },
  { code: 'crustacean', label: '甲壳类' },
  { code: 'fish', label: '鱼类' },
  { code: 'egg', label: '蛋类' },
  { code: 'peanut', label: '花生' },
  { code: 'soybean', label: '大豆' },
  { code: 'milk', label: '乳制品' },
  { code: 'nuts', label: '坚果' },
]

/** 家庭关系选项（BasePicker） */
const RELATION_OPTIONS = ['本人', '配偶', '孩子', '父母', '其他'].map((r) => ({ label: r, value: r }))

/** 口味三档选项（0 清淡 / 1 适中 / 2 嗜好，BasePicker） */
const TASTE_OPTIONS = [
  { label: '清淡', value: 0 },
  { label: '适中', value: 1 },
  { label: '嗜好', value: 2 },
]

/** 忌口预置选项 */
const DIETARY_PRESETS = ['香菜', '内脏', '肥肉', '葱', '姜', '蒜', '辣椒', '生食']

/** 特殊饮食 6 类 */
const SPECIAL_DIET_OPTIONS = ['素食', '纯素', '清真', '低 GI', '生酮', '无麸质']

/** 特殊人群 5 类 */
const SPECIAL_POPULATION_OPTIONS = ['孕期', '哺乳期', '婴幼儿辅食', '老年人', '慢病人群']

/* ── 页面状态 ── */

/** 正在编辑的成员 ID（null = 新增模式） */
const editingId = ref<number | null>(null)

/** 自定义过敏原输入缓冲 */
const customAllergenInput = ref('')

/** 自定义忌口输入缓冲 */
const customRestrictionInput = ref('')

/** 成员表单（新增缺省值与源码 openCreate 一致） */
const memberForm = reactive({
  name: '',
  relation: '本人',
  allergen_codes: [] as string[],
  custom_allergens: [] as string[],
  no_known_allergen: false,
  taste_spicy: 1,
  taste_salt: 1,
  taste_sweet: 1,
  dietary_restrictions: [] as string[],
  special_diet: [] as string[],
  special_population: [] as string[],
})

/** 过敏原是否已实质填写（八类或自定义任一非空） */
const allergenFilled = computed(
  () => memberForm.allergen_codes.length > 0 || memberForm.custom_allergens.length > 0,
)

/** 保存按钮可用性：姓名非空 +（过敏原三选一：填了 / 勾暂无） */
const canSave = computed(
  () => memberForm.name.trim().length > 0 && (allergenFilled.value || memberForm.no_known_allergen),
)

/** PIPL 同意等待器（非 null 表示正在等 P-00b 返回结果；onShow 兜底 resolve(false)） */
let consentWaiter: ((agreed: boolean) => void) | null = null

/**
 * 切换过敏原多选 tag。
 * @param code 致敏原编码
 * @returns 无
 */
function toggleAllergen(code: string): void {
  memberForm.allergen_codes = memberForm.allergen_codes.includes(code)
    ? memberForm.allergen_codes.filter((c) => c !== code)
    : [...memberForm.allergen_codes, code]
}

/**
 * 「暂无已知过敏原」切换：勾选时清空已选八类与自定义（互斥语义，对齐源码）。
 * @returns 无
 */
function toggleNoKnownAllergen(): void {
  memberForm.no_known_allergen = !memberForm.no_known_allergen
  if (memberForm.no_known_allergen) {
    memberForm.allergen_codes = []
    memberForm.custom_allergens = []
  }
}

/**
 * 添加自定义过敏原（去重；空输入忽略）。
 * @returns 无
 */
function addCustomAllergen(): void {
  const text = customAllergenInput.value.trim()
  if (!text) return
  if (!memberForm.custom_allergens.includes(text)) {
    memberForm.custom_allergens = [...memberForm.custom_allergens, text]
  }
  customAllergenInput.value = ''
}

/**
 * 删除自定义过敏原。
 * @param text 待删除文本
 * @returns 无
 */
function removeCustomAllergen(text: string): void {
  memberForm.custom_allergens = memberForm.custom_allergens.filter((t) => t !== text)
}

/**
 * 切换忌口预置多选 tag。
 * @param item 忌口项
 * @returns 无
 */
function toggleRestriction(item: string): void {
  memberForm.dietary_restrictions = memberForm.dietary_restrictions.includes(item)
    ? memberForm.dietary_restrictions.filter((t) => t !== item)
    : [...memberForm.dietary_restrictions, item]
}

/**
 * 添加自定义忌口（去重；空输入忽略）。
 * @returns 无
 */
function addCustomRestriction(): void {
  const text = customRestrictionInput.value.trim()
  if (!text) return
  if (!memberForm.dietary_restrictions.includes(text)) {
    memberForm.dietary_restrictions = [...memberForm.dietary_restrictions, text]
  }
  customRestrictionInput.value = ''
}

/**
 * 删除忌口（预置与自定义同列表）。
 * @param text 待删除文本
 * @returns 无
 */
function removeRestriction(text: string): void {
  memberForm.dietary_restrictions = memberForm.dietary_restrictions.filter((t) => t !== text)
}

/**
 * 切换特殊饮食多选 tag。
 * @param item 特殊饮食项
 * @returns 无
 */
function toggleSpecialDiet(item: string): void {
  memberForm.special_diet = memberForm.special_diet.includes(item)
    ? memberForm.special_diet.filter((t) => t !== item)
    : [...memberForm.special_diet, item]
}

/**
 * 切换特殊人群多选 tag。
 * @param item 特殊人群项
 * @returns 无
 */
function toggleSpecialPopulation(item: string): void {
  memberForm.special_population = memberForm.special_population.includes(item)
    ? memberForm.special_population.filter((t) => t !== item)
    : [...memberForm.special_population, item]
}

/**
 * onLoad：有 id 参数则回填该成员（编辑模式），否则保持新增缺省表单。
 * @param options 页面参数（id 可选）
 * @returns 无
 */
onLoad((options) => {
  const id = Number(options?.id)
  if (!id || Number.isNaN(id)) return
  const member = profile.family?.members.find((m) => m.id === id)
  if (!member) {
    toastWarning('未找到该成员，请返回重试')
    return
  }
  editingId.value = member.id
  Object.assign(memberForm, {
    name: member.name,
    relation: member.relation,
    allergen_codes: [...member.allergen_codes],
    custom_allergens: [...member.custom_allergens],
    no_known_allergen: member.no_known_allergen,
    taste_spicy: member.taste_spicy,
    taste_salt: member.taste_salt,
    taste_sweet: member.taste_sweet,
    dietary_restrictions: [...member.dietary_restrictions],
    special_diet: [...member.special_diet],
    special_population: [...member.special_population],
  })
})

/**
 * onShow 兜底：从 P-00b 返回但未收到同意事件（暂不同意 / 中途退出）→ 视为拒绝，中断保存。
 * @returns 无
 */
onShow(() => {
  if (consentWaiter) {
    const waiter = consentWaiter
    consentWaiter = null
    waiter(false)
  }
})

/**
 * P-00b 同意结果事件：同意 → resolve(true) 续跑保存。
 * @returns 无
 */
function onConsentSensitiveEvent(): void {
  if (consentWaiter) {
    const waiter = consentWaiter
    consentWaiter = null
    waiter(true)
  }
}

// 注册同意结果监听（页面卸载时解除，防跨页误触发）
uni.$on('aicook:consent-sensitive', onConsentSensitiveEvent)
onUnload(() => {
  uni.$off('aicook:consent-sensitive', onConsentSensitiveEvent)
  if (consentWaiter) {
    const waiter = consentWaiter
    consentWaiter = null
    waiter(false)
  }
})

/**
 * 实际落库：新增 / 更新成员（异常就地转错误 toast）。
 * @returns 无
 * @throws 不向外抛出（接口失败就地提示）
 */
async function doSave(): Promise<void> {
  const payload: Omit<FamilyMember, 'id'> = {
    name: memberForm.name.trim(),
    relation: memberForm.relation,
    allergen_codes: [...memberForm.allergen_codes],
    custom_allergens: [...memberForm.custom_allergens],
    no_known_allergen: memberForm.no_known_allergen,
    taste_spicy: memberForm.taste_spicy,
    taste_salt: memberForm.taste_salt,
    taste_sweet: memberForm.taste_sweet,
    dietary_restrictions: [...memberForm.dietary_restrictions],
    special_diet: [...memberForm.special_diet],
    special_population: [...memberForm.special_population],
  }
  try {
    if (editingId.value == null) {
      await profile.addMember(payload)
      toastSuccess('成员已添加')
    } else {
      await profile.updateMember({ ...payload, id: editingId.value })
      toastSuccess('成员已更新')
    }
    uni.navigateBack({ fail: () => {} })
  } catch (e) {
    toastError((e as ApiError).message || '保存失败，请重试')
  }
}

/**
 * 保存入口：姓名本地校验 → RL-14 同意闸（首填过敏原且未同意先跳 P-00b）→ 落库。
 * @returns 无
 */
async function onSave(): Promise<void> {
  if (!canSave.value) {
    toastWarning(memberForm.name.trim() ? '请填写过敏原或勾选「暂无已知过敏原」' : '请填写成员姓名')
    return
  }
  // RL-14：首次填写过敏原（八类或自定义任一非空）且未单独同意 → 先走 P-00b
  if (allergenFilled.value && !profile.sensitiveConsented) {
    const agreed = await new Promise<boolean>((resolve) => {
      consentWaiter = resolve
      uni.navigateTo({ url: `${ROUTES.CONSENT}?scene=allergen`, fail: () => {} })
    })
    if (!agreed) {
      toastInfo('未同意前不会保存过敏原信息')
      return
    }
  }
  await doSave()
}

// onHide：尽力上报缓冲埋点
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <view class="member-edit">
      <!-- 姓名 -->
      <view class="member-edit__field">
        <text class="member-edit__label">姓名（必填）</text>
        <BaseInput v-model="memberForm.name" placeholder="如：妈妈" :maxlength="20" />
      </view>

      <!-- 关系 -->
      <view class="member-edit__field">
        <text class="member-edit__label">与本人关系</text>
        <BasePicker v-model="memberForm.relation" :options="RELATION_OPTIONS" />
      </view>

      <!-- 过敏原八类多选 -->
      <view class="member-edit__field">
        <text class="member-edit__label">过敏原（GB 7718 八类，可多选）</text>
        <view class="member-edit__tags">
          <view
            v-for="opt in ALLERGEN_OPTIONS"
            :key="opt.code"
            class="member-edit__tag"
            :class="{ 'is-active': memberForm.allergen_codes.includes(opt.code) }"
            @click="toggleAllergen(opt.code)"
          >
            {{ opt.label }}
          </view>
        </view>
      </view>

      <!-- 自定义过敏原 -->
      <view class="member-edit__field">
        <text class="member-edit__label">其他过敏原（自定义）</text>
        <view class="member-edit__input-row">
          <BaseInput v-model="customAllergenInput" placeholder="如：芒果" :maxlength="20" />
          <BaseButton size="sm" type="default" @click="addCustomAllergen">添加</BaseButton>
        </view>
        <view v-if="memberForm.custom_allergens.length > 0" class="member-edit__tags">
          <view
            v-for="text in memberForm.custom_allergens"
            :key="text"
            class="member-edit__tag is-active"
            @click="removeCustomAllergen(text)"
          >
            {{ text }} ×
          </view>
        </view>
      </view>

      <!-- 暂无已知过敏原（互斥） -->
      <view class="member-edit__agree" @click="toggleNoKnownAllergen">
        <view class="member-edit__checkbox" :class="{ 'is-checked': memberForm.no_known_allergen }">
          <text v-if="memberForm.no_known_allergen" class="member-edit__check-mark">✓</text>
        </view>
        <text class="member-edit__agree-text">暂无已知过敏原</text>
      </view>

      <!-- 口味三档 -->
      <view class="member-edit__field">
        <text class="member-edit__label">口味偏好（辣 / 咸 / 甜）</text>
        <view class="member-edit__taste">
          <view class="member-edit__taste-item">
            <text class="member-edit__taste-label">辣</text>
            <BasePicker v-model="memberForm.taste_spicy" :options="TASTE_OPTIONS" />
          </view>
          <view class="member-edit__taste-item">
            <text class="member-edit__taste-label">咸</text>
            <BasePicker v-model="memberForm.taste_salt" :options="TASTE_OPTIONS" />
          </view>
          <view class="member-edit__taste-item">
            <text class="member-edit__taste-label">甜</text>
            <BasePicker v-model="memberForm.taste_sweet" :options="TASTE_OPTIONS" />
          </view>
        </view>
      </view>

      <!-- 忌口 -->
      <view class="member-edit__field">
        <text class="member-edit__label">忌口（可多选 / 自定义）</text>
        <view class="member-edit__tags">
          <view
            v-for="item in DIETARY_PRESETS"
            :key="item"
            class="member-edit__tag"
            :class="{ 'is-active': memberForm.dietary_restrictions.includes(item) }"
            @click="toggleRestriction(item)"
          >
            {{ item }}
          </view>
        </view>
        <view class="member-edit__input-row">
          <BaseInput v-model="customRestrictionInput" placeholder="其他忌口，如：苦味" :maxlength="20" />
          <BaseButton size="sm" type="default" @click="addCustomRestriction">添加</BaseButton>
        </view>
        <view v-if="memberForm.dietary_restrictions.filter((t) => !DIETARY_PRESETS.includes(t)).length > 0" class="member-edit__tags">
          <view
            v-for="text in memberForm.dietary_restrictions.filter((t) => !DIETARY_PRESETS.includes(t))"
            :key="text"
            class="member-edit__tag is-active"
            @click="removeRestriction(text)"
          >
            {{ text }} ×
          </view>
        </view>
      </view>

      <!-- 特殊饮食 -->
      <view class="member-edit__field">
        <text class="member-edit__label">特殊饮食（可多选）</text>
        <view class="member-edit__tags">
          <view
            v-for="item in SPECIAL_DIET_OPTIONS"
            :key="item"
            class="member-edit__tag"
            :class="{ 'is-active': memberForm.special_diet.includes(item) }"
            @click="toggleSpecialDiet(item)"
          >
            {{ item }}
          </view>
        </view>
      </view>

      <!-- 特殊人群 -->
      <view class="member-edit__field">
        <text class="member-edit__label">特殊人群（可多选）</text>
        <view class="member-edit__tags">
          <view
            v-for="item in SPECIAL_POPULATION_OPTIONS"
            :key="item"
            class="member-edit__tag"
            :class="{ 'is-active': memberForm.special_population.includes(item) }"
            @click="toggleSpecialPopulation(item)"
          >
            {{ item }}
          </view>
        </view>
      </view>

      <!-- 保存 -->
      <BaseButton class="member-edit__save" block :loading="profile.saving" @click="onSave">
        保存
      </BaseButton>
    </view>
  </view>
</template>

<style scoped lang="scss">
.member-edit {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md) var(--space-md) var(--space-xl);
}

.member-edit__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  margin-bottom: var(--space-lg);
}

.member-edit__label {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.member-edit__tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.member-edit__tag {
  box-sizing: border-box;
  padding: var(--space-xs) var(--space-md);
  min-height: 72rpx;
  display: flex;
  align-items: center;
  border: 1rpx solid var(--border-color);
  border-radius: var(--radius-ctrl);
  background: var(--bg-card);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);

  &.is-active {
    border-color: var(--color-primary);
    background: var(--color-primary-weak);
    color: var(--color-primary);
  }
}

.member-edit__input-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

/* 输入框占满剩余宽度（添加按钮固定右侧）
   🔴 wxss 兼容：`> :first-child` 编译产物 `>:first-child` 会使微信 wxss 编译器报
   "error at token ':'"（渲染层崩溃白屏），故去掉子代组合器；页面 scoped 样式带
   data-v 标记，组件内部节点不受影响，后代写法语义等价 */
.member-edit__input-row :first-child {
  flex: 1;
  min-width: 0;
}

.member-edit__agree {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  min-height: var(--hit-min);
  margin-bottom: var(--space-lg);
}

.member-edit__checkbox {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40rpx;
  height: 40rpx;
  border: 2rpx solid var(--border-color);
  border-radius: var(--radius-ctrl);
  background: var(--bg-card);
  flex-shrink: 0;

  &.is-checked {
    border-color: var(--color-primary);
    background: var(--color-primary);
  }
}

.member-edit__check-mark {
  font-size: var(--font-size-sm);
  color: var(--text-inverse);
}

.member-edit__agree-text {
  font-size: var(--font-size-base);
  color: var(--text-primary);
}

.member-edit__taste {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.member-edit__taste-item {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.member-edit__taste-label {
  width: 48rpx;
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  flex-shrink: 0;
}

/* 🔴 wxss 兼容：同上，去掉 > 子代组合器（见 .member-edit__input-row 注释） */
.member-edit__taste-item :last-child {
  flex: 1;
}

.member-edit__save {
  margin-top: var(--space-lg);
}
</style>
