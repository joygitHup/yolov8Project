// API 接口定义
import { get, post, put, del } from '@/utils/request'

// ============== 认证接口 ==============
export const authApi = {
  login: (data: { username: string; password: string }) => post('/auth/login', data),
  logout: () => post('/auth/logout'),
  getCurrentUser: () => get('/auth/me'),
  changePassword: (data: { oldPassword: string; newPassword: string }) =>
    post('/auth/change-password', data),

  // 用户管理
  getUsers: (params?: any) => get('/auth/users', params),
  addUser: (data: any) => post('/auth/users', data),
  updateUser: (id: number, data: any) => put(`/auth/users/${id}`, data),
  deleteUser: (id: number) => del(`/auth/users/${id}`),
  resetPassword: (id: number, data: { newPassword: string }) =>
    post(`/auth/users/${id}/reset-password`, data)
}

// ============== 摄像头接口 ==============
export const cameraApi = {
  getList: (params?: any) => get('/cameras', params),
  getAll: () => get('/cameras/all'),
  getDetail: (id: number) => get(`/cameras/${id}`),
  add: (data: any) => post('/cameras', data),
  update: (id: number, data: any) => put(`/cameras/${id}`, data),
  delete: (id: number) => del(`/cameras/${id}`),
  batchDelete: (ids: number[]) => post('/cameras/batch-delete', { ids }),
  toggle: (id: number) => post(`/cameras/${id}/toggle`),
  ptz: (id: number, data: { direction: string; speed?: number }) =>
    post(`/cameras/${id}/ptz`, data),
  getDetection: (id: number) => get(`/cameras/${id}/detection`)
}

// ============== 告警接口 ==============
export const alertApi = {
  getList: (params?: any) => get('/alerts', params),
  getStats: () => get('/alerts/stats'),
  getDetail: (id: number) => get(`/alerts/${id}`),
  handle: (id: number, data: { status: string; note?: string }) =>
    post(`/alerts/${id}/handle`, data),
  batchHandle: (data: { ids: number[]; status: string; note?: string }) =>
    post('/alerts/batch-handle', data),
  getHeatmap: () => get('/alerts/heatmap/data')
}

// ============== 配置接口 ==============
export const configApi = {
  getSettings: () => get('/config/settings'),
  updateSettings: (data: any) => put('/config/settings', data),

  getDetection: () => get('/config/detection'),
  updateDetection: (data: any) => put('/config/detection', data),

  getNotification: () => get('/config/notification'),
  updateNotification: (data: any) => put('/config/notification', data),
  testNotification: (channel: string) => post('/config/notification/test', { channel }),

  getStrategies: () => get('/config/strategies'),
  getStrategy: (id: number) => get(`/config/strategies/${id}`),
  addStrategy: (data: any) => post('/config/strategies', data),
  updateStrategy: (id: number, data: any) => put(`/config/strategies/${id}`, data),
  deleteStrategy: (id: number) => del(`/config/strategies/${id}`),
  toggleStrategy: (id: number) => post(`/config/strategies/${id}/toggle`),

  getSystemInfo: () => get('/config/system/info')
}

// ============== 大屏接口 ==============
export const dashboardApi = {
  getOverview: () => get('/dashboard/overview'),
  getAlertTrend: () => get('/dashboard/alert-trend'),
  getAlertTypes: () => get('/dashboard/alert-types'),
  getAlertLevels: () => get('/dashboard/alert-levels'),
  getCameraRank: () => get('/dashboard/camera-rank'),
  getRecentAlerts: () => get('/dashboard/recent-alerts'),
  getAreaDistribution: () => get('/dashboard/area-distribution'),
  getRealtimeDetections: () => get('/dashboard/realtime-detections')
}
