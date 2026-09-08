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
              <div v-if="isRealMedia(alert?.snapshotUrl || alert?.imageUrl)" class="shot-wrap">
                <div class="shot-toolbar">
                  <el-button size="small" :type="showBoxes ? 'default' : 'warning'" @click="showBoxes = !showBoxes">
                    {{ showBoxes ? '隐藏检测框' : '显示检测框' }}
                  </el-button>
                  <span class="shot-hint">点击图片可原尺寸查看</span>
                </div>
                <div class="real-media-frame">
                  <div class="shot">
                    <img
                      class="real-image"
                      :src="mediaSrc(alert.snapshotUrl || alert.imageUrl)"
                      :alt="`告警 ${alert?.id} 现场图`"
                      draggable="false"
                      @click="openSnapshotPreview"
                    />
                    <template v-if="showBoxes">
                      <div
                        v-for="box in detectionBoxes"
                        :key="box.id"
                        class="detect-box"
                        :class="boxTone(box.label)"
                        :style="boxStyle(box)"
                      >
                        <span class="box-label">
                          {{ translateLabel(box.label) }} {{ confidencePercent(box.confidence) }}%
                        </span>
                      </div>
                    </template>
                    <div class="image-info-overlay">
                      <span>{{ alert?.cameraName }}</span>
                      <span>{{ formatDate(alert?.triggeredAt) }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else-if="mediaPending" class="pending-media">
                <el-icon class="is-loading" :size="36"><Loading /></el-icon>
                <p>{{ alert?.media?.message || '现场图片采集中，请稍候…' }}</p>
                <p class="pending-sub">系统正从摄像头 RTSP 抓拍，约数秒到十几秒</p>
              </div>
              <div class="evidence-frame" v-else-if="alert?.evidenceSvg" v-html="alert.evidenceSvg"></div>
              <div v-else class="mock-image">
                <div class="image-bg"></div>
                <div class="image-info-overlay">
                  <span>{{ alert?.cameraName }}</span>
                  <span>{{ formatDate(alert?.triggeredAt) }}</span>
                </div>
              </div>
            </div>
            <div v-else class="video-container">
              <div v-if="isRealMedia(alert?.videoUrl) || alert?.clip?.available" class="real-media-frame">
                <video
                  class="real-video"
                  :src="mediaSrc(alert.videoUrl || alert.clip?.url)"
                  controls
                  playsinline
                  preload="metadata"
                />
              </div>
              <div v-else-if="mediaPending" class="pending-media">
                <el-icon class="is-loading" :size="36"><Loading /></el-icon>
                <p>{{ alert?.media?.message || '视频片段采集中，请稍候…' }}</p>
                <p class="pending-sub">告警触发后自动录制约 5 秒现场短视频</p>
              </div>
              <div v-else class="mock-video-player">
                <div class="evidence-frame" v-if="alert?.evidenceSvg" v-html="alert.evidenceSvg"></div>
                <div v-else class="video-bg"></div>
              </div>
              <p class="clip-hint">{{ alert?.clip?.message || alert?.media?.message || '' }}</p>
            </div>
          </div>
        </el-card>

        <el-card class="detection-card" style="margin-top: 20px">
          <template #header>
            <span class="card-title">检测结果（{{ detectionBoxes.length }}）</span>
          </template>
          <el-table :data="detectionBoxes" size="default" border>
            <el-table-column prop="id" label="序号" width="70" />
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
            <el-table-column label="位置坐标 bbox (0~1)">
              <template #default="{ row }">
                <code>
                  x: {{ row.bbox.x.toFixed(3) }},
                  y: {{ row.bbox.y.toFixed(3) }},
                  w: {{ row.bbox.w.toFixed(3) }},
                  h: {{ row.bbox.h.toFixed(3) }}
                </code>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

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
              <span class="value">{{ alert?.camera?.name || alert?.cameraName || '-' }}</span>
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
              <span class="label">检测目标</span>
              <span class="value">{{ alert?.detectionCount ?? detectionBoxes.length }}</span>
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
              <span class="value">
                #{{ alert.ticket.id }}
                {{ alert.ticket.status === 'open' ? '待处理' : '已完成' }}
              </span>
            </div>
          </div>
        </el-card>

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

        <el-card class="quick-actions" style="margin-top: 20px">
          <template #header>
            <span class="card-title">快速操作</span>
          </template>
          <div class="action-grid">
            <el-button :icon="Download" @click="handleDownload">下载取证图</el-button>
            <el-button :icon="Share" @click="handleShare">复制链接</el-button>
            <el-button :icon="Printer" @click="handlePrint">打印报告</el-button>
            <el-button :icon="Warning" type="danger" :disabled="!!alert?.hasTicket || !!alert?.ticket" @click="openDispatch">
              {{ alert?.hasTicket || alert?.ticket ? '已派发' : '派发工单' }}
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
  ArrowLeft, VideoPlay, Download, Share, Printer, Warning, Loading
} from '@element-plus/icons-vue'
import dayjs from 'dayjs'

interface DetectionBox {
  id: number | string
  label: string
  confidence: number
  bbox: { x: number; y: number; w: number; h: number }
}

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const submitLoading = ref(false)
const dispatchLoading = ref(false)
const dispatchVisible = ref(false)
const alert = ref<any>(null)
const mediaTab = ref<'image' | 'video'>('image')
const showBoxes = ref(true)
const clipPlaying = ref(false)
const clipProgress = ref(0)
const clipElapsed = ref(0)
let clipTimer: any = null
let mediaPollTimer: any = null
let mediaPollCount = 0
const mediaGaveUp = ref(false)
const realtimeOffs: Array<() => void> = []

const mediaPending = computed(() => {
  const a = alert.value
  if (!a || mediaGaveUp.value) return false
  if (mediaTab.value === 'image') {
    if (isRealMedia(a.snapshotUrl || a.imageUrl)) return false
    return true
  }
  if (isRealMedia(a.videoUrl) || a.clip?.available) return false
  return true
})

function isRealMedia(url?: string) {
  const u = (url || '').trim()
  return u.startsWith('/media/alerts/') || /\.(jpg|jpeg|png|webp|mp4|webm)(\?|$)/i.test(u)
}

function mediaSrc(url?: string) {
  const u = (url || '').trim()
  if (!u) return ''
  const sep = u.includes('?') ? '&' : '?'
  return `${u}${sep}t=${encodeURIComponent(String(alert.value?.updatedAt || alert.value?.id || Date.now()))}`
}

function openSnapshotPreview() {
  const u = mediaSrc(alert.value?.snapshotUrl || alert.value?.imageUrl)
  if (u) window.open(u, '_blank', 'noopener')
}

function stopMediaPoll() {
  if (mediaPollTimer) {
    clearInterval(mediaPollTimer)
    mediaPollTimer = null
  }
}

function startMediaPoll() {
  stopMediaPoll()
  mediaPollCount = 0
  mediaGaveUp.value = false
  mediaPollTimer = setInterval(async () => {
    mediaPollCount += 1
    if (mediaPollCount > 45) {
      // ~90s
      mediaGaveUp.value = true
      stopMediaPoll()
      return
    }
    const a = alert.value
    if (!a?.id) return
    const snapOk = isRealMedia(a.snapshotUrl || a.imageUrl)
    const vidOk = isRealMedia(a.videoUrl) || !!a.clip?.available
    if (snapOk && vidOk) {
      stopMediaPoll()
      return
    }
    try {
      const res: any = await alertApi.getDetail(a.id)
      alert.value = normalizeDetail(res)
      const n = alert.value
      if (isRealMedia(n.snapshotUrl || n.imageUrl) && (isRealMedia(n.videoUrl) || n.clip?.available)) {
        stopMediaPoll()
      }
    } catch {
      /* ignore */
    }
  }, 2000)
}

const handleForm = reactive({
  status: 'resolved',
  note: ''
})
const dispatchForm = reactive({
  assignee: '',
  note: ''
})

const detectionBoxes = computed<DetectionBox[]>(() => {
  return (alert.value?.detectionBoxes || []).map((item: any, idx: number) => {
    const bbox = item?.bbox && typeof item.bbox === 'object' ? item.bbox : item
    return {
      id: item?.id ?? idx + 1,
      label: item?.label || 'object',
      confidence: Number(item?.confidence ?? 0),
      bbox: {
        x: Number(bbox?.x || 0),
        y: Number(bbox?.y || 0),
        w: Number(bbox?.w || 0),
        h: Number(bbox?.h || 0)
      }
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

function boxStyle(box: DetectionBox) {
  return {
    left: (box.bbox.x || 0) * 100 + '%',
    top: (box.bbox.y || 0) * 100 + '%',
    width: (box.bbox.w || 0) * 100 + '%',
    height: (box.bbox.h || 0) * 100 + '%'
  }
}

function boxTone(label?: string) {
  const l = (label || '').toLowerCase()
  if (l.includes('火') || l === 'fire') return 'fire'
  if (l.includes('烟') || l === 'smoke') return 'smoke'
  if (l.includes('违停') || l.includes('乱停') || l === 'car' || l === 'truck') return 'car'
  return 'person'
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
    bus: '公交车',
    bicycle: '自行车',
    motorcycle: '摩托车',
    fire: '火焰',
    smoke: '烟雾',
    人员: '人员',
    轿车: '轿车',
    卡车: '卡车',
    公交车: '公交车',
    自行车: '自行车',
    摩托车: '摩托车',
    火焰: '火焰',
    乱停乱放: '乱停乱放',
    乱扔垃圾: '乱扔垃圾',
    网格区违停: '网格区违停'
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

function normalizeDetail(raw: any) {
  return {
    ...raw,
    cameraName: raw.cameraName || raw.camera?.name || '',
    cameraLocation: raw.cameraLocation || raw.camera?.location || '',
    cameraIp: raw.cameraIp || raw.camera?.ip || '',
    detectionBoxes: Array.isArray(raw.detectionBoxes) ? raw.detectionBoxes : [],
    detectionCount: Number(raw.detectionCount ?? (raw.detectionBoxes || []).length ?? 0),
    hasTicket: !!(raw.hasTicket || raw.ticket),
    actions: Array.isArray(raw.actions) ? raw.actions : [],
    clip: raw.clip || null,
    ticket: raw.ticket || null,
    camera: raw.camera || null,
    media: raw.media || null,
    snapshotUrl: raw.snapshotUrl || '',
    imageUrl: raw.imageUrl || '',
    videoUrl: raw.videoUrl || '',
    evidenceUrl: raw.evidenceUrl || `/api/alerts/${raw.id}/evidence`,
    evidenceSvg: raw.evidenceSvg || ''
  }
}

async function loadDetail() {
  const id = Number(route.params.id)
  if (!id) return
  loading.value = true
  try {
    const res: any = await alertApi.getDetail(id)
    alert.value = normalizeDetail(res)
    const snapOk = isRealMedia(alert.value.snapshotUrl || alert.value.imageUrl)
    const vidOk = isRealMedia(alert.value.videoUrl) || !!alert.value.clip?.available
    if (!snapOk || !vidOk) startMediaPoll()
    else stopMediaPoll()
  } finally {
    loading.value = false
  }
}

async function submitHandle() {
  if (!alert.value) return
  submitLoading.value = true
  try {
    const res: any = await alertApi.handle(alert.value.id, {
      status: handleForm.status,
      note: handleForm.note || ''
    })
    alert.value = normalizeDetail(res)
    ElMessage.success('处理成功')
  } catch {
    /* interceptor */
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
    const snap = alert.value.snapshotUrl || alert.value.imageUrl
    if (isRealMedia(snap)) {
      const a = document.createElement('a')
      a.href = snap
      a.download = `alert-${alert.value.id}-snapshot.jpg`
      a.target = '_blank'
      a.click()
      ElMessage.success('现场图片已下载')
      return
    }
    const res: any = await alertApi.getEvidence(alert.value.id)
    downloadText(
      res.filename || `alert-${alert.value.id}.svg`,
      res.content,
      res.mimeType || 'image/svg+xml'
    )
    ElMessage.success('取证图已下载')
  } catch {
    /* interceptor */
  }
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
  } catch {
    /* interceptor */
  }
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
    if (res.alert) {
      alert.value = normalizeDetail(res.alert)
    } else if (res.ticket) {
      alert.value.ticket = res.ticket
      alert.value.hasTicket = true
    }
    dispatchVisible.value = false
    ElMessage.success(res.message || '工单已派发')
  } catch {
    /* interceptor */
  } finally {
    dispatchLoading.value = false
  }
}

onMounted(() => {
  loadDetail()
  realtimeOffs.push(
    onRealtime('alert:updated', (payload) => {
      if (payload?.id && payload.id === alert.value?.id) {
        // Prefer payload media URLs when present; still refresh for clip/media status
        if (isRealMedia(payload.snapshotUrl) || isRealMedia(payload.videoUrl)) {
          alert.value = normalizeDetail({ ...alert.value, ...payload })
        }
        loadDetail()
      }
    })
  )
})

onUnmounted(() => {
  stopClip()
  stopMediaPoll()
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

.real-media-frame {
  width: 100%;
  max-width: 960px;
  border-radius: 8px;
  overflow: hidden;
  background: #0b1220;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.shot-wrap {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.shot-toolbar {
  width: 100%;
  max-width: 960px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.shot-hint {
  font-size: 12px;
  color: #9ca3af;
}

.shot {
  position: relative;
  display: inline-block;
  line-height: 0;
  max-width: 100%;
}

.real-image {
  max-width: 100%;
  max-height: calc(100vh - 280px);
  width: auto;
  height: auto;
  display: block;
  background: #000;
  image-rendering: auto;
  cursor: zoom-in;
}

.real-image :deep(img) {
  max-width: 100%;
  max-height: calc(100vh - 280px);
  width: auto;
  height: auto;
  object-fit: contain;
  image-rendering: auto;
  display: block;
}

.real-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  background: #000;
}

.pending-media {
  width: 100%;
  max-width: 700px;
  aspect-ratio: 16/9;
  border-radius: 8px;
  background: #0f172a;
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
  padding: 24px;
}

.pending-media p {
  margin: 0;
  font-size: 14px;
}

.pending-sub {
  font-size: 12px !important;
  color: #94a3b8 !important;
}

.real-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  background: #000;
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
  pointer-events: none;
  box-sizing: border-box;
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

.video-container .real-media-frame {
  width: 100%;
  max-width: 960px;
  aspect-ratio: 16 / 9;
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
