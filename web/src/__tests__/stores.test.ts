/**
 * Store 单元测试
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useTaskStore } from '@/stores/task'
import { useMapStore } from '@/stores/map'

// Mock axios
vi.mock('axios', () => ({
  default: {
    create: () => ({
      get: vi.fn(),
      post: vi.fn(),
      delete: vi.fn(),
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() }
      }
    })
  }
}))

describe('TaskStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should have initial state', () => {
    const store = useTaskStore()
    
    expect(store.currentTask).toBeNull()
    expect(store.tasks).toEqual([])
    expect(store.totalTasks).toBe(0)
    expect(store.isLoading).toBe(false)
    expect(store.error).toBeNull()
    expect(store.generatedCode).toBeNull()
  })

  it('should compute isRunning correctly', () => {
    const store = useTaskStore()
    
    // 没有任务时
    expect(store.isRunning).toBe(false)
    
    // 有正在运行的任务
    store.currentTask = {
      task_id: 'test-1',
      status: 'executing',
      message: 'Running',
      created_at: new Date().toISOString(),
      progress: 50,
      output_files: [],
      logs: []
    }
    expect(store.isRunning).toBe(true)
    
    // 任务完成
    store.currentTask.status = 'completed'
    expect(store.isRunning).toBe(false)
  })

  it('should compute isCompleted correctly', () => {
    const store = useTaskStore()
    
    store.currentTask = {
      task_id: 'test-1',
      status: 'completed',
      message: 'Done',
      created_at: new Date().toISOString(),
      progress: 100,
      output_files: [],
      logs: []
    }
    
    expect(store.isCompleted).toBe(true)
    
    store.currentTask.status = 'failed'
    expect(store.isCompleted).toBe(false)
  })

  it('should compute progress correctly', () => {
    const store = useTaskStore()
    
    expect(store.progress).toBe(0)
    
    store.currentTask = {
      task_id: 'test-1',
      status: 'executing',
      message: 'Running',
      created_at: new Date().toISOString(),
      progress: 75,
      output_files: [],
      logs: []
    }
    
    expect(store.progress).toBe(75)
  })

  it('should clear current task', () => {
    const store = useTaskStore()
    
    store.currentTask = {
      task_id: 'test-1',
      status: 'completed',
      message: 'Done',
      created_at: new Date().toISOString(),
      progress: 100,
      output_files: [],
      logs: []
    }
    store.generatedCode = 'print("hello")'
    store.error = 'Some error'
    
    store.clearCurrentTask()
    
    expect(store.currentTask).toBeNull()
    expect(store.generatedCode).toBeNull()
    expect(store.error).toBeNull()
  })

  it('should set current task', () => {
    const store = useTaskStore()
    
    const task = {
      task_id: 'test-1',
      status: 'pending' as const,
      message: 'Waiting',
      created_at: new Date().toISOString(),
      progress: 0,
      output_files: [],
      logs: []
    }
    
    store.setCurrentTask(task)
    
    expect(store.currentTask).toEqual(task)
  })
})

describe('MapStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should have initial state', () => {
    const store = useMapStore()
    
    expect(store.map).toBeNull()
    expect(store.layers).toEqual([])
    expect(store.selectedLayerId).toBeNull()
    expect(store.selectedFeature).toBeNull()
    expect(store.isMapLoaded).toBe(false)
  })

  it('should compute visibleLayers correctly', () => {
    const store = useMapStore()
    
    store.layers = [
      { id: '1', name: 'Layer 1', type: 'polygon', visible: true },
      { id: '2', name: 'Layer 2', type: 'point', visible: false },
      { id: '3', name: 'Layer 3', type: 'line', visible: true }
    ] as any[]
    
    expect(store.visibleLayers.length).toBe(2)
    expect(store.visibleLayers.map(l => l.id)).toEqual(['1', '3'])
  })

  it('should compute selectedLayer correctly', () => {
    const store = useMapStore()
    
    store.layers = [
      { id: '1', name: 'Layer 1', type: 'polygon', visible: true },
      { id: '2', name: 'Layer 2', type: 'point', visible: true }
    ] as any[]
    
    expect(store.selectedLayer).toBeNull()
    
    store.selectedLayerId = '2'
    expect(store.selectedLayer?.name).toBe('Layer 2')
  })

  it('should compute layerCount correctly', () => {
    const store = useMapStore()
    
    expect(store.layerCount).toBe(0)
    
    store.layers = [
      { id: '1', name: 'Layer 1', type: 'polygon', visible: true }
    ] as any[]
    
    expect(store.layerCount).toBe(1)
  })

  it('should select layer', () => {
    const store = useMapStore()
    
    store.selectLayer('layer-1')
    expect(store.selectedLayerId).toBe('layer-1')
    
    store.selectLayer(null)
    expect(store.selectedLayerId).toBeNull()
  })

  it('should set selected feature', () => {
    const store = useMapStore()
    
    const feature = {
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [0, 0] },
      properties: { name: 'Test' }
    }
    
    store.setSelectedFeature(feature)
    expect(store.selectedFeature).toEqual(feature)
    
    store.setSelectedFeature(null)
    expect(store.selectedFeature).toBeNull()
  })
})

