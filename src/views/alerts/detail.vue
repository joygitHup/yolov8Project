<template>
  <div class="alert-detail-page">
    <div class="page-header">
      <el-button :icon="ArrowLeft" @click="goBack">返回列表</el-button>
      <h2 class="page-title">告警详情 #{{ alert?.id }}</h2>
      <div class="header-actions">
        <el-tag v-if="alert" :type="levelTagType(alert.level)" size="large" effect="dark">
          {{ levelText(alert.level) }}
        </el-tag>
        <el-tag v-if="alert" :type="statusTagType(alert.status)" size="large">
          {{ statusText(alert.status) }}
        </el-tag>
      </div>
    </div>

    <el-row :gutter="20" v-loading="loading">
      <!-- 左侧 - 图片/视频 -->
      <el-col :span="16">
        <el-card class="media-card">
          <template #header>
            <div class="card-tabs">
              <div
                class="tab-item"
                :class="{ active: mediaTab === 'image' }"
                @click="mediaTab = 'image'"
              >
                现场图片
              </div>
              <div
                class="tab-item"
                :class="{ active: mediaTab === 'video' }"
                @click="mediaTab = 'video'"
              >
                视频片段
              </div>
            </div>
          </template>
          <div class="media-content">
            <div v-if="mediaTab === 'image'" class="image-container">
              <div class="evidence-frame" v-if="alert?.evidenceSvg" v-html="alert.evidenceSvg"></div>
              <div v-else class="mock-image">
                <div class="image-bg"></div>
                <div
                  v-for="(box, idx) in normalizedBoxes"
                  :key="idx"
                  class="detect-box"
                  :class="box.label"
                  :style="boxStyle(box)"
                >
                  <span class="box-label">
                    {{ translateLabel(box.label) }} {{ formatConfidence(box.confidence) }}
                  </span>
                </div>
                <div class="image-info-overlay">
                  <span>{{ alert?.cameraName }}</span>
                  <span>{{ formatDate(alert?.triggeredAt) }}</span>
                </div>
              </div>
            </div>
            <div v-else class="video-container">
              <div class="mock-video-player" @click="toggleClip">
                <div class="evidence-frame" v-if="alert?.evidenceSvg" v-html="alert.evidenceSvg"></div>
                <div v-else class="video-bg"></div>
                <div class="play-overlay" v-if="!clipPlaying">
                  <el-icon :size="64"><VideoPlay /></el-icon>
                </div>
                <div class="video-controls" @click.stop>
                  <span class="time">{{ clipLabel }}</span>
                  <div class="progress-bar">
                    <div class="progress" :style="{ width: clipProgress + '%' }"></div>
                  </div>
                  <span>{{ alert?.clip?.duration || 15 }}s</span>
                </div>
              </div>
              <p class="clip-hint">{{ alert?.clip?.message || '暂未接入录像文件' }}</p>
            </div>
          </div>
        </el-card>

        <!-- 检测结果 -->
        <el-card class="detection-card" style="margin-top: 20px">
          <template #header>
            <span class="card-title">检测结果</span>
          </template>
          <el-table :data="normalizedBoxes" size="default" border>
            <el-table-column type="index" label="序号" width="60" />
            <el-table-column label="目标类型" width="120">
              <template #default="{ row }">
                <el-tag size="small">{{ translateLabel(row.label) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="置信度" width="160">
              <template #default="{ row }">
                <el-progress :percentage="confidencePercent(row.confidence)" :show-text="true" />
              </template>
            </el-table-column>
            <el-table-column label="位置坐标">
              <template #default="{ row }">
                <code>
                  x: {{ row.x.toFixed(3) }}, y: {{ row.y.toFixed(3) }}, w: {{ row.w.toFixed(3) }}, h: {{ row.h.toFixed(3) }}
                </code>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- 右侧 - 告警信息 -->
      <el-col :span="8">
        <el-card class="info-card">
          <template #header>
            <span class="card-title">告警信息</span>
          </template>
          <div class="info-list">
            <div class="info-item">
              <span class="label">告警类型</span>
              <span class="value">{{ typeText(alert?.type) }}</span>
            </div>
            <div class="info-item">
              <span class="label">告警级别</span>
              <span class="value">
                <el-tag :type="levelTagType(alert?.level)" size="small" effect="dark">
                  {{ levelText(alert?.level) }}
                </el-tag>
              </span>
            </div>
            <div class="info-item">
              <span class="label">关联摄像头</span>
              <span class="value">{{ alert?.cameraName }}</span>
            </div>
            <div class="info-item" v-if="alert?.camera?.location || alert?.cameraLocation">
              <span class="label">安装位置</span>
              <span class="value">{{ alert?.camera?.location || alert?.cameraLocation }}</span>
            </div>
            <div class="info-item" v-if="alert?.camera?.ip || alert?.cameraIp">
              <span class="label">设备 IP</span>
              <span class="value">{{ alert?.camera?.ip || alert?.cameraIp }}</span>
            </div>
            <div class="info-item">
              <span class="label">告警描述</span>
              <span class="value desc">{{ alert?.description }}</span>
            </div>
            <div class="info-item">
              <span class="label">置信度</span>
              <span class="value">{{ formatConfidence(alert?.confidence) }}</span>
            </div>
            <div class="info-item">
              <span class="label">触发时间</span>
              <span class="value">{{ formatDate(alert?.triggeredAt) }}</span>
            </div>
            <div class="info-item">
              <span class="label">当前状态</span>
              <span class="value">
                <el-tag :type="statusTagType(alert?.status)" size="small">
                  {{ statusText(alert?.status) }}
                </el-tag>
              </span>
            </div>
            <template v-if="alert?.status === 'processing' || alert?.status === 'resolved'">
              <div class="info-item" v-if="alert.resolvedBy">
                <span class="label">处理人</span>
                <span class="value">{{ alert.resolvedBy }}</span>
              </div>
              <div class="info-item" v-if="alert.resolvedAt">
                <span class="label">处理时间</span>
                <span class="value">{{ formatDate(alert.resolvedAt) }}</span>
              </div>
              <div class="info-item" v-if="alert.resolvedNote">
                <span class="label">处理备注</span>
                <span class="value desc">{{ alert.resolvedNote }}</span>
              </div>
            </template>
            <div class="info-item" v-if="alert?.ticket">
              <span class="label">工单</span>
              <span class="value">#{{ alert.ticket.id }} {{ alert.ticket.status === 'open' ? '待处理' : '已完成' }}</span>
            </div>
          </div>
        </el-card>

        <!-- 操作 -->
        <el-card v-if="alert?.status !== 'resolved'" class="action-card" style="margin-top: 20px">
          <template #header>
            <span class="card-title">告警处理</span>
          </template>
          <el-form :model="handleForm" label-width="80px">
            <el-form-item label="处理状态">
              <el-radio-group v-model="handleForm.status">
                <el-radio value="processing">处理中</el-radio>
                <el-radio value="resolved">已处理</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="处理备注">
              <el-input
                v-model="handleForm.note"
                type="textarea"
                :rows="3"
                placeholder="请输入处理备注"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="submitLoading" @click="submitHandle" style="width: 100%">
                提交处理
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card v-if="(alert?.actions || []).length" class="history-card" style="margin-top: 20px">
          <template #header>
            <span class="card-title">处理记录</span>
          </template>
          <el-timeline>
            <el-timeline-item
              v-for="act in alert.actions"
              :key="act.id"
              :timestamp="formatDate(act.createdAt)"
              placement="top"
            >
              {{ act.operator || '系统' }}
              {{ actionText(act) }}
              <div v-if="act.note" class="action-note">{{ act.note }}</div>
            </el-timeline-item>
          </el-timeline>
        </el-card>

        <!-- 快速操作 -->
        <el-card class="quick-actions" style="margin-top: 20px">
          <template #header>
            <span class="card-title">快速操作</span>
          </template>
          <div class="action-grid">
            <el-button :icon="Download" @click="handleDownload">下载取证图</el-button>
            <el-button :icon="Share" @click="handleShare">复制链接</el-button>
            <el-button :icon="Printer" @click="handlePrint">打印报告</el-button>
            <el-button :icon="Warning" type="danger" :disabled="!!alert?.ticket" @click="openDispatch">
              {{ alert?.ticket ? '已派发' : '派发工单' }}
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="dispatchVisible" title="派发工单" width="460px">
      <el-form :model="dispatchForm" label-width="80px">
        <el-form-item label="指派人">
          <el-input v-model="dispatchForm.assignee" placeholder="可选，值班人员" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="dispatchForm.note" type="textarea" :rows="3" placeholder="工单说明" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dispatchVisible = false">取消</el-button>
        <el-button type="primary" :loading="dispatchLoading" @click="submitDispatch">确认派发</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { alertApi } from '@/api'
import { onRealtime } from '@/utils/realtime'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft, VideoPlay, Download, Share, Printer, Warning
} from '@element-plus/icons-vue'
import dayjs from 'dayjs'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const submitLoading = ref(false)
const dispatchLoading = ref(false)
const dispatchVisible = ref(false)
const alert = ref<any>(null)
const mediaTab = ref<'image' | 'video'>('image')
const clipPlaying = ref(false)
const clipProgress = ref(0)
const clipElapsed = ref(0)
let clipTimer: any = null
const realtimeOffs: Array<() => void> = []

const handleForm = reactive({
  status: 'resolved',
  note: ''
})
const dispatchForm = reactive({
  assignee: '',
  note: ''
})

const normalizedBoxes = computed(() => {
  return (alert.value?.detectionBoxes || []).map((item: any) => {
    const bbox = item?.bbox || item || {}
    return {
      x: Number(bbox.x || 0),
      y: Number(bbox.y || 0),
      w: Number(bbox.w || 0),
      h: Number(bbox.h || 0),
      label: item.label || bbox.label || 'object',
      confidence: Number(item.confidence ?? bbox.confidence ?? 0)
    }
  })
})

const clipLabel = computed(() => {
  const total = alert.value?.clip?.duration || 15
  const cur = Math.min(clipElapsed.value, total)
  return `${formatSeconds(cur)} / ${formatSeconds(total)}`
})

function formatSeconds(sec: number) {
  const s = Math.max(0, Math.floor(sec))
  return `00:${String(s).padStart(2, '0')}`
}

function boxStyle(box: any) {
  return {
    left: (box.x || 0) * 100 + '%',
    top: (box.y || 0) * 100 + '%',
    width: (box.w || 0) * 100 + '%',
    height: (box.h || 0) * 100 + '%'
  }
}

function confidencePercent(value?: number) {
  if (value == null) return 0
  const n = Number(value)
  const pct = n <= 1 ? n * 100 : n
  return Math.max(0, Math.min(100, Math.round(pct)))
}

function formatConfidence(value?: number) {
  if (value == null || Number.isNaN(Number(value))) return '-'
  return `${confidencePercent(value).toFixed(1)}%`
}

function actionText(act: any) {
  if (act.action === 'dispatch') return '派发了工单'
  const map: Record<string, string> = {
    processing: '标记为处理中',
    resolved: '标记为已处理',
    unhandled: '恢复为待处理'
  }
  return map[act.toStatus] || act.toStatus || act.action
}

function levelText(level?: string) {
  const map: Record<string, string> = { high: '高危', medium: '中危', low: '低危' }
  return map[level || ''] || level || '-'
}

function levelTagType(level?: string) {
  const map: Record<string, string> = { high: 'danger', medium: 'warning', low: 'info' }
  return map[level || ''] || 'info'
}

function typeText(type?: string) {
  const map: Record<string, string> = {
    intrusion: '区域入侵',
    parking: '违停占道',
    fire: '火灾隐患'
  }
  return map[type || ''] || type || '-'
}

function statusText(status?: string) {
  const map: Record<string, string> = {
    unhandled: '待处理',
    processing: '处理中',
    resolved: '已处理'
  }
  return map[status || ''] || status || '-'
}

function statusTagType(status?: string) {
  const map: Record<string, string> = {
    unhandled: 'danger',
    processing: 'warning',
    resolved: 'success'
  }
  return map[status || ''] || 'info'
}

function translateLabel(label: string) {
  const map: Record<string, string> = {
    person: '人',
    car: '轿车',
    truck: '卡车',
    fire: '火焰',
    smoke: '烟雾',
    bicycle: '自行车',
    motorcycle: '摩托车'
  }
  return map[label] || label
}

function formatDate(date?: string) {
  if (!date) return '-'
  return dayjs(date).format('YYYY-MM-DD HH:mm:ss')
}

function goBack() {
  router.push('/alerts')
}

async function loadDetail() {
  const id = route.params.id as string
  loading.value = true
  try {
    const res: any = await alertApi.getDetail(parseInt(id, 10))
    alert.value = res
  } finally {
    loading.value = false
  }
}

async function submitHandle() {
  if (!alert.value) return
  submitLoading.value = true
  try {
    const res: any = await alertApi.handle(alert.value.id, handleForm)
    alert.value = res
    ElMessage.success('处理成功')
  } catch (e) {
    // 错误已处理
  } finally {
    submitLoading.value = false
  }
}

function toggleClip() {
  if (clipPlaying.value) {
    stopClip()
    return
  }
  clipPlaying.value = true
  clipElapsed.value = 0
  clipProgress.value = 0
  const total = alert.value?.clip?.duration || 15
  clipTimer = setInterval(() => {
    clipElapsed.value += 0.2
    clipProgress.value = Math.min(100, (clipElapsed.value / total) * 100)
    if (clipElapsed.value >= total) stopClip()
  }, 200)
}

function stopClip() {
  clipPlaying.value = false
  if (clipTimer) {
    clearInterval(clipTimer)
    clipTimer = null
  }
}

function downloadText(filename: string, content: string, mime = 'text/plain') {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function handleDownload() {
  if (!alert.value) return
  try {
    const res: any = await alertApi.getEvidence(alert.value.id)
    downloadText(res.filename || `alert-${alert.value.id}.svg`, res.content, res.mimeType || 'image/svg+xml')
    ElMessage.success('取证图已下载')
  } catch (e) {}
}

async function handleShare() {
  const url = window.location.href
  try {
    await navigator.clipboard.writeText(url)
    ElMessage.success('链接已复制')
  } catch {
    ElMessage.info(url)
  }
}

async function handlePrint() {
  if (!alert.value) return
  try {
    await alertApi.getReport(alert.value.id)
    window.print()
  } catch (e) {}
}

function openDispatch() {
  dispatchForm.assignee = ''
  dispatchForm.note = ''
  dispatchVisible.value = true
}

async function submitDispatch() {
  if (!alert.value) return
  dispatchLoading.value = true
  try {
    const res: any = await alertApi.dispatch(alert.value.id, { ...dispatchForm })
    alert.value = res.alert || alert.value
    if (res.ticket) alert.value.ticket = res.ticket
    dispatchVisible.value = false
    ElMessage.success(res.message || '工单已派发')
  } catch (e) {
  } finally {
    dispatchLoading.value = false
  }
}

onMounted(() => {
  loadDetail()
  realtimeOffs.push(
    onRealtime('alert:updated', (payload) => {
      if (payload?.id && payload.id === alert.value?.id) {
        loadDetail()
      }
    })
  )
})

onUnmounted(() => {
  stopClip()
  realtimeOffs.forEach((fn) => fn())
})
</script>

<style scoped>
.alert-detail-page {
  padding: 4px;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0;
  flex: 1;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.card-title {
  font-weight: 600;
}

.card-tabs {
  display: flex;
  gap: 16px;
}

.tab-item {
  cursor: pointer;
  font-size: 14px;
  color: #6b7280;
  padding-bottom: 4px;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.tab-item.active {
  color: #1677ff;
  border-bottom-color: #1677ff;
  font-weight: 500;
}

.media-content {
  min-height: 400px;
}

.evidence-frame {
  width: 100%;
  max-width: 700px;
  aspect-ratio: 16/9;
  border-radius: 8px;
  overflow: hidden;
  background: #0f172a;
}

.evidence-frame :deep(svg) {
  width: 100%;
  height: 100%;
  display: block;
}

.clip-hint {
  margin-top: 10px;
  font-size: 12px;
  color: #9ca3af;
  text-align: center;
}

.action-note {
  margin-top: 4px;
  color: #6b7280;
  font-size: 12px;
}

.history-card :deep(.el-card__header) {
  font-weight: 600;
}

.image-container {
  width: 100%;
  display: flex;
  justify-content: center;
}

.mock-image {
  width: 100%;
  max-width: 700px;
  aspect-ratio: 16/9;
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  background: #0f172a;
}

.image-bg {
  width: 100%;
  height: 100%;
  background: 
    radial-gradient(ellipse at 30% 30%, rgba(59, 130, 246, 0.2) 0%, transparent 50%),
    linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
}

.detect-box {
  position: absolute;
  border: 2px solid #52c41a;
  border-radius: 2px;
  z-index: 10;
}

.detect-box.person { border-color: #52c41a; }
.detect-box.car { border-color: #3b82f6; }
.detect-box.truck { border-color: #8b5cf6; }
.detect-box.fire { border-color: #f5222d; }
.detect-box.smoke { border-color: #f59e0b; }

.box-label {
  position: absolute;
  top: -24px;
  left: -2px;
  background: #52c41a;
  color: #fff;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 3px 3px 0 0;
  white-space: nowrap;
}

.detect-box.person .box-label { background: #52c41a; }
.detect-box.car .box-label { background: #3b82f6; }
.detect-box.truck .box-label { background: #8b5cf6; }
.detect-box.fire .box-label { background: #f5222d; }
.detect-box.smoke .box-label { background: #f59e0b; }

.image-info-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 12px 16px;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.7));
  display: flex;
  justify-content: space-between;
  color: #fff;
  font-size: 13px;
}

.video-container {
  display: flex;
  justify-content: center;
}

.mock-video-player {
  width: 100%;
  max-width: 700px;
  aspect-ratio: 16/9;
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  background: #000;
}

.video-bg {
  width: 100%;
  height: 100%;
  background: 
    radial-gradient(ellipse at 30% 30%, rgba(59, 130, 246, 0.15) 0%, transparent 50%),
    linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
}

.play-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.8);
  cursor: pointer;
}

.video-controls {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 12px 16px;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.8));
  display: flex;
  align-items: center;
  gap: 12px;
  color: #fff;
  font-size: 12px;
}

.progress-bar {
  flex: 1;
  height: 4px;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 2px;
  overflow: hidden;
}

.progress {
  height: 100%;
  background: #1677ff;
  border-radius: 2px;
}

.detection-card :deep(.el-card__header),
.info-card :deep(.el-card__header),
.action-card :deep(.el-card__header),
.quick-actions :deep(.el-card__header) {
  font-weight: 600;
}

.info-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  font-size: 13px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f3f4f6;
}

.info-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.label {
  color: #6b7280;
  flex-shrink: 0;
}

.value {
  color: #1f2937;
  text-align: right;
  max-width: 60%;
  font-weight: 500;
}

.value.desc {
  text-align: left;
  max-width: 70%;
  line-height: 1.5;
}

.action-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
</style>
