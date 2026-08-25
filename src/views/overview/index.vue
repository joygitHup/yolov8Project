<template>
  <div class="overview-page">
    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6">
        <el-card class="stat-card total-card" shadow="hover">
          <div class="stat-icon-wrapper">
            <el-icon :size="28"><VideoCamera /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-num">{{ stats.cameras?.total || 0 }}</div>
            <div class="stat-label">接入摄像头</div>
          </div>
          <div class="stat-foot">
            <el-tag :type="stats.cameras?.online ? 'success' : 'danger'" size="small">
              在线 {{ stats.cameras?.online || 0 }}
            </el-tag>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card today-card" shadow="hover">
          <div class="stat-icon-wrapper">
            <el-icon :size="28"><Bell /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-num">{{ stats.alerts?.today || 0 }}</div>
            <div class="stat-label">今日告警</div>
          </div>
          <div class="stat-foot">
            <el-tag type="danger" size="small">待处理 {{ stats.alerts?.unhandled || 0 }}</el-tag>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card week-card" shadow="hover">
          <div class="stat-icon-wrapper">
            <el-icon :size="28"><DataLine /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-num">{{ stats.week || 0 }}</div>
            <div class="stat-label">本周告警</div>
          </div>
          <div class="stat-foot">
            <span class="trend-text">较上周 +12%</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card rate-card" shadow="hover">
          <div class="stat-icon-wrapper">
            <el-icon :size="28"><CircleCheck /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-num">{{ resolvedRate }}%</div>
            <div class="stat-label">处置率</div>
          </div>
          <div class="stat-foot">
            <el-tag type="success" size="small">已处置 {{ stats.statusCounts?.resolved || 0 }}</el-tag>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区 -->
    <el-row :gutter="16" class="chart-row">
      <el-col :span="16">
        <el-card class="chart-card">
          <template #header>
            <div class="card-header">
              <span>告警趋势分析</span>
              <el-radio-group v-model="trendPeriod" size="small" @change="loadTrendData">
                <el-radio-button value="day">今日</el-radio-button>
                <el-radio-button value="week">近7天</el-radio-button>
                <el-radio-button value="month">近30天</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <div ref="trendChartRef" class="chart-box"></div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="chart-card">
          <template #header>
            <span>告警类型分布</span>
          </template>
          <div ref="typeChartRef" class="chart-box"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 第二行 -->
    <el-row :gutter="16" class="chart-row">
      <el-col :span="12">
        <el-card class="chart-card">
          <template #header>
            <span>告警级别分布</span>
          </template>
          <div ref="levelChartRef" class="chart-box"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="chart-card">
          <template #header>
            <span>最近告警</span>
            <el-button type="primary" link size="small" @click="$router.push('/alerts')">
              查看全部
            </el-button>
          </template>
          <el-table :data="recentAlerts" style="width: 100%" size="small" empty-text="暂无告警">
            <el-table-column prop="cameraName" label="摄像头" width="120" />
            <el-table-column prop="description" label="告警描述" min-width="150" show-overflow-tooltip />
            <el-table-column label="级别" width="80">
              <template #default="{ row }">
                <el-tag :type="levelTagType(row.level)" size="small">
                  {{ levelText(row.level) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small" effect="plain">
                  {{ statusText(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="时间" width="150">
              <template #default="{ row }">
                {{ formatTime(row.triggeredAt) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 摄像头告警分布 -->
    <el-row :gutter="16" class="chart-row">
      <el-col :span="24">
        <el-card class="chart-card">
          <template #header>
            <span>摄像头告警排行</span>
          </template>
          <div ref="rankChartRef" class="chart-box horizontal"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { alertApi, dashboardApi, configApi } from '@/api'
import dayjs from 'dayjs'

const trendPeriod = ref('day')
const stats = reactive<any>({})
const recentAlerts = ref<any[]>([])
const resolvedRate = computed(() => {
  const total = stats.total || 1
  const resolved = stats.statusCounts?.resolved || 0
  return ((resolved / total) * 100).toFixed(1)
})

const trendChartRef = ref<HTMLElement>()
const typeChartRef = ref<HTMLElement>()
const levelChartRef = ref<HTMLElement>()
const rankChartRef = ref<HTMLElement>()

let trendChart: echarts.ECharts | null = null
let typeChart: echarts.ECharts | null = null
let levelChart: echarts.ECharts | null = null
let rankChart: echarts.ECharts | null = null

function levelText(level: string) {
  const map: Record<string, string> = { high: '高危', medium: '中危', low: '低危' }
  return map[level] || level
}

function levelTagType(level: string) {
  const map: Record<string, string> = { high: 'danger', medium: 'warning', low: 'info' }
  return map[level] || 'info'
}

function statusText(status: string) {
  const map: Record<string, string> = { unhandled: '待处理', processing: '处理中', resolved: '已处理' }
  return map[status] || status
}

function statusTagType(status: string) {
  const map: Record<string, string> = { unhandled: 'danger', processing: 'warning', resolved: 'success' }
  return map[status] || 'info'
}

function formatTime(time: string) {
  return dayjs(time).format('MM-DD HH:mm:ss')
}

async function loadStats() {
  try {
    const res: any = await alertApi.getStats()
    Object.assign(stats, res)
  } catch (e) {}
}

async function loadRecentAlerts() {
  try {
    const res: any = await alertApi.getList({ page: 1, pageSize: 8 })
    recentAlerts.value = res.list || []
  } catch (e) {}
}

function initCharts() {
  if (trendChartRef.value) {
    trendChart = echarts.init(trendChartRef.value)
  }
  if (typeChartRef.value) {
    typeChart = echarts.init(typeChartRef.value)
  }
  if (levelChartRef.value) {
    levelChart = echarts.init(levelChartRef.value)
  }
  if (rankChartRef.value) {
    rankChart = echarts.init(rankChartRef.value)
  }
}

function updateTrendChart(data: any[]) {
  if (!trendChart) return
  const option: any = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['区域入侵', '违停占道', '火灾隐患'] },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: {
      type: 'category',
      data: data.map(d => d.hour || d.date),
      boundaryGap: false
    },
    yAxis: { type: 'value' },
    series: [
      {
        name: '区域入侵', type: 'line', smooth: true,
        data: data.map(d => d.intrusion),
        itemStyle: { color: '#f5222d' },
        areaStyle: { opacity: 0.1 }
      },
      {
        name: '违停占道', type: 'line', smooth: true,
        data: data.map(d => d.parking),
        itemStyle: { color: '#faad14' },
        areaStyle: { opacity: 0.1 }
      },
      {
        name: '火灾隐患', type: 'line', smooth: true,
        data: data.map(d => d.fire),
        itemStyle: { color: '#fa541c' },
        areaStyle: { opacity: 0.1 }
      }
    ]
  }
  trendChart.setOption(option)
}

function updateTypeChart(data: any[]) {
  if (!typeChart) return
  const option: any = {
    tooltip: { trigger: 'item' },
    legend: { orient: 'vertical', right: 10, top: 'center' },
    series: [{
      type: 'pie',
      radius: ['50%', '75%'],
      center: ['35%', '50%'],
      itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      data: data.map((d: any) => ({ value: d.value, name: d.name, itemStyle: { color: d.color } }))
    }]
  }
  typeChart.setOption(option)
}

function updateLevelChart(data: any[]) {
  if (!levelChart) return
  const option: any = {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie',
      radius: '60%',
      itemStyle: { borderRadius: 6 },
      label: {
        formatter: '{b}\n{d}%',
        fontSize: 12
      },
      data: data.map((d: any) => ({ value: d.value, name: d.name, itemStyle: { color: d.color } }))
    }]
  }
  levelChart.setOption(option)
}

function updateRankChart(data: any[]) {
  if (!rankChart) return
  const names = data.map((d: any) => d.name).reverse()
  const values = data.map((d: any) => d.total).reverse()
  const highValues = data.map((d: any) => d.high).reverse()

  const option: any = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['总告警', '高危告警'], right: 20 },
    grid: { left: 120, right: 40, top: 40, bottom: 20 },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: names },
    series: [
      {
        name: '总告警', type: 'bar',
        data: values,
        barWidth: 14,
        itemStyle: { color: '#1677ff', borderRadius: [0, 4, 4, 0] }
      },
      {
        name: '高危告警', type: 'bar',
        data: highValues,
        barWidth: 14,
        itemStyle: { color: '#f5222d', borderRadius: [0, 4, 4, 0] }
      }
    ]
  }
  rankChart.setOption(option)
}

async function loadTrendData() {
  try {
    const res: any = await dashboardApi.getAlertTrend()
    updateTrendChart(res)
  } catch (e) {}
}

async function loadTypeData() {
  try {
    const res: any = await dashboardApi.getAlertTypes()
    updateTypeChart(res)
  } catch (e) {}
}

async function loadLevelData() {
  try {
    const res: any = await dashboardApi.getAlertLevels()
    updateLevelChart(res)
  } catch (e) {}
}

async function loadRankData() {
  try {
    const res: any = await dashboardApi.getCameraRank()
    updateRankChart(res)
  } catch (e) {}
}

function handleResize() {
  trendChart?.resize()
  typeChart?.resize()
  levelChart?.resize()
  rankChart?.resize()
}

onMounted(async () => {
  await nextTick()
  initCharts()
  await Promise.all([
    loadStats(),
    loadRecentAlerts(),
    loadTrendData(),
    loadTypeData(),
    loadLevelData(),
    loadRankData()
  ])
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  trendChart?.dispose()
  typeChart?.dispose()
  levelChart?.dispose()
  rankChart?.dispose()
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.overview-page {
  padding: 4px;
}

.stat-row {
  margin-bottom: 16px;
}

.stat-card {
  display: flex;
  align-items: center;
  padding: 8px 0;
}

.stat-icon-wrapper {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 16px;
  flex-shrink: 0;
}

.total-card .stat-icon-wrapper {
  background: rgba(22, 119, 255, 0.1);
  color: #1677ff;
}

.today-card .stat-icon-wrapper {
  background: rgba(245, 34, 45, 0.1);
  color: #f5222d;
}

.week-card .stat-icon-wrapper {
  background: rgba(250, 173, 20, 0.1);
  color: #faad14;
}

.rate-card .stat-icon-wrapper {
  background: rgba(82, 196, 26, 0.1);
  color: #52c41a;
}

.stat-content {
  flex: 1;
}

.stat-num {
  font-size: 28px;
  font-weight: 700;
  color: #1f2937;
  line-height: 1.2;
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.stat-label {
  font-size: 13px;
  color: #6b7280;
  margin-top: 4px;
}

.stat-foot {
  margin-left: 12px;
}

.trend-text {
  font-size: 12px;
  color: #f5222d;
}

.chart-row {
  margin-bottom: 16px;
}

.chart-row:last-child {
  margin-bottom: 0;
}

.chart-card :deep(.el-card__header) {
  font-weight: 600;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.chart-box {
  width: 100%;
  height: 300px;
}

.chart-box.horizontal {
  height: 340px;
}
</style>
