<script setup lang="ts">
/**
 * 视图职责：家庭档案页（Task 9 / 路由 /profile）。
 * 区块：① 家庭成员卡：成员列表（口味/过敏原摘要）+ 新增/编辑弹窗 + 删除二次确认；
 *       ② 厨艺与设备卡：13 项设备 checkbox + 厨艺水平 1~5（el-rate 语义滑杆）；
 *       ③ 饮食目标卡：5 选 1 + 疾病相关强提示 alert + 备注。
 * 成员弹窗校验：过敏原「八类多选 / 自定义输入 / 暂无已知过敏原」三者满足其一，
 * 且姓名非空，否则「保存」按钮禁用（严格 Element Plus 规范）。
 * PIPL 单独同意：首次填写过敏原（本地无同意记录）时弹独立同意层，
 * 调 POST /v1/consent/sensitive（scene=family_allergen）落库后放行保存。
 * 三态：加载 = 骨架；异常 = el-alert + 重试；深色模式全变量适配。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { postConsentSensitive } from '@/api/endpoints'
import type { ApiError, FamilyMember } from '@/api/types'
import { useProfileStore } from '@/stores/profile'
import { allergenLabel } from '@/utils/recipe'
import { saveAfterSensitiveConsent } from '@/utils/sensitiveConsent'
import { validateMemberWizardStep } from '@/utils/memberWizard'

/** 档案 store */
const profileStore = useProfileStore()

/* ── 常量选项（对齐契约）── */

/** GB 7718 八类致敏原编码（多选项） */
const ALLERGEN_OPTIONS = [
  'gluten',
  'crustacean',
  'fish',
  'egg',
  'peanut',
  'soybean',
  'milk',
  'nuts',
]

/** 家庭关系选项 */
const RELATION_OPTIONS = ['本人', '配偶', '孩子', '父母', '其他']
const AGE_GROUP_OPTIONS = [
  { value: '0-3', label: '0–3 岁' },
  { value: '4-12', label: '4–12 岁' },
  { value: '13-17', label: '13–17 岁' },
  { value: '18-59', label: '18–59 岁' },
  { value: '60+', label: '60 岁以上' },
] as const

/** 忌口预置选项（el-select 可创建新条目） */
const DIETARY_PRESETS = ['香菜', '内脏', '肥肉', '葱', '姜', '蒜', '辣椒', '生食']

/** 特殊饮食 6 类 */
const SPECIAL_DIET_OPTIONS = ['素食', '纯素', '清真', '低 GI', '生酮', '无麸质']

/** 特殊人群 5 类 */
const SPECIAL_POPULATION_OPTIONS = ['孕期', '哺乳期', '婴幼儿辅食', '老年人', '慢病人群']

/** 厨房设备选项（对齐后端 EQUIPMENT_WHITELIST；含燃气灶/电磁炉/炖锅/砂锅补齐项） */
const EQUIPMENT_OPTIONS = [
  '炒锅',
  '蒸锅',
  '电饭煲',
  '空气炸锅',
  '烤箱',
  '微波炉',
  '破壁机',
  '高压锅',
  '平底锅',
  '汤锅',
  '刨丝器',
  '厨房秤',
  '砧板',
  '燃气灶',
  '电磁炉',
  '炖锅',
  '砂锅',
]

/** 饮食目标 5 类 */
const GOAL_OPTIONS: Array<{ value: 'control_weight' | 'muscle_gain' | 'light_salt' | 'low_sugar' | 'balanced'; label: string; desc: string }> = [
  { value: 'control_weight', label: '控制体重', desc: '优先低热量高饱腹' },
  { value: 'muscle_gain', label: '增肌', desc: '优先高蛋白' },
  { value: 'light_salt', label: '少盐', desc: '控制钠摄入' },
  { value: 'low_sugar', label: '低糖', desc: '控制糖分摄入' },
  { value: 'balanced', label: '均衡饮食', desc: '不设特别倾向' },
]

const TASTE_SCALES = {
  spicy: ['不吃辣', '微辣', '嗜辣'],
  salt: ['清淡', '适中', '偏咸'],
  sweet: ['少甜', '适中', '偏甜'],
} as const

/** PIPL 同意记录的本地记忆键 */
const PIPL_CONSENT_KEY = 'aicook_pipl_consent_allergen_v2'

/* ── 成员编辑弹窗状态 ── */

/** 弹窗可见性 */
const memberDialogVisible = ref(false)
const memberStep = ref(0)
const memberStepError = ref<'name' | 'allergen' | null>(null)
/** 正在编辑的成员 ID（null = 新增） */
const editingId = ref<number | null>(null)
/** 自定义过敏原输入缓冲 */
const customAllergenInput = ref('')

/** 成员表单（弹窗内双向绑定） */
const memberForm = reactive({
  name: '',
  relation: '本人',
  age_group: '18-59' as FamilyMember['age_group'],
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

/** 保存按钮可用性：姓名非空 + 过敏原三选一满足 */
const canSaveMember = computed(
  () => memberForm.name.trim().length > 0 && (allergenFilled.value || memberForm.no_known_allergen),
)
const hasAllergenChoice = computed(() => allergenFilled.value || memberForm.no_known_allergen)

function nextMemberStep(): void {
  const error = validateMemberWizardStep(memberStep.value, memberForm.name, hasAllergenChoice.value)
  if (error) {
    memberStepError.value = error
    return
  }
  memberStepError.value = null
  memberStep.value = Math.min(memberStep.value + 1, 2)
}

function previousMemberStep(): void {
  memberStepError.value = null
  memberStep.value = Math.max(memberStep.value - 1, 0)
}

/* ── PIPL 单独同意层状态 ── */

/** 同意层可见性 */
const consentVisible = ref(false)
const consentSubmitting = ref(false)
/** 同意层关闭后待执行的保存动作（同意成功后自动续跑） */
let pendingSave: (() => Promise<void>) | null = null

/**
 * 判断是否需要 PIPL 单独同意（本地无记录且本会话未同意）。
 * @returns 需要弹同意层为 true
 */
function needsConsent(): boolean {
  if (profileStore.sensitiveConsented) return false
  try {
    return localStorage.getItem(PIPL_CONSENT_KEY) !== '1'
  } catch {
    return true
  }
}

/**
 * 打开新增成员弹窗（空白表单）。
 * @returns 无
 */
function openCreate(): void {
  editingId.value = null
  memberStep.value = 0
  memberStepError.value = null
  Object.assign(memberForm, {
    name: '',
    relation: '本人',
    age_group: '18-59',
    allergen_codes: [],
    custom_allergens: [],
    no_known_allergen: false,
    taste_spicy: 1,
    taste_salt: 1,
    taste_sweet: 1,
    dietary_restrictions: [],
    special_diet: [],
    special_population: [],
  })
  customAllergenInput.value = ''
  memberDialogVisible.value = true
}

/**
 * 打开编辑成员弹窗（回填既有数据）。
 * @param member 待编辑成员
 * @returns 无
 */
function openEdit(member: FamilyMember): void {
  editingId.value = member.id
  memberStep.value = 0
  memberStepError.value = null
  Object.assign(memberForm, {
    name: member.name,
    relation: member.relation,
    age_group: member.age_group,
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
  customAllergenInput.value = ''
  memberDialogVisible.value = true
}

/**
 * 「暂无已知过敏原」切换：勾选时清空已选八类与自定义（互斥语义）。
 * @param checked 当前勾选值
 * @returns 无
 */
function onNoAllergenChange(checked: boolean): void {
  memberStepError.value = null
  if (checked) {
    memberForm.allergen_codes = []
    memberForm.custom_allergens = []
  }
}

/**
 * 添加自定义过敏原（回车/按钮触发，去重）。
 * @returns 无
 */
function addCustomAllergen(): void {
  const text = customAllergenInput.value.trim()
  if (!text) return
  if (!memberForm.custom_allergens.includes(text)) {
    memberForm.custom_allergens = [...memberForm.custom_allergens, text]
  }
  memberStepError.value = null
  customAllergenInput.value = ''
}

/**
 * 弹窗「保存」：先过 PIPL 同意闸（首次填写过敏原），再落库。
 * @returns 无
 */
function onSaveMember(): void {
  if (!canSaveMember.value) return
  const payload: Omit<FamilyMember, 'id'> = {
    name: memberForm.name.trim(),
    relation: memberForm.relation,
    age_group: memberForm.age_group,
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
  /** 实际落库动作（新增或更新） */
  const doSave = async (): Promise<void> => {
    try {
      if (editingId.value == null) {
        await profileStore.addMember(payload)
        ElMessage.success('成员已添加')
      } else {
        await profileStore.updateMember({ ...payload, id: editingId.value })
        ElMessage.success('成员已更新')
      }
      memberDialogVisible.value = false
    } catch (e) {
      ElMessage.error((e as ApiError).message || '保存失败，请重试')
    }
  }
  // 首次填写过敏原（或勾选暂无）→ PIPL 单独同意层
  if (needsConsent()) {
    pendingSave = doSave
    consentVisible.value = true
    return
  }
  void doSave()
}

/**
 * PIPL 同意层「同意并保存」：落库同意记录 → 记忆 → 续跑保存。
 * @returns 无
 */
async function onConsentAgree(): Promise<void> {
  if (consentSubmitting.value) return
  consentSubmitting.value = true
  try {
    await saveAfterSensitiveConsent(
      () => postConsentSensitive('family_allergen'),
      async () => {
        const save = pendingSave
        pendingSave = null
        await save?.()
      },
    )
    profileStore.sensitiveConsented = true
    try {
      localStorage.setItem(PIPL_CONSENT_KEY, '1')
    } catch {
      // 本地记忆失败不影响本次放行
    }
    consentVisible.value = false
  } catch (e) {
    ElMessage.error((e as ApiError).message || '同意记录保存失败，请重试；完成前不会保存过敏原信息')
  } finally {
    consentSubmitting.value = false
  }
}

/**
 * PIPL 同意层「暂不同意」：关闭层并中止保存（表单保留）。
 * @returns 无
 */
function onConsentDecline(): void {
  pendingSave = null
  consentVisible.value = false
  ElMessage.info('未同意前不会保存过敏原信息')
}

/**
 * 删除成员（store 内已本地同步移除）。
 * @param member 目标成员
 * @returns 无
 */
async function onDeleteMember(member: FamilyMember): Promise<void> {
  try {
    await profileStore.removeMember(member.id)
    ElMessage.success('成员已删除')
  } catch (e) {
    ElMessage.error((e as ApiError).message || '删除失败，请重试')
  }
}

/* ── 厨艺与设备 ── */

/** 本地编辑缓冲（进入页面从 store 拷贝，点保存落库） */
const skillForm = reactive({
  cooking_level: 3,
  equipment: [] as string[],
})

/** 厨艺水平文案 */
const LEVEL_LABELS = ['', '新手', '会做简单菜', '家常熟练', '进阶', '大厨']

/**
 * 保存厨艺与设备。
 * @returns 无
 */
async function onSaveSkill(): Promise<void> {
  try {
    await profileStore.saveSkill({ ...skillForm })
    ElMessage.success('厨艺与设备已保存')
  } catch (e) {
    ElMessage.error((e as ApiError).message || '保存失败，请重试')
  }
}

/* ── 饮食目标 ── */

/** 本地编辑缓冲 */
const goalForm = reactive<{ goal: 'control_weight' | 'muscle_gain' | 'light_salt' | 'low_sugar' | 'balanced'; note: string }>({
  goal: 'balanced',
  note: '',
})

/** 是否选择了慢病相关目标（少盐/低糖 → 强化提示） */
const goalDiseaseHint = computed(() => goalForm.goal === 'light_salt' || goalForm.goal === 'low_sugar')

/**
 * 保存饮食目标。
 * @returns 无
 */
async function onSaveGoal(): Promise<void> {
  try {
    await profileStore.saveGoal({ goal: goalForm.goal, note: goalForm.note.trim() })
    ElMessage.success('饮食目标已保存')
  } catch (e) {
    ElMessage.error((e as ApiError).message || '保存失败，请重试')
  }
}

/**
 * 成员卡摘要文案：口味 + 过敏原 + 忌口。
 * @param member 成员
 * @returns 摘要文本
 */
function memberSummary(member: FamilyMember): string {
  const parts: string[] = []
  if (member.no_known_allergen) {
    parts.push('暂无已知过敏原')
  } else {
    const codes = member.allergen_codes.map((c) => allergenLabel(c))
    if (codes.length > 0) parts.push(`过敏原：${codes.join('、')}`)
    if (member.custom_allergens.length > 0) parts.push(`自定义：${member.custom_allergens.join('、')}`)
  }
  if (member.dietary_restrictions.length > 0) parts.push(`忌口：${member.dietary_restrictions.join('、')}`)
  if (member.special_population.length > 0) parts.push(`${member.special_population.join('、')}`)
  return parts.length > 0 ? parts.join('；') : '未填写偏好'
}

function memberAgeLabel(member: FamilyMember): string {
  return AGE_GROUP_OPTIONS.find((option) => option.value === member.age_group)?.label ?? member.age_group
}

/**
 * 重试加载档案。
 * @returns 无
 */
function retry(): void {
  void profileStore.loadAll()
}

// 挂载：拉取三段档案并把服务端值灌入本地编辑缓冲
onMounted(async () => {
  await profileStore.loadAll()
  if (profileStore.skill) {
    skillForm.cooking_level = profileStore.skill.cooking_level
    skillForm.equipment = [...profileStore.skill.equipment]
  }
  if (profileStore.goal) {
    goalForm.goal = profileStore.goal.goal
    goalForm.note = profileStore.goal.note
  }
})
</script>

<template>
  <section class="page-card profile-page">
    <h1 class="page-title">家庭档案</h1>

    <!-- 异常态 -->
    <el-alert
      v-if="profileStore.error"
      class="profile-alert"
      type="error"
      :title="`档案加载失败：${profileStore.error.message}`"
      :closable="false"
      show-icon
    >
      <el-button size="small" type="primary" plain @click="retry">重试</el-button>
    </el-alert>

    <!-- 加载态 -->
    <div v-if="profileStore.loading" class="profile-skeleton">
      <el-skeleton :rows="6" animated />
    </div>

    <template v-else>
      <!-- ① 家庭成员 -->
      <div class="profile-section">
        <div class="section-head">
          <h2 class="section-title">家庭成员</h2>
          <el-button
            v-if="(profileStore.family?.members?.length ?? 0) > 0"
            type="primary"
            :icon="Plus"
            @click="openCreate"
          >
            新增成员
          </el-button>
        </div>

        <div v-if="(profileStore.family?.members?.length ?? 0) === 0" class="profile-empty" role="status">
          <svg class="profile-empty__art" viewBox="0 0 96 80" fill="none" aria-hidden="true">
            <circle cx="48" cy="22" r="8" />
            <circle cx="25" cy="29" r="6" />
            <circle cx="71" cy="29" r="6" />
            <path d="M30 66c1.4-12.2 7.8-19 18-19s16.6 6.8 18 19M7 65c1-9.8 6.8-15 16-15 4.1 0 7.4 1 10 3M89 65c-1-9.8-6.8-15-16-15-4.1 0-7.4 1-10 3" />
          </svg>
          <div class="profile-empty__copy">
            <h3>先建立家庭档案</h3>
            <p>添加家庭成员后，可以按过敏原、口味和饮食目标筛选推荐。</p>
            <el-button type="primary" :icon="Plus" @click="openCreate">添加家庭成员</el-button>
          </div>
        </div>

        <div v-else class="member-list">
          <div v-for="m in profileStore.family?.members ?? []" :key="m.id" class="member-card">
            <div class="member-head">
              <span class="member-name">{{ m.name }}</span>
              <el-tag size="small" type="info">{{ m.relation }}</el-tag>
              <span class="member-age">{{ memberAgeLabel(m) }}</span>
            </div>
            <p class="member-summary">{{ memberSummary(m) }}</p>
            <div class="member-actions">
              <el-button size="small" @click="openEdit(m)">编辑</el-button>
              <el-popconfirm
                title="确认删除该成员？"
                confirm-button-text="删除"
                cancel-button-text="取消"
                @confirm="onDeleteMember(m)"
              >
                <template #reference>
                  <el-button size="small" type="danger" plain>删除</el-button>
                </template>
              </el-popconfirm>
            </div>
          </div>
        </div>
      </div>

      <!-- ② 厨艺与设备 -->
      <div class="profile-section">
        <h2 class="section-title">厨艺与设备</h2>
        <p class="section-hint">按你现有的锅具推荐，缺设备的菜会明确标注。</p>

        <div class="skill-level">
          <span class="skill-label">厨艺水平：</span>
          <el-slider
            v-model="skillForm.cooking_level"
            class="skill-slider"
            :min="1"
            :max="5"
            :step="1"
            show-stops
            :marks="{ 1: '新手', 3: '熟练', 5: '大厨' }"
          />
          <span class="skill-value">{{ LEVEL_LABELS[skillForm.cooking_level] ?? '' }}</span>
        </div>

        <el-checkbox-group v-model="skillForm.equipment" class="equipment-group" aria-label="选择厨房设备">
          <el-checkbox-button v-for="eq in EQUIPMENT_OPTIONS" :key="eq" :value="eq" :label="eq">
            {{ eq }}
          </el-checkbox-button>
        </el-checkbox-group>

        <div class="profile-actions">
          <el-button type="primary" :loading="profileStore.saving" @click="onSaveSkill">
            保存厨艺与设备
          </el-button>
        </div>
      </div>

      <!-- ③ 饮食目标 -->
      <div class="profile-section">
        <h2 class="section-title">饮食目标</h2>

        <!-- 疾病相关强提示（选中慢病相关目标时强化文案） -->
        <el-alert
          class="profile-alert"
          :class="{ 'profile-guidance': !goalDiseaseHint }"
          :type="goalDiseaseHint ? 'warning' : 'info'"
          :title="goalDiseaseHint
            ? '你有高血压 / 糖尿病等慢性疾病时，请先咨询医生再设定该目标；本目标不构成医疗建议'
            : '饮食目标仅用于菜谱排序倾向，不构成医疗或营养治疗建议'"
          :closable="false"
          show-icon
        />

        <div class="goal-grid">
          <button
            v-for="g in GOAL_OPTIONS"
            :key="g.value"
            type="button"
            class="goal-card"
            :class="{ 'goal-card--active': goalForm.goal === g.value }"
            :aria-pressed="goalForm.goal === g.value"
            @click="goalForm.goal = g.value"
          >
            <span class="goal-label">{{ g.label }}</span>
            <span class="goal-desc">{{ g.desc }}</span>
          </button>
        </div>

        <el-input
          v-model="goalForm.note"
          type="textarea"
          :rows="2"
          maxlength="100"
          placeholder="备注（可选）：如「医生建议每日盐 <5g」"
          class="goal-note"
        />

        <div class="profile-actions">
          <el-button type="primary" :loading="profileStore.saving" @click="onSaveGoal">
            保存饮食目标
          </el-button>
        </div>
      </div>
    </template>

    <!-- 成员新增/编辑弹窗 -->
    <el-dialog
      v-model="memberDialogVisible"
      :title="editingId == null ? '新增成员' : '编辑成员'"
      width="480px"
      align-center
      destroy-on-close
      class="member-dialog"
      modal-class="member-dialog-overlay"
    >
      <el-form label-position="top">
        <ol class="member-stepper" aria-label="成员信息填写进度">
          <li v-for="(label, index) in ['基本信息', '安全与口味', '饮食偏好']" :key="label" :class="{ 'is-active': memberStep === index, 'is-complete': memberStep > index }">
            <span class="member-stepper__index">{{ memberStep > index ? '✓' : index + 1 }}</span>
            <span>{{ label }}</span>
          </li>
        </ol>

        <p v-if="memberStepError" class="member-step-error" role="alert">
          {{ memberStepError === 'name' ? '请先填写成员姓名。' : '请选择过敏原，或确认“暂无已知过敏原”。' }}
        </p>

        <div v-if="memberStep === 0" class="member-step-panel">
          <p class="member-step-intro">先确认成员身份，之后可随时在档案中调整。</p>
          <el-form-item label="姓名" required class="form-item">
            <el-input v-model="memberForm.name" maxlength="20" placeholder="如：妈妈" @input="memberStepError = null" />
          </el-form-item>
          <div class="form-row">
            <el-form-item label="关系" class="form-item">
              <el-select v-model="memberForm.relation">
                <el-option v-for="r in RELATION_OPTIONS" :key="r" :label="r" :value="r" />
              </el-select>
            </el-form-item>
            <el-form-item label="年龄段" class="form-item">
              <el-select v-model="memberForm.age_group">
                <el-option v-for="option in AGE_GROUP_OPTIONS" :key="option.value" :label="option.label" :value="option.value" />
              </el-select>
            </el-form-item>
          </div>
        </div>

        <div v-else-if="memberStep === 1" class="member-step-panel">
          <p class="member-step-intro">过敏原会用于菜谱安全过滤；不确定时请先核实后再填写。</p>
          <el-form-item label="已知过敏原，可多选" class="member-field">
            <el-checkbox-group
              v-model="memberForm.allergen_codes"
              class="member-chip-group"
              :disabled="memberForm.no_known_allergen"
              @change="memberStepError = null"
            >
              <el-checkbox-button v-for="code in ALLERGEN_OPTIONS" :key="code" :value="code" :label="code">
                {{ allergenLabel(code) }}
              </el-checkbox-button>
            </el-checkbox-group>
          </el-form-item>

          <el-form-item label="其他过敏原" class="member-field">
            <div class="custom-allergen-row">
              <el-input
                v-model="customAllergenInput"
                :disabled="memberForm.no_known_allergen"
                maxlength="20"
                placeholder="输入名称后按回车添加"
                @keyup.enter="addCustomAllergen"
              />
              <el-button :disabled="memberForm.no_known_allergen" @click="addCustomAllergen">添加</el-button>
            </div>
            <div v-if="memberForm.custom_allergens.length > 0" class="custom-tags" aria-label="已添加的自定义过敏原">
              <el-tag
                v-for="tag in memberForm.custom_allergens"
                :key="tag"
                closable
                @close="memberForm.custom_allergens = memberForm.custom_allergens.filter((t) => t !== tag)"
              >
                {{ tag }}
              </el-tag>
            </div>
          </el-form-item>

          <el-form-item class="member-no-allergen">
            <el-switch
              v-model="memberForm.no_known_allergen"
              active-text="暂无已知过敏原"
              @change="onNoAllergenChange"
            />
          </el-form-item>

          <div class="taste-list" aria-label="口味偏好">
            <div class="taste-control">
              <div class="taste-control__head"><span>辣度</span><strong>{{ TASTE_SCALES.spicy[memberForm.taste_spicy] }}</strong></div>
              <el-slider v-model="memberForm.taste_spicy" :min="0" :max="2" :step="1" :show-tooltip="false" />
              <div class="taste-scale"><span>{{ TASTE_SCALES.spicy[0] }}</span><span>{{ TASTE_SCALES.spicy[1] }}</span><span>{{ TASTE_SCALES.spicy[2] }}</span></div>
            </div>
            <div class="taste-control">
              <div class="taste-control__head"><span>咸淡</span><strong>{{ TASTE_SCALES.salt[memberForm.taste_salt] }}</strong></div>
              <el-slider v-model="memberForm.taste_salt" :min="0" :max="2" :step="1" :show-tooltip="false" />
              <div class="taste-scale"><span>{{ TASTE_SCALES.salt[0] }}</span><span>{{ TASTE_SCALES.salt[1] }}</span><span>{{ TASTE_SCALES.salt[2] }}</span></div>
            </div>
            <div class="taste-control">
              <div class="taste-control__head"><span>甜度</span><strong>{{ TASTE_SCALES.sweet[memberForm.taste_sweet] }}</strong></div>
              <el-slider v-model="memberForm.taste_sweet" :min="0" :max="2" :step="1" :show-tooltip="false" />
              <div class="taste-scale"><span>{{ TASTE_SCALES.sweet[0] }}</span><span>{{ TASTE_SCALES.sweet[1] }}</span><span>{{ TASTE_SCALES.sweet[2] }}</span></div>
            </div>
          </div>
        </div>

        <div v-else class="member-step-panel">
          <p class="member-step-intro">这些偏好用于优化推荐，不会改变过敏原安全过滤。</p>
          <el-form-item label="忌口，可输入自定义" class="member-field">
            <el-select
              v-model="memberForm.dietary_restrictions"
              multiple
              filterable
              allow-create
              default-first-option
              placeholder="选择或输入，如：香菜"
            >
              <el-option v-for="d in DIETARY_PRESETS" :key="d" :label="d" :value="d" />
            </el-select>
          </el-form-item>

          <el-form-item label="特殊饮食" class="member-field">
            <el-checkbox-group v-model="memberForm.special_diet" class="member-chip-group">
              <el-checkbox-button v-for="d in SPECIAL_DIET_OPTIONS" :key="d" :value="d" :label="d">{{ d }}</el-checkbox-button>
            </el-checkbox-group>
          </el-form-item>

          <el-form-item label="特殊人群" class="member-field">
            <el-checkbox-group v-model="memberForm.special_population" class="member-chip-group">
              <el-checkbox-button v-for="p in SPECIAL_POPULATION_OPTIONS" :key="p" :value="p" :label="p">{{ p }}</el-checkbox-button>
            </el-checkbox-group>
          </el-form-item>
        </div>
      </el-form>

      <template #footer>
        <div class="member-dialog-footer">
          <el-button v-if="memberStep === 0" text @click="memberDialogVisible = false">取消</el-button>
          <el-button v-else @click="previousMemberStep">上一步</el-button>
          <el-button v-if="memberStep < 2" type="primary" @click="nextMemberStep">继续</el-button>
          <el-button
            v-else
            type="primary"
            :disabled="!canSaveMember"
            :loading="profileStore.saving"
            @click="onSaveMember"
          >
            保存成员
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- PIPL 敏感信息单独同意层（首次填写过敏原时） -->
    <el-dialog
      v-model="consentVisible"
      title="过敏原信息收集告知（单独同意）"
      width="440px"
      align-center
      :close-on-click-modal="false"
    >
      <div class="consent-body">
        <p>
          根据《个人信息保护法》，过敏原信息属于敏感个人信息，收集前需取得你的单独同意：
        </p>
        <ul class="consent-list">
          <li>仅用于菜谱过敏原过滤与安全提示；</li>
          <li>不会用于广告或对外提供；</li>
          <li>你可随时在档案中修改或删除，或通过「我的 → 数据导出 / 注销」行使数据权利。</li>
        </ul>
      </div>
      <template #footer>
        <el-button @click="onConsentDecline">暂不同意</el-button>
        <el-button type="primary" :loading="consentSubmitting" @click="onConsentAgree">同意并保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.profile-page {
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  /* 说明类文案可读色（WCAG AA ≥4.5:1）：由既有变量 color-mix 自适应深浅色——
     浅色：55% --color-info(#68786f) + 45% --text-main(#26362e) ≈ #4a5a52，
       在 #f7f6f0 上 6.7:1、#eef2ee 上 6.5:1（原 #68786f 仅 4.3/4.12:1 不达标）；
     深色：55% --color-info(#a8b7ad) + 45% --text-main(#e8eee7) ≈ #c5cfc7，
       在深色表面上 ≥8.9:1。跟随 html.dark 变量自动切换，无需单独覆盖。 */
  --profile-info-text: color-mix(in srgb, var(--color-info) 55%, var(--text-main));
}

.profile-alert {
  margin-bottom: 14px;
}

.profile-guidance {
  --el-alert-bg-color: var(--color-warning-bg);
  color: var(--text-main);
  border: 1px solid var(--color-warning-border);
  border-radius: 8px;
}

.profile-guidance :deep(.el-alert__icon) {
  color: var(--color-warning);
}

.profile-guidance :deep(.el-alert__title) {
  color: var(--text-main);
}

.profile-skeleton {
  padding: 8px 0 24px;
}

.profile-section {
  padding: 24px 0 26px;
  border-top: 1px solid var(--color-info-border);
}

.profile-section:first-of-type {
  border-top: none;
  padding-top: 8px;
}

.section-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 18px;
}

.section-title {
  margin: 0 0 14px;
  font-size: var(--font-lg);
  font-weight: 600;
  color: var(--text-main);
}

.section-head .section-title {
  margin-bottom: 0;
}

.profile-page :deep(.el-button:not(.el-button--small)) {
  min-height: 40px;
  padding-inline: 16px;
  border-radius: 10px;
}

.profile-page :deep(.el-button--small) {
  min-height: 32px;
  border-radius: 8px;
}

.profile-page :deep(.el-button--primary) {
  transition: background-color 160ms ease, border-color 160ms ease, transform 160ms ease;
}

/* 主按钮文字用项目语义色 --text-on-accent（浅色 #fffefa 不变；深色 #17261e，
   在深色主色 #d7b292 上 8.0:1——修复 Element Plus 默认白字在深色下仅 1.96:1 的问题） */
.profile-page :deep(.el-button--primary:not(.is-disabled)) {
  color: var(--text-on-accent);
}

.profile-page :deep(.el-button--primary:not(.is-disabled):hover) {
  transform: translateY(-1px);
}

.profile-page :deep(.el-button--primary:not(.is-disabled):active) {
  transform: translateY(0);
}

.section-hint {
  max-width: 60ch;
  margin: -4px 0 18px;
  font-size: var(--font-sm);
  color: var(--profile-info-text);
  line-height: 1.65;
}

.profile-empty {
  display: flex;
  align-items: center;
  gap: 28px;
  max-width: 720px;
  min-height: 168px;
  margin: 0;
  padding: 12px 0 8px;
}

.profile-empty__art {
  width: 76px;
  height: 76px;
  flex: 0 0 auto;
  stroke: var(--accent-deep);
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.profile-empty__copy h3 {
  margin: 0;
  color: var(--text-main);
  font-size: var(--font-lg);
  font-weight: 600;
}

.profile-empty__copy p {
  max-width: 54ch;
  margin: 7px 0 16px;
  color: var(--profile-info-text);
  font-size: var(--font-sm);
  line-height: 1.7;
}

.profile-empty__copy :deep(.el-button) {
  min-height: 40px;
  border-radius: 8px;
}

/* ── 成员列表 ── */
.member-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
  margin-bottom: 0;
}

.member-card {
  display: flex;
  min-height: 150px;
  flex-direction: column;
  align-items: flex-start;
  padding: 16px;
  border: 1px solid var(--color-info-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--card-bg) 48%, transparent);
}

/* 成员卡内 EP 组件对比度加固（Axe color-contrast：成员态 4 节点修复）：
   el-tag"本人"与 danger"删除"按钮沿用 EP 默认配色时低于 4.5:1，:deep 提升文字色，
   复用 --profile-info-text / 语义色混合，浅深色模式同源自适应 */
.member-card :deep(.el-tag) {
  color: var(--profile-info-text);
}

.member-actions :deep(.el-button--danger) {
  color: color-mix(in srgb, var(--el-color-danger) 60%, var(--text-main));
}

.member-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.member-name {
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
}

.member-age {
  color: var(--profile-info-text);
  font-size: var(--font-sm);
}

.member-summary {
  flex: 1;
  margin: 0 0 14px;
  font-size: var(--font-sm);
  line-height: 1.7;
  color: var(--profile-info-text);
}

.member-actions {
  display: flex;
  gap: 8px;
  margin-top: auto;
}

/* ── 厨艺 ── */
.skill-level {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 22px;
}

.skill-label {
  flex-shrink: 0;
  font-size: var(--font-md);
  color: var(--text-main);
}

.skill-slider {
  flex: 1;
  margin: 0 18px 0 4px;
  --el-slider-main-bg-color: var(--el-color-primary);
  --el-slider-runway-bg-color: var(--surface-soft);
  --el-slider-stop-bg-color: var(--surface-raised);
}

.skill-slider :deep(.el-slider__button) {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary);
}

/* 滑杆刻度文字：Element Plus 默认 --el-text-color-secondary（浅色 #909399）
   在 #f7f6f0 上仅 2.84:1，改为说明类可读色（≥4.5:1，随深浅色自适应） */
.skill-slider :deep(.el-slider__marks-text) {
  color: var(--profile-info-text);
}

.skill-value {
  flex-shrink: 0;
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--el-color-primary);
}

.equipment-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 20px;
}

.equipment-group :deep(.el-checkbox-button) {
  margin: 0;
}

.equipment-group :deep(.el-checkbox-button__inner) {
  display: inline-flex;
  min-height: 40px;
  align-items: center;
  padding: 0 13px;
  color: var(--text-main);
  border: 1px solid var(--sidebar-line);
  border-left: 1px solid var(--sidebar-line);
  border-radius: 8px;
  background: transparent;
  box-shadow: none;
  transition: color 160ms ease, border-color 160ms ease, background-color 160ms ease;
}

.equipment-group :deep(.el-checkbox-button:not(.is-disabled):hover .el-checkbox-button__inner) {
  color: var(--accent-deep);
  border-color: var(--accent-deep);
  background: var(--surface-hover);
}

.equipment-group :deep(.el-checkbox-button.is-checked .el-checkbox-button__inner) {
  color: var(--sidebar-active-text);
  border-color: var(--sidebar-line);
  background: var(--sidebar-active);
  box-shadow: none;
}

.equipment-group :deep(.el-checkbox-button__original:focus-visible + .el-checkbox-button__inner) {
  outline: 2px solid var(--accent-deep);
  outline-offset: 2px;
}

/* ── 饮食目标 ── */
.goal-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.goal-card {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-height: 82px;
  padding: 15px 16px;
  border: 1px solid var(--color-info-border);
  border-radius: 8px;
  background: var(--card-bg);
  text-align: left;
  cursor: pointer;
  transition: border-color 160ms ease, background-color 160ms ease, transform 160ms ease;
}

.goal-card:hover {
  border-color: var(--line-strong);
  transform: translateY(-1px);
}

.goal-card:focus-visible {
  outline: 2px solid var(--accent-deep);
  outline-offset: 2px;
}

.goal-card--active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.goal-label {
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
}

.goal-desc {
  font-size: var(--font-sm);
  color: var(--profile-info-text);
}

.goal-note {
  margin-bottom: 18px;
}

.profile-actions {
  display: flex;
  justify-content: flex-end;
}

/* ── 成员弹窗 ── */
.form-row {
  display: flex;
  gap: 16px;
}

.form-row .form-item {
  flex: 1;
}

.custom-allergen-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

.custom-tags {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.member-stepper {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 0 0 20px;
  padding: 0 0 16px;
  border-bottom: 1px solid var(--color-info-border);
  list-style: none;
}

.member-stepper li {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 7px;
  color: var(--color-info);
  font-size: var(--font-xs);
  white-space: nowrap;
}

.member-stepper__index {
  display: grid;
  width: 23px;
  height: 23px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid var(--sidebar-line);
  border-radius: 50%;
  color: var(--color-info);
  font-size: 12px;
  font-weight: 600;
}

.member-stepper li.is-active {
  color: var(--accent-deep);
  font-weight: 600;
}

.member-stepper li.is-active .member-stepper__index,
.member-stepper li.is-complete .member-stepper__index {
  border-color: var(--accent-deep);
  background: var(--accent-deep);
  color: #fff;
}

.member-step-intro {
  margin: 0 0 18px;
  color: var(--color-info);
  font-size: var(--font-sm);
  line-height: 1.65;
}

.member-step-error {
  margin: -6px 0 14px;
  color: var(--el-color-danger);
  font-size: var(--font-sm);
}

.member-field {
  margin-bottom: 18px;
}

.member-chip-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
}

.member-chip-group :deep(.el-checkbox-button) {
  margin: 0;
}

.member-chip-group :deep(.el-checkbox-button__inner) {
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid var(--sidebar-line);
  border-left: 1px solid var(--sidebar-line);
  border-radius: 7px;
  background: transparent;
  box-shadow: none;
  color: var(--text-main);
  line-height: 34px;
  transition: color 150ms ease, border-color 150ms ease, background-color 150ms ease;
}

.member-chip-group :deep(.el-checkbox-button:not(.is-disabled):hover .el-checkbox-button__inner) {
  border-color: var(--accent-deep);
  background: var(--surface-hover);
  color: var(--accent-deep);
}

.member-chip-group :deep(.el-checkbox-button.is-checked .el-checkbox-button__inner) {
  border-color: var(--accent-deep);
  background: var(--sidebar-active);
  color: var(--accent-deep);
  box-shadow: none;
}

.member-chip-group :deep(.el-checkbox-button__original:focus-visible + .el-checkbox-button__inner) {
  outline: 2px solid var(--accent-deep);
  outline-offset: 2px;
}

.member-no-allergen {
  margin: -2px 0 18px;
  padding: 10px 12px;
  border: 1px solid var(--color-info-border);
  border-radius: 8px;
  background: var(--surface-soft);
}

.taste-list {
  display: grid;
  gap: 15px;
  padding-top: 2px;
}

.taste-control {
  min-width: 0;
}

.taste-control__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  color: var(--text-main);
  font-size: var(--font-sm);
}

.taste-control__head strong {
  color: var(--accent-deep);
  font-weight: 600;
}

.taste-control :deep(.el-slider) {
  margin: 8px 8px 4px;
}

.taste-scale {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: var(--color-info);
  font-size: var(--font-xs);
}

.member-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 9px;
}

:global(.member-dialog-overlay) {
  background: rgb(24 35 29 / 34%);
  backdrop-filter: blur(6px);
}

:global(.member-dialog) {
  display: flex;
  max-height: calc(100dvh - 32px);
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--color-info-border);
  border-radius: 12px;
  background: var(--card-bg);
  box-shadow: 0 18px 56px rgb(30 47 37 / 18%);
}

:global(.member-dialog .el-dialog__header) {
  flex: 0 0 auto;
  margin-right: 0;
  padding: 22px 24px 12px;
}

:global(.member-dialog .el-dialog__title) {
  color: var(--text-main);
  font-size: 20px;
  font-weight: 600;
}

:global(.member-dialog .el-dialog__body) {
  min-height: 0;
  overflow-y: auto;
  padding: 10px 24px 18px;
}

:global(.member-dialog .el-dialog__footer) {
  flex: 0 0 auto;
  padding: 12px 24px 20px;
  border-top: 1px solid var(--color-info-border);
}

:global(.member-dialog .el-form-item__label) {
  margin-bottom: 7px;
  color: var(--text-main);
  font-size: var(--font-sm);
  font-weight: 600;
}

:global(.member-dialog .el-input__wrapper),
:global(.member-dialog .el-select__wrapper) {
  min-height: 40px;
  border-radius: 7px;
  box-shadow: 0 0 0 1px var(--sidebar-line) inset;
}

:global(.member-dialog .el-input__wrapper.is-focus),
:global(.member-dialog .el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1px var(--accent-deep) inset;
}

/* ── PIPL 同意层 ── */
.consent-body p {
  margin: 0 0 10px;
  font-size: var(--font-md);
  line-height: 1.7;
  color: var(--text-main);
}

.consent-list {
  margin: 0;
  padding-left: 20px;
}

.consent-list li {
  font-size: var(--font-sm);
  line-height: 1.9;
  color: var(--color-info);
}

@media (max-width: 560px) {
  :global(.member-dialog) {
    width: calc(100vw - 24px) !important;
    max-height: calc(100dvh - 24px);
    margin: 12px auto;
  }

  :global(.member-dialog .el-dialog__header) {
    padding: 18px 18px 10px;
  }

  :global(.member-dialog .el-dialog__body) {
    padding: 8px 18px 14px;
  }

  :global(.member-dialog .el-dialog__footer) {
    padding: 10px 18px 16px;
  }

  .form-row {
    flex-direction: column;
    gap: 0;
  }

  .member-stepper {
    gap: 4px;
  }

  .member-stepper li {
    flex-direction: column;
    align-items: flex-start;
    gap: 5px;
    white-space: normal;
  }

  .member-chip-group {
    gap: 7px;
  }

  .member-chip-group :deep(.el-checkbox-button__inner) {
    padding-inline: 10px;
  }
}

@media (max-width: 560px) {
  .profile-section {
    padding: 20px 0 22px;
  }

  .section-head {
    margin-bottom: 15px;
  }

  .profile-empty {
    min-height: 0;
    align-items: flex-start;
    gap: 16px;
    padding: 8px 0 4px;
  }

  .profile-empty__art {
    width: 58px;
    height: 58px;
  }

  .skill-level {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 8px 12px;
    margin-bottom: 18px;
  }

  .skill-slider {
    grid-column: 1 / -1;
    grid-row: 2;
    margin: 0 12px 8px;
  }

  .goal-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .goal-card {
    min-height: 76px;
    padding: 13px;
  }

  .profile-actions :deep(.el-button) {
    width: 100%;
  }
}

@media (max-width: 380px) {
  .profile-empty {
    flex-direction: column;
  }

  .goal-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .section-head :deep(.el-button) {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .profile-page :deep(.el-button--primary),
  .equipment-group :deep(.el-checkbox-button__inner),
  .goal-card {
    transition-duration: 0.01ms;
  }

  .profile-page :deep(.el-button--primary:not(.is-disabled):hover),
  .goal-card:hover {
    transform: none;
  }
}
</style>
