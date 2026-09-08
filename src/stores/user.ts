// 用户状态管理
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api'

interface UserInfo {
  id: number
  username: string
  name: string
  realName?: string
  role: 'admin' | 'operator' | 'viewer'
  email: string
  phone: string
  status: string
  enabled?: boolean
  createdAt: string
  updatedAt: string
}

export const useUserStore = defineStore('user', () => {
  try {
    localStorage.removeItem('token')
    localStorage.removeItem('access_token')
  } catch {
    /* ignore */
  }
  const userInfo = ref<UserInfo | null>(null)

  const isLoggedIn = computed(() => !!userInfo.value)
  const isAdmin = computed(() => userInfo.value?.role === 'admin')
  const isOperator = computed(() => userInfo.value?.role === 'operator')
  const isViewer = computed(() => userInfo.value?.role === 'viewer')

  async function login(username: string, password: string) {
    const res: any = await authApi.login({ username, password })
    if (!res?.user) {
      throw new Error('登录失败')
    }
    userInfo.value = {
      ...res.user,
      name: res.user?.name || res.user?.realName
    }
    return res
  }

  async function fetchUserInfo() {
    const res: any = await authApi.getCurrentUser()
    userInfo.value = {
      ...res,
      name: res.name || res.realName
    }
    return userInfo.value
  }

  let loggingOut = false

  function logout() {
    userInfo.value = null
    if (loggingOut) return
    loggingOut = true
    authApi.logout().catch(() => undefined).finally(() => {
      loggingOut = false
    })
  }

  return {
    userInfo,
    isLoggedIn,
    isAdmin,
    isOperator,
    isViewer,
    login,
    fetchUserInfo,
    logout
  }
})
