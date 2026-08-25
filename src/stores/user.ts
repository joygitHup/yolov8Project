// 用户状态管理
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api'

interface UserInfo {
  id: number
  username: string
  name: string
  role: 'admin' | 'operator' | 'viewer'
  email: string
  phone: string
  status: string
  createdAt: string
  updatedAt: string
}

export const useUserStore = defineStore('user', () => {
  const token = ref<string>(localStorage.getItem('token') || '')
  const userInfo = ref<UserInfo | null>(null)

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => userInfo.value?.role === 'admin')
  const isOperator = computed(() => userInfo.value?.role === 'operator')
  const isViewer = computed(() => userInfo.value?.role === 'viewer')

  async function login(username: string, password: string) {
    const res: any = await authApi.login({ username, password })
    if (res.token) {
      token.value = res.token
      userInfo.value = res.user
      localStorage.setItem('token', res.token)
    }
    return res
  }

  async function fetchUserInfo() {
    try {
      const res: any = await authApi.getCurrentUser()
      userInfo.value = res
      return res
    } catch {
      logout()
      throw new Error('获取用户信息失败')
    }
  }

  function logout() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
  }

  function setToken(t: string) {
    token.value = t
    localStorage.setItem('token', t)
  }

  return {
    token,
    userInfo,
    isLoggedIn,
    isAdmin,
    isOperator,
    isViewer,
    login,
    fetchUserInfo,
    logout,
    setToken
  }
})
