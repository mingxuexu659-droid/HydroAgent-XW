/**
 * API 模块单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'

// Mock axios
vi.mock('axios', () => {
  const mockAxiosInstance = {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() }
    }
  }
  return {
    default: {
      create: vi.fn(() => mockAxiosInstance),
      ...mockAxiosInstance
    }
  }
})

describe('API Module', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Analysis API', () => {
    it('should have submitTask function', async () => {
      const { submitTask } = await import('@/api/analysis')
      expect(typeof submitTask).toBe('function')
    })

    it('should have getTask function', async () => {
      const { getTask } = await import('@/api/analysis')
      expect(typeof getTask).toBe('function')
    })

    it('should have listTasks function', async () => {
      const { listTasks } = await import('@/api/analysis')
      expect(typeof listTasks).toBe('function')
    })

    it('should have cancelTask function', async () => {
      const { cancelTask } = await import('@/api/analysis')
      expect(typeof cancelTask).toBe('function')
    })

    it('should have getTaskCode function', async () => {
      const { getTaskCode } = await import('@/api/analysis')
      expect(typeof getTaskCode).toBe('function')
    })

    it('should have getTaskResult function', async () => {
      const { getTaskResult } = await import('@/api/analysis')
      expect(typeof getTaskResult).toBe('function')
    })
  })

  describe('Data API', () => {
    it('should have listFiles function', async () => {
      const { listFiles } = await import('@/api/data')
      expect(typeof listFiles).toBe('function')
    })

    it('should have getGeoJSON function', async () => {
      const { getGeoJSON } = await import('@/api/data')
      expect(typeof getGeoJSON).toBe('function')
    })

    it('should have getDownloadUrl function', async () => {
      const { getDownloadUrl } = await import('@/api/data')
      expect(typeof getDownloadUrl).toBe('function')
    })

    it('should generate correct download URL', async () => {
      const { getDownloadUrl } = await import('@/api/data')
      const url = getDownloadUrl('results', 'test.geojson')
      expect(url).toContain('/api/data/download/results/test.geojson')
    })

    it('should have previewFile function', async () => {
      const { previewFile } = await import('@/api/data')
      expect(typeof previewFile).toBe('function')
    })
  })

  describe('Catalog API', () => {
    it('should have getCatalog function', async () => {
      const { getCatalog } = await import('@/api/catalog')
      expect(typeof getCatalog).toBe('function')
    })

    it('should have getCatalogEntry function', async () => {
      const { getCatalogEntry } = await import('@/api/catalog')
      expect(typeof getCatalogEntry).toBe('function')
    })

    it('should have searchCatalog function', async () => {
      const { searchCatalog } = await import('@/api/catalog')
      expect(typeof searchCatalog).toBe('function')
    })

    it('should have getCatalogStats function', async () => {
      const { getCatalogStats } = await import('@/api/catalog')
      expect(typeof getCatalogStats).toBe('function')
    })
  })
})

describe('Type Definitions', () => {
  it('should export all required types', async () => {
    const types = await import('@/types')
    
    // 检查类型导出
    expect(types).toBeDefined()
  })
})

