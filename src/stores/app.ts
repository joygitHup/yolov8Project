// 应用状态管理
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { configApi } from '@/api'

const DEFAULT_TITLE = 'YOLOv8 视频智能分析系统'

export const useAppStore = defineStore('app', () => {
  const sidebarCollapsed = ref(false)
  const theme = ref<'light' | 'dark'>('light')
  const currentPath = ref('/dashboard')
  const systemTitle = ref(DEFAULT_TITLE)
  const systemVersion = ref('1.0.0')

  const isDarkTheme = computed(() => theme.value === 'dark')

  function applySystemTitle(title?: string, version?: string) {
    if (title) {
      systemTitle.value = title
      const current = document.title
      const idx = current.lastIndexOf(' - ')
      document.title = idx > 0 ? `${current.slice(0, idx)} - ${title}` : title
    }
    if (version) systemVersion.value = version
  }

  async function loadPublicSettings() {
    try {
      const res: any = await configApi.getPublic()
      applySystemTitle(res?.title, res?.version)
      return res
    } catch {
      return null
    }
  }

  async function loadSettings() {
    try {
      const res: any = await configApi.getSettings()
      applySystemTitle(res?.system?.title, res?.system?.version)
      return res
    } catch {
      return loadPublicSettings()
    }
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function setTheme(t: 'light' | 'dark') {
    theme.value = t
    if (t === 'dark') {
      document.documentElement.classList.add('dark-theme')
    } else {
      document.documentElement.classList.remove('dark-theme')
    }
  }

  function toggleTheme() {
    setTheme(theme.value === 'light' ? 'dark' : 'light')
  }

  return {
    sidebarCollapsed,
    theme,
    currentPath,
    systemTitle,
    systemVersion,
    isDarkTheme,
    applySystemTitle,
    loadPublicSettings,
    loadSettings,
    toggleSidebar,
    setTheme,
    toggleTheme
  }
})
