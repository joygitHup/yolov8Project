<template>
  <div class="dashboard-page">
    <!-- 顶部标题栏 -->
    <div class="dashboard-header">
      <div class="header-left">
        <h1 class="main-title">
          <el-icon class="title-icon"><DataBoard /></el-icon>
          YOLOv8 智能视频分析数据大屏
        </h1>
        <div class="time-display">
          <el-icon><Clock /></el-icon>
          <span>{{ currentTime }}</span>
        </div>
      </div>
      <div class="header-right">
        <div class="system-status">
          <span class="status-dot online"></span>
          <span>系统运行中</span>
        </div>
        <el-button size="small" :icon="Refresh" @click="refreshData" :loading="loading">
          刷新数据
        </el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-icon camera">
          <el-icon><VideoCamera /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ overviewData.cameras?.online || 0 }}/{{ overviewData.cameras?.total || 0 }}</div>
          <div class="stat-label">在线设备 / 总设备</div>
          <div class="stat-rate">在线率 {{ overviewData.cameras?.rate || 0 }}%</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon alert">
          <el-icon><Warning /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ overviewData.alerts?.today || 0 }}</div>
          <div class="stat-label">今日告警</div>
          <div class="stat-rate text-danger">待处理 {{ overviewData.alerts?.unhandled || 0 }}</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon detection">
          <el-icon><Aim /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ overviewData.detection?.totalToday || 0 }}</div>
          <div class="stat-label">今日检测次数</div>
          <div class="stat-rate">平均置信度 {{ overviewData.detection?.avgConfidence || 0 }}</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon system">
          <el-icon><Monitor /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ overviewData.system?.uptime || '-' }}</div>
          <div class="stat-label">运行时长</div>
          <div class="stat-rate">GPU 负载 {{ overviewData.system?.gpu || 0 }}%</div>
        </div>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="dashboard-main">
      <!-- 左侧 -->
      <div class="dashboard-left">
        <!-- 告警趋势图 -->
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title">24小时告警趋势</span>
          </div>
          <div class="panel-body">
            <div ref="trendChartRef" class="chart-container"></div>
          </div>
        </div>

        <!-- 摄像头告警排行 -->
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title">摄像头告警排行</span>
          </div>
          <div class="panel-body">
            <div ref="rankChartRef" class="chart-container"></div>
          </div>
        </div>
      </div>

      <!-- 中间 - 实时监控 -->
      <div class="dashboard-center">
        <div class="panel monitor-panel">
          <div class="panel-header">
            <span class="panel-title">实时监控画面</span>
            <div class="panel-tools">
              <span class="live-tag">
                <span class="live-dot"></span> LIVE
              </span>
            </div>
          </div>
          <div class="panel-body">
            <div class="monitor-grid">
              <div
                v-for="cam in displayCameras"
                :key="cam.id"
                class="monitor-item"
                :class="{ offline: cam.status === 'offline' }"
              >
                <div class="video-placeholder">
                  <el-icon v-if="cam.status === 'offline'" class="offline-icon"><VideoPause /></el-icon>
                  <template v-else>
                    <div class="mock-video-bg"></div>
                    <div class="mock-scanline"></div>
                    <!-- 模拟检测框 -->
                    <div
                      v-for="(box, idx) in camMockDetections[cam.id] || []"
                      :key="idx"
                      class="detection-box"
                      :class="box.label"
                      :style="{
                        left: box.x + '%',
                        top: box.y + '%',
                        width: box.w + '%',
                        height: box.h + '%'
                      }"
                    >
                      <span class="detection-label">{{ box.label }} {{ box.confidence }}</span>
                    </div>
                  </template>
                </div>
                <div class="monitor-info">
                  <span class="cam-name">{{ cam.name }}</span>
                  <span class="cam-status" :class="cam.status">
                    <span class="status-dot"></span>
                    {{ cam.status === 'online' ? '在线' : '离线' }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧 -->
      <div class="dashboard-right">
        <!-- 告警类型分布 -->
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title">告警类型分布</span>
          </div>
          <div class="panel-body">
            <div ref="typeChartRef" class="chart-container small"></div>
          </div>
        </div>

        <!-- 实时告警流 -->
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title">实时告警</span>
            <span class="refresh-hint">每5秒刷新</span>
          </div>
          <div class="panel-body alert-list">
            <div
              v-for="alert in recentAlerts"
              :key="alert.id"
              class="alert-item"
              :class="alert.level"
            >
              <div class="alert-icon">
                <el-icon v-if="alert.type === 'intrusion'"><Warning /></el-icon>
                <el-icon v-else><Bell /></el-icon>
              </div>
              <div class="alert-content">
                <div class="alert-title">{{ alert.description }}</div>
                <div class="alert-meta">
                  <span>{{ alert.cameraName }}</span>
                  <span>{{ formatTime(alert.triggeredAt) }}</span>
                </div>
              </div>
              <div class="alert-level-tag" :class="alert.level">
                {{ levelText(alert.level) }}
              </div>
            </div>
            <div v-if="recentAlerts.length === 0" class="empty-text">暂无告警</div>
          </div>
        </div>

        <!-- 系统资源 -->
        <div class="panel">
          <div class="panel-header">
            <span class="panel-title">系统资源</span>
          </div>
          <div class="panel-body">
            <div class="resource-item">
              <div class="resource-label">
                <span>CPU</span>
                <span>{{ overviewData.system?.cpu || 0 }}%</span>
              </div>
              <el-progress :percentage="Number(overviewData.system?.cpu || 0)" :show-text="false" />
            </div>
            <div class="resource-item">
              <div class="resource-label">
                <span>内存</span>
                <span>{{ overviewData.system?.memory || 0 }}%</span>
              </div>
              <el-progress :percentage="Number(overviewData.system?.memory || 0)" :show-text="false" status="success" />
            </div>
            <div class="resource-item">
              <div class="resource-label">
                <span>GPU</span>
                <span>{{ overviewData.system?.gpu || 0 }}%</span>
              </div>
              <el-progress :percentage="Number(overviewData.system?.gpu || 0)" :show-text="false" color="#52c41a" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, reactive } from 'vue'
import * as echarts from 'echarts'
import { dashboardApi, cameraApi } from '@/api'
import { useAppStore } from '@/stores/app'
import { ElMessage } from 'element-plus'
import {
  DataBoard, Clock, Refresh, VideoCamera, Warning, Aim, Monitor,
  Bell, VideoPause
} from '@element-plus/icons-vue'
import dayjs from 'dayjs'

const appStore = useAppStore()
appStore.setTheme('dark')

const trendChartRef = ref<HTMLElement>()
const typeChartRef = ref<HTMLElement>()
const rankChartRef = ref<HTMLElement>()

let trendChart: echarts.ECharts | null = null
let typeChart: echarts.ECharts | null = null
let rankChart: echarts.ECharts | null = null

const loading = ref(false)
const currentTime = ref('')
const overviewData = reactive<any>({})
const displayCameras = ref<any[]>([])
const recentAlerts = ref<any[]>([])
const camMockDetections = reactive<Record<number, any[]>>({})

let timeTimer: any = null
let dataTimer: any = null
let detectionTimer: any = null

function updateTime() {
  currentTime.value = dayjs().format('YYYY年MM月DD日 HH:mm:ss')
}

function levelText(level: string) {
  const map: Record<string, string> = { high: '高危', medium: '中危', low: '低危' }
  return map[level] || level
}

function formatTime(time: string) {
  return dayjs(time).format('HH:mm:ss')
}

async function fetchOverview() {
  try {
    const res: any = await dashboardApi.getOverview()
    Object.assign(overviewData, res)
  } catch (e) {}
}

async function fetchCameras() {
  try {
    const res: any = await cameraApi.getAll()
    displayCameras.value = (res || []).slice(0, 4)
    // 初始化模拟检测框
    displayCameras.value.forEach(cam => {
      generateMockDetections(cam.id)
    })
  } catch (e) {}
}

function generateMockDetections(camId: number) {
  const types = ['person', 'car', 'truck', 'fire', 'smoke']
  const count = Math.floor(Math.random() * 4)
  const boxes = []
  for (let i = 0; i < count; i++) {
    boxes.push({
      label: types[Math.floor(Math.random() * types.length)],
      confidence: (0.7 + Math.random() * 0.25).toFixed(2),
      x: Math.random() * 60 + 10,
      y: Math.random() * 50 + 15,
      w: Math.random() * 15 + 8,
      h: Math.random() * 20 + 10
    })
  }
  camMockDetections[camId] = boxes
}

async function fetchRecentAlerts() {
  try {
    const res: any = await dashboardApi.getRecentAlerts()
    recentAlerts.value = res || []
  } catch (e) {}
}

function initCharts() {
  if (trendChartRef.value) {
    trendChart = echarts.init(trendChartRef.value)
    updateTrendChart([])
  }
  if (typeChartRef.value) {
    typeChart = echarts.init(typeChartRef.value)
    updateTypeChart([])
  }
  if (rankChartRef.value) {
    rankChart = echarts.init(rankChartRef.value)
    updateRankChart([])
  }
}

function updateTrendChart(data: any[]) {
  if (!trendChart) return
  const option: any = {
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(17, 24, 39, 0.9)',
      borderColor: '#3b82f6',
      textStyle: { color: '#e5e7eb' }
    },
    legend: {
      data: ['入侵', '违停', '火灾'],
      textStyle: { color: '#9ca3af' },
      right: 10,
      top: 0
    },
    grid: {
      left: 40,
      right: 20,
      top: 30,
      bottom: 24
    },
    xAxis: {
      type: 'category',
      data: data.map(d => d.hour),
      axisLine: { lineStyle: { color: '#374151' } },
      axisLabel: { color: '#9ca3af', fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#9ca3af', fontSize: 11 },
      splitLine: { lineStyle: { color: '#1f2937' } }
    },
    series: [
      {
        name: '入侵', type: 'line', smooth: true,
        data: data.map(d => d.intrusion),
        itemStyle: { color: '#ef4444' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(239, 68, 68, 0.3)' },
          { offset: 1, color: 'rgba(239, 68, 68, 0)' }
        ])}
      },
      {
        name: '违停', type: 'line', smooth: true,
        data: data.map(d => d.parking),
        itemStyle: { color: '#f59e0b' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(245, 158, 11, 0.3)' },
          { offset: 1, color: 'rgba(245, 158, 11, 0)' }
        ])}
      },
      {
        name: '火灾', type: 'line', smooth: true,
        data: data.map(d => d.fire),
        itemStyle: { color: '#f97316' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(249, 115, 22, 0.3)' },
          { offset: 1, color: 'rgba(249, 115, 22, 0)' }
        ])}
      }
    ]
  }
  trendChart.setOption(option)
}

function updateTypeChart(data: any[]) {
  if (!typeChart) return
  const option: any = {
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(17, 24, 39, 0.9)',
      borderColor: '#3b82f6',
      textStyle: { color: '#e5e7eb' }
    },
    series: [{
      type: 'pie',
      radius: ['45%', '70%'],
      avoidLabelOverlap: false,
      itemStyle: {
        borderRadius: 4,
        borderColor: '#111827',
        borderWidth: 2
      },
      label: {
        show: true,
        position: 'outside',
        color: '#e5e7eb',
        fontSize: 12,
        formatter: '{b}\n{d}%'
      },
      labelLine: { lineStyle: { color: '#374151' } },
      data: data.map((d: any) => ({ value: d.value, name: d.name, itemStyle: { color: d.color } }))
    }]
  }
  typeChart.setOption(option)
}

function updateRankChart(data: any[]) {
  if (!rankChart) return
  const names = data.map((d: any) => d.name).reverse()
  const values = data.map((d: any) => d.total).reverse()
  
  const option: any = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: 'rgba(17, 24, 39, 0.9)',
      borderColor: '#3b82f6',
      textStyle: { color: '#e5e7eb' }
    },
    grid: {
      left: 100,
      right: 20,
      top: 10,
      bottom: 10,
      containLabel: false
    },
    xAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'category',
      data: names,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#9ca3af', fontSize: 12 }
    },
    series: [{
      type: 'bar',
      data: values,
      barWidth: 16,
      itemStyle: {
        borderRadius: [0, 4, 4, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#1677ff' },
          { offset: 1, color: '#3b82f6' }
        ])
      },
      label: {
        show: true,
        position: 'right',
        color: '#e5e7eb',
        fontSize: 12
      }
    }]
  }
  rankChart.setOption(option)
}

async function loadChartsData() {
  try {
    const [trendRes, typeRes, rankRes] = await Promise.all([
      dashboardApi.getAlertTrend(),
      dashboardApi.getAlertTypes(),
      dashboardApi.getCameraRank()
    ])
    updateTrendChart(trendRes as any[])
    updateTypeChart(typeRes as any[])
    updateRankChart(rankRes as any[])
  } catch (e) {}
}

async function refreshData() {
  loading.value = true
  await Promise.all([
    fetchOverview(),
    fetchRecentAlerts(),
    loadChartsData()
  ])
  loading.value = false
  ElMessage.success('数据已刷新')
}

function handleResize() {
  trendChart?.resize()
  typeChart?.resize()
  rankChart?.resize()
}

onMounted(async () => {
  updateTime()
  timeTimer = setInterval(updateTime, 1000)

  await nextTick()
  initCharts()
  await fetchOverview()
  await fetchCameras()
  await fetchRecentAlerts()
  await loadChartsData()

  // 定时刷新数据
  dataTimer = setInterval(async () => {
    await fetchOverview()
    await fetchRecentAlerts()
  }, 5000)

  // 定时更新检测框
  detectionTimer = setInterval(() => {
    displayCameras.value.forEach(cam => {
      if (cam.status === 'online') {
        generateMockDetections(cam.id)
      }
    })
  }, 3000)

  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  clearInterval(timeTimer)
  clearInterval(dataTimer)
  clearInterval(detectionTimer)
  trendChart?.dispose()
  typeChart?.dispose()
  rankChart?.dispose()
  window.removeEventListener('resize', handleResize)
  appStore.setTheme('light')
})
</script>

<style scoped>
.dashboard-page {
  margin: -20px;
  padding: 20px;
  min-height: calc(100vh - 40px);
  background: linear-gradient(135deg, #0a0e17 0%, #0f172a 100%);
  color: #e5e7eb;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(59, 130, 246, 0.2);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 24px;
}

.main-title {
  font-size: 24px;
  font-weight: 600;
  margin: 0;
  background: linear-gradient(135deg, #60a5fa, #a78bfa);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  display: flex;
  align-items: center;
  gap: 12px;
}

.title-icon {
  color: #3b82f6;
  -webkit-text-fill-color: #3b82f6;
}

.time-display {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #9ca3af;
  font-size: 14px;
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.system-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #52c41a;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #52c41a;
  animation: pulse 2s ease-in-out infinite;
}

.status-dot.online {
  background: #52c41a;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  background: linear-gradient(135deg, rgba(17, 24, 39, 0.9), rgba(31, 41, 55, 0.8));
  border: 1px solid rgba(59, 130, 246, 0.2);
  border-radius: 8px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  transition: transform 0.3s, box-shadow 0.3s;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(59, 130, 246, 0.2);
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  flex-shrink: 0;
}

.stat-icon.camera {
  background: linear-gradient(135deg, rgba(22, 119, 255, 0.2), rgba(59, 130, 246, 0.1));
  color: #3b82f6;
}

.stat-icon.alert {
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(220, 38, 38, 0.1));
  color: #ef4444;
}

.stat-icon.detection {
  background: linear-gradient(135deg, rgba(82, 196, 26, 0.2), rgba(34, 197, 94, 0.1));
  color: #52c41a;
}

.stat-icon.system {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(139, 92, 246, 0.1));
  color: #a855f7;
}

.stat-info {
  flex: 1;
  min-width: 0;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #fff;
  font-family: 'JetBrains Mono', Consolas, monospace;
  line-height: 1.2;
}

.stat-label {
  font-size: 13px;
  color: #9ca3af;
  margin: 4px 0;
}

.stat-rate {
  font-size: 12px;
  color: #6b7280;
}

.stat-rate.text-danger {
  color: #f87171;
}

.dashboard-main {
  display: grid;
  grid-template-columns: 1fr 1.5fr 1fr;
  gap: 16px;
  height: calc(100vh - 260px);
  min-height: 500px;
}

.panel {
  background: linear-gradient(135deg, rgba(17, 24, 39, 0.9), rgba(31, 41, 55, 0.8));
  border: 1px solid rgba(59, 130, 246, 0.2);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  padding: 12px 16px;
  border-bottom: 1px solid rgba(59, 130, 246, 0.15);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #e5e7eb;
  position: relative;
  padding-left: 10px;
}

.panel-title::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 14px;
  background: linear-gradient(180deg, #3b82f6, #60a5fa);
  border-radius: 2px;
}

.panel-tools {
  display: flex;
  align-items: center;
  gap: 8px;
}

.live-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #ef4444;
  font-weight: 600;
  padding: 2px 8px;
  background: rgba(239, 68, 68, 0.1);
  border-radius: 4px;
}

.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #ef4444;
  animation: blink 1.5s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.refresh-hint {
  font-size: 11px;
  color: #6b7280;
}

.panel-body {
  flex: 1;
  padding: 12px;
  overflow: hidden;
}

.chart-container {
  width: 100%;
  height: 100%;
  min-height: 180px;
}

.chart-container.small {
  min-height: 160px;
}

.dashboard-left,
.dashboard-right {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.dashboard-left .panel {
  flex: 1;
}

.dashboard-right .panel {
  flex: 1;
  min-height: 0;
}

.dashboard-center {
  display: flex;
  flex-direction: column;
}

.monitor-panel {
  height: 100%;
}

.monitor-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  grid-template-rows: repeat(2, 1fr);
  gap: 8px;
  height: 100%;
}

.monitor-item {
  position: relative;
  background: #000;
  border-radius: 4px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.video-placeholder {
  flex: 1;
  position: relative;
  background: #0f172a;
  overflow: hidden;
}

.mock-video-bg {
  position: absolute;
  inset: 0;
  background: 
    radial-gradient(ellipse at 30% 40%, rgba(59, 130, 246, 0.15) 0%, transparent 50%),
    radial-gradient(ellipse at 70% 60%, rgba(82, 196, 26, 0.1) 0%, transparent 40%),
    linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
}

.mock-scanline {
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0, 0, 0, 0.3) 2px,
    rgba(0, 0, 0, 0.3) 4px
  );
  pointer-events: none;
}

.offline-icon {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 48px;
  color: #374151;
}

.detection-box {
  position: absolute;
  border: 2px solid #52c41a;
  border-radius: 2px;
  transition: all 0.5s ease;
}

.detection-box.person { border-color: #52c41a; }
.detection-box.car { border-color: #3b82f6; }
.detection-box.truck { border-color: #8b5cf6; }
.detection-box.fire { border-color: #ef4444; }
.detection-box.smoke { border-color: #f59e0b; }

.detection-label {
  position: absolute;
  top: -20px;
  left: -2px;
  background: inherit;
  background-color: #52c41a;
  color: #fff;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 2px 2px 0 0;
  white-space: nowrap;
}

.detection-box.person .detection-label { background-color: #52c41a; }
.detection-box.car .detection-label { background-color: #3b82f6; }
.detection-box.truck .detection-label { background-color: #8b5cf6; }
.detection-box.fire .detection-label { background-color: #ef4444; }
.detection-box.smoke .detection-label { background-color: #f59e0b; }

.monitor-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  background: rgba(0, 0, 0, 0.7);
  font-size: 12px;
}

.cam-name {
  color: #e5e7eb;
  font-weight: 500;
}

.cam-status {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
}

.cam-status.online {
  color: #52c41a;
}

.cam-status.offline {
  color: #6b7280;
}

.cam-status .status-dot {
  width: 6px;
  height: 6px;
  animation: none;
}

.cam-status.online .status-dot {
  background: #52c41a;
  animation: pulse 2s ease-in-out infinite;
}

.cam-status.offline .status-dot {
  background: #6b7280;
}

.alert-list {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.alert-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 6px;
  border-left: 3px solid #3b82f6;
  transition: background 0.2s;
}

.alert-item:hover {
  background: rgba(59, 130, 246, 0.1);
}

.alert-item.high { border-left-color: #ef4444; }
.alert-item.medium { border-left-color: #f59e0b; }
.alert-item.low { border-left-color: #3b82f6; }

.alert-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.alert-item.high .alert-icon { color: #ef4444; }
.alert-item.medium .alert-icon { color: #f59e0b; }
.alert-item.low .alert-icon { color: #3b82f6; }

.alert-content {
  flex: 1;
  min-width: 0;
}

.alert-title {
  font-size: 13px;
  color: #e5e7eb;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.alert-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: #6b7280;
}

.alert-level-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  flex-shrink: 0;
}

.alert-level-tag.high {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
}

.alert-level-tag.medium {
  background: rgba(245, 158, 11, 0.2);
  color: #fbbf24;
}

.alert-level-tag.low {
  background: rgba(59, 130, 246, 0.2);
  color: #60a5fa;
}

.empty-text {
  text-align: center;
  color: #6b7280;
  font-size: 13px;
  padding: 20px 0;
}

.resource-item {
  margin-bottom: 14px;
}

.resource-item:last-child {
  margin-bottom: 0;
}

.resource-label {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 6px;
}
</style>
