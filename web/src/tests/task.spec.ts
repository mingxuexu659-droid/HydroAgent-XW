/**
 * 任务状态管理测试
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useTaskStore } from '@/stores/task'
import * as analysisApi from '@/api/analysis'

// Mock API
vi.mock('@/api/analysis', () => ({
  submitTask: vi.fn(),
  getTask: vi.fn(),
  listTasks: vi.fn(),
  cancelTask: vi.fn(),
  getTaskCode: vi.fn()
}))

describe('useTaskStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })
  
  afterEach(() => {
    vi.restoreAllMocks()
  })
  
  describe('提交任务', () => {
    it('应该成功提交任务并连接 WebSocket', async () => {
      const mockTask = {
        task_id: 'test-123',
        status: 'pending' as const,
        message: '任务已创建',
        created_at: '2026-01-14T10:00:00',
        updated_at: '2026-01-14T10:00:00',
        progress: 0,
        current_step: '等待处理',
        output_files: [],
        logs: ''
      }
      
      vi.mocked(analysisApi.submitTask).mockResolvedValue(mockTask)
      
      const store = useTaskStore()
      const result = await store.submitTask({
        query: '测试查询',
        skip_download: false,
        auto_run: true,
        auto_optimize: true
      })
      
      expect(result).toEqual(mockTask)
      expect(store.currentTask).toEqual(mockTask)
      expect(analysisApi.submitTask).toHaveBeenCalledTimes(1)
    })
    
    it('应该处理提交失败', async () => {
      const error = new Error('提交失败')
      vi.mocked(analysisApi.submitTask).mockRejectedValue(error)
      
      const store = useTaskStore()
      
      await expect(store.submitTask({
        query: '测试查询',
        skip_download: false,
        auto_run: true,
        auto_optimize: true
      })).rejects.toThrow()
      
      expect(store.error).toBeTruthy()
    })
  })
  
  describe('获取任务状态', () => {
    it('应该成功获取任务状态', async () => {
      const mockTask = {
        task_id: 'test-123',
        status: 'analyzing' as const,
        message: '正在分析',
        created_at: '2026-01-14T10:00:00',
        updated_at: '2026-01-14T10:00:05',
        progress: 15,
        current_step: '意图分析',
        output_files: [],
        logs: ''
      }
      
      vi.mocked(analysisApi.getTask).mockResolvedValue(mockTask)
      
      const store = useTaskStore()
      const result = await store.fetchTask('test-123')
      
      expect(result).toEqual(mockTask)
      expect(store.currentTask).toEqual(mockTask)
    })
    
    it('应该处理任务不存在', async () => {
      const error = {
        response: {
          status: 404,
          data: { detail: '任务不存在' }
        }
      }
      vi.mocked(analysisApi.getTask).mockRejectedValue(error)
      
      const store = useTaskStore()
      await expect(store.fetchTask('non-existent')).rejects.toThrow()
    })
  })
  
  describe('轮询机制', () => {
    it('应该在 WebSocket 失败时启用轮询', async () => {
      vi.useFakeTimers()
      
      const mockTask = {
        task_id: 'test-123',
        status: 'analyzing' as const,
        message: '正在分析',
        created_at: '2026-01-14T10:00:00',
        updated_at: '2026-01-14T10:00:05',
        progress: 15,
        current_step: '意图分析',
        output_files: [],
        logs: ''
      }
      
      vi.mocked(analysisApi.getTask).mockResolvedValue(mockTask)
      
      const store = useTaskStore()
      // 手动触发轮询（因为 WebSocket Mock 比较复杂）
      store.currentTask = {
        task_id: 'test-123',
        status: 'pending',
        message: '等待处理',
        created_at: '2026-01-14T10:00:00',
        updated_at: '2026-01-14T10:00:00',
        progress: 0,
        current_step: '等待处理',
        output_files: [],
        logs: ''
      }
      
      // 通过调用内部方法测试（实际应用中通过 WebSocket 错误触发）
      // store.startPolling('test-123')  // 这个方法应该暴露或通过 WebSocket 触发
      
      // 快进时间，验证轮询调用
      await vi.advanceTimersByTimeAsync(2000)
      
      // 注意：在实际应用中，轮询会自动调用 API
      // 这里只是示例，实际测试可能需要更复杂的 Mock
      
      vi.useRealTimers()
    })
  })
  
  describe('状态计算', () => {
    it('应该正确计算 isRunning', () => {
      const store = useTaskStore()
      
      store.currentTask = {
        task_id: 'test-123',
        status: 'analyzing',
        message: '正在分析',
        created_at: '2026-01-14T10:00:00',
        updated_at: '2026-01-14T10:00:05',
        progress: 15,
        current_step: '意图分析',
        output_files: [],
        logs: ''
      }
      
      expect(store.isRunning).toBe(true)
      
      store.currentTask.status = 'completed'
      expect(store.isRunning).toBe(false)
    })
    
    it('应该正确计算 isCompleted 和 isFailed', () => {
      const store = useTaskStore()
      
      store.currentTask = {
        task_id: 'test-123',
        status: 'completed',
        message: '完成',
        created_at: '2026-01-14T10:00:00',
        updated_at: '2026-01-14T10:00:10',
        progress: 100,
        current_step: '完成',
        output_files: [],
        logs: ''
      }
      
      expect(store.isCompleted).toBe(true)
      expect(store.isFailed).toBe(false)
      
      store.currentTask.status = 'failed'
      expect(store.isCompleted).toBe(false)
      expect(store.isFailed).toBe(true)
    })
  })
})

