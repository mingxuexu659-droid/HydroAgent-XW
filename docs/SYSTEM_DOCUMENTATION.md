# AutoGIS 自动化地理空间分析系统

## 完整技术文档

> **版本**: v1.1.0  
> **更新日期**: 2026-01-15  
> **技术栈**: Python 3.10+ / FastAPI / Vue 3 / TypeScript / QGIS 3.44+

---

## 📋 目录

1. [系统概述](#1-系统概述)
2. [系统架构](#2-系统架构)
3. [核心算法引擎](#3-核心算法引擎)
4. [后端服务层](#4-后端服务层)
5. [前端应用层](#5-前端应用层)
6. [数据流程](#6-数据流程)
7. [API 接口](#7-api-接口)
8. [部署指南](#8-部署指南)
9. [配置说明](#9-配置说明)
10. [开发指南](#10-开发指南)

---

## 1. 系统概述

### 1.1 项目背景

AutoGIS 是一个**自动化地理空间分析平台**，旨在降低 GIS 分析的技术门槛。用户只需输入自然语言描述的分析需求，系统即可自动完成：

- 🔍 **智能理解**：解析用户意图，识别所需数据和分析操作
- 📥 **数据获取**：自动从多种数据源下载所需空间数据
- 💻 **代码生成**：生成可执行的 QGIS/PyQGIS 分析代码
- ▶️ **自动执行**：在 QGIS 环境中运行生成的代码
- 🔧 **智能优化**：执行失败时基于 RAG 自动优化代码
- 🗺️ **结果展示**：在 Web 地图上实时展示分析结果

### 1.2 核心特性

| 特性 | 描述 |
|------|------|
| **自然语言驱动** | 支持中文自然语言输入，无需编写代码 |
| **多数据源支持** | OSM、Sentinel-2、行政边界等多种数据源 |
| **本地数据优先** | 基于向量检索优先使用本地数据，避免重复下载 |
| **实时进度推送** | WebSocket 实时推送任务执行进度 |
| **Web 可视化** | 结果直接在 Web 地图上展示，支持图层管理 |
| **RAG 代码优化** | 失败时检索算法文档，智能修复代码 |

### 1.3 典型使用场景

```
用户输入: "下载北京的Sentinel-2影像并计算NDVI"

系统自动完成:
1. 意图分析 → 识别为"数据下载+代码生成"任务
2. 数据检索 → 检查本地是否有北京边界数据
3. 数据下载 → 下载北京边界 + Sentinel-2影像
4. 代码生成 → 生成NDVI计算的PyQGIS代码
5. 代码执行 → 在QGIS环境中执行
6. 结果展示 → NDVI结果显示在Web地图上
```

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              前端应用层                                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        Vue 3 + TypeScript                        │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │   │
│  │  │QueryInput│ │TaskLogs │ │MapView  │ │DataCatalog│ │ApiDocs │   │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘   │   │
│  │                                                                   │   │
│  │  ┌─────────────────┐     ┌─────────────────┐                     │   │
│  │  │   Pinia Store   │     │  MapLibre GL    │                     │   │
│  │  │  (Task/Map)     │     │   (地图渲染)     │                     │   │
│  │  └─────────────────┘     └─────────────────┘                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ HTTP/WebSocket
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              后端服务层                                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      FastAPI + Uvicorn                           │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │   │
│  │  │Analysis API │ │  Data API   │ │ Catalog API │                │   │
│  │  │(任务管理)    │ │(文件管理)    │ │(数据目录)    │                │   │
│  │  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘                │   │
│  │         │               │               │                        │   │
│  │  ┌──────┴───────────────┴───────────────┴──────┐                │   │
│  │  │              Task Manager                    │                │   │
│  │  │        (任务调度 / 进度管理 / 日志捕获)        │                │   │
│  │  └──────────────────────┬──────────────────────┘                │   │
│  │                         │                                        │   │
│  │  ┌──────────────────────┴──────────────────────┐                │   │
│  │  │           WebSocket Server                   │                │   │
│  │  │          (实时进度推送)                       │                │   │
│  │  └─────────────────────────────────────────────┘                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                             核心算法引擎                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Spatial Analysis System                       │   │
│  │                                                                   │   │
│  │  ┌─────────────────┐                    ┌─────────────────┐     │   │
│  │  │  Workflow Engine │◄──────────────────│   Config        │     │   │
│  │  │   (工作流引擎)    │                    │  (配置管理)      │     │   │
│  │  └────────┬────────┘                    └─────────────────┘     │   │
│  │           │                                                      │   │
│  │  ┌────────┼────────┬────────────────┬────────────────┐          │   │
│  │  ▼        ▼        ▼                ▼                ▼          │   │
│  │ ┌────┐ ┌────┐ ┌────────┐ ┌──────────┐ ┌──────────┐              │   │
│  │ │意图 │ │代码 │ │代码执行 │ │代码优化器│ │算法帮助  │              │   │
│  │ │分析 │ │生成 │ │  器    │ │(RAG)    │ │模块     │              │   │
│  │ └────┘ └────┘ └────────┘ └──────────┘ └──────────┘              │   │
│  │                                                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                         Core 数据引擎                            │   │
│  │  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐       │   │
│  │  │Data Retrieval  │ │Vector Database │ │Geo Query       │       │   │
│  │  │Engine (数据获取)│ │ (向量检索)      │ │Engine (地理查询)│       │   │
│  │  └────────────────┘ └────────────────┘ └────────────────┘       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              外部服务                                    │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ LLM API │ │ OSM API │ │Sentinel │ │Nominatim│ │Embedding│          │
│  │(通义千问)│ │(Overpass)│ │ Hub API │ │ (地理编码)│ │  API    │          │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘          │
└─────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              执行环境                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      QGIS 3.44+ (PyQGIS)                         │   │
│  │            Processing / GDAL / OGR / 空间分析算法                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
AutoGIS_main/
├── spatial_analysis_system/     # 🧠 核心算法引擎
│   ├── config.py               # 配置管理
│   ├── config.yaml             # 配置文件
│   ├── llm_client.py           # LLM 客户端
│   ├── intent_analyzer.py      # 意图分析器
│   ├── code_generator.py       # 代码生成器
│   ├── code_executor.py        # 代码执行器
│   ├── code_optimizer.py       # 代码优化器 (RAG)
│   ├── algorithm_helper.py     # 算法帮助模块
│   ├── workflow_engine.py      # 工作流引擎
│   └── catalog_builder.py      # 数据目录构建器
│
├── core/                        # 📦 数据引擎模块
│   ├── geo_query_engine.py     # 地理查询引擎
│   ├── data_retrieval_engine.py# 数据获取引擎
│   ├── local_vector_matcher.py # 本地数据匹配
│   ├── vector_database.py      # 向量数据库
│   ├── vector_embedding.py     # 向量嵌入
│   └── metadata_generator.py   # 元数据生成器
│
├── api/                         # 🌐 后端 API 服务
│   ├── main.py                 # FastAPI 主入口
│   ├── routers/                # 路由模块
│   │   ├── analysis.py         # 分析任务 API
│   │   ├── data.py             # 数据管理 API
│   │   └── catalog.py          # 数据目录 API
│   ├── schemas/                # Pydantic 数据模型
│   ├── services/               # 服务层
│   │   └── task_manager.py     # 任务管理器
│   └── websocket/              # WebSocket 模块
│       └── task_progress.py    # 进度推送
│
├── web/                         # 🖥️ 前端应用
│   ├── src/
│   │   ├── components/         # Vue 组件
│   │   │   ├── analysis/       # 分析相关组件
│   │   │   ├── map/            # 地图相关组件
│   │   │   ├── data/           # 数据目录组件
│   │   │   ├── history/        # 历史记录组件
│   │   │   └── docs/           # API 文档组件
│   │   ├── stores/             # Pinia 状态管理
│   │   ├── api/                # API 调用封装
│   │   └── types/              # TypeScript 类型
│   └── package.json            # 前端依赖
│
├── data/                        # 📊 数据存储
│   ├── data_catalog.json       # 数据目录
│   ├── vector_db.json          # 向量数据库
│   └── qgis_alg_detail.*.csv   # QGIS 算法文档
│
├── downloaded_data/             # 📥 下载的数据
├── output/                      # 📤 输出目录
│   ├── generated_scripts/      # 生成的脚本
│   ├── results/                # 分析结果
│   └── logs/                   # 日志文件
│
├── scripts/                     # Catalog, retrieval, maintenance, and development tools
└── run_analysis.py              # CLI 入口
```

### 2.3 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **前端** | Vue 3 + TypeScript | 响应式框架 + 类型安全 |
| | Vite | 现代构建工具 |
| | MapLibre GL JS | 高性能地图渲染 |
| | Pinia | 状态管理 |
| **后端** | FastAPI | 高性能异步 API 框架 |
| | Uvicorn | ASGI 服务器 |
| | WebSocket | 实时通信 |
| | Pydantic | 数据验证 |
| **算法引擎** | Python 3.10+ | 核心语言 |
| | QGIS 3.44 + PyQGIS | 空间分析 |
| | GDAL/OGR | 地理数据处理 |
| **AI/ML** | OpenAI API (兼容) | LLM 推理 |
| | 向量嵌入 | 本地数据检索 |
| **数据源** | OpenStreetMap | 矢量数据 |
| | Sentinel Hub | 遥感影像 |
| | Nominatim | 地理编码 |

---

## 3. 核心算法引擎

### 3.1 工作流引擎 (Workflow Engine)

工作流引擎是系统的核心调度器，协调各模块完成完整的分析流程。

```python
# 工作流执行流程
class WorkflowEngine:
    def process(self, query: str) -> WorkflowResult:
        # 1. 意图分析
        intent = self.intent_analyzer.analyze(query)
        
        # 2. 根据意图类型处理
        if intent.task_type == "DATA_AND_CODE":
            return self._handle_data_and_code(query, intent)
        elif intent.task_type == "DATA_DOWNLOAD_ONLY":
            return self._handle_data_only(query, intent)
        elif intent.task_type == "CODE_ONLY":
            return self._handle_code_only(query, intent)
```

**工作流类型**：

| 类型 | 触发条件 | 处理流程 |
|------|----------|----------|
| `DATA_AND_CODE` | 需要下载数据并分析 | 意图分析 → 数据获取 → 代码生成 → 执行 → 优化 |
| `DATA_DOWNLOAD_ONLY` | 仅需要下载数据 | 意图分析 → 数据获取 |
| `CODE_ONLY` | 使用已有数据分析 | 意图分析 → 代码生成 → 执行 → 优化 |

### 3.2 意图分析器 (Intent Analyzer)

基于 LLM 分析用户自然语言输入，提取关键信息。

**输入示例**：
```
"下载清华大学和北京大学的边界，计算600米缓冲区并展示重叠区域"
```

**分析输出**：
```json
{
  "task_type": "DATA_AND_CODE",
  "data_requirements": [
    {"name": "清华大学边界", "type": "boundary", "format": "geojson"},
    {"name": "北京大学边界", "type": "boundary", "format": "geojson"}
  ],
  "analysis_operations": ["buffer", "intersection"],
  "parameters": {"buffer_distance": 600}
}
```

### 3.3 代码生成器 (Code Generator)

根据分析需求和数据信息，生成 PyQGIS 代码。

**核心功能**：
- 多种分析模板（缓冲区、裁剪、相交、NDVI等）
- 自动处理坐标系转换（EPSG:4326 → EPSG:3857）
- 生成 `addMapLayer()` 调用便于前端提取结果

**生成代码示例**：
```python
# 自动生成的 PyQGIS 代码
from qgis.core import *
import processing

# 加载数据
layer1 = QgsVectorLayer("boundary_清华大学.geojson", "清华大学", "ogr")
layer2 = QgsVectorLayer("boundary_北京大学.geojson", "北京大学", "ogr")

# 重投影到 EPSG:3857 (米单位)
layer1_3857 = processing.run("native:reprojectlayer", {
    'INPUT': layer1, 'TARGET_CRS': 'EPSG:3857', 'OUTPUT': 'memory:'
})['OUTPUT']

# 缓冲区分析
buffer_result = processing.run("native:buffer", {
    'INPUT': layer1_3857, 'DISTANCE': 600, 'OUTPUT': 'output/buffer.geojson'
})

# 添加到地图 (供前端提取)
addMapLayer("缓冲区结果", "output/buffer.geojson", "vector")
```

### 3.4 代码优化器 (Code Optimizer)

当代码执行失败时，使用 RAG (检索增强生成) 技术自动修复。

**优化流程**：

```
┌─────────────────────────────────────────────────────────────────┐
│                      代码优化流程 (RAG)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 错误分析                                                     │
│     └─ 解析执行错误信息，识别失败原因                             │
│                                                                  │
│  2. 文件路径提取                                                 │
│     └─ 从代码中提取数据文件路径                                   │
│                                                                  │
│  3. 元数据检索                                                   │
│     └─ 从 data_catalog.json 检索文件元数据                       │
│        (几何类型、坐标系、字段信息等)                             │
│                                                                  │
│  4. 算法ID提取                                                   │
│     └─ 从代码中提取 processing.run() 的算法ID                    │
│                                                                  │
│  5. 算法文档检索                                                 │
│     └─ 从 qgis_alg_detail.csv 检索算法详细文档                   │
│     └─ 对于不存在的算法，进行模糊匹配推荐替代                     │
│                                                                  │
│  6. Prompt 构建                                                  │
│     └─ 组合：原始代码 + 错误信息 + 元数据 + 算法文档              │
│                                                                  │
│  7. LLM 优化                                                     │
│     └─ 调用 LLM 生成修复后的代码                                 │
│                                                                  │
│  8. 重新执行                                                     │
│     └─ 执行优化后的代码，失败则重复1-7                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.5 本地数据匹配 (Local Vector Matcher)

基于向量相似度搜索，优先使用本地数据避免重复下载。

**检索流程**：
1. 将用户查询转换为向量 (Embedding)
2. 在向量数据库中检索相似数据集
3. 使用 LLM 判断匹配的数据集是否满足需求
4. 满足则直接使用本地数据，否则执行在线下载

**向量数据库结构**：
```json
{
  "datasets": [
    {
      "id": "boundary_北京大学",
      "description": "北京大学边界多边形数据，GeoJSON格式",
      "embedding": [0.12, -0.34, 0.56, ...],
      "file_path": "downloaded_data/boundaries/boundary_北京大学.geojson"
    }
  ]
}
```

---

## 4. 后端服务层

### 4.1 FastAPI 应用架构

```python
# api/main.py
app = FastAPI(
    title="AutoGIS API",
    description="自动化地理空间分析系统 API",
    version="1.0.0"
)

# 路由注册
app.include_router(analysis.router, prefix="/api/analysis", tags=["分析任务"])
app.include_router(data.router, prefix="/api/data", tags=["数据管理"])
app.include_router(catalog.router, prefix="/api/catalog", tags=["数据目录"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])

# 静态文件服务
app.mount("/results", StaticFiles(directory="output/results"))
app.mount("/downloaded", StaticFiles(directory="downloaded_data"))
```

### 4.2 任务管理器 (Task Manager)

任务管理器是后端核心服务，负责：
- 任务创建和状态管理
- 日志实时捕获
- 进度更新推送
- 工作流引擎调用

**任务状态流转**：

```
┌─────────┐    ┌───────────┐    ┌─────────────┐    ┌───────────┐
│ PENDING │───▶│ ANALYZING │───▶│ DOWNLOADING │───▶│ GENERATING│
└─────────┘    └───────────┘    └─────────────┘    └───────────┘
                                                         │
                                                         ▼
┌───────────┐    ┌────────────┐    ┌───────────┐   ┌───────────┐
│ COMPLETED │◀───│ OPTIMIZING │◀───│ EXECUTING │◀──┤ (失败重试) │
└───────────┘    └────────────┘    └───────────┘   └───────────┘
      │                                   │
      │                                   ▼
      │                            ┌──────────┐
      └────────────────────────────│  FAILED  │
                                   └──────────┘
```

### 4.3 WebSocket 进度推送

实时推送任务执行进度到前端。

**消息类型**：

| 类型 | 说明 | 示例 |
|------|------|------|
| `initial` | 连接成功，发送当前状态 | `{"type":"initial","status":"executing","progress":45}` |
| `progress` | 进度更新 | `{"type":"progress","progress":60,"message":"正在执行代码"}` |
| `status` | 状态变更 | `{"type":"status","status":"completed"}` |
| `heartbeat` | 心跳保活 | `{"type":"heartbeat"}` |
| `error` | 错误消息 | `{"type":"error","message":"执行失败"}` |

**前端连接示例**：
```typescript
const ws = new WebSocket(`ws://localhost:8000/ws/task/${taskId}`)

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data)
  if (msg.type === 'progress') {
    updateProgress(msg.progress)
  }
}
```

### 4.4 数据目录 API

提供数据目录的查询和统计功能。

**主要端点**：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/catalog` | GET | 获取数据目录列表 |
| `/api/catalog/search` | GET | 搜索数据目录 |
| `/api/catalog/stats/summary` | GET | 获取统计摘要 |
| `/api/catalog/{id}` | GET | 获取数据详情 |

**数据目录结构**：
```json
{
  "vector_data": {
    "datasets": [...],
    "points": [...],
    "polygons": [...]
  },
  "raster_data": {
    "imagery": [...]
  }
}
```

---

## 5. 前端应用层

### 5.1 组件架构

```
App.vue
├── Header (导航栏)
│   └── 分析 | 数据目录 | 历史记录 | API文档
│
├── Sidebar (左侧面板)
│   ├── QueryInput (查询输入)
│   ├── TaskProgress (任务进度)
│   ├── TaskLogs (执行日志)
│   └── LayerPanel (图层管理)
│
├── MapArea (地图区域)
│   ├── MapContainer (MapLibre GL)
│   └── CodeViewer (代码查看器)
│
├── DataCatalog (数据目录) [全屏覆盖]
│   └── DataGraph (知识图谱)
│
├── TaskHistory (历史记录) [全屏覆盖]
│
└── ApiDocs (API文档) [全屏覆盖]
```

### 5.2 状态管理 (Pinia)

**Task Store**：
```typescript
// stores/task.ts
export const useTaskStore = defineStore('task', () => {
  // 状态
  const currentTask = ref<Task | null>(null)
  const generatedCode = ref<string | null>(null)
  const queryText = ref<string>('')  // 持久化查询文本
  
  // 操作
  async function submitTask(request: AnalysisRequest) { ... }
  async function fetchCode(taskId: string) { ... }
  function connectWebSocket(taskId: string) { ... }
  
  return { currentTask, generatedCode, queryText, submitTask, ... }
})
```

**Map Store**：
```typescript
// stores/map.ts
export const useMapStore = defineStore('map', () => {
  // 状态
  const layers = ref<Layer[]>([])
  const mapInstance = ref<maplibregl.Map | null>(null)
  
  // 操作
  async function addGeoJSONLayer(name: string, url: string) { ... }
  async function addRasterLayer(name: string, url: string, bounds: number[]) { ... }
  function removeLayer(layerId: string) { ... }
  
  return { layers, addGeoJSONLayer, addRasterLayer, ... }
})
```

### 5.3 地图功能

**支持的图层类型**：

| 类型 | 格式 | 说明 |
|------|------|------|
| 矢量 | GeoJSON | 点、线、面数据 |
| 栅格 | PNG | GeoTIFF 转换后的 PNG |
| 栅格 | COG | Cloud Optimized GeoTIFF |

**图层管理功能**：
- 图层可见性切换
- 图层顺序调整
- 图层样式配置
- 图层删除
- 飞行到图层范围

### 5.4 数据目录与知识图谱

**数据目录功能**：
- 数据统计概览（矢量/栅格数量）
- 几何类型分布
- 搜索和筛选
- 加载到地图

**知识图谱可视化**：
- 中心辐射布局
- 动态连接线
- 数据关联展示（同区域/同类型）
- 节点详情卡片

---

## 6. 数据流程

### 6.1 完整任务执行流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           用户交互层                                     │
│                                                                         │
│    ┌──────────┐          ┌──────────┐          ┌──────────┐            │
│    │ 输入查询  │─────────▶│  提交任务 │─────────▶│ 等待结果  │            │
│    └──────────┘          └──────────┘          └──────────┘            │
│         │                      │                     ▲                  │
└─────────┼──────────────────────┼─────────────────────┼──────────────────┘
          │                      │                     │
          │  自然语言查询         │  HTTP POST          │  WebSocket
          ▼                      ▼                     │
┌─────────────────────────────────────────────────────────────────────────┐
│                            后端服务层                                    │
│                                                                         │
│    ┌──────────┐          ┌──────────┐          ┌──────────┐            │
│    │ 创建任务  │─────────▶│ 后台执行  │─────────▶│ 进度推送  │            │
│    │(Task Mgr)│          │(Workflow)│          │(WebSocket)│            │
│    └──────────┘          └──────────┘          └──────────┘            │
│                                │                                        │
└────────────────────────────────┼────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           算法引擎层                                     │
│                                                                         │
│    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐       │
│    │ 意图分析  │───▶│ 数据获取  │───▶│ 代码生成  │───▶│ 代码执行  │       │
│    └──────────┘    └──────────┘    └──────────┘    └──────────┘       │
│         │               │               │               │              │
│         │               │               │               │  执行失败    │
│         │               │               │               ▼              │
│         │               │               │         ┌──────────┐        │
│         │               │               │         │ 代码优化  │        │
│         │               │               │         │  (RAG)   │        │
│         │               │               │         └──────────┘        │
│         ▼               ▼               ▼               │              │
│    ┌───────────────────────────────────────────────────┘              │
│    │                                                                   │
│    ▼                                                                   │
│    ┌──────────────────────────────────────────────────────┐           │
│    │                    执行结果                            │           │
│    │  - 生成的代码 (Python)                                 │           │
│    │  - 输出文件 (GeoJSON/GeoTIFF)                         │           │
│    │  - 执行日志                                           │           │
│    └──────────────────────────────────────────────────────┘           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.2 数据获取流程

```
用户查询: "下载北京的道路数据"
              │
              ▼
    ┌─────────────────────┐
    │    意图分析器        │
    │  提取数据需求:       │
    │  - 区域: 北京        │
    │  - 类型: 道路        │
    │  - 格式: GeoJSON     │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │  本地向量匹配器      │
    │  检索本地数据库      │──────▶ 找到匹配? ─▶ 使用本地数据
    └──────────┬──────────┘              │
               │ 未找到                   │
               ▼                         │
    ┌─────────────────────┐              │
    │   地理查询引擎       │              │
    │  1. Nominatim 地理编码             │
    │  2. 获取边界范围     │              │
    └──────────┬──────────┘              │
               │                         │
               ▼                         │
    ┌─────────────────────┐              │
    │  数据获取引擎        │              │
    │  1. OSM Overpass API│              │
    │  2. 下载道路数据     │              │
    │  3. 保存为 GeoJSON  │              │
    └──────────┬──────────┘              │
               │                         │
               ▼                         │
    ┌─────────────────────┐              │
    │  元数据生成器        │◀─────────────┘
    │  1. 提取文件信息     │
    │  2. LLM 生成描述    │
    │  3. 更新数据目录     │
    │  4. 更新向量数据库   │
    └─────────────────────┘
```

---

## 7. API 接口

### 7.1 分析任务 API

#### 提交任务
```http
POST /api/analysis/submit
Content-Type: application/json

{
  "query": "下载北京的Sentinel-2影像并计算NDVI",
  "skip_download": false,
  "auto_run": true,
  "auto_optimize": true,
  "max_optimization_rounds": 3
}
```

**响应**：
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "任务已创建，等待处理",
  "progress": 0
}
```

#### 获取任务状态
```http
GET /api/analysis/task/{task_id}
```

**响应**：
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "message": "任务完成",
  "progress": 100,
  "output_files": [
    {
      "name": "北京_NDVI",
      "path": "output/results/ndvi_result.tif",
      "url": "/results/ndvi_result.tif",
      "type": "raster"
    }
  ]
}
```

#### 获取生成的代码
```http
GET /api/analysis/task/{task_id}/code
```

**响应**：
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "code": "from qgis.core import *\nimport processing\n...",
  "language": "python",
  "script_path": "output/generated_scripts/analysis_xxx.py"
}
```

### 7.2 数据管理 API

#### 获取文件列表
```http
GET /api/data/files?source=results&type=vector
```

#### 转换栅格文件
```http
POST /api/data/convert-existing-raster
Content-Type: application/json

{
  "file_path": "output/results/ndvi.tif"
}
```

**响应**：
```json
{
  "success": true,
  "url": "/results/png/ndvi.png",
  "bounds": [116.0, 39.5, 116.8, 40.2],
  "format": "png"
}
```

### 7.3 数据目录 API

#### 获取目录
```http
GET /api/catalog?limit=100&type=vector
```

#### 搜索数据
```http
GET /api/catalog/search?q=北京&type=vector
```

#### 获取统计
```http
GET /api/catalog/stats/summary
```

**响应**：
```json
{
  "total": 15,
  "by_type": {
    "vector": 12,
    "raster": 3,
    "other": 0
  },
  "by_geometry": {
    "Polygon": 5,
    "Point": 4,
    "LineString": 3
  }
}
```

### 7.4 WebSocket API

#### 连接任务进度
```
ws://localhost:8000/ws/task/{task_id}
```

**接收消息**：
```json
{
  "type": "progress",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "executing",
  "message": "正在执行NDVI计算...",
  "progress": 75,
  "current_step": "代码执行"
}
```

---

## 8. 部署指南

### 8.1 环境要求

| 组件 | 版本要求 |
|------|----------|
| Python | 3.10+ |
| Node.js | 18+ |
| QGIS | 3.44+ |
| 操作系统 | Windows 10/11 |

### 8.2 安装步骤

#### 1. 克隆项目
```bash
git clone https://github.com/your-repo/AutoGIS.git
cd AutoGIS/AutoGIS_main
```

#### 2. 配置 Python 环境
```bash
# 推荐使用 Conda (与 QGIS 环境兼容)
conda create -n autogis python=3.10
conda activate autogis

# 安装依赖
pip install fastapi uvicorn websockets pydantic
pip install geopandas rasterio shapely
pip install openai httpx
```

#### 3. 配置 QGIS
```yaml
# spatial_analysis_system/config.yaml
qgis:
  root_path: "D:\\QGIS 3.44.5"
  runqgis_bat_path: "D:\\QGIS 3.44.5\\bin\\runqgis.bat"
```

#### 4. 配置 LLM API
```yaml
# spatial_analysis_system/config.yaml
llm:
  api_key: "your-api-key"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  model_name: "qwen-max"
```

#### 5. 安装前端依赖
```bash
cd web
npm install
```

### 8.3 启动服务

#### 启动后端
```bash
cd AutoGIS_main
conda activate qgis344  # 激活 QGIS 兼容环境
python -m uvicorn api.main:app --host 0.0.0.0 --port 8080
```

#### 启动前端 (开发模式)
```bash
cd web
npm run dev
```

#### 构建前端 (生产模式)
```bash
npm run build
```

### 8.4 访问地址

| 服务 | 地址 |
|------|------|
| 前端应用 | http://localhost:5173 |
| 后端 API | http://localhost:8000 |
| Swagger 文档 | http://localhost:8000/docs |
| ReDoc 文档 | http://localhost:8000/redoc |

---

## 9. 配置说明

### 9.1 完整配置文件

```yaml
# spatial_analysis_system/config.yaml

# ============ LLM 配置 ============
llm:
  api_key: ""                          # API Key (必填)
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  model_name: "qwen-max"               # 模型名称
  temperature: 0.3                     # 温度参数
  max_tokens: 15000                    # 最大 token 数
  timeout: 120                         # 超时时间 (秒)

# ============ 代码生成专用 LLM ============
llm_code_generator:
  enabled: true                        # 是否启用独立模型
  api_key: ""                          # 留空则使用 llm.api_key
  base_url: ""                         # 留空则使用 llm.base_url
  model_name: "QGIS-GPT"               # 代码生成专用模型
  temperature: 0.2                     # 低温度保证代码质量
  max_tokens: 15000
  timeout: 180

# ============ 向量嵌入配置 ============
vector_embedding:
  api_key: ""                          # 留空则使用 llm.api_key
  api_url: "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
  model_name: "text-embedding-v2"      # 向量模型
  timeout: 10

# ============ 工作流配置 ============
workflow:
  skip_data_download: false            # 跳过数据下载
  auto_run_script: true                # 自动运行脚本
  auto_optimize_on_failure: true       # 失败自动优化
  max_optimization_rounds: 3           # 最大优化轮数
  use_rag_for_optimization: true       # 使用 RAG 优化

# ============ QGIS 配置 ============
qgis:
  root_path: "D:\\QGIS 3.44.5"
  runqgis_bat_path: "D:\\QGIS 3.44.5\\bin\\runqgis.bat"
  script_timeout: 300                  # 脚本超时 (秒)
  algorithm_csv_path: "data/qgis_alg_detail.3.44.5.csv"

# ============ 数据配置 ============
data:
  local_data_dir: "downloaded_data"
  data_catalog_path: "data/data_catalog.json"
  vector_db_path: "data/vector_db.json"
  raw_data_dirs:
    - "downloaded_data"
  supported_extensions:
    vector: [".shp", ".geojson", ".gpkg"]
    raster: [".tif", ".tiff", ".img"]

# ============ 输出配置 ============
output:
  script_output_dir: "output/generated_scripts"
  result_output_dir: "output/results"
  log_output_dir: "output/logs"
```

### 9.2 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `AUTOGIS_API_KEY` | LLM API Key | `sk-xxx` |
| `AUTOGIS_BASE_URL` | API 地址 | `https://...` |
| `AUTOGIS_MODEL` | 模型名称 | `qwen-max` |
| `AUTOGIS_SKIP_DOWNLOAD` | 跳过下载 | `true/false` |
| `AUTOGIS_AUTO_RUN` | 自动运行 | `true/false` |

---

## 10. 开发指南

### 10.1 添加新的分析模板

在 `code_generator.py` 中添加新模板：

```python
# spatial_analysis_system/code_generator.py

TEMPLATES = {
    # 现有模板...
    
    # 新增模板
    "spatial_join": """
from qgis.core import *
import processing

# 空间连接分析
result = processing.run("native:joinattributesbylocation", {{
    'INPUT': '{input_layer}',
    'JOIN': '{join_layer}',
    'PREDICATE': [0],  # 相交
    'METHOD': 0,       # 一对多
    'OUTPUT': '{output_path}'
}})

addMapLayer("空间连接结果", '{output_path}', "vector")
"""
}
```

### 10.2 添加新的数据源

在 `data_retrieval_engine.py` 中添加新数据源：

```python
# core/data_retrieval_engine.py

class DataRetrievalEngine:
    def retrieve(self, query: DataQuery) -> DataResult:
        if query.source == "osm":
            return self._download_from_osm(query)
        elif query.source == "sentinel":
            return self._download_from_sentinel(query)
        elif query.source == "new_source":  # 新增数据源
            return self._download_from_new_source(query)
```

### 10.3 添加新的前端组件

```vue
<!-- web/src/components/NewComponent.vue -->
<script setup lang="ts">
import { ref } from 'vue'
import { useTaskStore } from '@/stores/task'

const taskStore = useTaskStore()
</script>

<template>
  <div class="new-component">
    <!-- 组件内容 -->
  </div>
</template>
```

在 `App.vue` 中集成：
```vue
<script setup lang="ts">
import NewComponent from '@/components/NewComponent.vue'
</script>

<template>
  <NewComponent :visible="showNewComponent" @close="..." />
</template>
```

### 10.4 运行测试

```bash
# 后端测试
cd AutoGIS_main
python -m pytest tests/ -v

# 前端测试
cd web
npm run test
```

---

## 附录

### A. 支持的 QGIS 算法

系统支持所有 QGIS Processing 算法，常用的包括：

| 算法 | ID | 说明 |
|------|-----|------|
| 缓冲区 | `native:buffer` | 创建缓冲区 |
| 裁剪 | `native:clip` | 按范围裁剪 |
| 相交 | `native:intersection` | 相交分析 |
| 融合 | `native:dissolve` | 要素融合 |
| 质心 | `native:centroids` | 计算质心 |
| 重投影 | `native:reprojectlayer` | 坐标转换 |
| NDVI | `gdal:rastercalculator` | 栅格计算 |

### B. 支持的数据格式

**矢量格式**：
- GeoJSON (.geojson, .json)
- Shapefile (.shp)
- GeoPackage (.gpkg)
- GeoDatabase (.gdb)

**栅格格式**：
- GeoTIFF (.tif, .tiff)
- Cloud Optimized GeoTIFF (COG)
- JPEG2000 (.jp2)
- HDF/NetCDF

### C. 常见问题

**Q: 代码执行超时怎么办？**
A: 在 `config.yaml` 中增加 `qgis.script_timeout` 的值。

**Q: 如何使用自定义 LLM？**
A: 修改 `llm.base_url` 和 `llm.model_name`，支持所有 OpenAI 兼容 API。

**Q: 栅格数据无法在地图上显示？**
A: 系统会自动将 GeoTIFF 转换为 PNG，确保 `/api/data/convert-existing-raster` 正常工作。

---

*文档版本: v1.1.0 | 最后更新: 2026-01-15*

