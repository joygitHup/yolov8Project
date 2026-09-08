<template>
  <div class="config-page">
    <el-row :gutter="20">
      <el-col :span="4">
        <el-card class="nav-card">
          <el-menu :default-active="activeMenu" router class="config-menu">
            <el-menu-item index="/config">
              <el-icon><Tools /></el-icon>
              <span>系统设置</span>
            </el-menu-item>
            <el-menu-item index="/config/detection">
              <el-icon><Aim /></el-icon>
              <span>检测参数</span>
            </el-menu-item>
            <el-menu-item index="/config/strategies">
              <el-icon><Lock /></el-icon>
              <span>布防策略</span>
            </el-menu-item>
            <el-menu-item index="/config/notification">
              <el-icon><Message /></el-icon>
              <span>通知配置</span>
            </el-menu-item>
            <el-menu-item index="/flywheel">
              <el-icon><EditPen /></el-icon>
              <span>标注台</span>
            </el-menu-item>
            <el-menu-item v-if="userStore.isAdmin" index="/config/users">
              <el-icon><User /></el-icon>
              <span>用户管理</span>
            </el-menu-item>
          </el-menu>
        </el-card>
      </el-col>

      <el-col :span="20">
        <el-card v-loading="loading" class="content-card">
          <template #header>
            <div class="card-header">
              <div class="card-title-wrap">
                <el-icon class="title-icon"><Tools /></el-icon>
                <span class="card-title">系统设置</span>
              </div>
              <div class="header-actions">
                <el-button :icon="Refresh" @click="loadData">刷新</el-button>
                <el-button
                  type="primary"
                  :loading="saveLoading"
                  :disabled="!userStore.isAdmin"
                  @click="handleSave"
                >
                  保存设置
                </el-button>
              </div>
            </div>
          </template>

          <el-alert
            v-if="!userStore.isAdmin"
            type="info"
            :closable="false"
            show-icon
            title="当前账号为操作员，可查看系统信息；保存设置需要管理员权限"
            style="margin-bottom: 16px"
          />

          <el-descriptions title="系统信息" :column="2" border style="margin-bottom: 24px">
            <el-descriptions-item label="系统名称">{{ systemInfo.system.title || '-' }}</el-descriptions-item>
            <el-descriptions-item label="版本号">{{ systemInfo.system.version || '-' }}</el-descriptions-item>
            <el-descriptions-item label="运行环境">{{ envText(systemInfo.system.environment) }}</el-descriptions-item>
            <el-descriptions-item label="运行时长">{{ systemInfo.system.uptime || '-' }}</el-descriptions-item>
            <el-descriptions-item label="CPU">{{ formatPercent(systemInfo.system.cpuPercent) }}</el-descriptions-item>
            <el-descriptions-item label="内存">{{ formatPercent(systemInfo.system.memoryPercent) }}</el-descriptions-item>
          </el-descriptions>

          <el-divider />

          <h4 class="section-title">资源状态</h4>
          <el-row :gutter="24" style="margin-bottom: 24px">
            <el-col :span="6">
              <div class="resource-card">
                <div class="resource-label">摄像头</div>
                <div class="resource-value">
                  {{ systemInfo.stats.cameras.online }} / {{ systemInfo.stats.cameras.total }}
                </div>
                <div class="resource-sub">在线 / 总数（启用 {{ systemInfo.stats.cameras.enabled }}）</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="resource-card">
                <div class="resource-label">今日告警</div>
                <div class="resource-value">{{ systemInfo.stats.alerts.today }}</div>
                <div class="resource-sub">待处理 {{ systemInfo.stats.alerts.unhandled }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="resource-card">
                <div class="resource-label">用户数</div>
                <div class="resource-value">{{ systemInfo.stats.users.total }}</div>
                <div class="resource-sub">活跃 {{ systemInfo.stats.users.active }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="resource-card">
                <div class="resource-label">检测 FPS</div>
                <div class="resource-value">{{ settings.detection.fps }}</div>
                <div class="resource-sub">
                  置信度 {{ formatConfidence(settings.detection.confidenceThreshold) }}
                </div>
              </div>
            </el-col>
          </el-row>

          <el-divider />

          <h4 class="section-title">基础设置</h4>
          <el-form :model="settingsForm" label-width="120px" style="max-width: 560px">
            <el-form-item label="系统标题" required>
              <el-input
                v-model="settingsForm.title"
                placeholder="请输入系统标题"
                maxlength="64"
                show-word-limit
                :disabled="!userStore.isAdmin"
              />
            </el-form-item>
            <el-form-item label="Logo 地址">
              <el-input
                v-model="settingsForm.logo"
                placeholder="可选，图片 URL"
                :disabled="!userStore.isAdmin"
              />
            </el-form-item>
            <el-form-item label="版本号">
              <el-input v-model="settingsForm.version" disabled />
            </el-form-item>
            <el-form-item label="告警去重">
              <el-switch v-model="settingsForm.dedupEnabled" :disabled="!userStore.isAdmin" />
              <span class="form-tip">开启后同一告警在间隔时间内不会重复推送</span>
            </el-form-item>
            <el-form-item v-if="settingsForm.dedupEnabled" label="去重间隔">
              <el-input-number
                v-model="settingsForm.dedupInterval"
                :min="5"
                :max="300"
                :disabled="!userStore.isAdmin"
              />
              <span class="form-tip">秒（5~300）</span>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { configApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { useAppStore } from '@/stores/app'
import { ElMessage } from 'element-plus'
import { Tools, Aim, Lock, Message, User, Refresh, EditPen } from '@element-plus/icons-vue'

/** Canonical settings sections from GET /config/settings */
interface SystemSettings {
  system: { title: string; logo: string; version: string }
  alertDeduplication: { enabled: boolean; interval: number }
  detection: {
    confidenceThreshold: number
    iouThreshold: number
    fps: number
    maxDetections: number
    categories: string[]
    trackingEnabled: boolean
    trackLostFrames: number
  }
  notification: Record<string, any>
}

interface SystemInfoPayload {
  system: {
    title: string
    logo: string
    version: string
    environment: string
    uptime: string
    cpuPercent: number | null
    memoryPercent: number | null
    gpuPercent: number | null
  }
  stats: {
    cameras: { total: number; online: number; offline: number; enabled: number }
    alerts: { total: number; today: number; unhandled: number }
    users: { total: number; active: number }
    strategies: { total: number; enabled: number }
  }
}

const route = useRoute()
const userStore = useUserStore()
const appStore = useAppStore()
const loading = ref(false)
const saveLoading = ref(false)
const activeMenu = ref('/config')

const settings = reactive<SystemSettings>({
  system: { title: '', logo: '', version: '1.0.0' },
  alertDeduplication: { enabled: true, interval: 30 },
  detection: {
    confidenceThreshold: 0.5,
    iouThreshold: 0.45,
    fps: 2,
    maxDetections: 100,
    categories: [],
    trackingEnabled: true,
    trackLostFrames: 30
  },
  notification: {}
})

const systemInfo = reactive<SystemInfoPayload>({
  system: {
    title: '',
    logo: '',
    version: '1.0.0',
    environment: '',
    uptime: '',
    cpuPercent: null,
    memoryPercent: null,
    gpuPercent: null
  },
  stats: {
    cameras: { total: 0, online: 0, offline: 0, enabled: 0 },
    alerts: { total: 0, today: 0, unhandled: 0 },
    users: { total: 0, active: 0 },
    strategies: { total: 0, enabled: 0 }
  }
})

const settingsForm = reactive({
  title: 'YOLOv8 视频智能分析系统',
  logo: '',
  version: '1.0.0',
  dedupEnabled: true,
  dedupInterval: 30
})

function envText(env?: string) {
  if (env === 'production') return '生产环境'
  if (env === 'development') return '开发环境'
  return env || '-'
}

function formatPercent(value: number | null | undefined) {
  if (value == null || Number.isNaN(Number(value))) return '-'
  return `${Number(value).toFixed(1)}%`
}

function formatConfidence(value?: number) {
  if (value == null || Number.isNaN(Number(value))) return '-'
  const n = Number(value)
  const pct = n <= 1 ? n * 100 : n
  return `${pct.toFixed(0)}%`
}

function applySettings(res: any) {
  const system = res?.system || {}
  const dedup = res?.alertDeduplication || {}
  const detection = res?.detection || {}

  settings.system = {
    title: system.title || '',
    logo: system.logo || '',
    version: system.version || '1.0.0'
  }
  settings.alertDeduplication = {
    enabled: !!dedup.enabled,
    interval: Number(dedup.interval || 30)
  }
  settings.detection = {
    confidenceThreshold: Number(detection.confidenceThreshold ?? 0.5),
    iouThreshold: Number(detection.iouThreshold ?? 0.45),
    fps: Number(detection.fps ?? 2),
    maxDetections: Number(detection.maxDetections ?? 100),
    categories: Array.isArray(detection.categories) ? detection.categories : [],
    trackingEnabled: detection.trackingEnabled !== false,
    trackLostFrames: Number(detection.trackLostFrames ?? 30)
  }
  settings.notification = res?.notification || {}

  settingsForm.title = settings.system.title
  settingsForm.logo = settings.system.logo
  settingsForm.version = settings.system.version
  settingsForm.dedupEnabled = settings.alertDeduplication.enabled
  settingsForm.dedupInterval = settings.alertDeduplication.interval
}

function applySystemInfo(res: any) {
  const sys = res?.system || {}
  const stats = res?.stats || {}
  systemInfo.system = {
    title: sys.title || sys.name || '',
    logo: sys.logo || '',
    version: sys.version || '1.0.0',
    environment: sys.environment || '',
    uptime: sys.uptime || '',
    cpuPercent: sys.cpuPercent ?? sys.cpu ?? null,
    memoryPercent: sys.memoryPercent ?? sys.memory ?? null,
    gpuPercent: sys.gpuPercent ?? sys.gpu ?? null
  }
  systemInfo.stats = {
    cameras: {
      total: Number(stats.cameras?.total || 0),
      online: Number(stats.cameras?.online || 0),
      offline: Number(stats.cameras?.offline || 0),
      enabled: Number(stats.cameras?.enabled || 0)
    },
    alerts: {
      total: Number(stats.alerts?.total || 0),
      today: Number(stats.alerts?.today || 0),
      unhandled: Number(stats.alerts?.unhandled || 0)
    },
    users: {
      total: Number(stats.users?.total || 0),
      active: Number(stats.users?.active || 0)
    },
    strategies: {
      total: Number(stats.strategies?.total || 0),
      enabled: Number(stats.strategies?.enabled || 0)
    }
  }
}

async function loadData() {
  loading.value = true
  try {
    const [settingsRes, infoRes] = await Promise.all([
      configApi.getSettings(),
      configApi.getSystemInfo()
    ])
    applySettings(settingsRes)
    applySystemInfo(infoRes)
    appStore.applySystemTitle(settings.system.title, settings.system.version)
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  if (!userStore.isAdmin) {
    ElMessage.warning('仅管理员可保存系统设置')
    return
  }
  const title = settingsForm.title.trim()
  if (!title) {
    ElMessage.warning('系统标题不能为空')
    return
  }
  saveLoading.value = true
  try {
    const res: any = await configApi.updateSettings({
      system: {
        title,
        logo: settingsForm.logo.trim()
      },
      alertDeduplication: {
        enabled: settingsForm.dedupEnabled,
        interval: settingsForm.dedupInterval
      }
    })
    const next = res?.settings || {}
    applySettings(next)
    appStore.applySystemTitle(next?.system?.title || title, next?.system?.version)
    ElMessage.success(res?.message || '设置已保存并立即生效')
    await loadData()
  } catch {
    /* interceptor */
  } finally {
    saveLoading.value = false
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

.card-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.title-icon {
  font-size: 18px;
  color: #1677ff;
}

.card-title {
  font-weight: 600;
  font-size: 16px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 16px;
}

.resource-card {
  background: #f9fafb;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}

.resource-label {
  font-size: 13px;
  color: #6b7280;
  margin-bottom: 8px;
}

.resource-value {
  font-size: 24px;
  font-weight: 700;
  color: #1f2937;
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.resource-sub {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 4px;
}

.form-tip {
  margin-left: 12px;
  font-size: 12px;
  color: #9ca3af;
}
</style>
