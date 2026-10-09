<script setup lang="ts">
/**
 * 视图职责：个人中心（Task 9 / 路由 /me）。
 * 区块：① 9 入口宫格（我的档案/我的收藏/烹饪历史/拿手菜/营养汇总 → 页内分区或外跳；
 *       会员中心/库存 → 外跳；设置 → 页内分区；反馈 → 触发全局 FeedbackFab 弹窗）；
 *       ② 收藏分区：分组 chips 过滤 + 列表 + 删除二次确认（el-popconfirm）；
 *       ③ 历史分区：倒序列表 + 「再做一次」（已选食材 → /recommend，否则引导回 /select）；
 *       ④ 拿手菜分区：烹饪次数 + 均分卡；
 *       ⑤ 营养汇总分区：近 7 天 kcal 柱状（el-progress）+ 三大营养素合计，
 *          缺失项灰字「未纳入统计」，底部估算值免责（DisclaimerBar nutrition 档）；
 *          手动补录外食弹窗（meal_type + 描述，命中风控展示拦截话术）；
 *       ⑥ 设置分区：字号 3 档（立即作用于本页 font-size CSS var）/ 单位 / 语音 / 提醒；
 *       ⑦ 数据权利：导出 JSON 下载 / 注销（二次确认 + 输入「注销」文字）。
 * 三态：各分区独立加载/空/异常；深色模式全变量适配。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { getNutritionSummary, postNutritionManual } from '@/api/endpoints'
import type {
  ApiError,
  NutritionSummaryResponse,
} from '@/api/types'
import { useMeStore } from '@/stores/me'
import { useIngredientsStore } from '@/stores/ingredients'
import DisclaimerBar from '@/components/DisclaimerBar.vue'

/** 路由（外跳与「再做一次」） */
const router = useRouter()
/** 个人中心 store */
const meStore = useMeStore()
/** 食材 store（「再做一次」判断是否可直接去推荐） */
const ingredientsStore = useIngredientsStore()

/** 页内激活分区（宫格点选切换；external 类入口直接路由跳转） */
type SectionKey = 'favorites' | 'history' | 'signature' | 'nutrition' | 'settings'
const activeSection = ref<SectionKey>('favorites')

/** 宫格入口配置 */
const GRID_ENTRIES: Array<{
  key: string
  icon: string
  title: string
  action: 'section' | 'route'
  target: string
}> = [
  { key: 'profile', icon: '👨‍👩‍👧', title: '我的档案', action: 'route', target: '/profile' },
  { key: 'favorites', icon: '⭐', title: '我的收藏', action: 'section', target: 'favorites' },
  { key: 'history', icon: '🕘', title: '烹饪历史', action: 'section', target: 'history' },
  { key: 'signature', icon: '🏆', title: '拿手菜', action: 'section', target: 'signature' },
  { key: 'nutrition', icon: '🥗', title: '营养汇总', action: 'section', target: 'nutrition' },
  { key: 'member', icon: '💎', title: '会员中心', action: 'route', target: '/member' },
  { key: 'inventory', icon: '🧊', title: '库存', action: 'route', target: '/inventory' },
  { key: 'settings', icon: '⚙️', title: '设置', action: 'section', target: 'settings' },
  { key: 'feedback', icon: '💬', title: '反馈', action: 'route', target: 'feedback' },
]

/**
 * 宫格入口点击：页内分区 / 路由跳转 / 触发全局反馈弹窗。
 * @param entry 宫格入口
 * @returns 无
 */
function onEntryClick(entry: (typeof GRID_ENTRIES)[number]): void {
  if (entry.action === 'section') {
    activeSection.value = entry.target as SectionKey
    return
  }
  if (entry.target === 'feedback') {
    // 复用全局 FeedbackFab 弹窗（事件名与组件内约定一致）
    window.dispatchEvent(new CustomEvent('aicook:open-feedback'))
    return
  }
  void router.push(entry.target)
}

/* ── 收藏 ── */

/** 当前收藏分组（'' = 全部） */
const favoriteGroup = ref('')

/**
 * 切换收藏分组（重拉该组）。
 * @param group 分组名
 * @returns 无
 */
function onGroupChange(group: string): void {
  favoriteGroup.value = group
  void meStore.loadFavorites(group || undefined)
}

/* ── 历史 ── */

/**
 * 「再做一次」：已选食材在库 → 直接去推荐；否则引导回选食材页。
 * @param recipeId 菜谱 ID
 * @returns 无
 */
function onCookAgain(recipeId: number): void {
  if (ingredientsStore.selectedCount > 0) {
    void router.push('/recommend')
    return
  }
  ElMessage.info('先选好食材，再去看看能做的菜（菜谱已为你记住）')
  void router.push({ path: '/select', query: { recipe_id: String(recipeId) } })
}

/**
 * 历史完成时间格式化（YYYY-MM-DD HH:mm）。
 * @param iso ISO 8601 时间
 * @returns 格式化文案（非法原样返回）
 */
function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/* ── 营养汇总 ── */

/** 汇总数据 */
const nutrition = ref<NutritionSummaryResponse | null>(null)
/** 加载中 */
const nutritionLoading = ref(false)
/** 加载错误 */
const nutritionError = ref<ApiError | null>(null)

/** 近 7 天逐日 kcal（柱状展示数据源：相对周内最大值归一） */
const dailyKcal = computed(() => {
  const days = nutrition.value?.days ?? []
  return days.map((d) => {
    const total =
      (d.meals.breakfast.kcal ?? 0) +
      (d.meals.lunch.kcal ?? 0) +
      (d.meals.dinner.kcal ?? 0) +
      (d.meals.snack.kcal ?? 0)
    return { date: d.date, kcal: total, hasData: total > 0 }
  })
})

/** 周内最大单日 kcal（柱状归一基数） */
const maxDailyKcal = computed(() => Math.max(1, ...dailyKcal.value.map((d) => d.kcal)))

/**
 * 拉取营养汇总。
 * @returns 无
 */
async function loadNutrition(): Promise<void> {
  nutritionLoading.value = true
  nutritionError.value = null
  try {
    nutrition.value = await getNutritionSummary(7)
  } catch (e) {
    nutritionError.value = e as ApiError
    nutrition.value = null
  } finally {
    nutritionLoading.value = false
  }
}

/** 手动补录弹窗可见性 */
const manualVisible = ref(false)
/** 餐次 */
const manualMealType = ref<'breakfast' | 'lunch' | 'dinner' | 'snack'>('lunch')
/** 描述 */
const manualDescription = ref('')
/** 提交中 */
const manualSubmitting = ref(false)

/** 餐次选项 */
const MEAL_OPTIONS: Array<{ value: 'breakfast' | 'lunch' | 'dinner' | 'snack'; label: string }> = [
  { value: 'breakfast', label: '早餐' },
  { value: 'lunch', label: '午餐' },
  { value: 'dinner', label: '晚餐' },
  { value: 'snack', label: '加餐' },
]

/**
 * 打开手动补录弹窗。
 * @returns 无
 */
function openManualDialog(): void {
  manualMealType.value = 'lunch'
  manualDescription.value = ''
  manualVisible.value = true
}

/**
 * 提交手动补录：正常 toast + 关闭；命中风控 → 弹窗内展示拦截话术。
 * @returns 无
 */
async function onManualSubmit(): Promise<void> {
  if (manualDescription.value.trim().length < 2) {
    ElMessage.warning('请简单描述这顿吃了什么')
    return
  }
  manualSubmitting.value = true
  try {
    const res = await postNutritionManual({
      meal_type: manualMealType.value,
      description: manualDescription.value.trim(),
    })
    if (res.blocked) {
      ElMessage.warning(`${res.title ?? '无法记录'}：${res.message ?? '内容未通过安全检查'}`)
      return
    }
    ElMessage.success('已记录，营养汇总稍后更新')
    manualVisible.value = false
    void loadNutrition()
  } catch (e) {
    ElMessage.error((e as ApiError).message || '记录失败，请重试')
  } finally {
    manualSubmitting.value = false
  }
}

/* ── 设置 ── */

/** 字号档位 → 像素映射（本页 CSS var 立即生效） */
const FONT_SIZE_MAP: Record<'normal' | 'large' | 'xlarge', string> = {
  normal: '16px',
  large: '18px',
  xlarge: '20px',
}

/** 本页根字号（CSS var --me-font-size，随设置即时变化） */
const meFontSize = computed(() => {
  const fs = meStore.settings?.font_size ?? 'normal'
  return FONT_SIZE_MAP[fs] ?? '16px'
})

/** 设置本地缓冲 */
const settingsForm = ref({
  font_size: 'normal' as 'normal' | 'large' | 'xlarge',
  unit: 'metric' as 'metric' | 'imperial',
  voice_enabled: false,
  reminder_enabled: false,
})

/**
 * 保存设置（PUT /v1/settings；字号档位经由 computed 即时生效）。
 * @returns 无
 */
async function onSaveSettings(): Promise<void> {
  try {
    await meStore.saveSettings({ ...settingsForm.value })
    ElMessage.success('设置已保存')
  } catch (e) {
    ElMessage.error((e as ApiError).message || '保存失败，请重试')
  }
}

/* ── 数据权利 ── */

/**
 * 导出个人数据：取 JSON → 触发浏览器下载 aicook_export.json。
 * @returns 无
 */
async function onExport(): Promise<void> {
  try {
    const data = await meStore.exportData()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `aicook_export_${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出已开始下载')
  } catch (e) {
    ElMessage.error((e as ApiError).message || '导出失败，请重试')
  }
}

/**
 * 注销账号：二次确认 + 输入「注销」文字确认 → DELETE /v1/me。
 * @returns 无
 */
async function onDeleteAccount(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '注销将删除你的档案、库存、收藏等全部数据，且不可恢复。确认继续？',
      '注销账号',
      { confirmButtonText: '下一步', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const { value } = await ElMessageBox.prompt('请输入「注销」以确认操作', '二次确认', {
      confirmButtonText: '确认注销',
      cancelButtonText: '取消',
      inputPattern: /^注销$/,
      inputErrorMessage: '输入不一致，请输入「注销」',
    })
    if (value !== '注销') return
    await meStore.deleteAccount()
    ElMessage.success('账号已注销，感谢你的使用')
  } catch (e) {
    if ((e as ApiError).code !== 'cancel' && (e as ApiError).code !== 'close') {
      ElMessage.error((e as ApiError).message || '注销失败，请重试')
    }
  }
}

/** 切到营养分区时懒加载汇总数据 */
watch(activeSection, (sec) => {
  if (sec === 'nutrition' && !nutrition.value && !nutritionLoading.value) {
    void loadNutrition()
  }
})

// 挂载：拉收藏 / 历史 / 拿手菜 / 设置（并行，互不阻塞）
onMounted(() => {
  void meStore.loadFavorites()
  void meStore.loadHistory()
  void meStore.loadSignature()
  void meStore.loadSettings().then(() => {
    if (meStore.settings) {
      settingsForm.value = { ...meStore.settings }
    }
  })
})
</script>

<template>
  <section class="page-card me-page" :style="{ '--me-font-size': meFontSize }">
    <h1 class="page-title">我的</h1>

    <!-- ① 9 入口宫格 -->
    <div class="me-grid">
      <button
        v-for="entry in GRID_ENTRIES"
        :key="entry.key"
        type="button"
        class="me-grid-item"
        :class="{ 'me-grid-item--active': entry.action === 'section' && entry.target === activeSection }"
        @click="onEntryClick(entry)"
      >
        <span class="me-grid-icon">{{ entry.icon }}</span>
        <span class="me-grid-title">{{ entry.title }}</span>
      </button>
    </div>

    <!-- ═══ 收藏分区 ═══ -->
    <div v-if="activeSection === 'favorites'" class="me-section">
      <h2 class="section-title">我的收藏</h2>

      <!-- 分组 chips -->
      <div class="chip-bar">
        <el-check-tag :checked="favoriteGroup === ''" @change="onGroupChange('')">全部</el-check-tag>
        <el-check-tag
          v-for="g in meStore.favoriteGroups"
          :key="g"
          :checked="favoriteGroup === g"
          @change="onGroupChange(g)"
        >
          {{ g }}
        </el-check-tag>
      </div>

      <el-alert
        v-if="meStore.favoritesError"
        type="error"
        :title="meStore.favoritesError.message"
        :closable="false"
        show-icon
        class="me-alert"
      >
        <el-button size="small" type="primary" plain @click="meStore.loadFavorites(favoriteGroup || undefined)">
          重试
        </el-button>
      </el-alert>

      <div v-else-if="meStore.favoritesLoading" class="me-skeleton">
        <el-skeleton :rows="4" animated />
      </div>

      <el-empty v-else-if="meStore.favorites.length === 0" description="还没有收藏，菜谱详情里可以收藏" />

      <div v-else class="fav-list">
        <div v-for="f in meStore.favorites" :key="f.recipe_id" class="fav-item">
          <span class="fav-emoji">{{ f.cover_emoji ?? '🍽️' }}</span>
          <div class="fav-info">
            <span class="fav-name">{{ f.recipe_name }}</span>
            <span class="fav-group">{{ f.group_name }}</span>
          </div>
          <div class="fav-actions">
            <el-button size="small" @click="router.push(`/recipe/${f.recipe_id}`)">看菜谱</el-button>
            <el-popconfirm
              title="确认取消收藏？"
              confirm-button-text="取消收藏"
              cancel-button-text="再想想"
              @confirm="meStore.removeFavorite(f.recipe_id)"
            >
              <template #reference>
                <el-button size="small" type="danger" plain>删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 历史分区 ═══ -->
    <div v-else-if="activeSection === 'history'" class="me-section">
      <h2 class="section-title">烹饪历史</h2>

      <el-alert
        v-if="meStore.historyError"
        type="error"
        :title="meStore.historyError.message"
        :closable="false"
        show-icon
        class="me-alert"
      >
        <el-button size="small" type="primary" plain @click="meStore.loadHistory()">重试</el-button>
      </el-alert>

      <div v-else-if="meStore.historyLoading" class="me-skeleton">
        <el-skeleton :rows="4" animated />
      </div>

      <el-empty v-else-if="meStore.history.length === 0" description="还没有做过的菜，从推荐里挑一道开始吧" />

      <div v-else class="hist-list">
        <div v-for="h in meStore.history" :key="h.session_id" class="hist-item">
          <div class="hist-info">
            <span class="hist-name">{{ h.recipe_name }}</span>
            <span class="hist-time">{{ formatTime(h.finished_at) }}</span>
          </div>
          <div class="hist-actions">
            <el-rate
              v-if="h.rating"
              :model-value="h.rating"
              disabled
              size="small"
              class="hist-rate"
            />
            <el-button size="small" type="primary" plain @click="onCookAgain(h.recipe_id)">
              再做一次
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 拿手菜分区 ═══ -->
    <div v-else-if="activeSection === 'signature'" class="me-section">
      <h2 class="section-title">拿手菜</h2>

      <el-alert
        v-if="meStore.signatureError"
        type="error"
        :title="meStore.signatureError.message"
        :closable="false"
        show-icon
        class="me-alert"
      >
        <el-button size="small" type="primary" plain @click="meStore.loadSignature()">重试</el-button>
      </el-alert>

      <div v-else-if="meStore.signatureLoading" class="me-skeleton">
        <el-skeleton :rows="3" animated />
      </div>

      <el-empty v-else-if="meStore.signature.length === 0" description="多做饭，你的拿手菜会出现在这里" />

      <div v-else class="sig-list">
        <div v-for="s in meStore.signature" :key="s.recipe_id" class="sig-card" role="button" @click="router.push(`/recipe/${s.recipe_id}`)">
          <span class="sig-name">{{ s.recipe_name }}</span>
          <span class="sig-count">做过 {{ s.cook_count }} 次</span>
          <div class="sig-rating">
            <span class="sig-rating-label">平均分</span>
            <el-rate v-if="s.avg_rating != null" :model-value="s.avg_rating" disabled size="small" />
            <span v-else class="me-muted">暂无评分</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 营养汇总分区 ═══ -->
    <div v-else-if="activeSection === 'nutrition'" class="me-section">
      <div class="section-head-row">
        <h2 class="section-title">营养汇总（近 7 天）</h2>
        <el-button size="small" @click="openManualDialog">补录外食</el-button>
      </div>

      <el-alert
        v-if="nutritionError"
        type="error"
        :title="nutritionError.message"
        :closable="false"
        show-icon
        class="me-alert"
      >
        <el-button size="small" type="primary" plain @click="loadNutrition">重试</el-button>
      </el-alert>

      <div v-else-if="nutritionLoading" class="me-skeleton">
        <el-skeleton :rows="5" animated />
      </div>

      <el-empty v-else-if="!nutrition || nutrition.days.length === 0" description="近 7 天暂无饮食记录" />

      <template v-else>
        <!-- 逐日 kcal 柱状（el-progress 归一周内最大值） -->
        <div class="kcal-chart">
          <div v-for="d in dailyKcal" :key="d.date" class="kcal-row">
            <span class="kcal-date">{{ d.date.slice(5) }}</span>
            <el-progress
              class="kcal-bar"
              :percentage="Math.round((d.kcal / maxDailyKcal) * 100)"
              :stroke-width="14"
              :format="() => (d.hasData ? `${d.kcal} kcal` : '')"
            />
            <span v-if="!d.hasData" class="me-muted kcal-miss">未纳入统计</span>
          </div>
        </div>

        <!-- 合计：三大营养素 + 钠（缺失灰字） -->
        <div class="nutri-grid">
          <div class="nutri-card">
            <span class="nutri-label">蛋白质合计</span>
            <span v-if="nutrition.totals.protein != null" class="nutri-value">{{ nutrition.totals.protein }} g</span>
            <span v-else class="me-muted">未纳入统计</span>
          </div>
          <div class="nutri-card">
            <span class="nutri-label">脂肪合计</span>
            <span v-if="nutrition.totals.fat != null" class="nutri-value">{{ nutrition.totals.fat }} g</span>
            <span v-else class="me-muted">未纳入统计</span>
          </div>
          <div class="nutri-card">
            <span class="nutri-label">碳水合计</span>
            <span v-if="nutrition.totals.carb != null" class="nutri-value">{{ nutrition.totals.carb }} g</span>
            <span v-else class="me-muted">未纳入统计</span>
          </div>
          <div class="nutri-card">
            <span class="nutri-label">钠合计</span>
            <span v-if="nutrition.totals.sodium != null" class="nutri-value">{{ nutrition.totals.sodium }} mg</span>
            <span v-else class="me-muted">未纳入统计</span>
          </div>
        </div>

        <!-- 未纳入统计食材说明 -->
        <p v-if="nutrition.excluded.length > 0" class="excluded-note">
          以下食材缺少营养数据，未纳入统计：{{ nutrition.excluded.join('、') }}
        </p>

        <!-- 估算值免责 -->
        <DisclaimerBar variant="nutrition" />
      </template>
    </div>

    <!-- ═══ 设置分区 ═══ -->
    <div v-else-if="activeSection === 'settings'" class="me-section">
      <h2 class="section-title">设置</h2>

      <el-alert
        v-if="meStore.settingsError"
        type="error"
        :title="meStore.settingsError.message"
        :closable="false"
        show-icon
        class="me-alert"
      />

      <div class="setting-row">
        <span class="setting-label">字号</span>
        <el-radio-group v-model="settingsForm.font_size">
          <el-radio-button value="normal">标准</el-radio-button>
          <el-radio-button value="large">大</el-radio-button>
          <el-radio-button value="xlarge">特大</el-radio-button>
        </el-radio-group>
      </div>

      <div class="setting-row">
        <span class="setting-label">计量单位</span>
        <el-radio-group v-model="settingsForm.unit">
          <el-radio-button value="metric">公制（g / ml）</el-radio-button>
          <el-radio-button value="imperial">英制（oz / lb）</el-radio-button>
        </el-radio-group>
      </div>

      <div class="setting-row">
        <span class="setting-label">语音播报步骤</span>
        <el-switch v-model="settingsForm.voice_enabled" />
      </div>

      <div class="setting-row">
        <span class="setting-label">做菜提醒</span>
        <el-switch v-model="settingsForm.reminder_enabled" />
      </div>

      <el-button
        type="primary"
        :loading="meStore.settingsSaving"
        class="setting-save"
        @click="onSaveSettings"
      >
        保存设置
      </el-button>

      <!-- 数据权利 -->
      <el-divider />
      <h3 class="sub-title">我的数据</h3>
      <div class="setting-row">
        <span class="setting-label">数据导出</span>
        <el-button :icon="Download" @click="onExport">导出我的数据（JSON）</el-button>
      </div>
      <div class="setting-row">
        <span class="setting-label">注销账号</span>
        <el-button type="danger" plain @click="onDeleteAccount">注销并删除全部数据</el-button>
      </div>
    </div>
  </section>

  <!-- 手动补录外食弹窗 -->
  <el-dialog v-model="manualVisible" title="补录外食" width="440px" align-center>
    <el-form label-position="top">
      <el-form-item label="餐次">
        <el-radio-group v-model="manualMealType">
          <el-radio-button v-for="m in MEAL_OPTIONS" :key="m.value" :value="m.value">
            {{ m.label }}
          </el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="吃了什么" required>
        <el-input
          v-model="manualDescription"
          type="textarea"
          :rows="3"
          maxlength="200"
          placeholder="如：午餐在公司楼下吃了一碗牛肉面"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="manualVisible = false">取消</el-button>
      <el-button type="primary" :loading="manualSubmitting" @click="onManualSubmit">记录</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* 本页字号 var（字号档位立即生效） */
.me-page {
  font-size: var(--me-font-size, 16px);
}

/* ── 宫格 ── */
.me-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 10px;
  margin-bottom: 20px;
}

.me-grid-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 14px 6px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
  background: var(--card-bg);
  cursor: pointer;
}

.me-grid-item--active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.me-grid-icon {
  font-size: 24px;
}

.me-grid-title {
  font-size: 13px;
  color: var(--text-main);
}

/* ── 分区通用 ── */
.me-section {
  padding-top: 6px;
  border-top: 1px solid var(--color-info-border);
}

.section-title {
  margin: 0 0 14px;
  font-size: var(--font-lg);
  font-weight: 600;
  color: var(--text-main);
}

.section-head-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.section-head-row .section-title {
  margin-bottom: 0;
}

.me-alert {
  margin-bottom: 12px;
}

.me-skeleton {
  padding: 6px 0 12px;
}

.me-muted {
  font-size: var(--font-sm);
  color: var(--color-info);
}

/* ── 收藏 ── */
.chip-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}

.fav-list,
.hist-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.fav-item,
.hist-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
}

.fav-emoji {
  font-size: 22px;
}

.fav-info,
.hist-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.fav-name,
.hist-name {
  font-weight: 600;
  color: var(--text-main);
}

.fav-group,
.hist-time {
  font-size: var(--font-sm);
  color: var(--color-info);
}

.fav-actions,
.hist-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.hist-rate {
  margin-right: 4px;
}

/* ── 拿手菜 ── */
.sig-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.sig-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
  cursor: pointer;
}

.sig-name {
  font-weight: 600;
  color: var(--text-main);
}

.sig-count {
  font-size: var(--font-sm);
  color: var(--color-info);
}

.sig-rating {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sig-rating-label {
  font-size: var(--font-sm);
  color: var(--color-info);
}

/* ── 营养 ── */
.kcal-chart {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.kcal-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.kcal-date {
  flex-shrink: 0;
  width: 46px;
  font-size: var(--font-sm);
  color: var(--color-info);
}

.kcal-bar {
  flex: 1;
}

.kcal-miss {
  flex-shrink: 0;
}

.nutri-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.nutri-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
}

.nutri-label {
  font-size: var(--font-sm);
  color: var(--color-info);
}

.nutri-value {
  font-size: var(--font-lg);
  font-weight: 700;
  color: var(--text-main);
}

.excluded-note {
  margin: 0 0 10px;
  font-size: var(--font-sm);
  color: var(--color-info);
}

/* ── 设置 ── */
.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 0;
}

.setting-label {
  font-size: var(--me-font-size, 16px);
  color: var(--text-main);
}

.setting-save {
  margin-top: 8px;
}

.sub-title {
  margin: 0 0 6px;
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
}
</style>
