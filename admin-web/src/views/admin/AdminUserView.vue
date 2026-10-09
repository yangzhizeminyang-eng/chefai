<!-- 文件职责：成员权限管理。成员表格 + 新增（用户名/密码/角色）+ 编辑（三级角色/状态/重置密码）。 -->
<script setup lang="ts">
/**
 * 成员权限逻辑：成员列表三态、新增成员表单、编辑成员（角色 / 状态 / 可选重置密码）。
 * 所有写操作前置确认，只读角色统一拦截提示。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

import { ROLE_LABELS, createAdminUser, listAdminUsers, notifyApiError, updateAdminUser } from '@/api/admin'
import type { AdminRole, AdminUser } from '@/api/admin'
import { useSimpleList } from '@/composables/useList'
import { useAuthStore } from '@/stores/auth'
import { confirmAction } from '@/utils/interaction'
import { formatDate } from '@/utils/format'

const auth = useAuthStore()

/** 角色选项（三级） */
const ROLE_OPTIONS: { value: AdminRole; label: string }[] = [
  { value: 'super_admin', label: '超级管理员' },
  { value: 'content_ops', label: '内容运营' },
  { value: 'readonly', label: '只读' },
]

// 列表三态
const { loading, error, items, load } = useSimpleList<AdminUser>(async () => (await listAdminUsers()).items)

// ==================== 新增 / 编辑 ====================

const dialogVisible = ref(false)
/** 表单模式：create 新增 / edit 编辑 */
const mode = ref<'create' | 'edit'>('create')
/** 当前编辑的成员 ID */
const editingId = ref(0)
/** 保存请求进行中标记 */
const saving = ref(false)
/** 表单引用（用于触发校验） */
const formRef = ref<FormInstance>()

/** 成员表单（编辑时 password 留空表示不重置） */
const form = reactive({
  username: '',
  password: '',
  role: 'content_ops' as AdminRole,
  status: 'active' as 'active' | 'disabled',
})

/** 表单校验规则（新增时密码必填，编辑时可不填） */
const rules = computed<FormRules>(() => ({
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: mode.value === 'create'
    ? [{ required: true, message: '请输入初始密码', trigger: 'blur' }]
    : [],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}))

/**
 * 打开新增成员对话框（只读角色拦截）。
 */
function openCreate(): void {
  if (!auth.ensureWritable()) return
  mode.value = 'create'
  editingId.value = 0
  form.username = ''
  form.password = ''
  form.role = 'content_ops'
  form.status = 'active'
  dialogVisible.value = true
}

/**
 * 打开编辑成员对话框并回填。
 * @param row 列表行
 */
function openEdit(row: AdminUser): void {
  if (!auth.ensureWritable()) return
  mode.value = 'edit'
  editingId.value = row.id
  form.username = row.username
  form.password = ''
  form.role = row.role
  form.status = row.status
  dialogVisible.value = true
}

/**
 * 保存成员（新增或更新）。
 */
async function handleSave(): Promise<void> {
  const valid = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  if (!await confirmAction(mode.value === 'create' ? '确认新增该成员？' : '确认保存成员修改？', '保存确认')) return
  saving.value = true
  try {
    if (mode.value === 'create') {
      await createAdminUser({ username: form.username.trim(), password: form.password, role: form.role })
      ElMessage.success('新增成功')
    } else {
      await updateAdminUser(editingId.value, {
        role: form.role,
        status: form.status,
        password: form.password.trim() || undefined,
      })
      ElMessage.success('保存成功')
    }
    dialogVisible.value = false
    await load()
  } catch (e) {
    notifyApiError(e, '保存失败')
  } finally {
    saving.value = false
  }
}

/**
 * 状态开关回调（编辑表单内启用/停用）。
 * @param value 开关值
 */
function onStatusChange(value: boolean | string | number): void {
  form.status = value ? 'active' : 'disabled'
}

onMounted(() => {
  load()
})
</script>

<template>
  <div class="page">
    <el-card shadow="never">
      <div class="toolbar">
        <span class="muted">角色三级：超级管理员（全部权限）/ 内容运营（内容类）/ 只读（仅查看）。</span>
        <div class="grow" />
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">新增成员</el-button>
      </div>

      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" class="block">
        <el-button size="small" @click="load">重试</el-button>
      </el-alert>

      <el-table v-loading="loading" :data="items" border stripe>
        <template #empty><el-empty description="暂无成员数据" /></template>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column label="角色" width="130">
          <template #default="{ row }">
            <el-tag :type="row.role === 'super_admin' ? 'danger' : row.role === 'content_ops' ? 'primary' : 'info'">
              {{ ROLE_LABELS[row.role as AdminRole] ?? row.role }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" effect="plain">
              {{ row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增 / 编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="mode === 'create' ? '新增成员' : '编辑成员'" width="460px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="用户名" :disabled="mode === 'edit'" maxlength="50" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="mode === 'create' ? '初始密码' : '留空表示不修改密码'"
          />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" style="width: 100%">
            <el-option v-for="opt in ROLE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="mode === 'edit'" label="状态">
          <el-switch
            :model-value="form.status === 'active'"
            active-text="启用"
            inactive-text="停用"
            @change="onStatusChange"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
