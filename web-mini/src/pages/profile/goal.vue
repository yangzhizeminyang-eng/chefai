<!--
  文件级注释：P-05 饮食目标页。
  - 目标 5 选 1（control_weight 控制体重 / muscle_gain 增肌 / light_salt 少盐 /
    low_sugar 低糖 / balanced 均衡饮食，对齐 DietGoal 契约与源码 GOAL_OPTIONS）；
  - 备注说明（textarea）；少盐/低糖等慢病相关目标展示强化提示（对齐源码 goalDiseaseHint
    文案：慢性疾病请先咨询医生，本目标不构成医疗建议）；
  - 保存调 profile.saveGoal（PUT /v1/profile/diet-goal）；保存异常 toast。
  敏感性差异说明：web-stage1 源码仅对过敏原走 PIPL 单独同意（postConsentSensitive
  仅 family_allergen 场景），饮食目标未走单独同意流，本页保持一致不接 P-00b。
-->
<script setup lang="ts">
import { computed, reactive } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import type { ApiError, DietGoal } from '@shared/types'
import { useProfileStore } from '@/stores/profile'
import { flushOnHide } from '@/utils/track'
import { toastSuccess, toastError } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import ErrorState from '@/components/ErrorState.vue'
import BaseInput from '@/components-base/BaseInput.vue'
import BaseButton from '@/components-base/BaseButton.vue'

/** 目标枚举（DietGoal['goal'] 五值联合） */
type GoalKey = DietGoal['goal']

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 档案 store（goal / loadAll / saveGoal / saving） */
const profile = useProfileStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 饮食目标 5 类（value + 中文标签 + 一句说明，对齐源码 GOAL_OPTIONS） */
const GOAL_OPTIONS: Array<{ value: GoalKey; label: string; desc: string }> = [
  { value: 'control_weight', label: '控制体重', desc: '优先低热量高饱腹' },
  { value: 'muscle_gain', label: '增肌', desc: '优先高蛋白' },
  { value: 'light_salt', label: '少盐', desc: '控制钠摄入' },
  { value: 'low_sugar', label: '低糖', desc: '控制糖分摄入' },
  { value: 'balanced', label: '均衡饮食', desc: '不设特别倾向' },
]

/** 本地编辑缓冲（进入页面从 store 拷贝，保存落库） */
const goalForm = reactive<{ goal: GoalKey; note: string }>({
  goal: 'balanced',
  note: '',
})

/** 是否选择了慢病相关目标（少盐/低糖 → 强化提示，对齐源码 goalDiseaseHint） */
const goalDiseaseHint = computed(() => goalForm.goal === 'light_salt' || goalForm.goal === 'low_sugar')

/** 顶部提示文案（慢病相关 → 强化版，其余常规免责语义） */
const goalHintText = computed(() =>
  goalDiseaseHint.value
    ? '你有高血压 / 糖尿病等慢性疾病时，请先咨询医生再设定该目标；本目标不构成医疗建议'
    : '饮食目标仅用于菜谱排序倾向，不构成医疗或营养治疗建议',
)

/**
 * 选择目标（单选语义：直接覆盖缓冲值）。
 * @param value 目标枚举值
 * @returns 无
 */
function selectGoal(value: GoalKey): void {
  goalForm.goal = value
}

/**
 * 保存饮食目标（备注 trim；异常就地转错误 toast）。
 * @returns 无
 * @throws 不向外抛出
 */
async function onSave(): Promise<void> {
  try {
    await profile.saveGoal({ goal: goalForm.goal, note: goalForm.note.trim() })
    toastSuccess('饮食目标已保存')
    uni.navigateBack({ fail: () => {} })
  } catch (e) {
    toastError((e as ApiError).message || '保存失败，请重试')
  }
}

// onShow：拉取三段档案并把服务端 goal 灌入本地缓冲
onShow(() => {
  void profile.loadAll().then(() => {
    if (profile.goal) {
      goalForm.goal = profile.goal.goal
      goalForm.note = profile.goal.note
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

    <view class="goal">
      <!-- 加载态 -->
      <SkeletonPage v-if="profile.loading" type="list" :rows="3" />

      <!-- 错误态 -->
      <ErrorState v-else-if="profile.error" kind="server" @retry="profile.loadAll()" />

      <template v-else>
        <!-- 医疗边界提示（慢病相关目标时强化，warning 语义） -->
        <view class="goal__hint" :class="{ 'is-warning': goalDiseaseHint }">
          <text class="goal__hint-text">{{ goalHintText }}</text>
        </view>

        <!-- 目标 5 选 1 -->
        <view class="goal__field">
          <text class="goal__label">我的目标</text>
          <view class="goal__grid">
            <view
              v-for="opt in GOAL_OPTIONS"
              :key="opt.value"
              class="goal__card"
              :class="{ 'is-active': goalForm.goal === opt.value }"
              @click="selectGoal(opt.value)"
            >
              <text class="goal__card-title">{{ opt.label }}</text>
              <text class="goal__card-desc">{{ opt.desc }}</text>
            </view>
          </view>
        </view>

        <!-- 备注 -->
        <view class="goal__field">
          <text class="goal__label">备注说明</text>
          <BaseInput
            v-model="goalForm.note"
            type="textarea"
            placeholder="补充说明，如：家里有老人需要低盐"
            :maxlength="100"
          />
        </view>

        <!-- 保存 -->
        <BaseButton class="goal__save" block :loading="profile.saving" @click="onSave">
          保存
        </BaseButton>
      </template>
    </view>
  </view>
</template>

<style scoped lang="scss">
.goal {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md) var(--space-md) var(--space-xl);
}

.goal__hint {
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-lg);
  border-radius: var(--radius-card);
  background: var(--color-info-bg);

  &.is-warning {
    background: var(--color-warning-bg);
  }
}

.goal__hint-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-secondary);
}

.goal__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  margin-bottom: var(--space-lg);
}

.goal__label {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.goal__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-sm);
}

.goal__card {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 6rpx;
  padding: var(--space-md);
  min-height: 128rpx;
  border: 1rpx solid var(--border-color);
  border-radius: var(--radius-card);
  background: var(--bg-card);

  &.is-active {
    border-color: var(--color-primary);
    background: var(--color-primary-weak);
  }
}

.goal__card-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.goal__card-desc {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.goal__save {
  margin-top: var(--space-lg);
}
</style>
