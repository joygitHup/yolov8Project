<template>
  <div class="config-page">
    <el-row :gutter="20">
      <!-- 左侧导航 -->
      <el-col :span="4">
        <el-card class="nav-card">
          <el-menu
            :default-active="activeMenu"
            router
            class="config-menu"
          >
            <el-menu-item index="/config">
              <el-icon><Setting /></el-icon>
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
            <el-menu-item v-if="userStore.isAdmin" index="/config/users">
              <el-icon><User /></el-icon>
              <span>用户管理</span>
            </el-menu-item>
          </el-menu>
        </el-card>
      </el-col>

      <!-- 右侧内容 -->
      <el-col :span="20">
        <el-card v-loading="loading" class="content-card">
          <template #header>
            <div class="card-header">
              <span class="card-title">系统设置</span>
              <el-button type="primary" :loading="saveLoading" @click="handleSave">
                保存设置
              </el-button>
            </div>
          </template>

          <el-descriptions title="系统信息" :column="2" border style="margin-bottom: 24px">
            <el-descriptions-item label="系统名称">{{ settings.system?.title || '-' }}</el-descriptions-item>
            <el-descriptions-item label="版本号">{{ systemInfo.system?.version || settings.system?.version || '-' }}</el-descriptions-item>
            <el-descriptions-item label="运行环境">{{ systemInfo.system?.environment || '-' }}</el-descriptions-item>
            <el-descriptions-item label="运行时长">{{ systemInfo.system?.uptime || '-' }}</el-descriptions-item>
            <el-descriptions-item label="CPU">{{ systemInfo.system?.cpu || '-' }}%</el-descriptions-item>
            <el-descriptions-item label="内存">{{ systemInfo.system?.memory || '-' }}%</el-descriptions-item>
          </el-descriptions>

          <el-divider />

          <h4 class="section-title">资源状态</h4>
          <el-row :gutter="24" style="margin-bottom: 24px">
            <el-col :span="6">
              <div class="resource-card">
                <div class="resource-label">摄像头</div>
                <div class="resource-value">
                  {{ systemInfo.stats?.cameras?.online || 0 }} / {{ systemInfo.stats?.cameras?.total || 0 }}
                </div>
                <div class="resource-sub">在线 / 总数</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="resource-card">
                <div class="resource-label">今日告警</div>
                <div class="resource-value">{{ systemInfo.stats?.alerts?.today || 0 }}</div>
                <div class="resource-sub">待处理 {{ systemInfo.stats?.alerts?.unhandled || 0 }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="resource-card">
                <div class="resource-label">用户数</div>
                <div class="resource-value">{{ systemInfo.stats?.users?.total || 0 }}</div>
                <div class="resource-sub">活跃 {{ systemInfo.stats?.users?.active || 0 }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="resource-card">
                <div class="resource-label">检测 FPS</div>
                <div class="resource-value">{{ settings.detection?.fps || 0 }}</div>
                <div class="resource-sub">置信度 {{ (settings.detection?.confidenceThreshold || 0) * 100 }}%</div>
              </div>
            </el-col>
          </el-row>

          <el-divider />

          <h4 class="section-title">基础设置</h4>
          <el-form :model="settingsForm" label-width="120px" style="max-width: 500px">
            <el-form-item label="系统标题">
              <el-input v-model="settingsForm.systemTitle" placeholder="请输入系统标题" />
            </el-form-item>
            <el-form-item label="告警去重">
              <el-switch v-model="settingsForm.dedupEnabled" />
              <span class="form-tip">开启后同一告警在间隔时间内不会重复推送</span>
            </el-form-item>
            <el-form-item v-if="settingsForm.dedupEnabled" label="去重间隔">
              <el-input-number v-model="settingsForm.dedupInterval" :min="5" :max="300" />
              <span class="form-tip">秒</span>
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
import { Setting, Aim, Lock, Message, User } from '@element-plus/icons-vue'

const route = useRoute()
const userStore = useUserStore()
const appStore = useAppStore()
const loading = ref(false)
const saveLoading = ref(false)
const settings = reactive<any>({})
const systemInfo = reactive<any>({})

const settingsForm = reactive({
  systemTitle: 'YOLOv8 视频智能分析系统',
  dedupEnabled: true,
  dedupInterval: 30
})

const activeMenu = ref('/config')

async function loadData() {
  loading.value = true
  try {
    const [settingsRes, infoRes] = await Promise.all([
      configApi.getSettings(),
      configApi.getSystemInfo()
    ])
    Object.assign(settings, settingsRes)
    Object.assign(systemInfo, infoRes)

    if (settings.system) {
      settingsForm.systemTitle = settings.system.title
    }
    if (settings.alertDeduplication) {
      settingsForm.dedupEnabled = settings.alertDeduplication.enabled
      settingsForm.dedupInterval = settings.alertDeduplication.interval
    }
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saveLoading.value = true
  try {
    const res: any = await configApi.updateSettings({
      system: { title: settingsForm.systemTitle },
      alertDeduplication: {
        enabled: settingsForm.dedupEnabled,
        interval: settingsForm.dedupInterval
      }
    })
    appStore.applySystemTitle(settingsForm.systemTitle, res?.settings?.system?.version)
    ElMessage.success('设置已保存并立即生效')
    loadData()
  } catch (e) {
    // 错误已处理
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

.card-title {
  font-weight: 600;
  font-size: 16px;
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
