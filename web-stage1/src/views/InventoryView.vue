<script setup lang="ts">
/**
 * 视图职责：我的冰箱 + 购物清单页（Task 9 / 路由 /inventory，双 Tab）。
 * Tab1 我的冰箱：库存列表（档位 tag 有/少量/充足、到期倒计时、致敏原红字、
 *   编辑/删除/标记用完）、临期置顶排序、新增条目（食材远程搜索选择器）；
 * Tab2 购物清单：勾选、删除、一键转入库存、清空已购、新增条目；
 * 扣减建议：「烹饪后记录消耗」入口 → deduct-suggest 拉建议 → 用户勾选 →
 *   deduct-confirm 确认（会话 ID 可从烹饪历史查看）。
 * 三态：加载 = 骨架；空 = 引导文案；异常 = el-alert + 重试；深色模式全变量适配。
 * P0 修复（2026-10-09 测试报告）：
 *   H1 —— 存放位置改为后端枚举 fridge/freezer/room/dry 提交（原提交中文标签必现 422），
 *         选项/提交/回显统一走 utils/inventory 的 LOCATION_OPTIONS；
 *   L4-2 —— 列表位置列经 locationLabel() 转中文展示；
 *   H1b —— 库存/购物清单食材选择改远程搜索（GET /v1/ingredients?q=，≥300ms 去抖，
 *         首屏仍加载默认列表，仅用户输入时走远程，支持别名如「柴鸡蛋」）；
 *   1.3 —— 422 时经 format422Detail() 解析后端 detail 拼进 toast 透出具体字段信息。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  getIngredients,
  postDeductConfirm,
  postDeductSuggest,
  type IngredientListResponse,
} from '@/api/endpoints'
import type {
  ApiError,
  DeductSuggestion,
  Ingredient,
  InventoryItem,
  StorageLocation,
} from '@/api/types'
import { useInventoryStore } from '@/stores/inventory'
import { allergenLabel } from '@/utils/recipe'
import { LOCATION_OPTIONS, locationLabel } from '@/utils/inventory'
import { format422Detail } from '@/utils/apiError'

/** 库存 store */
const inventoryStore = useInventoryStore()

/** 当前激活 Tab：fridge 我的冰箱 / shopping 购物清单 */
const activeTab = ref<'fridge' | 'shopping'>('fridge')

/** 数量档位中文映射 */
const LEVEL_LABELS: Record<InventoryItem['quantity_level'], string> = {
  low: '少量',
  mid: '有',
  plenty: '充足',
}

/** 档位 tag 语义色映射 */
const LEVEL_TAG_TYPES: Record<InventoryItem['quantity_level'], 'warning' | 'info' | 'success'> = {
  low: 'warning',
  mid: 'info',
  plenty: 'success',
}

/**
 * 到期倒计时文案（负数 = 已过期）。
 * @param expireDate 到期日 YYYY-MM-DD
 * @returns 展示文案
 */
function expireText(expireDate: string): string {
  const days = daysLeft(expireDate)
  if (!Number.isFinite(days)) return '未设置'
  if (days < 0) return `已过期 ${Math.abs(days)} 天`
  if (days === 0) return '今天到期'
  return `还剩 ${days} 天`
}

/**
 * 计算到期日剩余天数（本地时区，负数为已过期）。
 * @param expireDate 到期日 YYYY-MM-DD
 * @returns 天数（非法返回正无穷）
 */
function daysLeft(expireDate: string): number {
  if (!expireDate) return Number.POSITIVE_INFINITY
  const target = new Date(`${expireDate}T00:00:00`)
  if (Number.isNaN(target.getTime())) return Number.POSITIVE_INFINITY
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((target.getTime() - today.getTime()) / 86400000)
}

/** 临期置顶排序：剩余天数升序（临期/过期在前，无到期日垫底） */
const sortedItems = computed(() =>
  [...inventoryStore.items].sort((a, b) => daysLeft(a.expire_date) - daysLeft(b.expire_date)),
)

/* ── 新增/编辑条目弹窗 ── */

/** 弹窗可见性 */
const itemDialogVisible = ref(false)
/** 正在编辑的条目 ID（null = 新增） */
const editingId = ref<number | null>(null)
/** 食材候选列表（首屏默认列表，GET /v1/ingredients 无参拉取常用/分类数据） */
const ingredientOptions = ref<Ingredient[]>([])
/** 食材候选加载中（首屏拉取与远程搜索共用） */
const ingredientsLoading = ref(false)
/** 提交中 */
const itemSubmitting = ref(false)

/** 远程搜索关键词（非空 = 下拉展示远程搜索结果，空 = 回落默认列表） */
const searchKeyword = ref('')
/** 远程搜索结果列表 */
const searchResults = ref<Ingredient[]>([])
/** 搜索去抖计时器（模块内私有，无需响应式） */
let searchTimer: ReturnType<typeof setTimeout> | null = null
/** 搜索请求序号（竞态守卫：仅最新一次请求的结果允许写入，防慢响应覆盖新结果） */
let searchSeq = 0

/**
 * 下拉实际展示的食材候选：用户输入过关键词时展示远程搜索结果，否则展示首屏默认列表。
 */
const ingredientDisplayOptions = computed<Ingredient[]>(() =>
  searchKeyword.value ? searchResults.value : ingredientOptions.value,
)

/** 条目表单 */
const itemForm = reactive({
  ingredient_id: undefined as number | undefined,
  quantity_level: 'mid' as InventoryItem['quantity_level'],
  expire_date: '',
  // 存放位置必须提交后端枚举（fridge/freezer/room/dry），中文标签仅由 LOCATION_OPTIONS 渲染
  location: 'fridge' as StorageLocation,
})

/**
 * 重置食材远程搜索状态（清去抖计时器与关键词，下拉回落默认列表）。
 * 弹窗打开时调用，避免上一次搜索结果残留影响本次选择。
 * @returns 无
 */
function resetIngredientSearch(): void {
  if (searchTimer) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
  searchKeyword.value = ''
  searchResults.value = []
}

/**
 * 食材远程搜索（el-select 的 remote-method 回调，≥300ms 去抖）。
 * 空关键词（如打开下拉未输入）直接回落默认列表，不发请求；
 * 非空关键词去抖后走 doSearch 调 GET /v1/ingredients?q=（后端含别名匹配，如「柴鸡蛋」）。
 * @param query 用户在下拉框输入的关键词（Element Plus 传入，可能为空串）
 * @returns 无
 */
function searchIngredients(query: string): void {
  if (searchTimer) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
  const keyword = query.trim()
  if (!keyword) {
    searchKeyword.value = ''
    searchResults.value = []
    return
  }
  searchKeyword.value = keyword
  // 去抖 300ms：连续输入只发最后一次请求
  searchTimer = setTimeout(() => {
    void doSearch(keyword)
  }, 300)
}

/**
 * 执行远程食材检索（GET /v1/ingredients?q=keyword）。
 * @param keyword 已去抖的搜索关键词
 * @returns 无
 */
async function doSearch(keyword: string): Promise<void> {
  const seq = ++searchSeq
  ingredientsLoading.value = true
  try {
    const res: IngredientListResponse = await getIngredients({ q: keyword })
    // 竞态守卫：仅最新一次请求的结果允许写入
    if (seq === searchSeq) searchResults.value = res.items ?? []
  } catch (e) {
    if (seq === searchSeq) {
      searchResults.value = []
      ElMessage.error((e as ApiError).message || '食材搜索失败，请重试')
    }
  } finally {
    if (seq === searchSeq) ingredientsLoading.value = false
  }
}

/**
 * 编辑回显兜底：条目食材可能不在当前候选列表（如不在首屏 100 条内），
 * 补入最小候选项，避免 el-select 只显示食材 ID 而非名称。
 * @param id 食材 ID
 * @param name 食材名称（取自库存条目冗余字段 ingredient_name）
 * @returns 无
 */
function ensureIngredientOption(id: number, name: string): void {
  if (ingredientOptions.value.some((i) => i.id === id)) return
  ingredientOptions.value = [...ingredientOptions.value, { id, name, category: '' }]
}

/**
 * 打开新增/编辑弹窗并拉取食材候选（按当前食材库分类接口）。
 * @param item 待编辑条目（null = 新增）
 * @returns 无
 */
async function openItemDialog(item: InventoryItem | null): Promise<void> {
  editingId.value = item ? item.id : null
  resetIngredientSearch()
  if (item) {
    itemForm.ingredient_id = item.ingredient_id
    itemForm.quantity_level = item.quantity_level
    itemForm.expire_date = item.expire_date
    // 位置枚举直接回显，与 LOCATION_OPTIONS 的 value 一一对应即可正确选中
    itemForm.location = item.location || 'fridge'
    // 编辑回显兜底：条目食材可能不在默认候选里，补入避免只显示 ID
    ensureIngredientOption(item.ingredient_id, item.ingredient_name)
  } else {
    itemForm.ingredient_id = undefined
    itemForm.quantity_level = 'mid'
    itemForm.expire_date = ''
    itemForm.location = 'fridge'
  }
  itemDialogVisible.value = true
  if (ingredientOptions.value.length === 0) {
    ingredientsLoading.value = true
    try {
      const res: IngredientListResponse = await getIngredients()
      ingredientOptions.value = res.items ?? []
    } catch (e) {
      ElMessage.error((e as ApiError).message || '食材列表加载失败')
    } finally {
      ingredientsLoading.value = false
    }
  }
}

/**
 * 提交新增/编辑条目（位置字段提交后端枚举值）。
 * @returns 无
 */
async function onItemSubmit(): Promise<void> {
  if (itemForm.ingredient_id == null) {
    ElMessage.warning('请选择食材')
    return
  }
  itemSubmitting.value = true
  try {
    if (editingId.value == null) {
      await inventoryStore.addItem({
        ingredient_id: itemForm.ingredient_id,
        quantity_level: itemForm.quantity_level,
        expire_date: itemForm.expire_date || undefined,
        location: itemForm.location,
      })
      ElMessage.success('已加入冰箱')
    } else {
      await inventoryStore.patchItem(editingId.value, {
        quantity_level: itemForm.quantity_level,
        expire_date: itemForm.expire_date || undefined,
        location: itemForm.location,
      })
      ElMessage.success('已更新')
    }
    itemDialogVisible.value = false
  } catch (e) {
    const apiErr = e as ApiError
    // 422 时透传后端 detail 的具体字段信息（如「存放位置：值必须是 fridge/freezer/room/dry 之一」）
    const extra = format422Detail(apiErr)
    ElMessage.error(extra ? `${apiErr.message || '保存失败，请重试'}：${extra}` : apiErr.message || '保存失败，请重试')
  } finally {
    itemSubmitting.value = false
  }
}

/**
 * 标记条目用完。
 * @param item 目标条目
 * @returns 无
 */
async function onMarkUsed(item: InventoryItem): Promise<void> {
  try {
    await inventoryStore.markUsed(item.id)
    ElMessage.success(`已将「${item.ingredient_name}」标记为用完`)
  } catch (e) {
    ElMessage.error((e as ApiError).message || '操作失败，请重试')
  }
}

/**
 * 删除条目（二次确认）。
 * @param item 目标条目
 * @returns 无
 */
async function onDeleteItem(item: InventoryItem): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认从冰箱删除「${item.ingredient_name}」？`, '删除库存', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await inventoryStore.removeItem(item.id)
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error((e as ApiError).message || '删除失败，请重试')
  }
}

/* ── 购物清单 ── */

/** 新增购物条目表单 */
const shoppingForm = reactive({
  ingredient_id: undefined as number | undefined,
  quantity_note: '',
})

/** 购物新增弹窗可见性 */
const shoppingDialogVisible = ref(false)

/**
 * 打开购物新增弹窗（复用食材候选与远程搜索）。
 * @returns 无
 */
async function openShoppingDialog(): Promise<void> {
  shoppingForm.ingredient_id = undefined
  shoppingForm.quantity_note = ''
  resetIngredientSearch()
  shoppingDialogVisible.value = true
  if (ingredientOptions.value.length === 0) {
    ingredientsLoading.value = true
    try {
      const res: IngredientListResponse = await getIngredients()
      ingredientOptions.value = res.items ?? []
    } catch (e) {
      ElMessage.error((e as ApiError).message || '食材列表加载失败')
    } finally {
      ingredientsLoading.value = false
    }
  }
}

/**
 * 提交新增购物条目。
 * @returns 无
 */
async function onShoppingSubmit(): Promise<void> {
  if (shoppingForm.ingredient_id == null) {
    ElMessage.warning('请选择食材')
    return
  }
  const ing = ingredientDisplayOptions.value.find((i) => i.id === shoppingForm.ingredient_id)
  try {
    await inventoryStore.addShopping({
      items: [
        {
          ingredient_id: shoppingForm.ingredient_id,
          quantity_note: shoppingForm.quantity_note.trim() || '1 份',
          from_recipe_name: undefined,
        },
      ],
    })
    ElMessage.success(`已把「${ing?.name ?? '食材'}」加入购物清单`)
    shoppingDialogVisible.value = false
  } catch (e) {
    const apiErr = e as ApiError
    // 422 时透传后端 detail 的具体字段信息（如数量备注超长）
    const extra = format422Detail(apiErr)
    ElMessage.error(extra ? `${apiErr.message || '添加失败，请重试'}：${extra}` : apiErr.message || '添加失败，请重试')
  }
}

/**
 * 购物条目一键转入库存。
 * @param item 目标条目
 * @returns 无
 */
async function onToInventory(item: import('@/api/types').ShoppingItem): Promise<void> {
  try {
    await inventoryStore.toInventory(item.id)
    ElMessage.success(`「${item.ingredient_name}」已转入冰箱`)
  } catch (e) {
    ElMessage.error((e as ApiError).message || '转入失败，请重试')
  }
}

/**
 * 清空已购（勾选条目）。
 * @returns 无
 */
async function onClearChecked(): Promise<void> {
  const checkedCount = inventoryStore.shoppingItems.filter((it) => it.checked).length
  if (checkedCount === 0) {
    ElMessage.info('还没有勾选已购条目')
    return
  }
  try {
    await ElMessageBox.confirm(`确认清空 ${checkedCount} 条已购条目？`, '清空已购', {
      confirmButtonText: '清空',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await inventoryStore.clearChecked()
    ElMessage.success('已清空已购条目')
  } catch (e) {
    ElMessage.error((e as ApiError).message || '操作失败，请重试')
  }
}

/* ── 烹饪后扣减建议 ── */

/** 扣减弹窗可见性 */
const deductVisible = ref(false)
/** 会话 ID 输入（deduct-suggest 入参） */
const deductSessionId = ref('')
/** 建议列表 */
const suggestions = ref<DeductSuggestion[]>([])
/** 用户勾选（item_id → 勾选） */
const suggestionChecked = ref<Record<number, boolean>>({})
/** 建议加载中 */
const suggestLoading = ref(false)
/** 确认提交中 */
const confirmLoading = ref(false)

/**
 * 打开扣减建议弹窗。
 * @returns 无
 */
function openDeductDialog(): void {
  suggestions.value = []
  suggestionChecked.value = {}
  deductSessionId.value = ''
  deductVisible.value = true
}

/**
 * 拉取扣减建议（deduct-suggest）。
 * @returns 无
 */
async function onLoadSuggestions(): Promise<void> {
  const sid = deductSessionId.value.trim()
  if (!sid) {
    ElMessage.warning('请输入本次烹饪的会话 ID')
    return
  }
  suggestLoading.value = true
  try {
    const res = await postDeductSuggest(sid)
    suggestions.value = res.suggestions ?? []
    suggestionChecked.value = Object.fromEntries((res.suggestions ?? []).map((s) => [s.item_id, true]))
    if ((res.suggestions ?? []).length === 0) {
      ElMessage.info('本次烹饪无需扣减库存')
    }
  } catch (e) {
    ElMessage.error((e as ApiError).message || '建议获取失败，请重试')
  } finally {
    suggestLoading.value = false
  }
}

/**
 * 提交勾选确认（deduct-confirm）。
 * @returns 无
 */
async function onConfirmDeduct(): Promise<void> {
  const confirmations = suggestions.value
    .filter((s) => suggestionChecked.value[s.item_id])
    .map((s) => ({ item_id: s.item_id, action: s.suggest_action }))
  if (confirmations.length === 0) {
    ElMessage.warning('请至少勾选一条要扣减的食材')
    return
  }
  confirmLoading.value = true
  try {
    await postDeductConfirm({ session_id: deductSessionId.value.trim(), confirmations })
    ElMessage.success('库存已按确认扣减')
    deductVisible.value = false
    await inventoryStore.loadItems()
  } catch (e) {
    ElMessage.error((e as ApiError).message || '确认失败，请重试')
  } finally {
    confirmLoading.value = false
  }
}

/**
 * 重试当前 Tab 数据。
 * @returns 无
 */
function retry(): void {
  if (activeTab.value === 'fridge') void inventoryStore.loadItems()
  else void inventoryStore.loadShopping()
}

// 挂载：双列表并行拉取
onMounted(() => {
  void inventoryStore.loadItems()
  void inventoryStore.loadShopping()
})
</script>

<template>
  <section class="page-card inventory-page">
    <h1 class="page-title">我的冰箱</h1>

    <el-tabs v-model="activeTab">
      <!-- ═══ Tab1 我的冰箱 ═══ -->
      <el-tab-pane label="我的冰箱" name="fridge">
        <div class="tab-toolbar">
          <el-button type="primary" :icon="Plus" @click="openItemDialog(null)">新增条目</el-button>
          <el-button @click="openDeductDialog">烹饪后记录消耗</el-button>
        </div>

        <!-- 异常 / 加载 / 空 / 列表 -->
        <el-alert
          v-if="inventoryStore.error"
          type="error"
          :title="inventoryStore.error.message"
          :closable="false"
          show-icon
          class="inv-alert"
        >
          <el-button size="small" type="primary" plain @click="retry">重试</el-button>
        </el-alert>

        <div v-else-if="inventoryStore.loading" class="inv-skeleton">
          <el-skeleton :rows="6" animated />
        </div>

        <el-empty
          v-else-if="sortedItems.length === 0"
          description="冰箱空空的，把买回来的食材记进来，推荐与临期提醒才有依据"
        />

        <div v-else class="inv-list">
          <div
            v-for="item in sortedItems"
            :key="item.id"
            class="inv-item"
            :class="{ 'inv-item--urgent': daysLeft(item.expire_date) <= 3 }"
          >
            <div class="inv-main">
              <div class="inv-line">
                <span class="inv-name">{{ item.ingredient_name }}</span>
                <el-tag size="small" :type="LEVEL_TAG_TYPES[item.quantity_level]">
                  {{ LEVEL_LABELS[item.quantity_level] }}
                </el-tag>
                <el-tag v-if="daysLeft(item.expire_date) <= 3" size="small" type="danger">
                  {{ expireText(item.expire_date) }}
                </el-tag>
                <span v-else class="inv-expire">到期 {{ item.expire_date }}（{{ expireText(item.expire_date) }}）</span>
              </div>
              <div class="inv-line inv-meta">
                <!-- L4-2：位置枚举经 locationLabel 统一转中文展示 -->
                <span>{{ locationLabel(item.location) }}</span>
                <span v-if="item.allergen_codes.length > 0" class="inv-allergen">
                  ⚠ 致敏原：{{ item.allergen_codes.map((c) => allergenLabel(c)).join('、') }}
                </span>
              </div>
            </div>
            <div class="inv-actions">
              <el-button size="small" @click="openItemDialog(item)">编辑</el-button>
              <el-button size="small" type="success" plain @click="onMarkUsed(item)">标记用完</el-button>
              <el-button size="small" type="danger" plain @click="onDeleteItem(item)">删除</el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- ═══ Tab2 购物清单 ═══ -->
      <el-tab-pane name="shopping">
        <template #label>
          购物清单
          <el-badge
            v-if="inventoryStore.shoppingItems.length > 0"
            :value="inventoryStore.shoppingItems.length"
            class="tab-badge"
          />
        </template>

        <div class="tab-toolbar">
          <el-button type="primary" :icon="Plus" @click="openShoppingDialog">添加要买的</el-button>
          <el-button @click="onClearChecked">清空已购</el-button>
        </div>

        <el-alert
          v-if="inventoryStore.shoppingError"
          type="error"
          :title="inventoryStore.shoppingError.message"
          :closable="false"
          show-icon
          class="inv-alert"
        >
          <el-button size="small" type="primary" plain @click="retry">重试</el-button>
        </el-alert>

        <div v-else-if="inventoryStore.shoppingLoading" class="inv-skeleton">
          <el-skeleton :rows="5" animated />
        </div>

        <el-empty
          v-else-if="inventoryStore.shoppingItems.length === 0"
          description="购物清单是空的，缺什么记什么，买完一键转入冰箱"
        />

        <div v-else class="inv-list">
          <div
            v-for="item in inventoryStore.shoppingItems"
            :key="item.id"
            class="inv-item inv-item--shopping"
          >
            <el-checkbox
              :model-value="item.checked"
              @change="inventoryStore.toggleShopping(item.id)"
            >
              <span :class="{ 'inv-checked-text': item.checked }">{{ item.ingredient_name }}</span>
            </el-checkbox>
            <div class="inv-main">
              <div class="inv-line inv-meta">
                <span>{{ item.quantity_note }}</span>
                <span v-if="item.from_recipe_name">来自：{{ item.from_recipe_name }}</span>
                <span v-if="item.allergen_codes.length > 0" class="inv-allergen">
                  ⚠ {{ item.allergen_codes.map((c) => allergenLabel(c)).join('、') }}
                </span>
              </div>
            </div>
            <div class="inv-actions">
              <el-button size="small" type="primary" plain @click="onToInventory(item)">
                转入库存
              </el-button>
              <el-button size="small" type="danger" plain @click="inventoryStore.removeShopping(item.id)">
                删除
              </el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 新增/编辑库存条目弹窗 -->
    <el-dialog
      v-model="itemDialogVisible"
      :title="editingId == null ? '新增库存条目' : '编辑库存条目'"
      width="440px"
      align-center
    >
      <el-form label-position="top">
        <el-form-item label="食材" required>
          <!-- H1b：远程搜索（filterable + remote），输入去抖 300ms 后调 /v1/ingredients?q=，支持别名匹配 -->
          <el-select
            v-model="itemForm.ingredient_id"
            filterable
            remote
            :remote-method="searchIngredients"
            :loading="ingredientsLoading"
            placeholder="搜索或选择食材"
            :disabled="editingId != null"
          >
            <el-option
              v-for="ing in ingredientDisplayOptions"
              :key="ing.id"
              :label="ing.name"
              :value="ing.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="数量档位">
          <el-radio-group v-model="itemForm.quantity_level">
            <el-radio-button value="low">少量</el-radio-button>
            <el-radio-button value="mid">有</el-radio-button>
            <el-radio-button value="plenty">充足</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="到期日">
          <el-date-picker
            v-model="itemForm.expire_date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择到期日（可留空）"
          />
        </el-form-item>
        <el-form-item label="存放位置">
          <!-- H1：value 用后端枚举（fridge/freezer/room/dry），仅 label 展示中文，避免中文标签直传 422 -->
          <el-radio-group v-model="itemForm.location">
            <el-radio-button v-for="loc in LOCATION_OPTIONS" :key="loc.value" :value="loc.value">
              {{ loc.label }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="itemDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="itemSubmitting" @click="onItemSubmit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新增购物条目弹窗 -->
    <el-dialog v-model="shoppingDialogVisible" title="添加要买的食材" width="440px" align-center>
      <el-form label-position="top">
        <el-form-item label="食材" required>
          <!-- H1b：购物清单同样走远程搜索，与库存弹窗共用 searchIngredients / 去抖与竞态守卫 -->
          <el-select
            v-model="shoppingForm.ingredient_id"
            filterable
            remote
            :remote-method="searchIngredients"
            :loading="ingredientsLoading"
            placeholder="搜索或选择食材"
          >
            <el-option
              v-for="ing in ingredientDisplayOptions"
              :key="ing.id"
              :label="ing.name"
              :value="ing.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="数量备注">
          <el-input v-model="shoppingForm.quantity_note" maxlength="30" placeholder="如：2 根 / 500g" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="shoppingDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onShoppingSubmit">加入清单</el-button>
      </template>
    </el-dialog>

    <!-- 烹饪后扣减建议弹窗 -->
    <el-dialog v-model="deductVisible" title="烹饪后记录消耗" width="520px" align-center>
      <el-form label-position="top">
        <el-form-item label="本次烹饪会话 ID" required>
          <div class="deduct-row">
            <el-input v-model="deductSessionId" placeholder="如：sess_xxx（可在烹饪历史中查看）" />
            <el-button :loading="suggestLoading" @click="onLoadSuggestions">获取建议</el-button>
          </div>
        </el-form-item>
      </el-form>

      <template v-if="suggestions.length > 0">
        <p class="deduct-hint">根据本次菜谱用量，建议扣减以下食材（取消勾选即跳过）：</p>
        <div class="deduct-list">
          <div v-for="s in suggestions" :key="s.item_id" class="deduct-item">
            <el-checkbox v-model="suggestionChecked[s.item_id]">
              <span class="deduct-name">{{ s.ingredient_name }}</span>
              <el-tag size="small" type="info" class="deduct-tag">
                {{ s.suggest_action === 'mark_used' ? '标记用完' : '扣减数量' }}
              </el-tag>
            </el-checkbox>
            <p class="deduct-reason">{{ s.reason }}</p>
          </div>
        </div>
      </template>

      <template #footer>
        <el-button @click="deductVisible = false">关闭</el-button>
        <el-button
          type="primary"
          :disabled="suggestions.length === 0"
          :loading="confirmLoading"
          @click="onConfirmDeduct"
        >
          确认扣减
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.tab-toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}

.tab-badge {
  margin-left: 6px;
  vertical-align: middle;
}

.inv-alert {
  margin-bottom: 14px;
}

.inv-skeleton {
  padding: 8px 0 16px;
}

.inv-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.inv-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
}

.inv-item--urgent {
  border-color: var(--color-danger-border);
  background: var(--color-danger-bg);
}

.inv-main {
  flex: 1;
  min-width: 0;
}

.inv-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.inv-name {
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
}

.inv-expire {
  font-size: var(--font-sm);
  color: var(--color-info);
}

.inv-meta {
  margin-top: 4px;
  font-size: var(--font-sm);
  color: var(--color-info);
}

.inv-allergen {
  color: var(--color-danger);
  font-weight: 600;
}

.inv-actions {
  flex-shrink: 0;
  display: flex;
  gap: 6px;
}

.inv-item--shopping {
  align-items: flex-start;
}

.inv-checked-text {
  text-decoration: line-through;
  color: var(--color-info);
}

/* ── 扣减弹窗 ── */
.deduct-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

.deduct-hint {
  margin: 0 0 10px;
  font-size: var(--font-sm);
  color: var(--color-info);
}

.deduct-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.deduct-item {
  padding: 10px 12px;
  border: 1px solid var(--color-info-border);
  border-radius: 8px;
}

.deduct-name {
  font-weight: 600;
}

.deduct-tag {
  margin-left: 8px;
}

.deduct-reason {
  margin: 4px 0 0 24px;
  font-size: var(--font-sm);
  color: var(--color-info);
}
</style>
