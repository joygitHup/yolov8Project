<template>
  <div class="alerts-page">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <span class="header-title">报警中心</span>
          <div class="header-actions">
            <el-button :icon="Refresh" @click="refreshAll">刷新</el-button>
            <el-button
              type="primary"
              :icon="Check"
              :disabled="selectedIds.length === 0"
              @click="openBatchHandle('resolved')"
            >
              批量处理
            </el-button>
          </div>
        </div>
      </template>

      <!-- 统计条：绑定 alerts.* / 顶层别名 -->
      <el-row :gutter="12" class="stats-bar">
        <el-col :span="6">
          <div class="stat-item total" :class="{ active: !filterForm.status }" @click="filterByStatus('')">
            <div class="stat-num">{{ stats.total }}</div>
            <div class="stat-label">全部告警</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div
            class="stat-item unhandled"
            :class="{ active: filterForm.status === 'unhandled' }"
            @click="filterByStatus('unhandled')"
          >
            <div class="stat-num">{{ stats.unhandled }}</div>
            <div class="stat-label">待处理</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div
            class="stat-item processing"
            :class="{ active: filterForm.status === 'processing' }"
            @click="filterByStatus('processing')"
          >
            <div class="stat-num">{{ stats.processing }}</div>
            <div class="stat-label">处理中</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div
            class="stat-item resolved"
            :class="{ active: filterForm.status === 'resolved' }"
            @click="filterByStatus('resolved')"
          >
            <div class="stat-num">{{ stats.resolved }}</div>
            <div class="stat-label">已处理</div>
          </div>
        </el-col>
      </el-row>

      <div class="filter-bar">
        <el-form :inline="true" :model="filterForm">
          <el-form-item label="告警类型">
            <el-select v-model="filterForm.type" placeholder="全部" clearable style="width: 120px">
              <el-option label="区域入侵" value="intrusion" />
              <el-option label="违停占道" value="parking" />
              <el-option label="火灾隐患" value="fire" />
            </el-select>
          </el-form-item>
          <el-form-item label="告警级别">
            <el-select v-model="filterForm.level" placeholder="全部" clearable style="width: 100px">
              <el-option label="高危" value="high" />
              <el-option label="中危" value="medium" />
              <el-option label="低危" value="low" />
            </el-select>
          </el-form-item>
          <el-form-item label="处理状态">
            <el-select v-model="filterForm.status" placeholder="全部" clearable style="width: 120px">
              <el-option label="待处理" value="unhandled" />
              <el-option label="处理中" value="processing" />
              <el-option label="已处理" value="resolved" />
            </el-select>
          </el-form-item>
          <el-form-item label="摄像头">
            <el-select v-model="filterForm.cameraId" placeholder="全部" clearable style="width: 150px">
              <el-option
                v-for="cam in cameraOptions"
                :key="cam.id"
                :label="cam.name"
                :value="cam.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="关键词">
            <el-input
              v-model="filterForm.keyword"
              placeholder="描述 / 摄像头 / 备注"
              clearable
              style="width: 180px"
              @keyup.enter="loadData"
            />
          </el-form-item>
          <el-form-item label="时间范围">
            <el-date-picker
              v-model="dateRange"
              type="datetimerange"
              range-separator="至"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              style="width: 320px"
              value-format="YYYY-MM-DD HH:mm:ss"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="loadData">查询</el-button>
            <el-button @click="resetFilter">重置</el-button>
          </el-form-item>
        </el-form>
      </div>

      <el-table
        :data="tableData"
        v-loading="loading"
        border
        stripe
        @selection-change="handleSelectionChange"
        @row-click="handleRowClick"
      >
        <el-table-column type="selection" width="50" />
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="级别" width="80">
          <template #default="{ row }">
            <el-tag :type="levelTagType(row.level)" size="small" effect="dark">
              {{ levelText(row.level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <span class="type-cell">
              <el-icon :class="row.type"><Warning /></el-icon>
              {{ typeText(row.type) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="摄像头" min-width="150">
          <template #default="{ row }">
            <div>{{ row.cameraName || '-' }}</div>
            <div class="cam-sub">{{ row.cameraLocation || row.cameraIp || '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="告警描述" min-width="180" show-overflow-tooltip />
        <el-table-column label="目标数" width="80">
          <template #default="{ row }">
            {{ row.detectionCount }}
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="90">
          <template #default="{ row }">
            {{ formatConfidence(row.confidence) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small" effect="plain">
              {{ statusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="triggeredAt" label="触发时间" width="170">
          <template #default="{ row }">
            {{ formatDate(row.triggeredAt) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click.stop="viewDetail(row)">
              详情
            </el-button>
            <el-button
              v-if="row.status !== 'resolved'"
              type="success"
              link
              size="small"
              @click.stop="openSingleHandle(row)"
            >
              处理
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

    <el-dialog v-model="handleDialogVisible" title="处理告警" width="500px">
      <el-form :model="handleForm" label-width="80px">
        <el-form-item label="处理状态">
          <el-radio-group v-model="handleForm.status">
            <el-radio value="processing">标记处理中</el-radio>
            <el-radio value="resolved">标记已处理</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="处理备注">
          <el-input
            v-model="handleForm.note"
            type="textarea"
            :rows="4"
            placeholder="请输入处理备注"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="submitHandle">
          确认
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { alertApi, cameraApi } from '@/api'
import { onRealtime } from '@/utils/realtime'
import { ElMessage } from 'element-plus'
import { Refresh, Check, Warning } from '@element-plus/icons-vue'
import dayjs from 'dayjs'

/** Canonical alert list row (matches AlertSerializer list) */
interface AlertItem {
  id: number
  cameraId: number | null
  cameraName: string
  cameraLocation: string
  cameraIp: string
  cameraStatus: string
  type: string
  level: string
  description: string
  confidence: number
  status: string
  detectionCount: number
  hasTicket: boolean
  triggeredAt?: string
  resolvedBy?: string
  resolvedAt?: string
  resolvedNote?: string
}

interface CameraOption {
  id: number
  name: string
}

const router = useRouter()
const loading = ref(false)
const submitLoading = ref(false)
const tableData = ref<AlertItem[]>([])
const selectedIds = ref<number[]>([])
const cameraOptions = ref<CameraOption[]>([])
const handleDialogVisible = ref(false)
const handleMode = ref<'single' | 'batch'>('single')
const handleForm = reactive({ status: 'resolved', note: '' })
const stats = reactive({
  total: 0,
  unhandled: 0,
  processing: 0,
  resolved: 0
})

const filterForm = reactive({
  type: '',
  level: '',
  status: '',
  cameraId: '' as number | '',
  keyword: ''
})

const dateRange = ref<string[]>([])
const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0
})
const realtimeOffs: Array<() => void> = []

function levelText(level: string) {
  const map: Record<string, string> = { high: '高危', medium: '中危', low: '低危' }
  return map[level] || level
}

function levelTagType(level: string) {
  const map: Record<string, string> = { high: 'danger', medium: 'warning', low: 'info' }
  return map[level] || 'info'
}

function typeText(type: string) {
  const map: Record<string, string> = {
    intrusion: '区域入侵',
    parking: '违停占道',
    fire: '火灾隐患'
  }
  return map[type] || type
}

function statusText(status: string) {
  const map: Record<string, string> = {
    unhandled: '待处理',
    processing: '处理中',
    resolved: '已处理'
  }
  return map[status] || status
}

function statusTagType(status: string) {
  const map: Record<string, string> = {
    unhandled: 'danger',
    processing: 'warning',
    resolved: 'success'
  }
  return map[status] || 'info'
}

function formatConfidence(value?: number) {
  if (value == null || Number.isNaN(Number(value))) return '-'
  const n = Number(value)
  const pct = n <= 1 ? n * 100 : n
  return `${pct.toFixed(1)}%`
}

function formatDate(date?: string) {
  if (!date) return '-'
  return dayjs(date).format('YYYY-MM-DD HH:mm:ss')
}

function normalizeAlert(raw: any): AlertItem {
  return {
    id: Number(raw.id),
    cameraId: raw.cameraId == null ? null : Number(raw.cameraId),
    cameraName: raw.cameraName || '',
    cameraLocation: raw.cameraLocation || '',
    cameraIp: raw.cameraIp || '',
    cameraStatus: raw.cameraStatus || '',
    type: raw.type || '',
    level: raw.level || '',
    description: raw.description || '',
    confidence: Number(raw.confidence || 0),
    status: raw.status || 'unhandled',
    detectionCount: Number(raw.detectionCount ?? (raw.detectionBoxes || []).length ?? 0),
    hasTicket: !!raw.hasTicket,
    triggeredAt: raw.triggeredAt,
    resolvedBy: raw.resolvedBy || '',
    resolvedAt: raw.resolvedAt,
    resolvedNote: raw.resolvedNote || ''
  }
}

function applyStats(res: any) {
  const alerts = res?.alerts || {}
  const statusCounts = res?.statusCounts || {}
  stats.total = Number(alerts.total ?? res?.total ?? 0)
  stats.unhandled = Number(alerts.unhandled ?? res?.unhandled ?? statusCounts.unhandled ?? 0)
  stats.processing = Number(alerts.processing ?? res?.processing ?? statusCounts.processing ?? 0)
  stats.resolved = Number(alerts.resolved ?? res?.resolved ?? statusCounts.resolved ?? 0)
}

function filterByStatus(status: string) {
  filterForm.status = status
  pagination.page = 1
  loadData()
}

async function loadCameras() {
  try {
    const res: any = await cameraApi.getAll()
    cameraOptions.value = (res || []).map((c: any) => ({
      id: Number(c.id),
      name: c.name || `摄像头#${c.id}`
    }))
  } catch {
    cameraOptions.value = []
  }
}

async function loadStats() {
  try {
    const res: any = await alertApi.getStats()
    applyStats(res)
  } catch {
    /* ignore */
  }
}

async function loadData() {
  loading.value = true
  try {
    const params: Record<string, any> = {
      page: pagination.page,
      pageSize: pagination.pageSize
    }
    if (filterForm.type) params.type = filterForm.type
    if (filterForm.level) params.level = filterForm.level
    if (filterForm.status) params.status = filterForm.status
    if (filterForm.cameraId !== '' && filterForm.cameraId != null) {
      params.cameraId = filterForm.cameraId
    }
    if (filterForm.keyword) params.keyword = filterForm.keyword
    if (dateRange.value?.length === 2) {
      params.startDate = dateRange.value[0]
      params.endDate = dateRange.value[1]
    }

    const res: any = await alertApi.getList(params)
    tableData.value = (res.list || []).map(normalizeAlert)
    pagination.total = Number(res.total || 0)
  } finally {
    loading.value = false
  }
}

function refreshAll() {
  loadStats()
  loadData()
}

function resetFilter() {
  filterForm.type = ''
  filterForm.level = ''
  filterForm.status = ''
  filterForm.cameraId = ''
  filterForm.keyword = ''
  dateRange.value = []
  pagination.page = 1
  loadData()
}

function handleSelectionChange(selection: AlertItem[]) {
  selectedIds.value = selection.map((item) => item.id)
}

function handleRowClick(row: AlertItem) {
  viewDetail(row)
}

function viewDetail(row: AlertItem) {
  router.push(`/alerts/${row.id}`)
}

function openSingleHandle(row: AlertItem) {
  handleMode.value = 'single'
  selectedIds.value = [row.id]
  handleForm.status = 'resolved'
  handleForm.note = ''
  handleDialogVisible.value = true
}

function openBatchHandle(status: string) {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请选择要处理的告警')
    return
  }
  handleMode.value = 'batch'
  handleForm.status = status
  handleForm.note = ''
  handleDialogVisible.value = true
}

async function submitHandle() {
  submitLoading.value = true
  try {
    const payload = {
      status: handleForm.status,
      note: handleForm.note || ''
    }
    let count = selectedIds.value.length
    if (handleMode.value === 'single' || selectedIds.value.length === 1) {
      await alertApi.handle(selectedIds.value[0], payload)
      count = 1
    } else {
      const res: any = await alertApi.batchHandle({
        ids: selectedIds.value,
        ...payload
      })
      count = Number(res.count ?? selectedIds.value.length)
    }
    ElMessage.success(`成功处理 ${count} 条告警`)
    handleDialogVisible.value = false
    selectedIds.value = []
    refreshAll()
  } catch {
    /* request interceptor */
  } finally {
    submitLoading.value = false
  }
}

onMounted(() => {
  loadCameras()
  refreshAll()
  realtimeOffs.push(
    onRealtime('alert:created', () => refreshAll()),
    onRealtime('alert:updated', () => refreshAll())
  )
})

onUnmounted(() => {
  realtimeOffs.forEach((fn) => fn())
})
</script>

<style scoped>
.alerts-page {
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

.stats-bar {
  margin-bottom: 16px;
}

.stat-item {
  padding: 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: transform 0.2s;
}

.stat-item:hover {
  transform: translateY(-2px);
}

.stat-item.active {
  outline: 2px solid #1677ff;
  outline-offset: 1px;
}

.stat-item.total {
  background: linear-gradient(135deg, #e6f4ff, #bae0ff);
}

.stat-item.unhandled {
  background: linear-gradient(135deg, #fff1f0, #ffa39e);
}

.stat-item.processing {
  background: linear-gradient(135deg, #fffbe6, #ffe58f);
}

.stat-item.resolved {
  background: linear-gradient(135deg, #f6ffed, #b7eb8f);
}

.stat-num {
  font-size: 28px;
  font-weight: 700;
  color: #1f2937;
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.stat-label {
  font-size: 13px;
  color: #4b5563;
  margin-top: 4px;
}

.filter-bar {
  padding: 16px 0;
  border-bottom: 1px solid #e5e7eb;
  margin-bottom: 16px;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

.type-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.type-cell .intrusion { color: #f5222d; }
.type-cell .parking { color: #faad14; }
.type-cell .fire { color: #fa541c; }

.cam-sub {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 2px;
}
</style>
