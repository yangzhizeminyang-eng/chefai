<!-- 文件职责：远程开关管理。五大能力开关（修改确认 + 失败回退）+ 一键回滚（恢复上一份快照）。 -->
<script setup lang="ts">
/**
 * 远程开关逻辑：加载开关状态、单开关切换（before-change 确认并调接口）、一键回滚。
 * 所有写操作前置确认，只读角色统一拦截提示。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { SWITCH_DEFAULTS, getErrorMessage, getSwitches, notifyApiError, rollbackSwitches, updateSwitches } from '@/api/admin'
import type { SwitchesState } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'
import { confirmAction } from '@/utils/interaction'

const auth = useAuthStore()

/** 开关展示元信息 */
const SWITCH_META: { key: keyof SwitchesState; label: string; description: string }[] = [
  { key: 'recommend', label: '推荐服务', description: '关闭后不再提供个性化菜谱推荐' },
  { key: 'vision', label: '视觉识别', description: '拍照识菜 / 卡路里识别能力' },
  { key: 'qa', label: '智能问答', description: '美食问答 Agent' },
  { key: 'payment', label: '支付能力', description: '会员与下单支付入口' },
  { key: 'innovation', label: '创新玩法', description: '创新菜谱生成与巡检' },
]

/** 开关状态（加载后覆盖） */
const switches = reactive<SwitchesState>({ ...SWITCH_DEFAULTS })
/** 加载中标记 */
const loading = ref(false)
/** 加载错误文案 */
const error = ref('')
/** 回滚请求进行中标记 */
const rollbacking = ref(false)

/**
 * 加载开关状态。
 */
async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    Object.assign(switches, await getSwitches())
  } catch (e) {
    error.value = getErrorMessage(e, '开关配置加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 单开关切换守卫（el-switch :before-change）：确认 → 调接口 → 成功才允许 UI 翻转。
 * @param key 开关键名
 * @returns 允许翻转返回 true
 */
async function guardSwitch(key: keyof SwitchesState): Promise<boolean> {
  if (!auth.ensureWritable()) return false
  const next = !switches[key]
  const meta = SWITCH_META.find((it) => it.key === key)
  if (!await confirmAction(`确认${next ? '开启' : '关闭'}「${meta?.label ?? key}」？`, '开关变更确认')) return false
  try {
    await updateSwitches({ ...switches, [key]: next })
    ElMessage.success(`已${next ? '开启' : '关闭'}「${meta?.label ?? key}」`)
    return true
  } catch (e) {
    notifyApiError(e, '开关更新失败')
    return false
  }
}

/**
 * 一键回滚开关（恢复上一份快照）。
 */
async function handleRollback(): Promise<void> {
  if (!auth.ensureWritable()) return
  if (!await confirmAction('确认将全部开关回滚到上一份快照？', '回滚确认')) return
  rollbacking.value = true
  try {
    await rollbackSwitches()
    ElMessage.success('回滚成功')
    await load()
  } catch (e) {
    notifyApiError(e, '回滚失败')
  } finally {
    rollbacking.value = false
  }
}

onMounted(() => {
  load()
})
</script>

<template>
  <div class="page">
    <el-card shadow="never">
      <div class="toolbar">
        <span class="muted">远程开关实时控制线上各能力入口，修改前请确认影响范围。</span>
        <div class="grow" />
        <el-button @click="load">刷新</el-button>
        <el-button type="warning" :loading="rollbacking" @click="handleRollback">一键回滚</el-button>
      </div>

      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" class="block">
        <el-button size="small" @click="load">重试</el-button>
      </el-alert>

      <div v-loading="loading" class="switch-list">
        <div v-for="item in SWITCH_META" :key="item.key" class="switch-row">
          <div class="switch-info">
            <div class="switch-label">
              {{ item.label }}
              <span class="mono muted">{{ item.key }}</span>
            </div>
            <div class="muted">{{ item.description }}</div>
          </div>
          <el-switch :model-value="switches[item.key]" :before-change="() => guardSwitch(item.key)" />
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.switch-list {
  min-height: 160px;
}

.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 4px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.switch-row:last-child {
  border-bottom: none;
}

.switch-label {
  font-weight: 600;
  margin-bottom: 4px;
}
</style>
