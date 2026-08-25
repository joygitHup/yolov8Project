<template>
  <div class="cameras-page">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <span class="header-title">摄像头管理</span>
          <div class="header-actions">
            <el-button type="primary" :icon="Plus" @click="handleAdd">
              新增摄像头
            </el-button>
            <el-button :icon="Refresh" @click="loadData">刷新</el-button>
          </div>
        </div>
      </template>

      <!-- 筛选区 -->
      <div class="filter-bar">
        <el-form :inline="true" :model="filterForm">
          <el-form-item label="名称/位置">
            <el-input
              v-model="filterForm.keyword"
              placeholder="请输入关键词"
              clearable
              style="width: 200px"
              @keyup.enter="loadData"
            />
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="filterForm.status" placeholder="全部" clearable style="width: 120px">
              <el-option label="在线" value="online" />
              <el-option label="离线" value="offline" />
            </el-select>
          </el-form-item>
          <el-form-item label="设备类型">
            <el-select v-model="filterForm.type" placeholder="全部" clearable style="width: 120px">
              <el-option label="海康威视" value="hikvision" />
              <el-option label="大华" value="dahua" />
              <el-option label="其他" value="other" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="loadData">查询</el-button>
            <el-button @click="resetFilter">重置</el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 批量操作 -->
      <div class="batch-bar" v-if="selectedIds.length > 0">
        <span>已选择 {{ selectedIds.length }} 项</span>
        <el-button type="danger" size="small" :icon="Delete" @click="handleBatchDelete">
          批量删除
        </el-button>
        <el-button size="small" @click="clearSelection">取消选择</el-button>
      </div>

      <!-- 列表 -->
      <el-table
        :data="tableData"
        v-loading="loading"
        border
        stripe
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="50" />
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="摄像头名称" min-width="140">
          <template #default="{ row }">
            <div class="cam-name-cell">
              <el-icon :class="row.status === 'online' ? 'online' : 'offline'">
                <VideoCamera />
              </el-icon>
              <span>{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="location" label="位置" min-width="120" />
        <el-table-column prop="ip" label="IP 地址" width="130" />
        <el-table-column label="设备类型" width="100">
          <template #default="{ row }">
            {{ typeText(row.type) }}
          </template>
        </el-table-column>
        <el-table-column prop="resolution" label="分辨率" width="110" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'online' ? 'success' : 'danger'" size="small">
              {{ row.status === 'online' ? '在线' : '离线' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用状态" width="80">
          <template #default="{ row }">
            <el-switch
              v-model="row.enabled"
              size="small"
              @change="handleToggle(row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="检测类型" min-width="160">
          <template #default="{ row }">
            <el-tag
              v-for="t in row.detectionTypes"
              :key="t"
              size="small"
              style="margin-right: 4px"
            >
              {{ detectionText(t) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="createdAt" label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatDate(row.createdAt) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="handlePreview(row)">
              预览
            </el-button>
            <el-button type="primary" link size="small" @click="handleEdit(row)">
              编辑
            </el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'add' ? '新增摄像头' : '编辑摄像头'"
      width="600px"
      @closed="resetForm"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="100px"
      >
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="名称" prop="name">
              <el-input v-model="formData.name" placeholder="请输入摄像头名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="位置" prop="location">
              <el-input v-model="formData.location" placeholder="请输入安装位置" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="IP 地址" prop="ip">
              <el-input v-model="formData.ip" placeholder="如：192.168.1.100" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="设备类型" prop="type">
              <el-select v-model="formData.type" style="width: 100%">
                <el-option label="海康威视" value="hikvision" />
                <el-option label="大华" value="dahua" />
                <el-option label="其他" value="other" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="RTSP 地址" prop="rtsp">
          <el-input v-model="formData.rtsp" placeholder="rtsp://username:password@ip:port/stream" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="用户名">
              <el-input v-model="formData.username" placeholder="默认为 admin" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="密码">
              <el-input v-model="formData.password" type="password" show-password placeholder="设备密码" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="分辨率">
              <el-select v-model="formData.resolution" style="width: 100%">
                <el-option label="1920x1080" value="1920x1080" />
                <el-option label="1280x720" value="1280x720" />
                <el-option label="3840x2160" value="3840x2160" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="通道数">
              <el-input-number v-model="formData.channels" :min="1" :max="32" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="检测类型">
          <el-checkbox-group v-model="formData.detectionTypes">
            <el-checkbox value="intrusion">区域入侵</el-checkbox>
            <el-checkbox value="parking">违停检测</el-checkbox>
            <el-checkbox value="fire">火灾检测</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="formData.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { cameraApi } from '@/api'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Refresh, Delete, VideoCamera } from '@element-plus/icons-vue'
import dayjs from 'dayjs'

const router = useRouter()
const loading = ref(false)
const submitLoading = ref(false)
const dialogVisible = ref(false)
const dialogMode = ref<'add' | 'edit'>('add')
const formRef = ref<FormInstance>()
const tableData = ref<any[]>([])
const selectedIds = ref<number[]>([])

const filterForm = reactive({
  keyword: '',
  status: '',
  type: ''
})

const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0
})

const formData = reactive({
  name: '',
  location: '',
  ip: '',
  type: 'hikvision',
  rtsp: '',
  username: 'admin',
  password: '',
  resolution: '1920x1080',
  channels: 1,
  enabled: true,
  detectionTypes: ['intrusion', 'parking', 'fire'] as string[]
})

const formRules: FormRules = {
  name: [
    { required: true, message: '请输入摄像头名称', trigger: 'blur' }
  ],
  rtsp: [
    { required: true, message: '请输入 RTSP 地址', trigger: 'blur' }
  ]
}

function typeText(type: string) {
  const map: Record<string, string> = {
    hikvision: '海康威视',
    dahua: '大华',
    other: '其他'
  }
  return map[type] || type
}

function detectionText(type: string) {
  const map: Record<string, string> = {
    intrusion: '区域入侵',
    parking: '违停检测',
    fire: '火灾检测'
  }
  return map[type] || type
}

function formatDate(date: string) {
  return dayjs(date).format('YYYY-MM-DD HH:mm:ss')
}

async function loadData() {
  loading.value = true
  try {
    const res: any = await cameraApi.getList({
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
  filterForm.status = ''
  filterForm.type = ''
  pagination.page = 1
  loadData()
}

function handleSelectionChange(selection: any[]) {
  selectedIds.value = selection.map(item => item.id)
}

function clearSelection() {
  selectedIds.value = []
}

function handleAdd() {
  dialogMode.value = 'add'
  resetForm()
  dialogVisible.value = true
}

function handleEdit(row: any) {
  dialogMode.value = 'edit'
  Object.assign(formData, row)
  if (!formData.detectionTypes) formData.detectionTypes = []
  dialogVisible.value = true
}

function handlePreview(row: any) {
  router.push('/monitor')
}

async function handleToggle(row: any) {
  try {
    await cameraApi.toggle(row.id)
    ElMessage.success(row.enabled ? '已启用' : '已禁用')
  } catch (e) {
    row.enabled = !row.enabled
  }
}

function handleDelete(row: any) {
  ElMessageBox.confirm(`确定要删除摄像头"${row.name}"吗？`, '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    await cameraApi.delete(row.id)
    ElMessage.success('删除成功')
    loadData()
  }).catch(() => {})
}

async function handleBatchDelete() {
  ElMessageBox.confirm(`确定要删除选中的 ${selectedIds.value.length} 个摄像头吗？`, '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    await cameraApi.batchDelete(selectedIds.value)
    ElMessage.success('删除成功')
    clearSelection()
    loadData()
  }).catch(() => {})
}

async function handleSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
    submitLoading.value = true

    if (dialogMode.value === 'add') {
      await cameraApi.add(formData)
      ElMessage.success('新增成功')
    } else {
      await cameraApi.update((formData as any).id, formData)
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

function resetForm() {
  Object.assign(formData, {
    name: '',
    location: '',
    ip: '',
    type: 'hikvision',
    rtsp: '',
    username: 'admin',
    password: '',
    resolution: '1920x1080',
    channels: 1,
    enabled: true,
    detectionTypes: ['intrusion', 'parking', 'fire']
  })
  formRef.value?.clearValidate()
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.cameras-page {
  padding: 4px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-title {
  font-weight: 600;
  font-size: 16px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.filter-bar {
  padding: 16px 0;
  border-bottom: 1px solid #e5e7eb;
  margin-bottom: 16px;
}

.batch-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: #e6f4ff;
  border-radius: 4px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #1677ff;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

.cam-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cam-name-cell .online {
  color: #52c41a;
}

.cam-name-cell .offline {
  color: #9ca3af;
}
</style>
