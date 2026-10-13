<!--
  文件级注释：P-29 设置页（pages/member 分包，含数据权利区）。
  - 设置分区（语义自 web-stage1 MeView 设置分区迁移，字段对齐 SettingsData 契约）：
    字号三档 BasePicker（normal/large/xlarge，变更即经 useFontSize.setSize 同步本地
    字号档位全局生效；服务端落库在点「保存」时统一提交，对齐源码统一保存语义）/
    计量单位三选（gram/ml/spoon，历史 metric/imperial 由 me.loadSettings 读时经
    migrateUnitSetting 迁移，DEF-09）/ 语音播报与做菜提醒开关（BaseSwitch）；
  - 数据权利区（PRD §13.3）：
    导出我的数据 → me.exportData()；小程序端无 DOM 下载能力（浏览器 showSaveFilePicker /
    a 标签下载均不可用），降级方案 = JSON 全文复制到剪贴板 + toast「已复制到剪贴板」；
    删除账号（注销）→ BaseDialog 二次确认 + 输入「注销」文字确认 → me.deleteAccount()
    → 清本地 storage（aicook_ 前缀）+ 重置会话内存态 → reLaunch 免责声明页（免责门重新生效）；
  - 三态：SkeletonPage / ErrorState（重试）/ 内容区；onShow 拉取，onHide flush 埋点。
-->
<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import type { ApiError, SettingsData } from '@shared/types'
import { useMeStore } from '@/stores/me'
import { useSessionStore } from '@/stores/session'
import { ROUTES } from '@/utils/routes'
import { flushOnHide } from '@/utils/track'
import { clear as storageClear } from '@/utils/storage'
import { toastSuccess, toastError } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize, type FontSizeKey } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import ErrorState from '@/components/ErrorState.vue'
import BasePicker from '@/components-base/BasePicker.vue'
import BaseSwitch from '@/components-base/BaseSwitch.vue'
import BaseInput from '@/components-base/BaseInput.vue'
import BaseButton from '@/components-base/BaseButton.vue'
import BaseDialog from '@/components-base/BaseDialog.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 个人中心 store（settings / settingsSaving / settingsError / loadSettings / saveSettings / exportData / deleteAccount） */
const me = useMeStore()
/** 匿名会话 store（注销后重置内存态，免责门重新生效） */
const session = useSessionStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()
/** 字号平台状态（setSize 切换本地档位并持久化） */
const font = useFontSize()

/** 设置本地编辑缓冲（进入页面从 store 拷贝，统一「保存」落库，对齐源码语义） */
const form = reactive<SettingsData>({
  font_size: 'normal',
  unit: 'gram',
  voice_enabled: false,
  reminder_enabled: false,
})

/** 字号三档选项（value 对齐 SettingsData['font_size'] 枚举） */
const FONT_OPTIONS: Array<{ label: string; value: string }> = [
  { label: '标准', value: 'normal' },
  { label: '大', value: 'large' },
  { label: '特大', value: 'xlarge' },
]

/** 计量单位三选选项（PRD §5.4：克 / 毫升 / 勺） */
const UNIT_OPTIONS: Array<{ label: string; value: string }> = [
  { label: '克（g）', value: 'gram' },
  { label: '毫升（ml）', value: 'milliliter' },
  { label: '勺', value: 'spoon' },
]

/** 注销确认弹层可见性 */
const deleteDialogVisible = ref(false)
/** 注销确认输入文案（须精确输入「注销」才可确认） */
const deleteConfirmText = ref('')
/** 注销请求进行中（防连点） */
const deleting = ref(false)

/** 注销确认按钮可用（输入与确认文案一致才可点） */
const canConfirmDelete = computed(() => deleteConfirmText.value.trim() === '注销')

/**
 * 服务端字号档位 → 小程序本地字号档位映射。
 * platform/fontSize 仅 sm/base/lg 三档且 base 为标准档：normal→base；
 * 本地无第四档，xlarge 与 large 同渲染为 lg（特大档在服务端仍独立保存）。
 * @param fs 服务端字号档位
 * @returns 本地字号档位
 */
function mapServerFont(fs: SettingsData['font_size']): FontSizeKey {
  return fs === 'large' || fs === 'xlarge' ? 'lg' : 'base'
}

/**
 * 字号选择变更：缓冲更新 + useFontSize.setSize 即时同步本地档位（全局立即生效，页内可预览）；
 * 服务端落库仍以「保存」按钮为准（若不保存直接离开，本地字号保留、服务端值不变）。
 * @param value 新字号档位（BasePicker 回传 string）
 * @returns 无
 */
function onFontChange(value: string | number): void {
  form.font_size = value as SettingsData['font_size']
  font.setSize(mapServerFont(form.font_size))
}

/**
 * 计量单位选择变更（仅更新缓冲，统一保存时落库）。
 * @param value 新单位枚举值
 * @returns 无
 */
function onUnitChange(value: string | number): void {
  form.unit = value as SettingsData['unit']
}

/**
 * 保存设置（统一保存，对齐源码 onSaveSettings）：me.saveSettings（PUT /v1/settings）；
 * 失败就地转错误 toast，不向外抛出。
 * @returns 无
 * @throws 不向外抛出（接口异常已就地提示）
 */
async function onSave(): Promise<void> {
  try {
    await me.saveSettings({ ...form })
    toastSuccess('设置已保存')
  } catch (e) {
    toastError((e as ApiError).message || '保存失败，请重试')
  }
}

/**
 * 导出我的数据：me.exportData() 取 JSON 后复制到剪贴板。
 * 平台差异说明：小程序端无 DOM 下载（浏览器 showSaveFilePicker / a[download] 均不可用），
 * 降级方案 = 完整 JSON 复制到剪贴板（微信端系统会自带「内容已复制」提示，可能与本页 toast 双重提示，属预期）。
 * @returns 无
 * @throws 不向外抛出（接口/剪贴板异常均就地提示）
 */
async function onExport(): Promise<void> {
  try {
    const data = await me.exportData()
    uni.setClipboardData({
      data: JSON.stringify(data, null, 2),
      success: () => toastSuccess('已复制到剪贴板'),
      fail: () => toastError('复制失败，请重试'),
    })
  } catch (e) {
    toastError((e as ApiError).message || '导出失败，请重试')
  }
}

/**
 * 打开注销确认弹层（重置确认输入）。
 * @returns 无
 */
function askDeleteAccount(): void {
  deleteConfirmText.value = ''
  deleteDialogVisible.value = true
}

/**
 * 关闭注销确认弹层。
 * @returns 无
 */
function cancelDeleteAccount(): void {
  deleteDialogVisible.value = false
}

/**
 * 确认注销：me.deleteAccount()（DELETE /v1/me）→ 清本地 aicook_ 前缀 storage
 * → 重置会话内存态（匿名 ID / 免责同意记忆）→ reLaunch 免责声明页（免责门重新生效）。
 * @returns 无
 * @throws 不向外抛出（接口异常就地提示）
 */
async function confirmDeleteAccount(): Promise<void> {
  if (!canConfirmDelete.value || deleting.value) return
  deleting.value = true
  try {
    await me.deleteAccount()
    storageClear('aicook_')
    session.anonymousId = ''
    session.disclaimerAgreed = false
    toastSuccess('账号已注销，感谢你的使用')
    uni.reLaunch({ url: ROUTES.DISCLAIMER, fail: () => {} })
  } catch (e) {
    toastError((e as ApiError).message || '注销失败，请重试')
  } finally {
    deleting.value = false
    deleteDialogVisible.value = false
    deleteConfirmText.value = ''
  }
}

// onShow：拉取服务端设置并灌入本地缓冲（保存失败 / 他页改动后返回时即时对齐）
onShow(() => {
  void me.loadSettings().then(() => {
    if (me.settings) {
      form.font_size = me.settings.font_size
      form.unit = me.settings.unit
      form.voice_enabled = me.settings.voice_enabled
      form.reminder_enabled = me.settings.reminder_enabled
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

    <view class="settings">
      <!-- 加载态 -->
      <SkeletonPage v-if="me.settings == null && me.settingsError == null" type="list" :rows="4" />

      <!-- 错误态（重试） -->
      <ErrorState v-else-if="me.settingsError && me.settings == null" kind="server" @retry="me.loadSettings()" />

      <template v-else>
        <!-- ═══ 常规设置 ═══ -->
        <view class="settings__group">
          <text class="settings__group-title">通用</text>
          <view class="settings__cell">
            <text class="settings__label">字号</text>
            <view class="settings__control">
              <BasePicker
                :model-value="form.font_size"
                :options="FONT_OPTIONS"
                placeholder="选择字号"
                @update:model-value="onFontChange"
              />
            </view>
          </view>
          <view class="settings__cell">
            <text class="settings__label">计量单位</text>
            <view class="settings__control">
              <BasePicker
                :model-value="form.unit"
                :options="UNIT_OPTIONS"
                placeholder="选择单位"
                @update:model-value="onUnitChange"
              />
            </view>
          </view>
          <view class="settings__cell">
            <text class="settings__label">语音播报</text>
            <view class="settings__control">
              <BaseSwitch v-model="form.voice_enabled" />
            </view>
          </view>
          <view class="settings__cell settings__cell--last">
            <text class="settings__label">做菜提醒</text>
            <view class="settings__control">
              <BaseSwitch v-model="form.reminder_enabled" />
            </view>
          </view>
        </view>

        <!-- 保存（统一保存，对齐源码语义） -->
        <BaseButton class="settings__save" block :loading="me.settingsSaving" @click="onSave">
          保存设置
        </BaseButton>

        <!-- ═══ 数据权利区（PRD §13.3） ═══ -->
        <view class="settings__group">
          <text class="settings__group-title">数据权利</text>
          <view class="settings__cell">
            <view class="settings__label-wrap">
              <text class="settings__label">导出我的数据</text>
              <text class="settings__label-desc">导出内容将复制到剪贴板（JSON 格式）</text>
            </view>
            <view class="settings__control">
              <BaseButton size="sm" type="default" @click="onExport">导出</BaseButton>
            </view>
          </view>
          <view class="settings__cell settings__cell--last">
            <view class="settings__label-wrap">
              <text class="settings__label">注销账号</text>
              <text class="settings__label-desc">删除档案、库存、收藏等全部数据，不可恢复</text>
            </view>
            <view class="settings__control">
              <BaseButton size="sm" type="danger" @click="askDeleteAccount">注销</BaseButton>
            </view>
          </view>
        </view>
      </template>

      <!-- 注销二次确认弹层：确认文案输入一致才可确认 -->
      <BaseDialog
        :visible="deleteDialogVisible"
        title="注销账号"
        position="center"
        :mask-closable="false"
        show-close
        @close="cancelDeleteAccount"
      >
        <view class="delete-dialog">
          <text class="delete-dialog__text">
            注销将删除你的档案、库存、收藏等全部数据，且不可恢复。确认继续？
          </text>
          <BaseInput
            v-model="deleteConfirmText"
            placeholder="请输入「注销」以确认操作"
            :maxlength="10"
          />
          <view class="delete-dialog__actions">
            <BaseButton type="default" block @click="cancelDeleteAccount">取消</BaseButton>
            <BaseButton
              type="danger"
              block
              :disabled="!canConfirmDelete"
              :loading="deleting"
              @click="confirmDeleteAccount"
            >
              确认注销
            </BaseButton>
          </view>
        </view>
      </BaseDialog>
    </view>
  </view>
</template>

<style scoped lang="scss">
.settings {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md) var(--space-md) var(--space-xl);
}

.settings__group {
  margin-bottom: var(--space-lg);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  padding: var(--space-md) var(--space-sm) var(--space-xs);
}

.settings__group-title {
  display: block;
  margin: 0 0 var(--space-xs) var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.settings__cell {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  min-height: var(--hit-min);
  padding: var(--space-xs) var(--space-xs);
  border-bottom: 1rpx solid var(--divider);

  /* 组内最后一行去分割线 */
  &--last {
    border-bottom: none;
  }
}

.settings__label,
.settings__label-wrap {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4rpx;
}

.settings__label {
  font-size: var(--font-size-base);
  color: var(--text-primary);
}

.settings__label-desc {
  font-size: var(--font-size-sm);
  line-height: 1.5;
  color: var(--text-tertiary);
}

.settings__control {
  flex-shrink: 0;
  min-width: 220rpx;
}

.settings__save {
  margin-bottom: var(--space-lg);
}

/* ── 注销确认弹层 ── */
.delete-dialog {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
  padding: var(--space-sm) 0 var(--space-md);
}

.delete-dialog__text {
  font-size: var(--font-size-base);
  line-height: 1.6;
  color: var(--text-primary);
}

.delete-dialog__actions {
  display: flex;
  gap: var(--space-sm);
}
</style>
