<template>
  <div class="config-page">
    <el-row :gutter="20">
      <el-col :span="4">
        <el-card class="nav-card">
          <el-menu :default-active="activeMenu" router class="config-menu">
            <el-menu-item index="/config"><el-icon><Setting /></el-icon><span>系统设置</span></el-menu-item>
            <el-menu-item index="/config/detection"><el-icon><Aim /></el-icon><span>检测参数</span></el-menu-item>
            <el-menu-item index="/config/strategies"><el-icon><Lock /></el-icon><span>布防策略</span></el-menu-item>
            <el-menu-item index="/config/notification"><el-icon><Message /></el-icon><span>通知配置</span></el-menu-item>
            <el-menu-item v-if="userStore.isAdmin" index="/config/users"><el-icon><User /></el-icon><span>用户管理</span></el-menu-item>
          </el-menu>
        </el-card>
      </el-col>

      <el-col :span="20">
        <el-card v-loading="loading" class="content-card">
          <template #header>
            <div class="card-header">
              <span class="card-title">用户管理</span>
              <el-button type="primary" :icon="Plus" @click="handleAdd">新增用户</el-button>
            </div>
          </template>

          <div class="filter-bar">
            <el-form :inline="true" :model="filterForm">
              <el-form-item label="用户名">
                <el-input v-model="filterForm.keyword" placeholder="搜索用户名/姓名" clearable style="width: 200px" />
              </el-form-item>
              <el-form-item label="角色">
                <el-select v-model="filterForm.role" placeholder="全部" clearable style="width: 120px">
                  <el-option label="管理员" value="admin" />
                  <el-option label="操作员" value="operator" />
                  <el-option label="查看者" value="viewer" />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="loadData">查询</el-button>
                <el-button @click="resetFilter">重置</el-button>
              </el-form-item>
            </el-form>
          </div>

          <el-table :data="tableData" border stripe>
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column label="头像" width="70">
              <template #default="{ row }">
                <el-avatar :size="32" :src="row.avatar">
                  {{ row.username?.charAt(0).toUpperCase() }}
                </el-avatar>
              </template>
            </el-table-column>
            <el-table-column prop="username" label="用户名" width="140" />
            <el-table-column prop="realName" label="姓名" width="120" />
            <el-table-column label="角色" width="100">
              <template #default="{ row }">
                <el-tag :type="roleTagType(row.role)" size="small">
                  {{ roleText(row.role) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="email" label="邮箱" width="180" />
            <el-table-column prop="phone" label="手机号" width="130" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-switch v-model="row.enabled" size="small" @change="handleToggleStatus(row)" />
              </template>
            </el-table-column>
            <el-table-column prop="lastLoginAt" label="最后登录" width="170">
              <template #default="{ row }">
                {{ row.lastLoginAt ? formatDate(row.lastLoginAt) : '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="createdAt" label="创建时间" width="170">
              <template #default="{ row }">
                {{ formatDate(row.createdAt) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="handleEdit(row)">编辑</el-button>
                <el-button type="primary" link size="small" @click="handleResetPwd(row)">重置密码</el-button>
                <el-button v-if="row.id !== userStore.userInfo?.id" type="danger" link size="small" @click="handleDelete(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination">
            <el-pagination
              v-model:current-page="pagination.page"
              v-model:page-size="pagination.pageSize"
              :total="pagination.total"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="loadData"
              @current-change="loadData"
            />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'add' ? '新增用户' : '编辑用户'"
      width="500px"
    >
      <el-form :model="formData" label-width="100px">
        <el-form-item label="用户名">
          <el-input v-model="formData.username" :disabled="dialogMode === 'edit'" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="formData.realName" />
        </el-form-item>
        <el-form-item v-if="dialogMode === 'add'" label="密码">
          <el-input v-model="formData.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="角色">
          <el-radio-group v-model="formData.role">
            <el-radio value="admin">管理员</el-radio>
            <el-radio value="operator">操作员</el-radio>
            <el-radio value="viewer">查看者</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="formData.email" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="formData.phone" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="formData.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { authApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Setting, Aim, Lock, Message, User, Plus } from '@element-plus/icons-vue'
import dayjs from 'dayjs'

const route = useRoute()
const userStore = useUserStore()
const loading = ref(false)
const submitLoading = ref(false)
const activeMenu = ref('/config/users')
const tableData = ref<any[]>([])
const dialogVisible = ref(false)
const dialogMode = ref<'add' | 'edit'>('add')

const filterForm = reactive({
  keyword: '',
  role: ''
})

const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0
})

const formData = reactive<any>({
  username: '',
  realName: '',
  password: '',
  role: 'operator',
  email: '',
  phone: '',
  enabled: true
})

function roleText(role: string) {
  const map: Record<string, string> = { admin: '管理员', operator: '操作员', viewer: '查看者' }
  return map[role] || role
}

function roleTagType(role: string) {
  const map: Record<string, string> = { admin: 'danger', operator: 'primary', viewer: 'info' }
  return map[role] || 'info'
}

function formatDate(date: string) {
  return dayjs(date).format('YYYY-MM-DD HH:mm:ss')
}

async function loadData() {
  loading.value = true
  try {
    const res: any = await authApi.getUsers({
      page: pagination.page,
      pageSize: pagination.pageSize,
      ...filterForm
    })
    tableData.value = res.list || []
    pagination.total = res.total || 0
  } finally {
    loading.value = false
  }
}

function resetFilter() {
  filterForm.keyword = ''
  filterForm.role = ''
  pagination.page = 1
  loadData()
}

function handleAdd() {
  dialogMode.value = 'add'
  Object.assign(formData, {
    username: '',
    realName: '',
    password: '',
    role: 'operator',
    email: '',
    phone: '',
    enabled: true
  })
  dialogVisible.value = true
}

function handleEdit(row: any) {
  dialogMode.value = 'edit'
  Object.assign(formData, row)
  dialogVisible.value = true
}

async function handleToggleStatus(row: any) {
  try {
    await authApi.updateUser(row.id, { enabled: !row.enabled })
    ElMessage.success(row.enabled ? '已启用' : '已禁用')
  } catch (e) {
    row.enabled = !row.enabled
  }
}

function handleResetPwd(row: any) {
  ElMessageBox.prompt('请输入新密码', `重置 ${row.username} 的密码`, {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputType: 'password',
    inputValidator: (value: string) => {
      if (!value || value.length < 6) return '密码长度至少 6 位'
      return true
    }
  }).then(async ({ value }: any) => {
    await authApi.resetPassword(row.id, { newPassword: value })
    ElMessage.success('密码已重置')
  }).catch(() => {})
}

function handleDelete(row: any) {
  ElMessageBox.confirm(`确定要删除用户"${row.username}"吗？`, '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    await authApi.deleteUser(row.id)
    ElMessage.success('删除成功')
    loadData()
  }).catch(() => {})
}

async function handleSubmit() {
  submitLoading.value = true
  try {
    if (dialogMode.value === 'add') {
      await authApi.addUser(formData)
      ElMessage.success('新增成功')
    } else {
      await authApi.updateUser(formData.id, formData)
      ElMessage.success('更新成功')
    }
    dialogVisible.value = false
    loadData()
  } catch (e) {
    // 错误已处理
  } finally {
    submitLoading.value = false
  }
}

onMounted(() => {
  activeMenu.value = route.path
  loadData()
})
</script>

<style scoped>
.config-page {
  padding: 4px;
}

.nav-card {
  padding: 0;
}

.config-menu {
  border-right: none;
}

.config-menu :deep(.el-menu-item) {
  height: 48px;
  line-height: 48px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-weight: 600;
  font-size: 16px;
}

.filter-bar {
  padding-bottom: 16px;
  border-bottom: 1px solid #e5e7eb;
  margin-bottom: 16px;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}
</style>
