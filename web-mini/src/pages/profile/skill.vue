<!--
  文件级注释：P-04 厨艺与设备页。
  - 厨艺水平 1~5 单选（BasePicker：新手 / 会做简单菜 / 家常熟练 / 进阶 / 大厨）；
  - 已有厨房设备多选（tag 复选，17 项白名单对齐 web-stage1 ProfileView EQUIPMENT_OPTIONS /
    后端 EQUIPMENT_WHITELIST）；保存调 profile.saveSkill（PUT /v1/profile/skill）；
  - onShow loadAll 后把服务端值灌入本地缓冲；保存异常 toast。
  注：源码该页无敏感字段（设备/厨艺非 PIPL 敏感信息），不接单独同意流。
-->
<script setup lang="ts">
import { reactive } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import type { ApiError } from '@shared/types'
import { useProfileStore } from '@/stores/profile'
import { flushOnHide } from '@/utils/track'
import { toastSuccess, toastError } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import ErrorState from '@/components/ErrorState.vue'
import BasePicker from '@/components-base/BasePicker.vue'
import BaseButton from '@/components-base/BaseButton.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 档案 store（skill / loadAll / saveSkill / saving） */
const profile = useProfileStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 厨艺水平选项（1~5，文案对齐源码 LEVEL_LABELS） */
const LEVEL_OPTIONS = [
  { label: '新手', value: 1 },
  { label: '会做简单菜', value: 2 },
  { label: '家常熟练', value: 3 },
  { label: '进阶', value: 4 },
  { label: '大厨', value: 5 },
]

/** 厨房设备白名单（17 项，对齐源码 EQUIPMENT_OPTIONS / 后端白名单） */
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

/** 本地编辑缓冲（进入页面从 store 拷贝，保存落库） */
const skillForm = reactive({
  cooking_level: 3,
  equipment: [] as string[],
})

/**
 * 切换设备多选 tag。
 * @param item 设备名
 * @returns 无
 */
function toggleEquipment(item: string): void {
  skillForm.equipment = skillForm.equipment.includes(item)
    ? skillForm.equipment.filter((t) => t !== item)
    : [...skillForm.equipment, item]
}

/**
 * 保存厨艺与设备（异常就地转错误 toast）。
 * @returns 无
 * @throws 不向外抛出
 */
async function onSave(): Promise<void> {
  try {
    await profile.saveSkill({ ...skillForm })
    toastSuccess('厨艺与设备已保存')
    uni.navigateBack({ fail: () => {} })
  } catch (e) {
    toastError((e as ApiError).message || '保存失败，请重试')
  }
}

// onShow：拉取三段档案并把服务端 skill 灌入本地缓冲
onShow(() => {
  void profile.loadAll().then(() => {
    if (profile.skill) {
      skillForm.cooking_level = profile.skill.cooking_level
      skillForm.equipment = [...profile.skill.equipment]
    }
  })
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

    <view class="skill">
      <!-- 加载态 -->
      <SkeletonPage v-if="profile.loading" type="list" :rows="3" />

      <!-- 错误态 -->
      <ErrorState v-else-if="profile.error" kind="server" @retry="profile.loadAll()" />

      <template v-else>
        <!-- 厨艺水平 -->
        <view class="skill__field">
          <text class="skill__label">厨艺水平</text>
          <BasePicker v-model="skillForm.cooking_level" :options="LEVEL_OPTIONS" />
        </view>

        <!-- 设备多选 -->
        <view class="skill__field">
          <text class="skill__label">已有厨房设备（可多选）</text>
          <view class="skill__tags">
            <view
              v-for="item in EQUIPMENT_OPTIONS"
              :key="item"
              class="skill__tag"
              :class="{ 'is-active': skillForm.equipment.includes(item) }"
              @click="toggleEquipment(item)"
            >
              {{ item }}
            </view>
          </view>
          <text class="skill__note">设备越全，推荐里可做的做法越多（如烤箱菜 / 空气炸锅菜）</text>
        </view>

        <!-- 保存 -->
        <BaseButton class="skill__save" block :loading="profile.saving" @click="onSave">
          保存
        </BaseButton>
      </template>
    </view>
  </view>
</template>

<style scoped lang="scss">
.skill {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md) var(--space-md) var(--space-xl);
}

.skill__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  margin-bottom: var(--space-lg);
}

.skill__label {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.skill__tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.skill__tag {
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

.skill__note {
  font-size: var(--font-size-sm);
  line-height: 1.5;
  color: var(--text-tertiary);
}

.skill__save {
  margin-top: var(--space-lg);
}
</style>
