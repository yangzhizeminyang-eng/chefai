<!--
  文件级注释：P-21 营养手动补录页（分包 pages/nutrition）。
  - 自 web-stage1 MeView「补录外食」弹窗交互迁移（postNutritionManual 语义）：
    契约字段仅 meal_type（餐次）+ description（外食描述，自然语言，涵盖菜名/食材）；
    描述 ≥2 字本地校验（对齐源码「请简单描述这顿吃了什么」）；
  - 提交成功 toast + navigateBack；命中风控（res.blocked）→ 展示拦截话术 toast 不关闭；
  - 估算口径说明：补录数据同样按估算口径计入营养汇总（页面顶部固定标注
    NUTRITION_ESTIMATE_NOTE，仅客观陈述，不做营养声称）；
  - 契约差异说明：阶段一交互无「日期 / 份量 / 菜名」独立字段（后端以描述文本 +
    提交时刻归餐），本页严格对齐 NutritionManualBody 契约不虚构字段；
  - 五态：提交 loading / 本地校验警示 / 提交错误 toast / 离线提示条；深浅色 + 字号适配。
-->
<script setup lang="ts">
import { ref } from 'vue'
import { onHide } from '@dcloudio/uni-app'
import type { ApiError, NutritionManualBody, NutritionManualResponse } from '@shared/types'
import { NUTRITION_ESTIMATE_NOTE } from '@shared/constants'
import { postNutritionManual } from '@/api/endpoints'
import { flushOnHide } from '@/utils/track'
import { toastSuccess, toastWarning, toastError } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import BaseInput from '@/components-base/BaseInput.vue'
import BasePicker from '@/components-base/BasePicker.vue'
import BaseButton from '@/components-base/BaseButton.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 餐次选项（BasePicker；value 为后端枚举，label 仅展示） */
const MEAL_OPTIONS: ReadonlyArray<{ label: string; value: NutritionManualBody['meal_type'] }> = [
  { label: '早餐', value: 'breakfast' },
  { label: '午餐', value: 'lunch' },
  { label: '晚餐', value: 'dinner' },
  { label: '加餐', value: 'snack' },
]

/** 餐次（缺省午餐，对齐源码 openManualDialog） */
const mealType = ref<NutritionManualBody['meal_type']>('lunch')
/** 外食描述（自然语言，涵盖菜名/食材） */
const description = ref('')
/** 提交中（防连点） */
const submitting = ref(false)

/**
 * 提交补录：本地校验 → postNutritionManual（走风控）→ 成功 toast 返回；
 * 命中拦截在页内 toast 拦截话术，不关闭页面（用户可改写描述重试）。
 * @returns 无
 * @throws 不向外抛出（接口失败就地转错误 toast）
 */
async function onSubmit(): Promise<void> {
  if (submitting.value) return
  const desc = description.value.trim()
  if (desc.length < 2) {
    toastWarning('请简单描述这顿吃了什么')
    return
  }
  submitting.value = true
  try {
    const res: NutritionManualResponse = await postNutritionManual({
      meal_type: mealType.value,
      description: desc,
    })
    if (res.blocked) {
      toastWarning(`${res.title ?? '无法记录'}：${res.message ?? '内容未通过安全检查'}`)
      return
    }
    toastSuccess('已记录，营养汇总稍后更新')
    uni.navigateBack({ fail: () => {} })
  } catch (e) {
    toastError((e as ApiError).message || '记录失败，请重试')
  } finally {
    submitting.value = false
  }
}

// onHide：尽力上报缓冲埋点
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <!-- 离线提示条（提交仍可尝试，失败由错误 toast 兜底） -->
    <OfflineBar v-if="!network.isConnected" />

    <view class="manual">
      <!-- 估算口径固定标注（补录数据同样为估算口径，仅客观陈述） -->
      <view class="manual__note">
        <text class="manual__note-text">
          手动记录按 {{ NUTRITION_ESTIMATE_NOTE }}口径计入营养汇总，仅供参考
        </text>
      </view>

      <!-- 餐次 -->
      <view class="manual__field">
        <text class="manual__label">餐次</text>
        <BasePicker v-model="mealType" :options="[...MEAL_OPTIONS]" />
      </view>

      <!-- 外食描述（自然语言，涵盖菜名/食材） -->
      <view class="manual__field">
        <text class="manual__label">吃了什么（必填）</text>
        <BaseInput
          v-model="description"
          type="textarea"
          :maxlength="200"
          placeholder="如：中午在公司楼下吃了一碗牛肉面"
        />
      </view>

      <!-- 提交 -->
      <BaseButton class="manual__submit" block :loading="submitting" @click="onSubmit">
        记录
      </BaseButton>
    </view>
  </view>
</template>

<style scoped lang="scss">
.manual {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
}

/* ── 估算口径固定标注 ── */
.manual__note {
  padding: var(--space-xs) var(--space-md);
  margin-bottom: var(--space-lg);
  border-radius: var(--radius-ctrl);
  background: var(--color-info-bg);
}

.manual__note-text {
  font-size: var(--font-size-sm);
  line-height: 1.5;
  color: var(--text-secondary);
}

.manual__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  margin-bottom: var(--space-lg);
}

.manual__label {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.manual__submit {
  margin-top: var(--space-lg);
}
</style>
