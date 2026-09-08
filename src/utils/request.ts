// API 请求封装
import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import { useUserStore } from '@/stores/user'

const request: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
request.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  (response: AxiosResponse) => {
    return response.data
  },
  (error) => {
    const userStore = useUserStore()
    const { response } = error

    if (response) {
      const { status, data } = response

      switch (status) {
        case 401:
          if (router.currentRoute.value.path !== '/login') {
            ElMessage.error(data?.error || '登录已过期，请重新登录')
            userStore.logout()
            router.push('/login')
          }
          break
        case 403:
          ElMessage.error(data?.error || '权限不足')
          break
        case 404:
          ElMessage.error(data?.error || '资源不存在')
          break
        case 500:
          ElMessage.error(data?.error || '服务器内部错误')
          break
        default:
          ElMessage.error(data?.error || `请求失败 (${status})`)
      }
    } else if (error.code === 'ECONNABORTED') {
      ElMessage.error('请求超时，请稍后重试')
    } else {
      ElMessage.error(error.message || '网络错误')
    }

    return Promise.reject(error)
  }
)

export interface ApiResponse<T = any> {
  code?: number
  data?: T
  message?: string
  list?: T
  total?: number
  [key: string]: any
}

export function get<T = any>(url: string, params?: any, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return request.get(url, { params, ...config })
}

export function post<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return request.post(url, data, config)
}

export function put<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return request.put(url, data, config)
}

export function del<T = any>(url: string, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return request.delete(url, config)
}

export default request
