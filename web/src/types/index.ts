/**
 * 类型定义
 */

// ============ 任务相关类型 ============

/** 任务状态枚举 */
export type TaskStatus = 
  | 'pending'
  | 'analyzing'
  | 'downloading'
  | 'generating'
  | 'executing'
  | 'optimizing'
  | 'completed'
  | 'failed'

/** 输出文件 */
export interface OutputFile {
  name: string
  path: string
  url: string
  type: 'vector' | 'raster' | 'script' | 'image' | 'json' | 'other'
  size: number
}

/** 日志条目 */
export interface LogEntry {
  level: 'info' | 'warning' | 'error'
  message: string
  timestamp: string
}

/** 任务信息 */
export interface Task {
  task_id: string
  status: TaskStatus
  message: string
  created_at: string
  updated_at?: string
  progress: number
  current_step?: string
  output_files: OutputFile[]
  logs: string  // 原始输出文本
}

/** 分析请求 */
export interface AnalysisRequest {
  query: string
  skip_download?: boolean
  auto_run?: boolean
  auto_optimize?: boolean
  max_optimization_rounds?: number
}

/** 任务列表响应 */
export interface TaskListResponse {
  total: number
  tasks: Task[]
}

/** 代码响应 */
export interface CodeResponse {
  task_id: string
  code: string | null
  language: string
  script_path: string | null
}

/** 任务结果响应 */
export interface TaskResultResponse {
  task_id: string
  status: TaskStatus
  output_files: OutputFile[]
  geojson_data?: GeoJSON.FeatureCollection | null
}

// ============ 数据相关类型 ============

/** 文件信息 */
export interface FileInfo {
  name: string
  path: string
  url: string
  type: string
  size: number
  modified_at?: string
}

/** 文件列表响应 */
export interface FileListResponse {
  total: number
  files: FileInfo[]
}

/** 数据目录条目 */
export interface CatalogEntry {
  id: string
  name: string
  file_path: string
  file_type: string
  geometry_type?: string
  crs?: string
  feature_count?: number
  description?: string
  attributes?: string[]
  bounds?: [number, number, number, number]
  file_size_mb?: number
  created_at?: string
  data_category?: string
}

/** 数据目录响应 */
export interface CatalogResponse {
  total: number
  entries: CatalogEntry[]
}

/** 数据目录搜索请求 */
export interface CatalogSearchRequest {
  query: string
  type?: 'vector' | 'raster'
  limit?: number
}

/** 数据目录统计 */
export interface CatalogStats {
  total: number
  by_type: {
    vector: number
    raster: number
    other: number
  }
  by_geometry: Record<string, number>
}

// ============ 地图相关类型 ============

/** 图层类型 */
export type LayerType = 'point' | 'line' | 'polygon' | 'raster'

/** 栅格图层源信息 */
export interface RasterSource {
  url: string
  format: 'cog' | 'png'
}

/** 图层信息 */
export interface Layer {
  id: string
  name: string
  type: LayerType
  visible: boolean
  featureCount?: number
  bounds?: [number, number, number, number]
  style?: LayerStyle
  sourceData?: GeoJSON.FeatureCollection
  rasterSource?: RasterSource  // 栅格图层的源信息
}

/** 图层样式 */
export interface LayerStyle {
  // 通用
  color?: string
  opacity?: number
  
  // 点
  radius?: number
  
  // 线
  width?: number
  
  // 面
  fillColor?: string
  fillOpacity?: number
  strokeColor?: string
  strokeWidth?: number
}

// ============ WebSocket 相关类型 ============

/** WebSocket 消息类型 */
export type WSMessageType = 
  | 'initial'
  | 'progress'
  | 'status'
  | 'pong'
  | 'heartbeat'
  | 'error'

/** WebSocket 消息基础 */
export interface WSMessageBase {
  type: WSMessageType
}

/** WebSocket 进度消息 */
export interface WSProgressMessage extends WSMessageBase {
  type: 'progress' | 'initial' | 'status'
  task_id: string
  status: TaskStatus
  message: string
  progress: number
  current_step?: string
  updated_at?: string
  created_at?: string
}

/** WebSocket 错误消息 */
export interface WSErrorMessage extends WSMessageBase {
  type: 'error'
  message: string
}

/** WebSocket 心跳消息 */
export interface WSHeartbeatMessage extends WSMessageBase {
  type: 'heartbeat' | 'pong'
}

export type WSMessage = WSProgressMessage | WSErrorMessage | WSHeartbeatMessage

// ============ API 相关类型 ============

/** API 错误响应 */
export interface ApiError {
  detail: string
  type?: string
}

/** 服务状态 */
export interface ServiceStatus {
  service: string
  version: string
  status: string
  docs: string
  redoc: string
}

