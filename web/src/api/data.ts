/**
 * 数据管理 API
 */
import apiClient from './index'
import type { FileListResponse } from '@/types'

const BASE_URL = '/api/data'

/**
 * 获取文件列表
 */
export async function listFiles(
  source: 'results' | 'downloaded' | 'scripts' = 'results',
  type?: 'vector' | 'raster' | 'script' | 'all'
): Promise<FileListResponse> {
  const response = await apiClient.get<FileListResponse>(`${BASE_URL}/files`, {
    params: { source, type }
  })
  return response.data
}

/**
 * 获取 GeoJSON 文件内容
 */
export async function getGeoJSON(filename: string): Promise<GeoJSON.FeatureCollection> {
  const response = await apiClient.get<GeoJSON.FeatureCollection>(
    `${BASE_URL}/geojson/${filename}`
  )
  return response.data
}

/**
 * 获取文件下载 URL
 */
export function getDownloadUrl(source: string, filename: string): string {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
  return `${baseUrl}${BASE_URL}/download/${source}/${filename}`
}

/**
 * 预览文件信息
 */
export async function previewFile(
  source: string,
  filename: string
): Promise<{
  name: string
  path: string
  type: string
  size: number
  extension: string
  feature_count?: number
  geometry_types?: string[]
  properties?: string[]
}> {
  const response = await apiClient.get(`${BASE_URL}/preview/${source}/${filename}`)
  return response.data
}

