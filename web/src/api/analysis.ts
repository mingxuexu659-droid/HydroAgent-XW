/**
 * 分析任务 API
 */
import apiClient from './index'
import type {
  AnalysisRequest,
  Task,
  TaskListResponse,
  CodeResponse,
  TaskResultResponse
} from '@/types'

const BASE_URL = '/api/analysis'

/**
 * 提交分析任务
 */
export async function submitTask(request: AnalysisRequest): Promise<Task> {
  const response = await apiClient.post<Task>(`${BASE_URL}/submit`, request)
  return response.data
}

/**
 * 获取任务状态
 */
export async function getTask(taskId: string): Promise<Task> {
  const response = await apiClient.get<Task>(`${BASE_URL}/task/${taskId}`)
  return response.data
}

/**
 * 获取任务列表
 */
export async function listTasks(limit = 20, offset = 0): Promise<TaskListResponse> {
  const response = await apiClient.get<TaskListResponse>(`${BASE_URL}/tasks`, {
    params: { limit, offset }
  })
  return response.data
}

/**
 * 取消任务
 */
export async function cancelTask(taskId: string): Promise<{ message: string; task_id: string }> {
  const response = await apiClient.delete<{ message: string; task_id: string }>(
    `${BASE_URL}/task/${taskId}`
  )
  return response.data
}

/**
 * 获取生成的代码
 */
export async function getTaskCode(taskId: string): Promise<CodeResponse> {
  const response = await apiClient.get<CodeResponse>(`${BASE_URL}/task/${taskId}/code`)
  return response.data
}

/**
 * 获取任务结果
 */
export async function getTaskResult(taskId: string): Promise<TaskResultResponse> {
  const response = await apiClient.get<TaskResultResponse>(`${BASE_URL}/task/${taskId}/result`)
  return response.data
}

/**
 * 从脚本路径加载图层
 */
export async function loadLayersFromScript(scriptPath: string): Promise<any> {
  const response = await apiClient.post(`${BASE_URL}/load-layers`, {
    script_path: scriptPath
  })
  return response.data
}

