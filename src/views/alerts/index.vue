<template>
  <div class="alerts-page">
    <el-card class="page-card">
      <template #header>
        <div class="card-header">
          <span class="header-title">报警中心</span>
          <div class="header-actions">
            <el-button :icon="Refresh" @click="loadData">刷新</el-button>
            <el-button type="primary" :icon="Check" @click="handleBatchHandle('resolved')" :disabled="selectedIds.length === 0">
              批量处理
            </el-button>
          </div>
        </div>
      </template>

      <!-- 统计条 -->
      <el-row :gutter="12" class="stats-bar">
        <el-col :span="6">
          <div class="stat-item total" :class="{ active: !filterForm.status }" @click="filterByStatus('')">
            <div class="stat-num">{{ stats.total || 0 }}</div>
            <div class="stat-label">全部告警</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item unhandled" :class="{ active: filterForm.status === 'unhandled' }" @click="filterByStatus('unhandled')">
            <div class="stat-num">{{ stats.unhandled || 0 }}</div>
            <div class="stat-label">待处理</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item processing" :class="{ active: filterForm.status === 'processing' }" @click="filterByStatus('processing')">
            <div class="stat-num">{{ stats.processing || 0 }}</div>
            <div class="stat-label">处理中</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-item resolved" :class="{ active: filterForm.status === 'resolved' }" @click="filterByStatus('resolved')">
            <div class="stat-num">{{ stats.resolved || 0 }}</div>
            <div class="stat-label">已处理</div>
          </div>
        </el-col>
      </el-row>

      <!-- 筛选区 -->
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

      <!-- 列表 -->
      <el-table
        :data="tableData"
        v-loading="loading"
        border
        stripe
        @selection-change="handleSelectionChange"
        @row-click="handleRowClick"
      >
        <el-table-column type="selection" width="50" />
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="级别" width="80">
          <template #default="{ row }">
            <el-tag :type="levelTagType(row.level)" size="small" effect="dark">
              {{ levelText(row.level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <span class="type-cell">
              <el-icon :class="row.type">
                <component :is="alertIcon(row.type)" />
              </el-icon>
              {{ typeText(row.type) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="摄像头" min-width="150">
          <template #default="{ row }">
            <div>{{ row.cameraName }}</div>
            <div class="cam-sub">{{ row.cameraLocation || row.cameraIp || '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="告警描述" min-width="180" show-overflow-tooltip />
        <el-table-column label="置信度" width="90">
          <template #default="{ row }">
            <span>{{ formatConfidence(row.confidence) }}</span>
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
              @click.stop="handleSingle(row)"
            >
              处理
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

    <!-- 处理弹窗 -->
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Check, Warning } from '@element-plus/icons-vue'
import dayjs from 'dayjs'

const router = useRouter()
const loading = ref(false)
const submitLoading = ref(false)
const tableData = ref<any[]>([])
const selectedIds = ref<number[]>([])
const selectedRows = ref<any[]>([])
const cameraOptions = ref<any[]>([])
const handleDialogVisible = ref(false)
const handleForm = reactive({ status: 'resolved', note: '' })
const stats = reactive<any>({ total: 0, unhandled: 0, processing: 0, resolved: 0 })

const filterForm = reactive({
  type: '',
  level: '',
  status: '',
  cameraId: '',
  keyword: ''
})

const dateRange = ref<string[]>([])

const pagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0
})
const realtimeOffs: Array<() => void> = []

function alertIcon(type: string) {
  // Element Plus 图标库无 Fire/Parking 等，统一用 Warning 图标
  return Warning
}

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

function formatDate(date: string) {
  return dayjs(date).format('YYYY-MM-DD HH:mm:ss')
}

function filterByStatus(status: string) {
  filterForm.status = status
  pagination.page = 1
  loadData()
}

async function loadCameras() {
  try {
    const res: any = await cameraApi.getAll()
    cameraOptions.value = res || []
  } catch (e) {}
}

async function loadStats() {
  try {
    const res: any = await alertApi.getStats()
    stats.total = res.total || 0
    stats.unhandled = res.statusCounts?.unhandled || 0
    stats.processing = res.statusCounts?.processing || 0
    stats.resolved = res.statusCounts?.resolved || 0
  } catch (e) {}
}

async function loadData() {
  loading.value = true
  try {
    const params: any = {
      page: pagination.page,
      pageSize: pagination.pageSize,
      ...filterForm
    }
    if (dateRange.value?.length === 2) {
      params.startDate = dateRange.value[0]
      params.endDate = dateRange.value[1]
    }
    const res: any = await alertApi.getList(params)
    tableData.value = res.list || []
    pagination.total = res.total || 0
  } finally {
    loading.value = false
  }
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

function handleSelectionChange(selection: any[]) {
  selectedIds.value = selection.map(item => item.id)
  selectedRows.value = selection
}

function handleRowClick(row: any) {
  viewDetail(row)
}

function viewDetail(row: any) {
  router.push(`/alerts/${row.id}`)
}

function handleSingle(row: any) {
  selectedRows.value = [row]
  selectedIds.value = [row.id]
  handleForm.status = 'resolved'
  handleForm.note = ''
  handleDialogVisible.value = true
}

function handleBatchHandle(status: string) {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请选择要处理的告警')
    return
  }
  handleForm.status = status
  handleForm.note = ''
  handleDialogVisible.value = true
}

async function submitHandle() {
  submitLoading.value = true
  try {
    if (selectedIds.value.length === 1) {
      await alertApi.handle(selectedIds.value[0], handleForm)
    } else {
      await alertApi.batchHandle({
        ids: selectedIds.value,
        status: handleForm.status,
        note: handleForm.note
      })
    }
    ElMessage.success(`成功处理 ${selectedIds.value.length} 条告警`)
    handleDialogVisible.value = false
    selectedIds.value = []
    selectedRows.value = []
    loadData()
    loadStats()
  } catch (e) {
    // 错误已处理
  } finally {
    submitLoading.value = false
  }
}

onMounted(() => {
  loadCameras()
  loadStats()
  loadData()
  realtimeOffs.push(
    onRealtime('alert:created', () => {
      loadData()
      loadStats()
    }),
    onRealtime('alert:updated', () => {
      loadData()
      loadStats()
    })
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
