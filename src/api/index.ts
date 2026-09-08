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
    post(`/auth/users/${id}/reset-password`, data),
  toggleStatus: (id: number, data?: { enabled?: boolean }) =>
    post(`/auth/users/${id}/toggle-status`, data || {})
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
  toggle: (id: number, data?: { enabled?: boolean }) =>
    post(`/cameras/${id}/toggle`, data || {}),
  ptz: (id: number, data: { direction: string; speed?: number }) =>
    post(`/cameras/${id}/ptz`, data),
  getPtz: (id: number) => get(`/cameras/${id}/ptz`),
  getDetection: (id: number) => get(`/cameras/${id}/detection`),
  getMonitorWall: () => get('/cameras/monitor'),
  snapshot: (id: number) => post(`/cameras/${id}/snapshot`),
  getSnapshots: (id: number) => get(`/cameras/${id}/snapshot`),
  record: (id: number, data?: { action?: 'start' | 'stop' | 'toggle' }) =>
    post(`/cameras/${id}/record`, data || { action: 'toggle' }),
  getRecord: (id: number) => get(`/cameras/${id}/record`),
  startStream: (id: number, data?: { preferRtsp?: boolean; wait?: boolean }) =>
    post(`/cameras/${id}/stream/start`, data || { preferRtsp: true, wait: false }, { timeout: 15000 }),
  stopStream: (id: number) => post(`/cameras/${id}/stream/stop`),
  getStream: (id: number) => get(`/cameras/${id}/stream`)
}

/** Poll stream status written by runtime to Redis (API does not wait on ffmpeg). */
export async function waitStreamReady(id: number, first?: any) {
  const ready = (row: any) => !!(row?.hlsUrl && (row.playlistReady || row.hlsReady))
  if (ready(first)) return first
  const deadline = Date.now() + 18000
  let last = first
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 700))
    last = await cameraApi.getStream(id)
    if (ready(last)) return last
  }
  return last
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
  getHeatmap: () => get('/alerts/heatmap/data'),
  getEvidence: (id: number) => get(`/alerts/${id}/evidence`),
  getReport: (id: number) => get(`/alerts/${id}/report`),
  dispatch: (id: number, data?: { note?: string; assignee?: string }) =>
    post(`/alerts/${id}/dispatch`, data || {})
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
  getNotificationLogs: () => get('/config/notification/logs'),
  getPublic: () => get('/config/public'),

  getStrategies: () => get('/config/strategies'),
  getStrategy: (id: number) => get(`/config/strategies/${id}`),
  addStrategy: (data: any) => post('/config/strategies', data),
  updateStrategy: (id: number, data: any) => put(`/config/strategies/${id}`, data),
  deleteStrategy: (id: number) => del(`/config/strategies/${id}`),
  toggleStrategy: (id: number, data?: { enabled?: boolean }) =>
    post(`/config/strategies/${id}/toggle`, data || {}),

  getSystemInfo: () => get('/config/system/info'),

  getFlywheel: () => get('/config/flywheel'),
  updateFlywheel: (data: any) => put('/config/flywheel', data),
  getFlywheelStats: () => get('/config/flywheel/stats'),
  getFlywheelSamples: (params?: any) => get('/config/flywheel/samples', params),
  getFlywheelSample: (id: number) => get(`/config/flywheel/samples/${id}`),
  getFlywheelSampleNext: (params?: { afterId?: number }) =>
    get('/config/flywheel/samples/next', params),
  getFlywheelSampleImage: (id: number) =>
    get(`/config/flywheel/samples/${id}/image`, undefined, { responseType: 'blob' }),
  updateFlywheelSample: (id: number, data: { boxes: any[] }) =>
    put(`/config/flywheel/samples/${id}`, data),
  approveFlywheelSample: (id: number, data?: { boxes?: any[] }) =>
    post(`/config/flywheel/samples/${id}/approve`, data || {}),
  discardFlywheelSample: (id: number) => post(`/config/flywheel/samples/${id}/discard`, {}),
  getFlywheelTrain: () => get('/config/flywheel/train'),
  startFlywheelTrain: () => post('/config/flywheel/train', {}),
  promoteFlywheelTrain: (id: number) => post(`/config/flywheel/train/${id}/promote`, {}),
  rollbackFlywheelTrain: (id: number) => post(`/config/flywheel/train/${id}/rollback`, {})
}

// ============== 大屏接口 ==============
export const dashboardApi = {
  /** 总览分析聚合 period=day|week|month */
  getAnalysis: (params?: { period?: 'day' | 'week' | 'month' }) =>
    get('/dashboard/analysis', params),
  getScreen: () => get('/dashboard/screen'),
  getOverview: () => get('/dashboard/overview'),
  getAlertTrend: (params?: any) => get('/dashboard/alert-trend', params),
  getAlertTypes: () => get('/dashboard/alert-types'),
  getAlertLevels: () => get('/dashboard/alert-levels'),
  getCameraRank: () => get('/dashboard/camera-rank'),
  getRecentAlerts: () => get('/dashboard/recent-alerts'),
  getAreaDistribution: () => get('/dashboard/area-distribution'),
  getRealtimeDetections: () => get('/dashboard/realtime-detections')
}
