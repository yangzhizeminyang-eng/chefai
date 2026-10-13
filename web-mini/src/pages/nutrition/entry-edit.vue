<!--
  文件级注释：P-23 库存条目编辑页（分包 pages/nutrition，新增 / 编辑双模式，onLoad options.id 区分）。
  - 自 web-stage1 InventoryView「新增/编辑条目弹窗」迁移（InventoryItem 契约字段：
    quantity_level 数量档位 low/mid/plenty、expire_date 到期日、location 存放位置枚举）；
  - 新建模式（无 id）：食材经搜索选择（GET /v1/ingredients，无关键词走默认列表，
    有关键词走 q 搜索含别名；候选最多展示 10 条）→ InventoryCreateBody（ingredient_id 必填）
    提交 postInventory（inventory store addItem），成功埋点 inventory_add（仅新建）；
  - 编辑模式（有 id）：回填数量档位/到期日/位置，食材只读不可改（对齐源码 disabled）；
    提交 patchInventory（store patchItem）；删除按钮 → BaseDialog 确认 → deleteInventory
    （store removeItem）；
  - RL-3 第三处：表单顶部固定说明条 INEDIBLE_JUDGE_NOTE（系统不判断食材是否可食用，
    到期日仅提醒用途）；
  - 位置提交必须为后端 StorageLocation 四值枚举（fridge/freezer/room/dry，中文标签仅由
    LOCATION_OPTIONS 渲染，直传中文会 422——P0-H1 修复语义）；422 校验错误经
    format422Detail 拼进 toast 透出具体字段信息（对齐源码 1.3 修复）；
  - 深浅色 + 字号适配；onHide flushOnHide。
-->
<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { onHide, onLoad } from '@dcloudio/uni-app'
import type { ApiError, Ingredient, InventoryItem, StorageLocation } from '@shared/types'
import { LOCATION_OPTIONS, format422Detail } from '@shared/utils'
import { INEDIBLE_JUDGE_NOTE } from '@shared/constants'
import { getIngredients, type IngredientListResponse } from '@/api/endpoints'
import { useInventoryStore } from '@/stores/inventory'
import { flushOnHide, trackEvent } from '@/utils/track'
import { toastSuccess, toastWarning, toastError } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import BaseDialog from '@/components-base/BaseDialog.vue'
import BaseInput from '@/components-base/BaseInput.vue'
import BasePicker from '@/components-base/BasePicker.vue'
import BaseButton from '@/components-base/BaseButton.vue'
import BaseTag from '@/components-base/BaseTag.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 库存 store（items 回填 / addItem / patchItem / removeItem / mutating 防连点） */
const inventory = useInventoryStore()

/** 数量档位选项（value 为后端枚举，label 仅展示；对齐源码 LEVEL_LABELS） */
const LEVEL_OPTIONS: ReadonlyArray<{ label: string; value: InventoryItem['quantity_level'] }> = [
  { label: '少量', value: 'low' },
  { label: '有', value: 'mid' },
  { label: '充足', value: 'plenty' },
]

/** 候选食材最大展示条数（防超长列表撑爆页面，截断不展示其余） */
const MAX_DISPLAY = 10

/** 正在编辑的条目 ID（null = 新增模式） */
const editingId = ref<number | null>(null)
/** 编辑条目的食材名（编辑模式只读展示） */
const editingName = ref('')
/** 回填失败标记（编辑模式下找不到条目 → 错误提示态） */
const notFound = ref(false)

/** 食材搜索关键词（非空 = 展示搜索结果，空 = 回落默认列表，对齐源码 ingredientDisplayOptions） */
const searchKeyword = ref('')
/** 首屏默认候选（GET /v1/ingredients 无参，常用食材） */
const defaultOptions = ref<Ingredient[]>([])
/** 关键词搜索结果 */
const searchResults = ref<Ingredient[]>([])
/** 食材候选加载中 */
const ingredientsLoading = ref(false)
/** 新建模式已选食材（null = 未选择） */
const selectedIngredient = ref<{ id: number; name: string } | null>(null)

/** 条目表单（新建缺省值对齐源码 openItemDialog(null)：mid / 空 / fridge） */
const form = reactive({
  quantity_level: 'mid' as InventoryItem['quantity_level'],
  expire_date: '',
  location: 'fridge' as StorageLocation,
})

/** 删除确认弹窗可见性（仅编辑模式） */
const deleteVisible = ref(false)

/** 提交/删除防连点（透传 store.mutating） */
const submitting = computed(() => inventory.mutating)

/** 下拉实际展示的候选：有关键词展示搜索结果，否则展示默认列表（最多 10 条） */
const displayOptions = computed<Ingredient[]>(() => {
  const list = searchKeyword.value ? searchResults.value : defaultOptions.value
  return list.slice(0, MAX_DISPLAY)
})

/** 新建模式下是否已选出食材（保存按钮校验用） */
const canSave = computed(() => editingId.value != null || selectedIngredient.value != null)

/**
 * 拉取食材候选：无关键词走默认列表（首屏一次），有关键词走 q 搜索（含别名）。
 * @param keyword 搜索关键词（空串 = 默认列表）
 * @returns 无
 * @throws 不向外抛出（失败清空候选并就地错误 toast）
 */
async function loadIngredients(keyword: string): Promise<void> {
  ingredientsLoading.value = true
  try {
    const res: IngredientListResponse = await getIngredients(keyword ? { q: keyword } : undefined)
    if (keyword) {
      searchResults.value = res.items ?? []
    } else {
      defaultOptions.value = res.items ?? []
    }
  } catch (e) {
    if (keyword) searchResults.value = []
    else defaultOptions.value = []
    toastError((e as ApiError).message || '食材列表加载失败')
  } finally {
    ingredientsLoading.value = false
  }
}

/**
 * 搜索食材（按钮触发；空关键词回落默认列表）。
 * @returns 无
 */
function onSearch(): void {
  void loadIngredients(searchKeyword.value.trim())
}

/**
 * 选中候选食材（仅新建模式；重复点击同一项 = 取消选择）。
 * @param ing 候选食材
 * @returns 无
 */
function onPick(ing: Ingredient): void {
  if (selectedIngredient.value?.id === ing.id) {
    selectedIngredient.value = null
    return
  }
  selectedIngredient.value = { id: ing.id, name: ing.name }
}

/**
 * 到期日 picker change：回写 YYYY-MM-DD（空值可经「清除」按钮置空）。
 * @param e change 事件（detail.value 为选中日期）
 * @returns 无
 */
function onDateChange(e: { detail: { value: string } }): void {
  form.expire_date = e.detail.value
}

/**
 * onLoad：有 id 参数 → 编辑模式（store 无数据时先拉列表再回填；找不到转错误提示态）；
 * 无 id → 新建模式（首屏拉默认食材候选）。
 * @param options 页面参数（id 可选）
 * @returns 无
 */
onLoad((options) => {
  const id = Number(options?.id)
  if (id && !Number.isNaN(id)) {
    void initEdit(id)
  } else {
    void loadIngredients('')
  }
})

/**
 * 编辑模式初始化：确保 store 已加载 → 按 id 找条目回填（食材不可改，对齐源码 disabled）。
 * @param id 库存条目 ID
 * @returns 无
 */
async function initEdit(id: number): Promise<void> {
  if (inventory.items.length === 0 && !inventory.error) {
    await inventory.loadItems()
  }
  const item = inventory.items.find((it) => it.id === id)
  if (!item) {
    notFound.value = true
    toastWarning('未找到该条目，请返回重试')
    return
  }
  editingId.value = item.id
  editingName.value = item.ingredient_name
  form.quantity_level = item.quantity_level
  form.expire_date = item.expire_date
  // 位置枚举直接回显（与 LOCATION_OPTIONS 的 value 一一对应；兼容历史空值兜底 fridge）
  form.location = (item.location || 'fridge') as StorageLocation
}

/**
 * 保存：本地校验（新建必选食材）→ 新建 postInventory（埋点 inventory_add，仅新建）/
 * 编辑 patchInventory（不含食材与状态字段，对齐源码增量语义）→ toast 返回。
 * 422 校验错误经 format422Detail 拼进 toast 透出具体字段信息。
 * @returns 无
 * @throws 不向外抛出（接口失败就地转错误 toast）
 */
async function onSave(): Promise<void> {
  if (!canSave.value) {
    toastWarning('请选择食材')
    return
  }
  if (inventory.mutating) return
  try {
    if (editingId.value == null && selectedIngredient.value) {
      await inventory.addItem({
        ingredient_id: selectedIngredient.value.id,
        quantity_level: form.quantity_level,
        expire_date: form.expire_date || undefined,
        location: form.location,
      })
      trackEvent('inventory_add')
      toastSuccess('已加入冰箱')
    } else if (editingId.value != null) {
      await inventory.patchItem(editingId.value, {
        quantity_level: form.quantity_level,
        expire_date: form.expire_date || undefined,
        location: form.location,
      })
      toastSuccess('已更新')
    }
    uni.navigateBack({ fail: () => {} })
  } catch (e) {
    const apiErr = e as ApiError
    const extra = format422Detail(apiErr)
    toastError(
      extra
        ? `${apiErr.message || '保存失败，请重试'}：${extra}`
        : apiErr.message || '保存失败，请重试',
    )
  }
}

/**
 * 打开删除确认弹窗（仅编辑模式入口）。
 * @returns 无
 */
function onAskDelete(): void {
  deleteVisible.value = true
}

/**
 * 确认删除：removeItem → toast 返回（弹窗由调用方关闭）。
 * @returns 无
 * @throws 不向外抛出（接口失败就地转错误 toast，弹窗保留供重试）
 */
async function onConfirmDelete(): Promise<void> {
  if (editingId.value == null || inventory.mutating) return
  try {
    await inventory.removeItem(editingId.value)
    deleteVisible.value = false
    toastSuccess('已删除')
    uni.navigateBack({ fail: () => {} })
  } catch (e) {
    toastError((e as ApiError).message || '删除失败，请重试')
  }
}

// onHide：尽力上报缓冲埋点
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <!-- 离线提示条 -->
    <OfflineBar v-if="!network.isConnected" />

    <view class="entry-edit">
      <!-- 回填失败态（编辑模式下找不到条目） -->
      <view v-if="notFound" class="entry-edit__missing">
        <text class="entry-edit__missing-text">未找到该库存条目，可能已被删除</text>
      </view>

      <template v-else>
        <!-- RL-3 第三处固定说明条：不判断食材可食用性，到期日仅提醒 -->
        <view class="entry-edit__note">
          <text class="entry-edit__note-text">{{ INEDIBLE_JUDGE_NOTE }}</text>
        </view>

        <!-- 食材：新建 = 搜索选择；编辑 = 只读回显（对齐源码 disabled） -->
        <view class="entry-edit__field">
          <text class="entry-edit__label">食材（必选）</text>

          <template v-if="editingId == null">
            <view class="entry-edit__search-row">
              <BaseInput
                v-model="searchKeyword"
                :maxlength="30"
                placeholder="搜索食材名（支持别名，如「柴鸡蛋」）"
              />
              <BaseButton size="sm" type="default" :loading="ingredientsLoading" @click="onSearch">
                搜索
              </BaseButton>
            </view>

            <!-- 已选结果 -->
            <view v-if="selectedIngredient" class="entry-edit__picked">
              <text class="entry-edit__picked-text">已选：{{ selectedIngredient.name }}</text>
              <BaseTag text="点击候选可取消" kind="info" />
            </view>

            <!-- 候选列表（空关键词 = 默认常用列表） -->
            <view v-if="displayOptions.length > 0" class="entry-edit__candidates">
              <view
                v-for="ing in displayOptions"
                :key="ing.id"
                class="candidate"
                :class="{ 'is-active': selectedIngredient?.id === ing.id }"
                @click="onPick(ing)"
              >
                <text class="candidate__name">{{ ing.name }}</text>
              </view>
            </view>
            <text v-else-if="!ingredientsLoading" class="entry-edit__empty-hint">
              {{ searchKeyword ? '没有找到相关食材，换个关键词试试' : '输入关键词搜索，或从常用食材中选择' }}
            </text>
          </template>

          <view v-else class="entry-edit__readonly">
            <text class="entry-edit__readonly-text">{{ editingName }}</text>
            <BaseTag text="编辑时食材不可更改" kind="neutral" />
          </view>
        </view>

        <!-- 数量档位 -->
        <view class="entry-edit__field">
          <text class="entry-edit__label">数量档位</text>
          <BasePicker v-model="form.quantity_level" :options="[...LEVEL_OPTIONS]" />
        </view>

        <!-- 存放位置（提交后端枚举，label 仅展示） -->
        <view class="entry-edit__field">
          <text class="entry-edit__label">存放位置</text>
          <BasePicker v-model="form.location" :options="[...LOCATION_OPTIONS]" />
        </view>

        <!-- 到期日（可空；原生 date picker + 清除） -->
        <view class="entry-edit__field">
          <text class="entry-edit__label">到期日（可留空）</text>
          <view class="entry-edit__date-row">
            <picker
              class="entry-edit__date-picker"
              mode="date"
              :value="form.expire_date"
              @change="onDateChange"
            >
              <view
                class="entry-edit__date-display"
                :class="{ 'is-placeholder': !form.expire_date }"
              >
                {{ form.expire_date || '选择到期日' }}
              </view>
            </picker>
            <BaseButton
              v-if="form.expire_date"
              size="sm"
              type="default"
              @click="form.expire_date = ''"
            >
              清除
            </BaseButton>
          </view>
        </view>

        <!-- 保存 -->
        <BaseButton
          class="entry-edit__save"
          block
          :loading="submitting"
          @click="onSave"
        >
          保存
        </BaseButton>

        <!-- 删除（仅编辑模式；BaseDialog 二次确认） -->
        <BaseButton
          v-if="editingId != null"
          class="entry-edit__delete"
          block
          type="danger"
          :disabled="submitting"
          @click="onAskDelete"
        >
          删除该条目
        </BaseButton>
      </template>
    </view>

    <!-- 删除确认弹窗 -->
    <BaseDialog
      :visible="deleteVisible"
      title="删除库存"
      position="center"
      @close="deleteVisible = false"
    >
      <view class="entry-edit__confirm">
        <text class="entry-edit__confirm-text">
          确认从冰箱删除「{{ editingName }}」？删除后不可恢复
        </text>
        <view class="entry-edit__confirm-actions">
          <BaseButton type="default" @click="deleteVisible = false">取消</BaseButton>
          <BaseButton type="danger" :loading="submitting" @click="onConfirmDelete">删除</BaseButton>
        </view>
      </view>
    </BaseDialog>
  </view>
</template>

<style scoped lang="scss">
.entry-edit {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
}

/* ── 回填失败提示 ── */
.entry-edit__missing {
  padding: var(--space-lg) var(--space-md);
  display: flex;
  justify-content: center;
}

.entry-edit__missing-text {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
}

/* ── RL-3 固定说明条 ── */
.entry-edit__note {
  padding: var(--space-xs) var(--space-md);
  margin-bottom: var(--space-lg);
  border-radius: var(--radius-ctrl);
  background: var(--color-info-bg);
}

.entry-edit__note-text {
  font-size: var(--font-size-sm);
  line-height: 1.5;
  color: var(--text-secondary);
}

.entry-edit__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  margin-bottom: var(--space-lg);
}

.entry-edit__label {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

/* ── 食材搜索 ── */
.entry-edit__search-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

/* 🔴 wxss 兼容：去掉 > 子代组合器（`:first-child` 产物 `>:first-child` 会使微信 wxss 编译器报错，见 member-edit.vue 注释） */
.entry-edit__search-row :first-child {
  flex: 1;
  min-width: 0;
}

.entry-edit__picked {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-top: var(--space-xs);
}

.entry-edit__picked-text {
  font-size: var(--font-size-sm);
  color: var(--color-primary);
  font-weight: 600;
}

.entry-edit__candidates {
  margin-top: var(--space-xs);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.candidate {
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

.candidate__name {
  font-size: var(--font-size-sm);
}

.entry-edit__empty-hint {
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* ── 编辑模式食材只读 ── */
.entry-edit__readonly {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-ctrl);
  background: var(--bg-page);
}

.entry-edit__readonly-text {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 到期日 ── */
.entry-edit__date-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.entry-edit__date-picker {
  flex: 1;
  min-width: 0;
}

.entry-edit__date-display {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
  padding: 0 var(--space-md);
  border: 1rpx solid var(--border-color);
  border-radius: var(--radius-ctrl);
  background: var(--bg-card);
  font-size: var(--font-size-base);
  color: var(--text-primary);

  &.is-placeholder {
    color: var(--text-tertiary);
  }
}

.entry-edit__save {
  margin-top: var(--space-md);
}

.entry-edit__delete {
  margin-top: var(--space-md);
}

/* ── 删除确认弹窗内容 ── */
.entry-edit__confirm {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
  padding: var(--space-sm) 0;
}

.entry-edit__confirm-text {
  font-size: var(--font-size-base);
  line-height: 1.6;
  color: var(--text-primary);
}

.entry-edit__confirm-actions {
  display: flex;
  gap: var(--space-sm);

  > view {
    flex: 1;
  }
}
</style>
