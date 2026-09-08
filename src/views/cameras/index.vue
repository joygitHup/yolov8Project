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
          <el-form-item label="在线状态">
            <el-select v-model="filterForm.status" placeholder="全部" clearable style="width: 120px">
              <el-option label="在线" value="online" />
              <el-option label="离线" value="offline" />
            </el-select>
          </el-form-item>
          <el-form-item label="启用状态">
            <el-select v-model="filterForm.enabled" placeholder="全部" clearable style="width: 120px">
              <el-option label="已启用" value="true" />
              <el-option label="已禁用" value="false" />
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

      <div class="batch-bar" v-if="selectedIds.length > 0">
        <span>已选择 {{ selectedIds.length }} 项</span>
        <el-button type="danger" size="small" :icon="Delete" @click="handleBatchDelete">
          批量删除
        </el-button>
        <el-button size="small" @click="clearSelection">取消选择</el-button>
      </div>

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
              <el-icon :class="row.live ? 'online' : 'offline'">
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
        <el-table-column label="画面" width="90">
          <template #default="{ row }">
            <el-tag :type="row.live ? 'success' : 'info'" size="small">
              {{ row.live ? '在播' : '未在播' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="流状态" min-width="220">
          <template #default="{ row }">
            <el-tag :type="row.rtspConfigured ? 'success' : 'info'" size="small" style="margin-right: 4px">
              RTSP
            </el-tag>
            <el-tag :type="row.hlsReady ? 'success' : 'info'" size="small" style="margin-right: 4px">
              HLS
            </el-tag>
            <el-tag :type="row.hasLastFrame ? 'success' : 'info'" size="small" style="margin-right: 4px">
              帧
            </el-tag>
            <el-tag :type="row.armed ? 'success' : 'info'" size="small">
              布防
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-switch
              v-model="row.enabled"
              size="small"
              @change="(val) => handleToggle(row, !!val)"
            />
          </template>
        </el-table-column>
        <el-table-column label="检测类型" min-width="160">
          <template #default="{ row }">
            <el-tag
              v-for="t in row.detectionTypes || []"
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
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openPreview(row)">
              预览
            </el-button>
            <el-button type="primary" link size="small" @click="goMonitor(row)">
              监控
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

    <!-- 新增/编辑 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'add' ? '新增摄像头' : '编辑摄像头'"
      width="640px"
      destroy-on-close
      @closed="onDialogClosed"
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
            <el-form-item :label="dialogMode === 'edit' ? '新密码' : '密码'">
              <el-input
                v-model="formData.password"
                type="password"
                show-password
                :placeholder="dialogMode === 'edit' ? '留空则不修改' : '设备密码'"
              />
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
              <el-input-number v-model="formData.channels" :min="1" :max="64" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="在线状态">
              <el-select v-model="formData.status" style="width: 100%">
                <el-option label="在线" value="online" />
                <el-option label="离线" value="offline" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="启用">
              <el-switch v-model="formData.enabled" />
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
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- 预览 -->
    <el-dialog
      v-model="previewVisible"
      :title="previewCamera ? `预览 - ${previewCamera.name}` : '预览'"
      width="720px"
      destroy-on-close
      @closed="closePreview"
    >
      <div class="preview-meta" v-if="previewCamera">
        <el-tag size="small" :type="previewCamera.status === 'online' ? 'success' : 'danger'">
          {{ previewCamera.live ? '在播' : '未在播' }}
        </el-tag>
        <el-tag size="small" :type="previewCamera.enabled ? 'success' : 'info'">
          {{ previewCamera.enabled ? '已启用' : '已禁用' }}
        </el-tag>
        <el-tag size="small" :type="previewCamera.hlsReady ? 'success' : 'info'">HLS</el-tag>
        <el-tag size="small" :type="previewCamera.armed ? 'success' : 'info'">
          {{ previewCamera.armed ? '布防中' : '未布防' }}
        </el-tag>
        <span class="meta-text">{{ previewCamera.location || '-' }} · {{ previewCamera.ip || '-' }}</span>
      </div>
      <div class="preview-box" v-loading="previewLoading">
        <video
          v-show="previewHlsUrl"
          ref="previewVideoRef"
          class="preview-video"
          muted
          autoplay
          playsinline
          controls
        />
        <div v-if="!previewHlsUrl && !previewLoading" class="preview-empty">
          {{ previewError || '预览视频未获取到' }}
        </div>
      </div>
      <template #footer>
        <el-button @click="previewVisible = false">关闭</el-button>
        <el-button type="primary" :disabled="!previewCamera" @click="goMonitor(previewCamera!)">
          进入实时监控
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { cameraApi, waitStreamReady } from '@/api'
import { attachHls, type HlsHandle } from '@/utils/hlsPlayer'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Refresh, Delete, VideoCamera } from '@element-plus/icons-vue'
import dayjs from 'dayjs'

/** Canonical camera management row (matches CameraSerializer) */
interface CameraItem {
  id: number
  name: string
  location: string
  ip: string
  rtsp: string
  type: 'hikvision' | 'dahua' | 'other' | string
  username: string
  resolution: string
  channels: number
  status: 'online' | 'offline' | string
  enabled: boolean
  live: boolean
  rtspConfigured?: boolean
  hlsReady?: boolean
  previewReady?: boolean
  hasLastFrame?: boolean
  inferActive?: boolean
  armed?: boolean
  detectionTypes: string[]
  createdAt?: string
  updatedAt?: string
}

const router = useRouter()
const loading = ref(false)
const submitLoading = ref(false)
const dialogVisible = ref(false)
const dialogMode = ref<'add' | 'edit'>('add')
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const tableData = ref<CameraItem[]>([])
const selectedIds = ref<number[]>([])

const filterForm = reactive({
  keyword: '',
  status: '',
  enabled: '' as '' | 'true' | 'false',
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
  status: 'online',
  enabled: true,
  detectionTypes: ['intrusion', 'parking', 'fire'] as string[]
})

const formRules: FormRules = {
  name: [{ required: true, message: '请输入摄像头名称', trigger: 'blur' }],
  rtsp: [{ required: true, message: '请输入 RTSP 地址', trigger: 'blur' }]
}

const previewVisible = ref(false)
const previewLoading = ref(false)
const previewCamera = ref<CameraItem | null>(null)
const previewHlsUrl = ref('')
const previewError = ref('')
const previewVideoRef = ref<HTMLVideoElement | null>(null)
let previewHandle: HlsHandle | null = null

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

function formatDate(date?: string) {
  if (!date) return '-'
  return dayjs(date).format('YYYY-MM-DD HH:mm:ss')
}

function normalizeCamera(raw: any): CameraItem {
  return {
    id: Number(raw.id),
    name: raw.name || '',
    location: raw.location || '',
    ip: raw.ip || '',
    rtsp: raw.rtsp || '',
    type: raw.type || 'other',
    username: raw.username || '',
    resolution: raw.resolution || '1920x1080',
    channels: Number(raw.channels || 1),
    status: raw.status === 'offline' ? 'offline' : 'online',
    enabled: !!raw.enabled,
    live: !!raw.live,
    rtspConfigured: !!raw.rtspConfigured,
    hlsReady: !!raw.hlsReady,
    previewReady: !!raw.previewReady,
    hasLastFrame: !!raw.hasLastFrame,
    inferActive: !!raw.inferActive,
    armed: !!raw.armed,
    detectionTypes: Array.isArray(raw.detectionTypes) ? raw.detectionTypes : [],
    createdAt: raw.createdAt,
    updatedAt: raw.updatedAt
  }
}

async function loadData() {
  loading.value = true
  try {
    const params: Record<string, any> = {
      page: pagination.page,
      pageSize: pagination.pageSize
    }
    if (filterForm.keyword) params.keyword = filterForm.keyword
    if (filterForm.status) params.status = filterForm.status
    if (filterForm.type) params.type = filterForm.type
    if (filterForm.enabled !== '') params.enabled = filterForm.enabled

    const res: any = await cameraApi.getList(params)
    tableData.value = (res.list || []).map(normalizeCamera)
    pagination.total = Number(res.total || 0)
  } finally {
    loading.value = false
  }
}

function resetFilter() {
  filterForm.keyword = ''
  filterForm.status = ''
  filterForm.enabled = ''
  filterForm.type = ''
  pagination.page = 1
  loadData()
}

function handleSelectionChange(selection: CameraItem[]) {
  selectedIds.value = selection.map((item) => item.id)
}

function clearSelection() {
  selectedIds.value = []
}

function handleAdd() {
  dialogMode.value = 'add'
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function handleEdit(row: CameraItem) {
  dialogMode.value = 'edit'
  editingId.value = row.id
  Object.assign(formData, {
    name: row.name,
    location: row.location,
    ip: row.ip,
    type: row.type || 'hikvision',
    rtsp: row.rtsp,
    username: row.username || 'admin',
    password: '',
    resolution: row.resolution || '1920x1080',
    channels: row.channels || 1,
    status: row.status || 'online',
    enabled: !!row.enabled,
    detectionTypes: [...(row.detectionTypes || [])]
  })
  dialogVisible.value = true
}

function goMonitor(row: CameraItem) {
  router.push({ path: '/monitor', query: { cameraId: String(row.id) } })
}

async function openPreview(row: CameraItem) {
  previewCamera.value = row
  previewVisible.value = true
  previewLoading.value = true
  previewError.value = ''
  previewHlsUrl.value = ''
  destroyPreviewPlayer()

  if (!row.enabled) {
    previewLoading.value = false
    previewError.value = '摄像头已禁用，请先启用'
    return
  }
  if (!row.rtspConfigured && !(row as any).rtsp) {
    previewLoading.value = false
    previewError.value = '未配置 RTSP 地址'
    return
  }

  try {
    const started: any = await cameraApi.startStream(row.id, { preferRtsp: true, wait: false })
    const res: any = await waitStreamReady(row.id, started)
    const url = res?.hlsUrl || res?.url || ''
    if (!url || !res?.playlistReady) {
      previewError.value = res?.error || '预览流尚未就绪，请确认 runtime 已启动且 MediaMTX 有推流'
      return
    }
    previewHlsUrl.value = url
    previewCamera.value = { ...row, hlsReady: true, previewReady: true }
    await nextTick()
    if (previewVideoRef.value) {
      previewHandle = attachHls(previewVideoRef.value, url)
    }
  } catch {
    previewError.value = '拉流失败，请稍后重试'
  } finally {
    previewLoading.value = false
  }
}

function destroyPreviewPlayer() {
  if (previewHandle) {
    previewHandle.destroy()
    previewHandle = null
  }
}

function closePreview() {
  destroyPreviewPlayer()
  previewHlsUrl.value = ''
  previewError.value = ''
  previewCamera.value = null
}

async function handleToggle(row: CameraItem, enabled: boolean) {
  try {
    const res: any = await cameraApi.toggle(row.id, { enabled })
    Object.assign(row, normalizeCamera(res))
    ElMessage.success(row.enabled ? '已启用' : '已禁用')
  } catch {
    row.enabled = !enabled
  }
}

function handleDelete(row: CameraItem) {
  ElMessageBox.confirm(`确定要删除摄像头「${row.name}」吗？`, '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  })
    .then(async () => {
      await cameraApi.delete(row.id)
      ElMessage.success('删除成功')
      loadData()
    })
    .catch(() => {})
}

async function handleBatchDelete() {
  ElMessageBox.confirm(`确定要删除选中的 ${selectedIds.value.length} 个摄像头吗？`, '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  })
    .then(async () => {
      await cameraApi.batchDelete(selectedIds.value)
      ElMessage.success('删除成功')
      clearSelection()
      loadData()
    })
    .catch(() => {})
}

function buildPayload() {
  const payload: Record<string, any> = {
    name: formData.name.trim(),
    location: formData.location.trim(),
    ip: formData.ip.trim(),
    type: formData.type,
    rtsp: formData.rtsp.trim(),
    username: formData.username.trim() || 'admin',
    resolution: formData.resolution,
    channels: formData.channels,
    status: formData.status,
    enabled: formData.enabled,
    detectionTypes: [...formData.detectionTypes]
  }
  // password: write-only; empty on edit means keep unchanged
  if (formData.password) {
    payload.password = formData.password
  } else if (dialogMode.value === 'add') {
    payload.password = ''
  }
  return payload
}

async function handleSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  submitLoading.value = true
  try {
    const payload = buildPayload()
    if (dialogMode.value === 'add') {
      await cameraApi.add(payload)
      ElMessage.success('新增成功')
    } else if (editingId.value != null) {
      await cameraApi.update(editingId.value, payload)
      ElMessage.success('更新成功')
    }
    dialogVisible.value = false
    await loadData()
  } catch (e: any) {
    const data = e?.response?.data
    const msg =
      (typeof data?.error === 'string' && data.error) ||
      (typeof data?.detail === 'string' && data.detail) ||
      (data?.detail && typeof data.detail === 'object'
        ? Object.values(data.detail).flat().join('; ')
        : '') ||
      (data && typeof data === 'object'
        ? Object.entries(data)
            .filter(([k]) => k !== 'error')
            .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(',') : v}`)
            .join('; ')
        : '')
    if (msg) ElMessage.error(String(msg))
  } finally {
    submitLoading.value = false
  }
}

function onDialogClosed() {
  // Avoid racing with a quick re-open of the edit dialog
  if (dialogVisible.value) return
  resetForm()
}

function resetForm() {
  editingId.value = null
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
    status: 'online',
    enabled: true,
    detectionTypes: ['intrusion', 'parking', 'fire']
  })
  formRef.value?.clearValidate()
}

onMounted(() => {
  loadData()
})

onBeforeUnmount(() => {
  destroyPreviewPlayer()
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

.preview-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.preview-meta .meta-text {
  font-size: 13px;
  color: #6b7280;
}

.preview-box {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #0f172a;
  border-radius: 6px;
  overflow: hidden;
}

.preview-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}

.preview-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 14px;
}
</style>
