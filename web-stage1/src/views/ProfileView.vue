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

/** 口味滑块档位文案（0/1/2） */
const TASTE_MARKS = { 0: '清淡', 1: '适中', 2: '嗜好' }

/** PIPL 同意记录的本地记忆键 */
const PIPL_CONSENT_KEY = 'aicook_pipl_consent_allergen_v1'

/* ── 成员编辑弹窗状态 ── */

/** 弹窗可见性 */
const memberDialogVisible = ref(false)
/** 正在编辑的成员 ID（null = 新增） */
const editingId = ref<number | null>(null)
/** 自定义过敏原输入缓冲 */
const customAllergenInput = ref('')

/** 成员表单（弹窗内双向绑定） */
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

/** 保存按钮可用性：姓名非空 + 过敏原三选一满足 */
const canSaveMember = computed(
  () => memberForm.name.trim().length > 0 && (allergenFilled.value || memberForm.no_known_allergen),
)

/* ── PIPL 单独同意层状态 ── */

/** 同意层可见性 */
const consentVisible = ref(false)
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
  Object.assign(memberForm, {
    name: '',
    relation: '本人',
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
  customAllergenInput.value = ''
  memberDialogVisible.value = true
}

/**
 * 「暂无已知过敏原」切换：勾选时清空已选八类与自定义（互斥语义）。
 * @param checked 当前勾选值
 * @returns 无
 */
function onNoAllergenChange(checked: boolean): void {
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
  try {
    await postConsentSensitive('family_allergen')
    profileStore.sensitiveConsented = true
    try {
      localStorage.setItem(PIPL_CONSENT_KEY, '1')
    } catch {
      // 本地记忆失败不影响本次放行
    }
    consentVisible.value = false
    const save = pendingSave
    pendingSave = null
    await save?.()
  } catch (e) {
    // 落库失败：本地兜底放行（与免责同意同策略，不阻塞建档）
    ElMessage.warning('同意记录同步失败，已按本地同意处理')
    profileStore.sensitiveConsented = true
    try {
      localStorage.setItem(PIPL_CONSENT_KEY, '1')
    } catch {
      // 忽略
    }
    consentVisible.value = false
    const save = pendingSave
    pendingSave = null
    await save?.()
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
          <el-button type="primary" :icon="Plus" @click="openCreate">新增成员</el-button>
        </div>

        <el-empty
          v-if="(profileStore.family?.members?.length ?? 0) === 0"
          description="还没有成员，先添加「本人」，推荐会按你的过敏原与口味过滤"
          :image-size="80"
        />

        <div v-else class="member-list">
          <div v-for="m in profileStore.family?.members ?? []" :key="m.id" class="member-card">
            <div class="member-head">
              <span class="member-name">{{ m.name }}</span>
              <el-tag size="small" type="info">{{ m.relation }}</el-tag>
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

        <el-checkbox-group v-model="skillForm.equipment" class="equipment-group">
          <el-checkbox v-for="eq in EQUIPMENT_OPTIONS" :key="eq" :value="eq" :label="eq">
            {{ eq }}
          </el-checkbox>
        </el-checkbox-group>

        <el-button type="primary" :loading="profileStore.saving" @click="onSaveSkill">
          保存厨艺与设备
        </el-button>
      </div>

      <!-- ③ 饮食目标 -->
      <div class="profile-section">
        <h2 class="section-title">饮食目标</h2>

        <!-- 疾病相关强提示（选中慢病相关目标时强化文案） -->
        <el-alert
          class="profile-alert"
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

        <el-button type="primary" :loading="profileStore.saving" @click="onSaveGoal">
          保存饮食目标
        </el-button>
      </div>
    </template>

    <!-- 成员新增/编辑弹窗 -->
    <el-dialog
      v-model="memberDialogVisible"
      :title="editingId == null ? '新增成员' : '编辑成员'"
      width="560px"
      align-center
      destroy-on-close
    >
      <el-form label-position="top">
        <div class="form-row">
          <el-form-item label="姓名" required class="form-item">
            <el-input v-model="memberForm.name" maxlength="20" placeholder="如：妈妈" />
          </el-form-item>
          <el-form-item label="关系" class="form-item">
            <el-select v-model="memberForm.relation">
              <el-option v-for="r in RELATION_OPTIONS" :key="r" :label="r" :value="r" />
            </el-select>
          </el-form-item>
        </div>

        <!-- 过敏原：八类多选 + 自定义 + 暂无 开关（三选一） -->
        <el-form-item label="过敏原（八类，多选）">
          <el-checkbox-group v-model="memberForm.allergen_codes" :disabled="memberForm.no_known_allergen">
            <el-checkbox v-for="code in ALLERGEN_OPTIONS" :key="code" :value="code" :label="code">
              {{ allergenLabel(code) }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="其他过敏原（自定义）">
          <div class="custom-allergen-row">
            <el-input
              v-model="customAllergenInput"
              :disabled="memberForm.no_known_allergen"
              maxlength="20"
              placeholder="如：芒果，回车添加"
              @keyup.enter="addCustomAllergen"
            />
            <el-button :disabled="memberForm.no_known_allergen" @click="addCustomAllergen">添加</el-button>
          </div>
          <div v-if="memberForm.custom_allergens.length > 0" class="custom-tags">
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

        <el-form-item>
          <el-switch
            v-model="memberForm.no_known_allergen"
            active-text="暂无已知过敏原"
            @change="onNoAllergenChange"
          />
        </el-form-item>

        <!-- 口味三滑块 -->
        <div class="form-row">
          <el-form-item label="辣度" class="form-item">
            <el-slider v-model="memberForm.taste_spicy" :min="0" :max="2" :step="1" :marks="TASTE_MARKS" />
          </el-form-item>
          <el-form-item label="咸淡" class="form-item">
            <el-slider v-model="memberForm.taste_salt" :min="0" :max="2" :step="1" :marks="TASTE_MARKS" />
          </el-form-item>
          <el-form-item label="甜度" class="form-item">
            <el-slider v-model="memberForm.taste_sweet" :min="0" :max="2" :step="1" :marks="TASTE_MARKS" />
          </el-form-item>
        </div>

        <el-form-item label="忌口（可输入自定义）">
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

        <el-form-item label="特殊饮食">
          <el-checkbox-group v-model="memberForm.special_diet">
            <el-checkbox v-for="d in SPECIAL_DIET_OPTIONS" :key="d" :value="d" :label="d">
              {{ d }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="特殊人群">
          <el-checkbox-group v-model="memberForm.special_population">
            <el-checkbox v-for="p in SPECIAL_POPULATION_OPTIONS" :key="p" :value="p" :label="p">
              {{ p }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="memberDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!canSaveMember"
          :loading="profileStore.saving"
          @click="onSaveMember"
        >
          保存
        </el-button>
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
        <el-button type="primary" @click="onConsentAgree">同意并保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.profile-alert {
  margin-bottom: 14px;
}

.profile-skeleton {
  padding: 8px 0 24px;
}

.profile-section {
  padding: 18px 0;
  border-top: 1px solid var(--color-info-border);
}

.profile-section:first-of-type {
  border-top: none;
  padding-top: 4px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  margin: 0 0 12px;
  font-size: var(--font-lg);
  font-weight: 600;
  color: var(--text-main);
}

.section-head .section-title {
  margin-bottom: 0;
}

.section-hint {
  margin: 0 0 12px;
  font-size: var(--font-sm);
  color: var(--color-info);
}

/* ── 成员列表 ── */
.member-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.member-card {
  padding: 14px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
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

.member-summary {
  margin: 0 0 10px;
  font-size: var(--font-sm);
  line-height: 1.7;
  color: var(--color-info);
}

.member-actions {
  display: flex;
  gap: 8px;
}

/* ── 厨艺 ── */
.skill-level {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 14px;
}

.skill-label {
  flex-shrink: 0;
  font-size: var(--font-md);
  color: var(--text-main);
}

.skill-slider {
  flex: 1;
  margin: 0 18px 0 4px;
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
  gap: 4px 18px;
  margin-bottom: 16px;
}

/* ── 饮食目标 ── */
.goal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.goal-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
  background: var(--card-bg);
  text-align: left;
  cursor: pointer;
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
  color: var(--color-info);
}

.goal-note {
  margin-bottom: 14px;
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
</style>
