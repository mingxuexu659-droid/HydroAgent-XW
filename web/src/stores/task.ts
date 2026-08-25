/**
 * 任务状态管理
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Task, AnalysisRequest, TaskStatus, WSMessage } from '@/types'
import * as analysisApi from '@/api/analysis'

export const useTaskStore = defineStore('task', () => {
  // ============ State ============
  
  /** 当前任务 */
  const currentTask = ref<Task | null>(null)
  
  /** 任务列表 */
  const tasks = ref<Task[]>([])
  
  /** 任务总数 */
  const totalTasks = ref(0)
  
  /** 加载状态 */
  const isLoading = ref(false)
  
  /** 错误信息 */
  const error = ref<string | null>(null)
  
  /** 生成的代码 */
  const generatedCode = ref<string | null>(null)
  
  /** 脚本路径 */
  const scriptPath = ref<string | null>(null)
  
  /** 用户输入的查询文本（持久化） */
  const queryText = ref<string>('')
  
  /** 查询选项（持久化） */
  const queryOptions = ref({
    skip_download: false,
    auto_run: true,
    auto_optimize: true,
    max_optimization_rounds: 3
  })
  
  /** WebSocket 连接 */
  const wsConnection = ref<WebSocket | null>(null)
  
  // ============ Getters ============
  
  /** 当前任务是否正在运行 */
  const isRunning = computed(() => {
    if (!currentTask.value) return false
    const runningStatuses: TaskStatus[] = [
      'pending', 'analyzing', 'downloading', 'generating', 'executing', 'optimizing'
    ]
    return runningStatuses.includes(currentTask.value.status)
  })
  
  /** 当前任务是否完成 */
  const isCompleted = computed(() => {
    return currentTask.value?.status === 'completed'
  })
  
  /** 当前任务是否失败 */
  const isFailed = computed(() => {
    return currentTask.value?.status === 'failed'
  })
  
  /** 进度百分比 */
  const progress = computed(() => {
    return currentTask.value?.progress ?? 0
  })
  
  // ============ Actions ============
  
  /**
   * 提交分析任务
   */
  async function submitTask(request: AnalysisRequest): Promise<Task> {
    isLoading.value = true
    error.value = null
    generatedCode.value = null
    
    try {
      const task = await analysisApi.submitTask(request)
      currentTask.value = task
      
      // 连接 WebSocket 监听进度
      connectWebSocket(task.task_id)
      
      return task
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || '提交任务失败'
      throw e
    } finally {
      isLoading.value = false
    }
  }
  
  /**
   * 获取任务状态
   */
  async function fetchTask(taskId: string): Promise<Task> {
    try {
      const task = await analysisApi.getTask(taskId)
      currentTask.value = task
      return task
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || '获取任务失败'
      throw e
    }
  }
  
  /**
   * 获取任务列表
   */
  async function fetchTasks(limit = 20, offset = 0): Promise<void> {
    isLoading.value = true
    
    try {
      const response = await analysisApi.listTasks(limit, offset)
      tasks.value = response.tasks
      totalTasks.value = response.total
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || '获取任务列表失败'
      throw e
    } finally {
      isLoading.value = false
    }
  }
  
  /**
   * 取消任务
   */
  async function cancelTask(taskId: string): Promise<void> {
    try {
      await analysisApi.cancelTask(taskId)
      
      if (currentTask.value?.task_id === taskId) {
        currentTask.value.status = 'failed'
        currentTask.value.message = '任务已取消'
      }
      
      disconnectWebSocket()
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || '取消任务失败'
      throw e
    }
  }
  
  /**
   * 获取生成的代码（带重试机制）
   */
  async function fetchCode(taskId: string, maxRetries: number = 3): Promise<string | null> {
    let lastError: any = null
    
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        console.log(`[fetchCode] 尝试获取代码 (${attempt}/${maxRetries})...`)
        const response = await analysisApi.getTaskCode(taskId)
        
        // 检查是否真的获取到了代码
        if (response.code && response.code.length > 0) {
          generatedCode.value = response.code
          scriptPath.value = response.script_path  // 存储脚本路径
          console.log('[fetchCode] ✅ 代码获取成功, 长度:', response.code.length)
          console.log('[fetchCode] 脚本路径:', response.script_path)
          return response.code
        } else {
          console.warn(`[fetchCode] ⚠️ 获取到空代码，等待重试...`)
          // 代码可能还没生成完，等待后重试
          if (attempt < maxRetries) {
            await new Promise(resolve => setTimeout(resolve, 2000))
          }
        }
      } catch (e: any) {
        lastError = e
        console.error(`[fetchCode] ❌ 第 ${attempt} 次尝试失败:`, e.message || e)
        
        // 如果不是最后一次尝试，等待后重试
        if (attempt < maxRetries) {
          const waitTime = attempt * 2000  // 递增等待时间
          console.log(`[fetchCode] 等待 ${waitTime}ms 后重试...`)
          await new Promise(resolve => setTimeout(resolve, waitTime))
        }
      }
    }
    
    // 所有重试都失败
    console.error('[fetchCode] ❌ 所有重试都失败')
    error.value = lastError?.response?.data?.detail || lastError?.message || '获取代码失败'
    return null  // 返回 null 而不是抛出异常，避免中断流程
  }
  
  /**
   * 设置代码（用于手动加载）
   */
  function setCode(code: string | null): void {
    generatedCode.value = code
  }
  
  /** 轮询定时器 */
  let pollingTimer: ReturnType<typeof setInterval> | null = null
  
  /**
   * 连接 WebSocket（带轮询备份）
   */
  function connectWebSocket(taskId: string): void {
    // 先断开已有连接和轮询
    disconnectWebSocket()
    
    // 启动轮询作为备份
    startPolling(taskId)
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const defaultWsBaseUrl = `${protocol}//${window.location.host}`
    const wsUrl = `${import.meta.env.VITE_WS_BASE_URL || defaultWsBaseUrl}/ws/task/${taskId}`
    
    try {
      const ws = new WebSocket(wsUrl)
      
      ws.onopen = () => {
        console.log('WebSocket connected')
        // WebSocket 连接成功后，降低轮询频率
        stopPolling()
      }
      
      ws.onmessage = (event) => {
        try {
          const message: WSMessage = JSON.parse(event.data)
          handleWebSocketMessage(message)
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e)
        }
      }
      
      ws.onerror = (event) => {
        console.error('WebSocket error:', event)
        // WebSocket 出错时，启用轮询
        startPolling(taskId)
      }
      
      ws.onclose = () => {
        console.log('WebSocket closed')
        wsConnection.value = null
        // WebSocket 关闭时，启用轮询
        if (currentTask.value && isRunning.value) {
          startPolling(taskId)
        }
      }
      
      wsConnection.value = ws
    } catch (e) {
      console.error('Failed to connect WebSocket:', e)
      // 连接失败时依赖轮询
    }
  }
  
  /**
   * 启动轮询
   */
  function startPolling(taskId: string): void {
    if (pollingTimer) return
    
    console.log('Starting polling for task:', taskId)
    pollingTimer = setInterval(async () => {
      try {
        const task = await analysisApi.getTask(taskId)
        if (task) {
          currentTask.value = task
          
          // 任务完成或失败时停止轮询
          // 注意：代码获取由 App.vue 中的 watch 统一处理，避免重复调用
          if (task.status === 'completed' || task.status === 'failed') {
            stopPolling()
          }
        }
      } catch (e) {
        console.error('Polling error:', e)
        // 如果连续失败，可能任务不存在
        if ((e as any).response?.status === 404) {
          stopPolling()
          error.value = '任务不存在或已过期'
        }
      }
    }, 2000) // 每2秒轮询一次
  }
  
  /**
   * 停止轮询
   */
  function stopPolling(): void {
    if (pollingTimer) {
      console.log('Stopping polling')
      clearInterval(pollingTimer)
      pollingTimer = null
    }
  }
  
  /**
   * 处理 WebSocket 消息
   */
  function handleWebSocketMessage(message: WSMessage): void {
    switch (message.type) {
      case 'initial':
      case 'progress':
      case 'status':
        if (currentTask.value && currentTask.value.task_id === message.task_id) {
          currentTask.value.status = message.status
          currentTask.value.message = message.message
          currentTask.value.progress = message.progress
          currentTask.value.current_step = message.current_step
          
          if (message.updated_at) {
            currentTask.value.updated_at = message.updated_at
          }
          
          // 更新日志
          if ((message as any).logs) {
            currentTask.value.logs = (message as any).logs
          }
          
          // 更新任务类型
          if ((message as any).task_type) {
            currentTask.value.task_type = (message as any).task_type
          }
          
          // 更新下载的文件列表
          if ((message as any).downloaded_files) {
            currentTask.value.downloaded_files = (message as any).downloaded_files
          }
          
          // 任务完成或失败时，代码获取由 App.vue 中的 watch 统一处理
          // 这里不再调用 fetchCode，避免重复调用
        }
        break
        
      case 'heartbeat':
        // 响应心跳
        if (wsConnection.value?.readyState === WebSocket.OPEN) {
          wsConnection.value.send(JSON.stringify({ action: 'ping' }))
        }
        break
        
      case 'error':
        // 如果是"任务不存在"错误，可能是后端重启了，尝试轮询
        if (message.message === '任务不存在' && currentTask.value) {
          console.warn('Task not found via WebSocket, trying polling...')
          startPolling(currentTask.value.task_id)
        } else {
          error.value = message.message
        }
        break
    }
  }
  
  /**
   * 断开 WebSocket 和停止轮询
   */
  function disconnectWebSocket(): void {
    stopPolling()
    
    if (wsConnection.value) {
      wsConnection.value.close()
      wsConnection.value = null
    }
  }
  
  /**
   * 清除当前任务
   */
  function clearCurrentTask(): void {
    disconnectWebSocket()
    currentTask.value = null
    generatedCode.value = null
    error.value = null
  }
  
  /**
   * 设置当前任务
   */
  function setCurrentTask(task: Task): void {
    currentTask.value = task
  }
  
  return {
    // State
    currentTask,
    tasks,
    totalTasks,
    isLoading,
    error,
    generatedCode,
    scriptPath,
    wsConnection,
    queryText,
    queryOptions,
    
    // Getters
    isRunning,
    isCompleted,
    isFailed,
    progress,
    
    // Actions
    submitTask,
    fetchTask,
    fetchTasks,
    cancelTask,
    fetchCode,
    setCode,
    connectWebSocket,
    disconnectWebSocket,
    clearCurrentTask,
    setCurrentTask
  }
})

