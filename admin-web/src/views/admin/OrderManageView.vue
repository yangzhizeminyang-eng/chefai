<!-- 文件职责：订单管理。订单表格（状态筛选）+ 补发按钮（人工修正补发权益，原因必填）。 -->
<script setup lang="ts">
/**
 * 订单管理逻辑：按状态筛选列表三态、补发对话框（原因必填 + 确认）。
 * 所有写操作前置确认，只读角色统一拦截提示。
 */
import { onMounted, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

import { compensateOrder, listOrders, notifyApiError } from '@/api/admin'
import type { OrderItem } from '@/api/admin'
import { useSimpleList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { confirmAction } from '@/utils/interaction'
import { formatDate, formatYuan } from '@/utils/format'

const auth = useAuthStore()

/** 订单状态展示映射（未知状态回退展示原始值） */
const ORDER_STATUS_META: Record<string, { label: string; type: 'success' | 'info' | 'warning' | 'danger' | 'primary' }> = {
  pending: { label: '待支付', type: 'warning' },
  paid: { label: '已支付', type: 'success' },
  refunded: { label: '已退款', type: 'info' },
  compensated: { label: '已补发', type: 'primary' },
}

/** 状态筛选值（空字符串表示全部） */
const status = ref('')

// 列表三态
const { loading, error, items, load } = useSimpleList<OrderItem>(async () =>
  (await listOrders({ status: status.value || undefined })).items,
)

// ==================== 补发 ====================

const compensateVisible = ref(false)
/** 当前补发的订单 */
const currentOrder = ref<OrderItem | null>(null)
/** 补发原因（必填） */
const reason = ref('')
/** 提交进行中标记 */
const saving = ref(false)
/** 表单引用（用于触发校验） */
const formRef = ref<FormInstance>()

/** 补发表单校验规则（原因必填） */
const rules: FormRules = {
  reason: [{ required: true, message: '请填写补发原因', trigger: 'blur' }],
}

/**
 * 打开补发对话框（只读角色拦截）。
 * @param row 订单行
 */
function openCompensate(row: OrderItem): void {
  if (!auth.ensureWritable()) return
  currentOrder.value = row
  reason.value = ''
  compensateVisible.value = true
}

/**
 * 提交补发：原因校验通过 + 确认后调用接口。
 */
async function handleCompensate(): Promise<void> {
  const valid = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  if (!currentOrder.value) return
  if (!await confirmAction(`确认为订单 ${currentOrder.value.order_no} 人工补发权益？`, '补发确认')) return
  saving.value = true
  try {
    await compensateOrder(currentOrder.value.order_no, reason.value.trim())
    ElMessage.success('补发成功')
    compensateVisible.value = false
    await load()
  } catch (e) {
    notifyApiError(e, '补发失败')
  } finally {
    saving.value = false
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
        <el-select v-model="status" placeholder="状态" clearable style="width: 160px" @change="load">
          <el-option label="全部" value="" />
          <el-option label="待支付" value="pending" />
          <el-option label="已支付" value="paid" />
          <el-option label="已退款" value="refunded" />
          <el-option label="已补发" value="compensated" />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
        <div class="grow" />
        <el-button @click="load">刷新</el-button>
      </div>

      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" class="block">
        <el-button size="small" @click="load">重试</el-button>
      </el-alert>

      <el-table v-loading="loading" :data="items" border stripe>
        <template #empty><el-empty description="暂无订单数据" /></template>
        <el-table-column label="订单号" min-width="180">
          <template #default="{ row }"><span class="mono">{{ row.order_no }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="ORDER_STATUS_META[row.status]?.type ?? 'info'">
              {{ ORDER_STATUS_META[row.status]?.label ?? row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="120">
          <template #default="{ row }">{{ row.amount_cents != null ? formatYuan(row.amount_cents) : '-' }}</template>
        </el-table-column>
        <el-table-column label="用户（脱敏）" width="160">
          <template #default="{ row }">
            <span class="mono">{{ row.user_id_hash || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="下单时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button link type="warning" @click="openCompensate(row)">补发</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 补发对话框 -->
    <el-dialog v-model="compensateVisible" title="人工修正补发" width="480px" destroy-on-close>
      <el-form ref="formRef" :model="{ reason }" :rules="rules" label-width="80px">
        <el-form-item label="订单号">
          <span class="mono">{{ currentOrder?.order_no }}</span>
        </el-form-item>
        <el-form-item label="原因" prop="reason">
          <el-input v-model="reason" type="textarea" :rows="3" placeholder="必填，请说明人工修正补发的原因" maxlength="200" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="compensateVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleCompensate">确认补发</el-button>
      </template>
    </el-dialog>
  </div>
</template>
