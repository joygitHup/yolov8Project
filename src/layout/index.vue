<template>
  <div class="layout-container" :class="{ 'sidebar-collapsed': appStore.sidebarCollapsed }">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="logo">
        <el-icon class="logo-icon"><VideoCamera /></el-icon>
        <span v-if="!appStore.sidebarCollapsed" class="logo-text">{{ appStore.systemTitle }}</span>
      </div>
      <el-menu
        :key="activeMenu"
        :default-active="activeMenu"
        :collapse="appStore.sidebarCollapsed"
        :collapse-transition="false"
        router
        class="sidebar-menu"
        background-color="#001529"
        text-color="#a6adb4"
        active-text-color="#ffffff"
      >
        <template v-for="item in menuItems" :key="item.path">
          <el-menu-item v-if="!item.hidden" :index="item.path">
            <el-icon><component :is="item.icon" /></el-icon>
            <template #title>
              <span>{{ item.title }}</span>
            </template>
          </el-menu-item>
        </template>
      </el-menu>
    </aside>

    <!-- 主内容区 -->
    <div class="main-wrapper">
      <!-- 顶部导航 -->
      <header class="header">
        <div class="header-left">
          <el-icon class="collapse-btn" @click="appStore.toggleSidebar()">
            <Fold v-if="!appStore.sidebarCollapsed" />
            <Expand v-else />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item v-for="item in breadcrumbs" :key="item.path">
              {{ item.title }}
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-tooltip content="数据大屏">
            <el-icon class="header-icon" @click="goDashboard">
              <DataBoard />
            </el-icon>
          </el-tooltip>
          <el-tooltip content="告警通知">
            <el-badge :value="unhandledCount" :hidden="unhandledCount === 0" class="header-badge">
              <el-icon class="header-icon" @click="goAlerts">
                <Bell />
              </el-icon>
            </el-badge>
          </el-tooltip>
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <el-avatar :size="32" class="user-avatar">
                {{ userStore.userInfo?.name?.charAt(0) || 'U' }}
              </el-avatar>
              <span class="user-name">{{ userStore.userInfo?.name || '用户' }}</span>
              <el-icon><CaretBottom /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  <el-icon><User /></el-icon>个人中心
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <!-- 内容区 -->
      <main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useAppStore } from '@/stores/app'
import { alertApi } from '@/api'
import { connectRealtime, disconnectRealtime, onRealtime } from '@/utils/realtime'
import { ElMessageBox, ElMessage, ElNotification } from 'element-plus'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const appStore = useAppStore()

const unhandledCount = ref(0)
const realtimeOffs: Array<() => void> = []

// 菜单项
const menuItems = computed(() => {
  const items = [
    { path: '/dashboard', title: '数据大屏', icon: 'DataBoard', hidden: false },
    { path: '/overview', title: '总览分析', icon: 'DataAnalysis', hidden: false },
    { path: '/monitor', title: '实时监控', icon: 'VideoCamera', hidden: false },
    { path: '/cameras', title: '摄像头管理', icon: 'Camera', hidden: false },
    { path: '/alerts', title: '报警中心', icon: 'Bell', hidden: false },
    { path: '/flywheel', title: '标注台', icon: 'EditPen', hidden: false },
    { path: '/config', title: '系统配置', icon: 'Tools', hidden: false }
  ]

  // 根据角色过滤
  if (userStore.isViewer) {
    return items.filter(i => !['/config', '/flywheel'].includes(i.path))
  }
  return items
})

const activeMenu = computed(() => {
  if (route.path.startsWith('/flywheel')) return '/flywheel'
  if (route.path.startsWith('/config')) return '/config'
  if (route.path.startsWith('/alerts')) return '/alerts'
  return route.path
})

const breadcrumbs = computed(() => {
  const matched = route.matched.filter(m => m.meta && m.meta.title && !m.meta.hidden)
  return matched.map(m => ({
    path: m.path,
    title: m.meta.title as string
  }))
})

function goDashboard() {
  router.push('/dashboard')
}

function goAlerts() {
  router.push('/alerts')
}

function handleCommand(command: string) {
  if (command === 'profile') {
    router.push('/profile')
  } else if (command === 'logout') {
    ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(() => {
      disconnectRealtime()
      userStore.logout()
      ElMessage.success('已退出登录')
      router.push('/login')
    }).catch(() => {})
  }
}

async function fetchUnhandledCount() {
  try {
    const res: any = await alertApi.getList({ page: 1, pageSize: 1, status: 'unhandled' })
    unhandledCount.value = res.total || 0
  } catch (e) {
    // 忽略错误
  }
}

onMounted(() => {
  fetchUnhandledCount()
  appStore.loadSettings()
  connectRealtime()
  realtimeOffs.push(
    onRealtime('alert:created', (alert) => {
      unhandledCount.value += 1
      ElNotification({
        title: alert?.level === 'high' ? '高危告警' : '新告警',
        message: `${alert?.cameraName || ''} ${alert?.description || ''}`,
        type: alert?.level === 'high' ? 'error' : 'warning',
        duration: 4500
      })
    }),
    onRealtime('alert:updated', () => {
      fetchUnhandledCount()
    }),
    onRealtime('config:updated', (payload) => {
      appStore.applySystemTitle(payload?.settings?.system?.title, payload?.settings?.system?.version)
    })
  )
})

onUnmounted(() => {
  realtimeOffs.forEach((fn) => fn())
  disconnectRealtime()
})
</script>

<style scoped>
.layout-container {
  display: flex;
  height: 100vh;
  background: #f0f2f5;
}

.sidebar {
  width: 220px;
  background: #001529;
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
  flex-shrink: 0;
}

.sidebar-collapsed .sidebar {
  width: 64px;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #fff;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding: 0 16px;
  white-space: nowrap;
  overflow: hidden;
}

.logo-icon {
  font-size: 24px;
  color: #1677ff;
  flex-shrink: 0;
}

.logo-text {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-menu {
  border-right: none;
  flex: 1;
}

.sidebar-menu :deep(.el-menu-item) {
  height: 50px;
  line-height: 50px;
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background: #1677ff !important;
}

.main-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.header {
  height: 60px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.collapse-btn {
  font-size: 20px;
  cursor: pointer;
  color: #4b5563;
  transition: color 0.2s;
}

.collapse-btn:hover {
  color: #1677ff;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.header-icon {
  font-size: 20px;
  color: #4b5563;
  cursor: pointer;
  transition: color 0.2s;
}

.header-icon:hover {
  color: #1677ff;
}

.header-badge {
  cursor: pointer;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #4b5563;
}

.user-info:hover {
  color: #1677ff;
}

.user-avatar {
  background: linear-gradient(135deg, #1677ff, #0958d9);
  color: #fff;
  font-weight: 600;
}

.user-name {
  font-size: 14px;
}

.main-content {
  flex: 1;
  overflow: auto;
  padding: 20px;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
