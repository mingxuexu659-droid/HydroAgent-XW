/**
 * 数据目录 API
 */
import apiClient from './index'
import type {
  CatalogResponse,
  CatalogEntry,
  CatalogSearchRequest,
  CatalogStats
} from '@/types'

const BASE_URL = '/api/catalog'

/**
 * 获取数据目录
 */
export async function getCatalog(
  limit = 100,
  offset = 0,
  type?: 'vector' | 'raster'
): Promise<CatalogResponse> {
  const response = await apiClient.get<CatalogResponse>(BASE_URL, {
    params: { limit, offset, type }
  })
  return response.data
}

/**
 * 获取数据目录条目
 */
export async function getCatalogEntry(entryId: string): Promise<CatalogEntry> {
  const response = await apiClient.get<CatalogEntry>(`${BASE_URL}/${entryId}`)
  return response.data
}

/**
 * 搜索数据目录
 */
export async function searchCatalog(request: CatalogSearchRequest): Promise<CatalogResponse> {
  const response = await apiClient.post<CatalogResponse>(`${BASE_URL}/search`, request)
  return response.data
}

/**
 * 获取数据目录统计
 */
export async function getCatalogStats(): Promise<CatalogStats> {
  const response = await apiClient.get<CatalogStats>(`${BASE_URL}/stats/summary`)
  return response.data
}

