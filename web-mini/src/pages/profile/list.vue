<!--
  文件级注释：P-02 家庭档案列表页。
  - family.members 列表（姓名 / 关系 / 过敏原 BaseTag 标签 / 偏好摘要）；
  - 成员卡点击 → P-03 member-edit?id=；「添加成员」→ member-edit（无 id 参数）；
  - 成员删除：BaseDialog 二次确认 → profile.removeMember（本地同步移除）；
  - 两个设置入口 BaseCell：厨艺与设备 → P-04 skill；饮食目标 → P-05 goal；
  - profile.loadAll() 加载；五态齐备；空态引导添加成员。
  数据结构对齐 web-stage1 ProfileView（FamilyProfile.members: FamilyMember[]）。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import type { FamilyMember } from '@shared/types'
import { allergenLabel } from '@shared/utils'
import { useProfileStore } from '@/stores/profile'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide } from '@/utils/track'
import { toastSuccess, toastError } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import BaseTag from '@/components-base/BaseTag.vue'
import BaseCell from '@/components-base/BaseCell.vue'
import BaseButton from '@/components-base/BaseButton.vue'
import BaseDialog from '@/components-base/BaseDialog.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 档案 store（family / loadAll / removeMember / saving） */
const profile = useProfileStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 待删除成员（BaseDialog 确认目标；null = 删除层关闭） */
const pendingRemove = ref<FamilyMember | null>(null)

/** 删除确认弹层可见性 */
const removeDialogVisible = computed(() => pendingRemove.value !== null)

/** 成员列表（family 未加载时为空数组） */
const members = computed<FamilyMember[]>(() => profile.family?.members ?? [])

/** 是否空态：加载完成、无错误且无成员 */
const isEmpty = computed(() => !profile.loading && !profile.error && members.value.length === 0)

/**
 * 成员偏好摘要文案：过敏原 / 自定义过敏原 / 忌口 / 特殊人群（对齐阶段一 memberSummary）。
 * @param member 成员
 * @returns 摘要文本（未填偏好时兜底提示）
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
  if (member.special_population.length > 0) parts.push(member.special_population.join('、'))
  return parts.length > 0 ? parts.join('；') : '未填写偏好'
}

/**
 * 点击成员卡 → P-03 成员编辑（携带 id 回填）。
 * @param member 成员
 * @returns 无
 */
function editMember(member: FamilyMember): void {
  uni.navigateTo({ url: `${ROUTES.PROFILE_MEMBER_EDIT}?id=${member.id}`, fail: () => {} })
}

/**
 * 添加成员 → P-03 成员编辑（无 id 参数 = 新增）。
 * @returns 无
 */
function addMember(): void {
  uni.navigateTo({ url: ROUTES.PROFILE_MEMBER_EDIT, fail: () => {} })
}

/**
 * 请求删除成员：打开确认弹层。
 * @param member 目标成员
 * @returns 无
 */
function askRemoveMember(member: FamilyMember): void {
  pendingRemove.value = member
}

/**
 * 确认删除成员：removeMember 落库 + 本地移除；失败 toast。
 * @returns 无
 * @throws 不抛出（接口失败就地转错误 toast）
 */
async function confirmRemoveMember(): Promise<void> {
  const target = pendingRemove.value
  if (!target) return
  try {
    await profile.removeMember(target.id)
    toastSuccess('成员已删除')
  } catch (e) {
    toastError((e as { message?: string }).message || '删除失败，请重试')
  } finally {
    pendingRemove.value = null
  }
}

/**
 * 取消删除：关闭弹层。
 * @returns 无
 */
function cancelRemoveMember(): void {
  pendingRemove.value = null
}

// onShow：重拉三段档案（成员编辑页返回后列表即时刷新）
onShow(() => {
  void profile.loadAll()
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

    <view class="profile-list">
      <!-- 加载态 -->
      <SkeletonPage v-if="profile.loading" type="list" :rows="3" />

      <!-- 错误态：retry 重拉 -->
      <ErrorState v-else-if="profile.error" kind="server" @retry="profile.loadAll()" />

      <!-- 空态：引导添加成员 -->
      <EmptyState
        v-else-if="isEmpty"
        icon="👨‍👩‍👧"
        title="还没有家庭成员档案"
        desc="添加成员并填写过敏原与口味，推荐会更懂你的家"
        action-text="添加成员"
        @action="addMember"
      />

      <template v-else>
        <!-- 成员列表 -->
        <view class="profile-list__members">
          <view
            v-for="member in members"
            :key="member.id"
            class="member-card"
            @click="editMember(member)"
          >
            <view class="member-card__head">
              <text class="member-card__name">{{ member.name }}</text>
              <BaseTag :text="member.relation" kind="primary" />
            </view>
            <!-- 过敏原标签行（有才渲染） -->
            <view v-if="member.allergen_codes.length > 0" class="member-card__tags">
              <BaseTag
                v-for="code in member.allergen_codes"
                :key="code"
                :text="allergenLabel(code)"
                kind="danger"
              />
            </view>
            <text class="member-card__summary">{{ memberSummary(member) }}</text>
            <view class="member-card__actions">
              <view class="member-card__action" @click.stop="editMember(member)">编辑</view>
              <view class="member-card__action is-danger" @click.stop="askRemoveMember(member)">删除</view>
            </view>
          </view>
        </view>

        <!-- 添加成员 -->
        <BaseButton class="profile-list__add" block @click="addMember">+ 添加成员</BaseButton>

        <!-- 设置入口 -->
        <view class="profile-list__settings">
          <BaseCell title="厨艺与设备" desc="厨艺水平与厨房设备，影响推荐难度与做法" arrow @click="goRoute(ROUTES.PROFILE_SKILL)" />
          <BaseCell title="饮食目标" desc="控体重 / 增肌 / 少盐 / 低糖等，影响营养展示" arrow @click="goRoute(ROUTES.PROFILE_GOAL)" />
        </view>
      </template>

      <!-- 删除确认弹层 -->
      <BaseDialog
        :visible="removeDialogVisible"
        title="删除成员"
        position="center"
        @close="cancelRemoveMember"
      >
        <view class="remove-dialog">
          <text class="remove-dialog__text">
            确定删除成员「{{ pendingRemove?.name }}」吗？删除后该成员的过敏原与口味偏好不再参与推荐过滤。
          </text>
          <view class="remove-dialog__actions">
            <BaseButton type="default" block @click="cancelRemoveMember">取消</BaseButton>
            <BaseButton type="danger" block :loading="profile.saving" @click="confirmRemoveMember">删除</BaseButton>
          </view>
        </view>
      </BaseDialog>

      <DisclaimerBar scene="home" />
    </view>
  </view>
</template>

<style scoped lang="scss">
.profile-list {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
}

.profile-list__members {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.member-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
}

.member-card__head {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.member-card__name {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.member-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
}

.member-card__summary {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-secondary);
}

.member-card__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-lg);
}

.member-card__action {
  min-height: var(--hit-min);
  display: flex;
  align-items: center;
  font-size: var(--font-size-base);
  color: var(--color-info);

  &.is-danger {
    color: var(--color-danger);
  }
}

.profile-list__add {
  margin-top: var(--space-lg);
}

.profile-list__settings {
  margin-top: var(--space-lg);
  border-radius: var(--radius-card);
  overflow: hidden;
}

.remove-dialog {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
  padding: var(--space-sm) 0 var(--space-md);
}

.remove-dialog__text {
  font-size: var(--font-size-base);
  line-height: 1.6;
  color: var(--text-primary);
}

.remove-dialog__actions {
  display: flex;
  gap: var(--space-sm);
}
</style>
