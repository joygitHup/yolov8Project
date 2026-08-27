<template>
  <div class="monitor-page">
    <!-- 左侧摄像头列表 -->
    <div class="camera-sidebar">
      <div class="sidebar-header">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索摄像头"
          :prefix-icon="Search"
          size="small"
          clearable
        />
      </div>
      <div class="camera-list">
        <div
          v-for="cam in filteredCameras"
          :key="cam.id"
          class="camera-item"
          :class="{ active: selectedCamera?.id === cam.id, offline: !isLive(cam) }"
          @click="selectCamera(cam)"
        >
          <div class="cam-icon">
            <el-icon><VideoCamera /></el-icon>
          </div>
          <div class="cam-info">
            <div class="cam-name">{{ cam.name }}</div>
            <div class="cam-location">{{ cam.location || cam.ip || '未标注位置' }}</div>
          </div>
          <div class="cam-status" :class="cameraState(cam)">
            <span class="status-dot"></span>
          </div>
        </div>
        <el-empty v-if="filteredCameras.length === 0" description="未找到摄像头" :image-size="60" />
      </div>
    </div>

    <!-- 主监控区 -->
    <div class="monitor-main">
      <div class="monitor-toolbar">
        <div class="toolbar-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item>实时监控</el-breadcrumb-item>
            <el-breadcrumb-item v-if="selectedCamera">{{ selectedCamera.name }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="toolbar-right">
          <el-select v-model="layoutMode" size="small" style="width: 120px">
            <el-option label="单画面" value="1" />
            <el-option label="4画面" value="4" />
            <el-option label="9画面" value="9" />
          </el-select>
          <el-divider direction="vertical" />
          <el-tooltip content="全屏">
            <el-icon class="tool-icon" @click="toggleFullscreen"><FullScreen /></el-icon>
          </el-tooltip>
          <el-tooltip content="截图">
            <el-icon class="tool-icon" @click="handleScreenshot"><Camera /></el-icon>
          </el-tooltip>
          <el-tooltip :content="isRecording ? '停止录制' : '开始录制'">
            <el-icon class="tool-icon" @click="handleRecord" :class="{ recording: isRecording }">
              <VideoCameraFilled />
            </el-icon>
          </el-tooltip>
        </div>
      </div>

      <div class="video-grid" :class="`grid-${layoutMode}`" ref="gridRef">
        <div
          v-for="(cam, idx) in gridSlots"
          :key="cam?.id || `empty-${idx}`"
          class="video-panel"
          :class="{ active: selectedCamera?.id === cam?.id }"
          @click="selectGridCamera(idx)"
        >
          <div v-if="cam" class="video-container">
            <div class="video-content">
              <div v-if="!isLive(cam)" class="video-offline">
                <el-icon :size="48"><VideoPause /></el-icon>
                <p>{{ !cam.enabled ? '设备已停用' : '设备离线' }}</p>
                <span class="offline-meta">{{ cam.ip }} {{ cam.resolution }}</span>
              </div>
              <template v-else>
                <div class="camera-scene" :style="sceneStyle(cam)"></div>
                <div class="video-overlay">
                  <div
                    v-for="(box, boxIdx) in detectionData[cam.id] || []"
                    :key="box.id || boxIdx"
                    class="detect-box"
                    :class="box.label"
                    :style="boxStyle(box)"
                  >
                    <span class="box-label">{{ translateLabel(box.label) }} {{ formatConfidence(box.confidence) }}</span>
                  </div>
                </div>
                <div class="video-info">
                  <span class="video-title">{{ cam.name }}</span>
                  <span class="live-badge" :class="{ recording: cam.recording }">
                    <span class="live-dot"></span> {{ cam.recording ? 'REC' : 'LIVE' }}
                  </span>
                </div>
                <div class="video-meta">
                  {{ cam.ip || '无IP' }} · {{ cam.resolution }} · {{ typeText(cam.type) }}
                </div>
                <div class="video-timestamp">
                  {{ detectionData[cam.id]?.length || 0 }} 目标 · {{ cam.fps || 0 }} FPS · {{ currentTime }}
                </div>
              </template>
            </div>
          </div>
          <div v-else class="video-placeholder">
            <el-icon :size="32" color="#9ca3af"><Plus /></el-icon>
          </div>
        </div>
      </div>

      <!-- PTZ 控制 -->
      <div v-if="selectedCamera && isLive(selectedCamera)" class="ptz-panel">
        <div class="ptz-title">云台控制</div>
        <div class="ptz-pad">
          <div class="ptz-row">
            <div></div>
            <div class="ptz-btn" @click="handlePtz('up')">
              <el-icon><ArrowUp /></el-icon>
            </div>
            <div></div>
          </div>
          <div class="ptz-row">
            <div class="ptz-btn" @click="handlePtz('left')">
              <el-icon><ArrowLeft /></el-icon>
            </div>
            <div class="ptz-center">
              <el-icon><Aim /></el-icon>
            </div>
            <div class="ptz-btn" @click="handlePtz('right')">
              <el-icon><ArrowRight /></el-icon>
            </div>
          </div>
          <div class="ptz-row">
            <div></div>
            <div class="ptz-btn" @click="handlePtz('down')">
              <el-icon><ArrowDown /></el-icon>
            </div>
            <div></div>
          </div>
        </div>
        <div class="ptz-zoom">
          <el-button size="small" @click="handlePtz('zoomin')">+ 放大</el-button>
          <el-button size="small" @click="handlePtz('zoomout')">- 缩小</el-button>
        </div>
        <div class="ptz-readout">
          <span>P {{ formatPtz(selectedCamera?.ptz?.pan) }}</span>
          <span>T {{ formatPtz(selectedCamera?.ptz?.tilt) }}</span>
          <span>Z {{ formatPtz(selectedCamera?.ptz?.zoom) }}</span>
        </div>
      </div>
    </div>

    <!-- 右侧实时告警 -->
    <div class="alert-sidebar">
      <div class="sidebar-header">
        <span class="header-title">实时告警</span>
        <el-badge :value="unhandledCount" class="alert-badge" />
      </div>
      <div class="alert-list">
        <div
          v-for="alert in realtimeAlerts"
          :key="alert.id"
          class="alert-item"
          :class="alert.level"
          @click="viewAlertDetail(alert)"
        >
          <div class="alert-icon">
            <el-icon>
              <component :is="alertIcon(alert.type)" />
            </el-icon>
          </div>
          <div class="alert-body">
            <div class="alert-desc">{{ alert.description }}</div>
            <div class="alert-meta">
              <span>{{ alert.cameraName }}</span>
              <span>{{ formatTime(alert.triggeredAt) }}</span>
            </div>
          </div>
        </div>
        <el-empty v-if="realtimeAlerts.length === 0" description="暂无告警" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { cameraApi, alertApi } from '@/api'
import { onRealtime } from '@/utils/realtime'
import { ElMessage } from 'element-plus'
import {
  Search, VideoCamera, FullScreen, Camera, VideoCameraFilled,
  Plus, ArrowUp, ArrowDown, ArrowLeft, ArrowRight, Aim, VideoPause,
  Warning, Bell
} from '@element-plus/icons-vue'
import dayjs from 'dayjs'

const router = useRouter()
const searchKeyword = ref('')
const layoutMode = ref('4')
const selectedCamera = ref<any>(null)
const cameras = ref<any[]>([])
const realtimeAlerts = ref<any[]>([])
const unhandledCount = ref(0)
const currentTime = ref('')
const gridRef = ref<HTMLElement>()
const detectionData = reactive<Record<number, any[]>>({})

let timeTimer: any = null
let wallTimer: any = null
const realtimeOffs: Array<() => void> = []

const isRecording = computed(() => !!selectedCamera.value?.recording)

const filteredCameras = computed(() => {
  if (!searchKeyword.value) return cameras.value
  const kw = searchKeyword.value.toLowerCase()
  return cameras.value.filter(c =>
    String(c.name || '').toLowerCase().includes(kw) ||
    String(c.location || '').toLowerCase().includes(kw) ||
    String(c.ip || '').toLowerCase().includes(kw)
  )
})

const gridSlots = computed(() => {
  const count = parseInt(layoutMode.value, 10) || 4
  const list = cameras.value
  if (!list.length) return Array.from({ length: count }, () => null)
  if (count === 1) return [selectedCamera.value || list[0]]
  const selected = selectedCamera.value
  const rest = list.filter(c => c.id !== selected?.id)
  const ordered = selected ? [selected, ...rest] : [...list]
  return Array.from({ length: count }, (_, i) => ordered[i] || null)
})

function isLive(cam: any) {
  return !!cam && cam.enabled !== false && cam.status === 'online'
}

function cameraState(cam: any) {
  if (!cam?.enabled) return 'disabled'
  return cam.status === 'online' ? 'online' : 'offline'
}

function typeText(type: string) {
  const map: Record<string, string> = {
    hikvision: '海康',
    dahua: '大华',
    other: '其他'
  }
  return map[type] || type || '未知'
}

function sceneStyle(cam: any) {
  const hue = ((cam?.id || 1) * 47) % 360
  return {
    background: `radial-gradient(ellipse at 28% 30%, hsla(${hue}, 70%, 45%, 0.28) 0%, transparent 52%),
      linear-gradient(180deg, #1e293b 0%, #0f172a 100%)`
  }
}

function boxStyle(box: any) {
  const bbox = box?.bbox || box || {}
  return {
    left: (bbox.x || 0) * 100 + '%',
    top: (bbox.y || 0) * 100 + '%',
    width: (bbox.w || 0) * 100 + '%',
    height: (bbox.h || 0) * 100 + '%'
  }
}

function formatConfidence(value: number) {
  if (value == null) return ''
  const pct = value <= 1 ? value * 100 : value
  return `${pct.toFixed(0)}%`
}

function formatPtz(value: number | undefined) {
  return Number(value || 0).toFixed(1)
}

function selectCamera(cam: any) {
  selectedCamera.value = cam
}

function selectGridCamera(idx: number) {
  const cam = gridSlots.value[idx]
  if (cam) selectedCamera.value = cam
}

function alertIcon(type: string) {
  return type === 'fire' ? Bell : Warning
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

function formatTime(time: string) {
  return dayjs(time).format('HH:mm:ss')
}

function applyFrames(frames: Record<string, any> = {}) {
  Object.entries(frames).forEach(([id, frame]) => {
    detectionData[Number(id)] = frame?.detections || []
  })
}

function syncSelected() {
  if (!cameras.value.length) {
    selectedCamera.value = null
    return
  }
  if (selectedCamera.value) {
    const next = cameras.value.find(c => c.id === selectedCamera.value.id)
    selectedCamera.value = next || cameras.value[0]
  } else {
    selectedCamera.value = cameras.value[0]
  }
}

async function loadWall() {
  try {
    const res: any = await cameraApi.getMonitorWall()
    cameras.value = res.cameras || []
    applyFrames(res.frames || {})
    realtimeAlerts.value = res.alerts?.list || []
    unhandledCount.value = res.alerts?.total || 0
    syncSelected()
  } catch {
    await loadCamerasFallback()
  }
}

async function loadCamerasFallback() {
  const res: any = await cameraApi.getAll()
  cameras.value = res || []
  syncSelected()
  cameras.value.forEach((cam: any) => {
    if (isLive(cam)) fetchDetection(cam.id)
  })
  await loadAlerts()
}

async function fetchDetection(cameraId: number) {
  try {
    const res: any = await cameraApi.getDetection(cameraId)
    detectionData[cameraId] = res.detections || []
  } catch (e) {}
}

async function loadAlerts() {
  try {
    const res: any = await alertApi.getList({ page: 1, pageSize: 20, status: 'unhandled' })
    realtimeAlerts.value = res.list || []
    unhandledCount.value = res.total || 0
  } catch (e) {}
}

function toggleFullscreen() {
  const el = gridRef.value as any
  if (!document.fullscreenElement) {
    el?.requestFullscreen()
  } else {
    document.exitFullscreen()
  }
}

async function handleScreenshot() {
  if (!selectedCamera.value) {
    ElMessage.warning('请先选择摄像头')
    return
  }
  try {
    const res: any = await cameraApi.snapshot(selectedCamera.value.id)
    ElMessage.success(`截图已保存（#${res.id}，${res.detectionCount || 0} 个目标）`)
  } catch (e) {}
}

async function handleRecord() {
  if (!selectedCamera.value) {
    ElMessage.warning('请先选择摄像头')
    return
  }
  if (!isLive(selectedCamera.value)) {
    ElMessage.warning('离线或停用设备无法录制')
    return
  }
  try {
    const action = selectedCamera.value.recording ? 'stop' : 'start'
    const res: any = await cameraApi.record(selectedCamera.value.id, { action })
    selectedCamera.value.recording = !!res.recording
    const idx = cameras.value.findIndex(c => c.id === selectedCamera.value.id)
    if (idx >= 0) cameras.value[idx].recording = !!res.recording
    ElMessage.info(res.recording ? '开始录制' : '录制已停止')
  } catch (e) {}
}

async function handlePtz(direction: string) {
  if (!selectedCamera.value) return
  try {
    const res: any = await cameraApi.ptz(selectedCamera.value.id, { direction })
    if (res?.ptz) {
      selectedCamera.value.ptz = res.ptz
      const idx = cameras.value.findIndex(c => c.id === selectedCamera.value.id)
      if (idx >= 0) cameras.value[idx].ptz = res.ptz
    }
    ElMessage.info(`云台${directionText(direction)}指令已发送`)
  } catch (e) {}
}

function directionText(dir: string) {
  const map: Record<string, string> = {
    up: '向上', down: '向下', left: '向左', right: '向右',
    zoomin: '放大', zoomout: '缩小'
  }
  return map[dir] || dir
}

function viewAlertDetail(alert: any) {
  router.push(`/alerts/${alert.id}`)
}

onMounted(() => {
  loadWall()

  timeTimer = setInterval(() => {
    currentTime.value = dayjs().format('YYYY-MM-DD HH:mm:ss')
  }, 1000)
  currentTime.value = dayjs().format('YYYY-MM-DD HH:mm:ss')
  wallTimer = setInterval(loadWall, 8000)

  const offFrame = onRealtime('detection:frame', (frame) => {
    if (frame?.cameraId == null) return
    detectionData[frame.cameraId] = frame.detections || []
    const cam = cameras.value.find(c => c.id === frame.cameraId)
    if (cam) {
      cam.detectionCount = (frame.detections || []).length
      cam.fps = frame.fps
      cam.lastFrameAt = frame.timestamp
    }
  })
  const offAlert = onRealtime('alert:created', (alert) => {
    if (!alert) return
    realtimeAlerts.value = [alert, ...realtimeAlerts.value].slice(0, 20)
    unhandledCount.value += 1
  })
  realtimeOffs.push(offFrame, offAlert)
})

onUnmounted(() => {
  clearInterval(timeTimer)
  clearInterval(wallTimer)
  realtimeOffs.forEach((fn) => fn())
})
</script>

<style scoped>
.monitor-page {
  display: flex;
  height: calc(100vh - 100px);
  gap: 16px;
  margin: -20px;
  padding: 20px;
  background: #f0f2f5;
}

.camera-sidebar {
  width: 240px;
  background: #fff;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

.sidebar-header {
  padding: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.camera-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.camera-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
  margin-bottom: 4px;
}

.camera-item:hover {
  background: #f3f4f6;
}

.camera-item.active {
  background: #e6f4ff;
  border: 1px solid #91caff;
}

.camera-item.offline .cam-icon,
.camera-item.offline .cam-name {
  opacity: 0.5;
}

.cam-icon {
  font-size: 20px;
  color: #1677ff;
  flex-shrink: 0;
}

.cam-info {
  flex: 1;
  min-width: 0;
}

.cam-name {
  font-size: 13px;
  font-weight: 500;
  color: #1f2937;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cam-location {
  font-size: 11px;
  color: #9ca3af;
  margin-top: 2px;
}

.cam-status {
  flex-shrink: 0;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #52c41a;
}

.cam-status.offline .status-dot {
  background: #d1d5db;
}

.cam-status.disabled .status-dot {
  background: #faad14;
}

.monitor-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.monitor-toolbar {
  height: 48px;
  background: #fff;
  border-radius: 8px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.toolbar-left, .toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.tool-icon {
  font-size: 18px;
  color: #4b5563;
  cursor: pointer;
  transition: color 0.2s;
}

.tool-icon:hover {
  color: #1677ff;
}

.tool-icon.recording {
  color: #f5222d;
  animation: blink 1s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.video-grid {
  flex: 1;
  display: grid;
  gap: 8px;
  min-height: 0;
}

.grid-1 { grid-template-columns: 1fr; grid-template-rows: 1fr; }
.grid-4 { grid-template-columns: repeat(2, 1fr); grid-template-rows: repeat(2, 1fr); }
.grid-9 { grid-template-columns: repeat(3, 1fr); grid-template-rows: repeat(3, 1fr); }

.video-panel {
  background: #000;
  border-radius: 6px;
  overflow: hidden;
  position: relative;
  cursor: pointer;
}

.video-panel.active {
  outline: 2px solid #1677ff;
  outline-offset: -2px;
}

.video-container {
  width: 100%;
  height: 100%;
}

.video-content {
  position: relative;
  width: 100%;
  height: 100%;
}

.video-offline {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #6b7280;
  background: #111827;
}

.video-offline p {
  margin-top: 12px;
  font-size: 14px;
}

.offline-meta {
  margin-top: 6px;
  font-size: 12px;
  color: #9ca3af;
}

.camera-scene {
  width: 100%;
  height: 100%;
  position: relative;
}

.camera-scene::after {
  content: '';
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0, 0, 0, 0.28) 2px,
    rgba(0, 0, 0, 0.28) 4px
  );
  pointer-events: none;
}

.video-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.detect-box {
  position: absolute;
  border: 2px solid #52c41a;
  border-radius: 2px;
}

.detect-box.person { border-color: #52c41a; }
.detect-box.car { border-color: #3b82f6; }
.detect-box.truck { border-color: #8b5cf6; }
.detect-box.fire { border-color: #f5222d; }
.detect-box.smoke { border-color: #f59e0b; }

.box-label {
  position: absolute;
  top: -22px;
  left: -2px;
  background: #52c41a;
  color: #fff;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 2px 2px 0 0;
  white-space: nowrap;
}

.detect-box.person .box-label { background: #52c41a; }
.detect-box.car .box-label { background: #3b82f6; }
.detect-box.truck .box-label { background: #8b5cf6; }
.detect-box.fire .box-label { background: #f5222d; }
.detect-box.smoke .box-label { background: #f59e0b; }

.video-info {
  position: absolute;
  top: 8px;
  left: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 10;
}

.video-title {
  color: #fff;
  font-size: 12px;
  font-weight: 500;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
}

.live-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(245, 34, 45, 0.9);
  color: #fff;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 600;
}

.live-badge.recording {
  background: rgba(245, 34, 45, 0.95);
}

.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #fff;
  animation: blink 1s ease-in-out infinite;
}

.video-meta {
  position: absolute;
  top: 32px;
  left: 8px;
  color: rgba(255, 255, 255, 0.85);
  font-size: 11px;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
  z-index: 10;
}

.video-timestamp {
  position: absolute;
  bottom: 8px;
  right: 8px;
  color: #fff;
  font-size: 11px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
  z-index: 10;
}

.video-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f3f4f6;
}

.ptz-panel {
  margin-top: 12px;
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 24px;
}

.ptz-title {
  font-weight: 600;
  color: #1f2937;
  writing-mode: vertical-rl;
}

.ptz-pad {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ptz-row {
  display: flex;
  gap: 4px;
}

.ptz-btn {
  width: 36px;
  height: 36px;
  background: #f3f4f6;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #4b5563;
  transition: all 0.2s;
}

.ptz-btn:hover {
  background: #e5e7eb;
  color: #1677ff;
}

.ptz-btn:active {
  background: #1677ff;
  color: #fff;
}

.ptz-center {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #9ca3af;
}

.ptz-zoom {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ptz-readout {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  color: #4b5563;
}

.alert-sidebar {
  width: 280px;
  background: #fff;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

.header-title {
  font-weight: 600;
  color: #1f2937;
}

.alert-badge {
  margin-left: auto;
}

.alert-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.alert-item {
  display: flex;
  gap: 10px;
  padding: 10px;
  border-radius: 6px;
  cursor: pointer;
  border-left: 3px solid transparent;
  margin-bottom: 6px;
  transition: background 0.2s;
}

.alert-item:hover {
  background: #f9fafb;
}

.alert-item.high { border-left-color: #f5222d; }
.alert-item.medium { border-left-color: #faad14; }
.alert-item.low { border-left-color: #1677ff; }

.alert-icon {
  font-size: 18px;
  flex-shrink: 0;
  margin-top: 2px;
}

.alert-item.high .alert-icon { color: #f5222d; }
.alert-item.medium .alert-icon { color: #faad14; }
.alert-item.low .alert-icon { color: #1677ff; }

.alert-body {
  flex: 1;
  min-width: 0;
}

.alert-desc {
  font-size: 13px;
  color: #1f2937;
  margin-bottom: 4px;
  line-height: 1.4;
}

.alert-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #9ca3af;
}
</style>
