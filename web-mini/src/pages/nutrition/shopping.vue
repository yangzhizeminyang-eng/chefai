<!--
  文件级注释：P-24 购物清单页（分包 pages/nutrition）。
  - 自 web-stage1 InventoryView 购物清单 Tab 迁移（ShoppingItem 契约：
    ingredient_name / quantity_note / from_recipe_name / checked / allergen_codes）：
    清单列表（勾选完成态划线 + 数量备注 + 来源菜谱 + 致敏原红字）+ 每条删除；
  - 添加：契约 ShoppingCreateBody 需 ingredient_id，故添加行为 = 关键词搜索食材
    （GET /v1/ingredients?q=，含别名）→ 候选点击加入（数量备注缺省「1 份」，对齐源码）；
  - 「已购入库存」：对勾选条目逐条 postShoppingToInventory（store toInventory，
    成功后双列表重拉——清单移除 + 库存刷新）；无勾选时信息提示（对齐源码）；
  - DEF-12 说明：>8 不入档 / >5 折叠规则经源码核对仅应用于阶段一完成评分缺料区，
    购物清单 Tab 无同类折叠逻辑，本页不添加（对齐任务边界）；
  - 勾选态为纯本地态（store toggleShopping；契约无勾选同步端点）；
  - 五态：加载骨架 / 空态（清单是空的，从菜谱缺料一键加入）/ 错误重试 / 离线提示条；
  - 深浅色 + 字号适配；onHide flushOnHide。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import type { ApiError, Ingredient, ShoppingItem } from '@shared/types'
import { allergenLabel } from '@shared/utils'
import { getIngredients, type IngredientListResponse } from '@/api/endpoints'
import { useInventoryStore } from '@/stores/inventory'
import { flushOnHide } from '@/utils/track'
import { toastSuccess, toastInfo, toastError } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import BaseInput from '@/components-base/BaseInput.vue'
import BaseButton from '@/components-base/BaseButton.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 库存与购物清单 store（shoppingItems / toggleShopping / removeShopping / toInventory / addShopping） */
const inventory = useInventoryStore()

/* ── 添加：食材搜索（契约需 ingredient_id，纯文本名称无法直接入清单） ── */

/** 添加区搜索关键词 */
const searchKeyword = ref('')
/** 搜索结果候选 */
const searchResults = ref<Ingredient[]>([])
/** 搜索加载中 */
const searchLoading = ref(false)
/** 候选最大展示条数（防超长列表） */
const MAX_DISPLAY = 10

/** 展示候选（截断前 10 条） */
const displayCandidates = computed(() => searchResults.value.slice(0, MAX_DISPLAY))

/**
 * 搜索食材候选（GET /v1/ingredients?q=，含别名匹配；空关键词不发请求）。
 * @returns 无
 * @throws 不向外抛出（失败清空候选并就地错误 toast）
 */
async function onSearch(): Promise<void> {
  const keyword = searchKeyword.value.trim()
  if (!keyword) {
    toastInfo('请先输入要买的食材名')
    return
  }
  searchLoading.value = true
  try {
    const res: IngredientListResponse = await getIngredients({ q: keyword })
    searchResults.value = res.items ?? []
    if ((res.items ?? []).length === 0) {
      toastInfo('没有找到相关食材，换个关键词试试')
    }
  } catch (e) {
    searchResults.value = []
    toastError((e as ApiError).message || '食材搜索失败，请重试')
  } finally {
    searchLoading.value = false
  }
}

/**
 * 把候选食材加入清单（后端按食材合并去重；数量备注缺省「1 份」对齐源码）。
 * @param ing 候选食材
 * @returns 无
 * @throws 不向外抛出（失败就地错误 toast）
 */
async function onAddCandidate(ing: Ingredient): Promise<void> {
  if (inventory.mutating) return
  try {
    await inventory.addShopping({
      items: [{ ingredient_id: ing.id, quantity_note: '1 份', from_recipe_name: undefined }],
    })
    toastSuccess(`已把「${ing.name}」加入清单`)
  } catch (e) {
    toastError((e as ApiError).message || '添加失败，请重试')
  }
}

/* ── 清单条目操作 ── */

/**
 * 切换条目勾选态（纯本地态，驱动「已购入库存」批量动作）。
 * @param item 清单条目
 * @returns 无
 */
function onToggle(item: ShoppingItem): void {
  inventory.toggleShopping(item.id)
}

/**
 * 删除条目（对齐源码：直接删除无二次确认）。
 * @param item 清单条目
 * @returns 无
 * @throws 不向外抛出（失败就地错误 toast）
 */
async function onRemove(item: ShoppingItem): Promise<void> {
  try {
    await inventory.removeShopping(item.id)
  } catch (e) {
    toastError((e as ApiError).message || '删除失败，请重试')
  }
}

/** 已勾选（已购）条目数（按钮文案计数用） */
const checkedCount = computed(() => inventory.shoppingItems.filter((it) => it.checked).length)

/**
 * 已购入库存：对勾选条目逐条转入库存（先取 ID 快照，避免重拉后引用失效）。
 * 逐条串行提交（store toInventory 内部重拉双列表），部分失败时提示首个错误。
 * @returns 无
 * @throws 不向外抛出（失败就地错误 toast，已成功条目保留）
 */
async function onCheckedToInventory(): Promise<void> {
  if (inventory.mutating) return
  const checkedIds = inventory.shoppingItems.filter((it) => it.checked).map((it) => it.id)
  if (checkedIds.length === 0) {
    toastInfo('还没有勾选已购条目')
    return
  }
  try {
    for (const id of checkedIds) {
      await inventory.toInventory(id)
    }
    toastSuccess('已购入库存，库存清单已刷新')
  } catch (e) {
    toastError((e as ApiError).message || '转入失败，请重试')
  }
}

/** 是否空态：加载完成、无错误且清单为空 */
const isEmpty = computed(
  () => !inventory.shoppingLoading && !inventory.shoppingError && inventory.shoppingItems.length === 0,
)

/**
 * ApiError → ErrorState 错误类别（不暴露技术细节）。
 * @param e 归一化 ApiError
 * @returns ErrorState kind
 */
function errorKind(e: ApiError): 'timeout' | 'network' | 'server' {
  if (e.code === 'TIMEOUT') return 'timeout'
  if (e.code === 'NETWORK') return 'network'
  return 'server'
}

/** 错误态类别 */
const errKind = computed(() =>
  inventory.shoppingError ? errorKind(inventory.shoppingError) : ('server' as const),
)

// onShow：每次进入重拉清单（保证从菜谱缺料加入后返回时新鲜）
onShow(() => {
  void inventory.loadShopping()
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

    <view class="shopping">
      <!-- 添加行：关键词搜索食材（契约需 ingredient_id）→ 候选点击加入 -->
      <view class="shopping__add">
        <view class="shopping__search-row">
          <BaseInput
            v-model="searchKeyword"
            :maxlength="30"
            placeholder="要买什么？输入食材名搜索"
          />
          <BaseButton size="sm" type="default" :loading="searchLoading" @click="onSearch">
            搜索
          </BaseButton>
        </view>
        <view v-if="displayCandidates.length > 0" class="shopping__candidates">
          <view v-for="ing in displayCandidates" :key="ing.id" class="candidate">
            <text class="candidate__name">{{ ing.name }}</text>
            <BaseButton
              size="sm"
              type="primary"
              :disabled="inventory.mutating"
              @click="onAddCandidate(ing)"
            >
              加入
            </BaseButton>
          </view>
        </view>
      </view>

      <!-- 加载态 -->
      <SkeletonPage v-if="inventory.shoppingLoading" type="list" :rows="4" />

      <!-- 错误态 -->
      <ErrorState
        v-else-if="inventory.shoppingError"
        :kind="errKind"
        @retry="inventory.loadShopping()"
      />

      <!-- 空态：引导从菜谱缺料一键加入 -->
      <EmptyState
        v-else-if="isEmpty"
        icon="🛒"
        title="清单是空的"
        desc="从菜谱缺料一键加入，或搜索添加，买完转入库存"
      />

      <template v-else>
        <!-- 清单列表 -->
        <view class="shopping__list">
          <view v-for="item in inventory.shoppingItems" :key="item.id" class="shop-item">
            <view class="shop-item__check" :class="{ 'is-checked': item.checked }" @click="onToggle(item)">
              <text v-if="item.checked" class="shop-item__check-mark">✓</text>
            </view>
            <view class="shop-item__body">
              <text class="shop-item__name" :class="{ 'is-checked': item.checked }">
                {{ item.ingredient_name }}
              </text>
              <view class="shop-item__meta">
                <text class="shop-item__meta-text">{{ item.quantity_note }}</text>
                <text v-if="item.from_recipe_name" class="shop-item__meta-text">
                  来自：{{ item.from_recipe_name }}
                </text>
                <text v-if="item.allergen_codes.length > 0" class="shop-item__allergen">
                  ⚠ 致敏原：{{ item.allergen_codes.map((c) => allergenLabel(c)).join('、') }}
                </text>
              </view>
            </view>
            <view class="shop-item__remove" @click="onRemove(item)">删除</view>
          </view>
        </view>

        <!-- 已购入库存（勾选条目批量转入） -->
        <BaseButton
          class="shopping__to-inventory"
          block
          :loading="inventory.mutating"
          @click="onCheckedToInventory"
        >
          已购入库存{{ checkedCount > 0 ? `（已勾选 ${checkedCount} 项）` : '' }}
        </BaseButton>
      </template>
    </view>
  </view>
</template>

<style scoped lang="scss">
.shopping {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
}

/* ── 添加区 ── */
.shopping__add {
  margin-bottom: var(--space-lg);
}

.shopping__search-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

/* 🔴 wxss 兼容：去掉 > 子代组合器（`:first-child` 产物 `>:first-child` 会使微信 wxss 编译器报错，见 member-edit.vue 注释） */
.shopping__search-row :first-child {
  flex: 1;
  min-width: 0;
}

.shopping__candidates {
  margin-top: var(--space-sm);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.candidate {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
  padding: var(--space-xs) var(--space-md);
  min-height: var(--hit-min);
  border-radius: var(--radius-ctrl);
  background: var(--bg-card);
  border: 1rpx solid var(--border-color);
}

.candidate__name {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 清单列表 ── */
.shopping__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.shop-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
}

/* 勾选框（复用 member-edit 自定义 checkbox 样式） */
.shop-item__check {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40rpx;
  height: 40rpx;
  margin-top: 6rpx;
  border: 2rpx solid var(--border-color);
  border-radius: var(--radius-ctrl);
  background: var(--bg-card);
  flex-shrink: 0;

  &.is-checked {
    border-color: var(--color-primary);
    background: var(--color-primary);
  }
}

.shop-item__check-mark {
  font-size: var(--font-size-sm);
  color: var(--text-inverse);
}

.shop-item__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4rpx;
}

.shop-item__name {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);

  /* 勾选完成态：划线弱化（非纯色彩表达） */
  &.is-checked {
    text-decoration: line-through;
    color: var(--text-tertiary);
    font-weight: 400;
  }
}

.shop-item__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.shop-item__meta-text {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.shop-item__allergen {
  font-size: var(--font-size-sm);
  color: var(--color-danger);
  font-weight: 600;
}

/* 行内删除（文字按钮，热区达标） */
.shop-item__remove {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
  padding: 0 var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--color-danger);
}

.shopping__to-inventory {
  margin-top: var(--space-lg);
}
</style>
