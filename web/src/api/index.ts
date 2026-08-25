/**
 * API 模块入口
 */
import axios, { type AxiosInstance, type AxiosError } from 'axios'
import type { ApiError } from '@/types'

// 创建 axios 实例
// 使用相对路径，通过 Vite 代理转发请求，避免 CORS 问题
const apiClient: AxiosInstance = axios.create({
  baseURL: '',  // 使用相对路径
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    // 可以在这里添加认证 token 等
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    return response
  },
  (error: AxiosError<ApiError>) => {
    // 统一错误处理
    const message = error.response?.data?.detail || error.message || '请求失败'
    console.error('API Error:', message)
    return Promise.reject(error)
  }
)

export default apiClient
export { apiClient }
export * from './analysis'
export * from './data'
export * from './catalog'

