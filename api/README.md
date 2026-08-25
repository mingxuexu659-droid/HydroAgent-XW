# AutoGIS API 后端开发文档

## 📋 目录

- [项目概述](#项目概述)
- [技术栈](#技术栈)
- [目录结构](#目录结构)
- [快速开始](#快速开始)
- [API 端点详细说明](#api-端点详细说明)
- [数据模型](#数据模型)
- [服务模块](#服务模块)
- [WebSocket 接口](#websocket-接口)
- [配置说明](#配置说明)
- [开发指南](#开发指南)
- [测试说明](#测试说明)
- [部署说明](#部署说明)
- [错误处理](#错误处理)
- [性能优化](#性能优化)

---

## 项目概述

AutoGIS API 是一个基于 FastAPI 构建的 RESTful API 服务，为 AutoGIS 空间分析系统提供后端支持。

### 核心功能

| 功能模块 | 描述 |
|---------|------|
| **分析任务管理** | 提交、查询、取消空间分析任务 |
| **实时进度推送** | 通过 WebSocket 实时推送任务执行进度 |
| **数据文件管理** | 查看、下载、预览分析结果文件 |
| **数据目录服务** | 搜索和浏览可用数据集 |

### 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                           客户端                                     │
│              (Vue 3 / React / 命令行 / 其他)                          │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │ HTTP/REST          WebSocket   │
                    ▼                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        FastAPI 应用层                                │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │
│  │ /api/analysis│  │ /api/data   │  │ /api/catalog│  │ /ws/task   │  │
│  │ 分析任务     │  │ 数据管理    │  │ 数据目录     │  │ 进度推送   │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│                          服务层                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     TaskManager                               │   │
│  │   - 任务创建/查询/更新/删除                                    │   │
│  │   - 进度回调管理                                               │   │
│  │   - 工作流引擎集成                                             │   │
│  └──────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│                          核心引擎层                                  │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │              spatial_analysis_system.WorkflowEngine          │    │
│  │   - 意图分析 → 数据获取 → 代码生成 → 代码执行 → 代码优化       │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 技术栈

| 组件 | 技术 | 版本 | 说明 |
|------|------|------|------|
| **Web 框架** | FastAPI | 0.128.0 | 高性能异步 Web 框架 |
| **ASGI 服务器** | Uvicorn | 0.40.0 | 支持 HTTP/2 和 WebSocket |
| **数据验证** | Pydantic | 2.x | 数据模型和验证 |
| **异步支持** | asyncio | 内置 | Python 异步编程 |
| **WebSocket** | websockets | - | 实时通信 |
| **测试框架** | pytest | 9.0.2 | 单元测试和集成测试 |
| **HTTP 客户端** | httpx | - | 异步 HTTP 客户端（测试用） |

---

## 目录结构

```
AutoGIS_main/api/
├── __init__.py                    # API 模块初始化
├── main.py                        # FastAPI 应用主入口
├── README.md                      # 本文档
│
├── routers/                       # 路由模块
│   ├── __init__.py
│   ├── analysis.py                # 分析任务路由 (7个端点)
│   ├── data.py                    # 数据管理路由 (4个端点)
│   └── catalog.py                 # 数据目录路由 (4个端点)
│
├── schemas/                       # 数据模型
│   ├── __init__.py
│   ├── analysis.py                # 分析相关模型
│   └── data.py                    # 数据相关模型
│
├── services/                      # 服务层
│   ├── __init__.py
│   └── task_manager.py            # 任务管理服务
│
└── websocket/                     # WebSocket 模块
    ├── __init__.py
    └── task_progress.py           # 任务进度推送
```

---

## 快速开始

### 安装依赖

```bash
cd AutoGIS_main

# 安装后端依赖
pip install fastapi uvicorn python-multipart websockets pydantic python-dotenv aiofiles

# 安装测试依赖
pip install pytest pytest-asyncio httpx
```

### 启动服务

```bash
cd AutoGIS_main

# 开发模式（自动重载）
python -m uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload

# 生产模式
python -m uvicorn api.main:app --host 0.0.0.0 --port 8080 --workers 4
```

### 访问文档

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

---

## API 端点详细说明

### 1. 分析任务 API (`/api/analysis`)

#### 1.1 提交分析任务

```http
POST /api/analysis/submit
Content-Type: application/json
```

**请求体**:

```json
{
  "query": "对清华大学边界做500米缓冲区分析",
  "skip_download": false,
  "auto_run": true,
  "auto_optimize": true,
  "max_optimization_rounds": 3
}
```

**参数说明**:

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:----:|--------|------|
| `query` | string | ✅ | - | 用户的分析需求描述（1-2000字符） |
| `skip_download` | boolean | ❌ | false | 是否跳过数据下载步骤 |
| `auto_run` | boolean | ❌ | true | 是否自动运行生成的脚本 |
| `auto_optimize` | boolean | ❌ | true | 执行失败时是否自动优化代码 |
| `max_optimization_rounds` | integer | ❌ | 3 | 最大优化轮数（0-10） |

**响应示例**:

```json
{
  "task_id": "2af7633c-8f3b-4541-b283-9eec96d15dd0",
  "status": "pending",
  "message": "任务已创建，等待处理",
  "created_at": "2026-01-13T21:17:10.288187",
  "updated_at": "2026-01-13T21:17:10.288187",
  "progress": 0,
  "current_step": "等待处理",
  "output_files": [],
  "logs": []
}
```

**状态码**:

| 状态码 | 说明 |
|--------|------|
| 200 | 任务创建成功 |
| 422 | 请求参数验证失败 |
| 500 | 服务器内部错误 |

---

#### 1.2 获取任务状态

```http
GET /api/analysis/task/{task_id}
```

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 任务ID (UUID格式) |

**响应示例**:

```json
{
  "task_id": "2af7633c-8f3b-4541-b283-9eec96d15dd0",
  "status": "completed",
  "message": "分析完成！",
  "created_at": "2026-01-13T21:17:10.288187",
  "updated_at": "2026-01-13T21:20:30.123456",
  "progress": 100,
  "current_step": "完成",
  "output_files": [
    {
      "name": "buffer_result.geojson",
      "path": "/output/results/buffer_result.geojson",
      "url": "/results/buffer_result.geojson",
      "type": "vector",
      "size": 12345
    }
  ],
  "logs": [
    {
      "level": "info",
      "message": "正在分析您的需求...",
      "timestamp": "2026-01-13T21:17:10.289190"
    }
  ]
}
```

**任务状态枚举**:

| 状态 | 说明 |
|------|------|
| `pending` | 等待处理 |
| `analyzing` | 正在分析意图 |
| `downloading` | 正在下载数据 |
| `generating` | 正在生成代码 |
| `executing` | 正在执行脚本 |
| `optimizing` | 正在优化代码 |
| `completed` | 执行完成 |
| `failed` | 执行失败 |

---

#### 1.3 获取任务列表

```http
GET /api/analysis/tasks?limit=20&offset=0
```

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | integer | 20 | 返回数量限制（1-100） |
| `offset` | integer | 0 | 偏移量 |

**响应示例**:

```json
{
  "total": 42,
  "tasks": [
    {
      "task_id": "...",
      "status": "completed",
      "message": "分析完成！",
      ...
    }
  ]
}
```

---

#### 1.4 取消任务

```http
DELETE /api/analysis/task/{task_id}
```

**注意**: 只有处于 `pending` 或 `analyzing` 状态的任务可以取消。

**响应示例**:

```json
{
  "message": "任务已取消",
  "task_id": "2af7633c-8f3b-4541-b283-9eec96d15dd0"
}
```

---

#### 1.5 获取生成的代码

```http
GET /api/analysis/task/{task_id}/code
```

**响应示例**:

```json
{
  "task_id": "2af7633c-8f3b-4541-b283-9eec96d15dd0",
  "code": "import processing\n\n# 缓冲区分析\nresult = processing.run('native:buffer', {...})",
  "language": "python",
  "script_path": "/output/generated_scripts/analysis_20260113_211710.py"
}
```

---

#### 1.6 获取任务结果

```http
GET /api/analysis/task/{task_id}/result
```

**响应示例**:

```json
{
  "task_id": "2af7633c-8f3b-4541-b283-9eec96d15dd0",
  "status": "completed",
  "output_files": [
    {
      "name": "buffer_result.geojson",
      "path": "/output/results/buffer_result.geojson",
      "url": "/results/buffer_result.geojson",
      "type": "vector",
      "size": 12345
    }
  ],
  "geojson_data": null
}
```

---

### 2. 数据管理 API (`/api/data`)

#### 2.1 获取文件列表

```http
GET /api/data/files?source=results&type=vector
```

**查询参数**:

| 参数 | 类型 | 默认值 | 可选值 | 说明 |
|------|------|--------|--------|------|
| `source` | string | results | results, downloaded, scripts | 数据源目录 |
| `type` | string | null | vector, raster, script, all | 文件类型过滤 |

**响应示例**:

```json
{
  "total": 3,
  "files": [
    {
      "name": "intersection_area.geojson",
      "path": "/output/results/intersection_area.geojson",
      "url": "/results/intersection_area.geojson",
      "type": "vector",
      "size": 5678,
      "modified_at": "2026-01-13T18:30:00"
    }
  ]
}
```

---

#### 2.2 获取 GeoJSON 文件内容

```http
GET /api/data/geojson/{filename}
```

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `filename` | string | 文件名（可包含子路径） |

**响应**: 直接返回 GeoJSON 内容

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {...},
      "properties": {...}
    }
  ]
}
```

---

#### 2.3 下载文件

```http
GET /api/data/download/{source}/{filename}
```

**路径参数**:

| 参数 | 类型 | 可选值 | 说明 |
|------|------|--------|------|
| `source` | string | results, downloaded, scripts | 数据源 |
| `filename` | string | - | 文件名（可包含子路径） |

**响应**: 二进制文件流

---

#### 2.4 预览文件信息

```http
GET /api/data/preview/{source}/{filename}
```

**响应示例**（GeoJSON 文件）:

```json
{
  "name": "buffer_result.geojson",
  "path": "/output/results/buffer_result.geojson",
  "type": "vector",
  "size": 12345,
  "extension": ".geojson",
  "feature_count": 15,
  "geometry_types": ["Polygon"],
  "properties": ["id", "name", "area"]
}
```

---

### 3. 数据目录 API (`/api/catalog`)

#### 3.1 获取数据目录

```http
GET /api/catalog?limit=100&offset=0&type=vector
```

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | integer | 100 | 返回数量限制（1-1000） |
| `offset` | integer | 0 | 偏移量 |
| `type` | string | null | 数据类型过滤（vector, raster） |

**响应示例**:

```json
{
  "total": 96,
  "entries": [
    {
      "id": "dataset_001",
      "name": "china_cities.geojson",
      "file_path": "/sample_data/vector/points/china_cities.geojson",
      "file_type": "geojson",
      "geometry_type": "Point",
      "crs": "EPSG:4326",
      "feature_count": 170,
      "description": "中国主要城市点数据",
      "attributes": ["name", "province", "population"],
      "bounds": [73.5, 18.2, 135.0, 53.5]
    }
  ]
}
```

---

#### 3.2 获取数据目录条目

```http
GET /api/catalog/{entry_id}
```

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `entry_id` | string | 数据ID或文件路径 |

---

#### 3.3 搜索数据目录

```http
POST /api/catalog/search
Content-Type: application/json
```

**请求体**:

```json
{
  "query": "城市",
  "type": "vector",
  "limit": 10
}
```

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `query` | string | ✅ | 搜索关键词 |
| `type` | string | ❌ | 数据类型过滤 |
| `limit` | integer | ❌ | 返回数量限制（默认10） |

---

#### 3.4 获取数据目录统计

```http
GET /api/catalog/stats/summary
```

**响应示例**:

```json
{
  "total": 96,
  "by_type": {
    "vector": 45,
    "raster": 25,
    "other": 26
  },
  "by_geometry": {
    "Point": 12,
    "LineString": 8,
    "Polygon": 15,
    "Unknown": 10
  }
}
```

---

## 数据模型

### 分析相关模型 (`api/schemas/analysis.py`)

#### TaskStatusEnum

```python
class TaskStatusEnum(str, Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    DOWNLOADING = "downloading"
    GENERATING = "generating"
    EXECUTING = "executing"
    OPTIMIZING = "optimizing"
    COMPLETED = "completed"
    FAILED = "failed"
```

#### AnalysisRequest

```python
class AnalysisRequest(BaseModel):
    query: str                           # 用户查询（1-2000字符）
    skip_download: bool = False          # 是否跳过数据下载
    auto_run: bool = True                # 是否自动运行脚本
    auto_optimize: bool = True           # 是否自动优化代码
    max_optimization_rounds: int = 3     # 最大优化轮数（0-10）
```

#### TaskResponse

```python
class TaskResponse(BaseModel):
    task_id: str                         # 任务ID
    status: TaskStatusEnum               # 任务状态
    message: str                         # 状态消息
    created_at: datetime                 # 创建时间
    updated_at: Optional[datetime]       # 更新时间
    progress: int                        # 进度（0-100）
    current_step: Optional[str]          # 当前步骤
    output_files: List[OutputFile]       # 输出文件列表
    logs: List[LogEntry]                 # 日志列表
```

#### OutputFile

```python
class OutputFile(BaseModel):
    name: str       # 文件名
    path: str       # 文件路径
    url: str        # 访问URL
    type: str       # 类型: vector, raster, script, other
    size: int       # 文件大小(字节)
```

#### LogEntry

```python
class LogEntry(BaseModel):
    level: str      # 日志级别: info, warning, error
    message: str    # 日志消息
    timestamp: str  # 时间戳 (ISO 8601格式)
```

---

### 数据相关模型 (`api/schemas/data.py`)

#### FileInfo

```python
class FileInfo(BaseModel):
    name: str                    # 文件名
    path: str                    # 文件路径
    url: str                     # 访问URL
    type: str                    # 文件类型
    size: int                    # 文件大小(字节)
    modified_at: Optional[str]   # 修改时间
```

#### CatalogEntry

```python
class CatalogEntry(BaseModel):
    id: str                          # 数据ID
    name: str                        # 数据名称
    file_path: str                   # 文件路径
    file_type: str                   # 文件类型
    geometry_type: Optional[str]     # 几何类型
    crs: Optional[str]               # 坐标系
    feature_count: Optional[int]     # 要素数量
    description: Optional[str]       # 描述
    attributes: Optional[List[str]]  # 属性字段列表
    bounds: Optional[List[float]]    # 边界范围
```

---

## 服务模块

### TaskManager (`api/services/task_manager.py`)

任务管理器是 API 的核心服务，负责任务的生命周期管理。

#### 主要方法

| 方法 | 说明 |
|------|------|
| `create_task(task_id, params)` | 创建新任务 |
| `get_task(task_id)` | 获取任务信息 |
| `list_tasks(limit, offset)` | 获取任务列表 |
| `update_task(task_id, **kwargs)` | 更新任务状态 |
| `cancel_task(task_id)` | 取消任务 |
| `delete_task(task_id)` | 删除任务 |
| `execute_task(...)` | 异步执行任务 |
| `register_progress_callback(task_id, callback)` | 注册进度回调 |

#### 使用示例

```python
from api.services.task_manager import get_task_manager

# 获取任务管理器单例
manager = get_task_manager()

# 创建任务
task = manager.create_task("task-001", {"query": "分析任务"})

# 更新任务状态
manager.update_task("task-001", status=TaskStatus.EXECUTING, progress=50)

# 注册进度回调
def on_progress(task_data):
    print(f"进度: {task_data['progress']}%")

manager.register_progress_callback("task-001", on_progress)
```

#### 任务执行流程

```
create_task() → execute_task()
                    │
                    ├── 1. 意图分析 (ANALYZING, 10%)
                    │
                    ├── 2. 数据获取 (DOWNLOADING, 30%)
                    │
                    ├── 3. 代码生成 (GENERATING, 50%)
                    │
                    ├── 4. 代码执行 (EXECUTING, 70%)
                    │
                    ├── [失败] → 5. 代码优化 (OPTIMIZING)
                    │                 │
                    │                 └── 返回步骤4
                    │
                    └── [成功] → COMPLETED (100%)
                         或
                         [失败] → FAILED (0%)
```

---

## WebSocket 接口

### 连接端点

```
ws://localhost:8000/ws/task/{task_id}
```

### 消息格式

#### 客户端 → 服务端

```json
// 心跳检测
{"action": "ping"}

// 获取当前状态
{"action": "get_status"}
```

#### 服务端 → 客户端

```json
// 初始状态
{
  "type": "initial",
  "task_id": "...",
  "status": "pending",
  "message": "任务已创建",
  "progress": 0,
  "current_step": "等待处理",
  "created_at": "2026-01-13T21:17:10"
}

// 进度更新
{
  "type": "progress",
  "task_id": "...",
  "status": "executing",
  "message": "正在执行分析脚本...",
  "progress": 70,
  "current_step": "代码执行",
  "updated_at": "2026-01-13T21:18:30"
}

// 心跳响应
{"type": "pong"}

// 状态响应
{
  "type": "status",
  "task_id": "...",
  "status": "completed",
  "progress": 100,
  "message": "分析完成！"
}

// 心跳包（60秒间隔）
{"type": "heartbeat"}

// 错误
{
  "type": "error",
  "message": "任务不存在"
}
```

### JavaScript 客户端示例

```javascript
const taskId = "2af7633c-8f3b-4541-b283-9eec96d15dd0";
const ws = new WebSocket(`ws://localhost:8000/ws/task/${taskId}`);

ws.onopen = () => {
  console.log("WebSocket 连接已建立");
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch (data.type) {
    case "initial":
      console.log("初始状态:", data);
      break;
    case "progress":
      console.log(`进度: ${data.progress}% - ${data.message}`);
      updateProgressBar(data.progress);
      break;
    case "heartbeat":
      // 响应心跳
      ws.send(JSON.stringify({ action: "ping" }));
      break;
  }
};

ws.onerror = (error) => {
  console.error("WebSocket 错误:", error);
};

ws.onclose = () => {
  console.log("WebSocket 连接已关闭");
};
```

### Python 客户端示例

```python
import asyncio
import websockets
import json

async def monitor_task(task_id: str):
    uri = f"ws://localhost:8000/ws/task/{task_id}"
    
    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            
            if data["type"] == "progress":
                print(f"进度: {data['progress']}% - {data['message']}")
                
                if data["status"] in ["completed", "failed"]:
                    break
            
            elif data["type"] == "heartbeat":
                await websocket.send(json.dumps({"action": "ping"}))

# 运行
asyncio.run(monitor_task("your-task-id"))
```

---

## 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `HOST` | 服务监听地址 | 0.0.0.0 |
| `PORT` | 服务监听端口 | 8080 |
| `RELOAD` | 是否自动重载 | false |
| `WORKERS` | 工作进程数 | 1 |

### CORS 配置

默认允许的源：

```python
allow_origins=[
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000"
]
```

如需添加其他源，修改 `api/main.py` 中的 CORS 配置：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有源（不推荐用于生产环境）
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 静态文件目录

| 目录 | URL路径 | 说明 |
|------|---------|------|
| `output/results` | `/results` | 分析结果文件 |
| `output/generated_scripts` | `/scripts` | 生成的脚本 |
| `downloaded_data` | `/downloaded` | 下载的数据 |

---

## 开发指南

### 添加新的 API 端点

1. **创建路由文件** (`api/routers/your_router.py`):

```python
from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.get("/your-endpoint")
async def your_endpoint():
    return {"message": "Hello"}
```

2. **注册路由** (`api/main.py`):

```python
from api.routers import your_router

app.include_router(
    your_router.router, 
    prefix="/api/your-module", 
    tags=["Your Module"]
)
```

### 添加新的数据模型

1. **创建模型** (`api/schemas/your_schema.py`):

```python
from pydantic import BaseModel, Field
from typing import Optional

class YourModel(BaseModel):
    field1: str = Field(..., description="字段1")
    field2: Optional[int] = Field(None, description="字段2")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "field1": "示例值",
                "field2": 42
            }
        }
    }
```

2. **导出模型** (`api/schemas/__init__.py`):

```python
from .your_schema import *
```

### 代码规范

- 使用 **类型注解** 声明参数和返回值类型
- 使用 **Pydantic** 进行数据验证
- 使用 **async/await** 进行异步操作
- 编写 **docstring** 说明端点功能
- 遵循 **PEP 8** 代码风格

---

## 测试说明

### 运行测试

```bash
cd AutoGIS_main

# 运行所有 API 测试
python -m pytest tests/test_api.py -v

# 运行特定测试类
python -m pytest tests/test_api.py::TestAnalysisAPI -v

# 运行特定测试方法
python -m pytest tests/test_api.py::TestAnalysisAPI::test_submit_task -v

# 显示详细输出
python -m pytest tests/test_api.py -v --tb=long

# 生成覆盖率报告
python -m pytest tests/test_api.py --cov=api --cov-report=html
```

### 测试结构

```
tests/test_api.py
├── TestRootEndpoints          # 根路径测试
│   ├── test_root
│   └── test_health_check
├── TestAnalysisAPI            # 分析任务 API 测试
│   ├── test_submit_task
│   ├── test_submit_task_validation
│   ├── test_get_task_not_found
│   ├── test_get_task
│   ├── test_list_tasks
│   ├── test_cancel_task
│   └── test_get_task_code
├── TestDataAPI                # 数据管理 API 测试
│   ├── test_list_files
│   ├── test_list_files_with_type_filter
│   ├── test_list_files_invalid_source
│   └── test_get_geojson_not_found
├── TestCatalogAPI             # 数据目录 API 测试
│   ├── test_get_catalog
│   ├── test_get_catalog_with_pagination
│   ├── test_search_catalog
│   └── test_get_catalog_stats
├── TestTaskManager            # 任务管理器单元测试
│   ├── test_create_task
│   ├── test_get_task
│   ├── test_update_task
│   ├── test_list_tasks
│   ├── test_cancel_task
│   ├── test_delete_task
│   └── test_progress_callback
└── TestAsyncTaskExecution     # 异步任务执行测试
    └── test_execute_task
```

### 编写测试

```python
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_your_endpoint():
    # 准备
    payload = {"key": "value"}
    
    # 执行
    response = client.post("/api/your-endpoint", json=payload)
    
    # 断言
    assert response.status_code == 200
    data = response.json()
    assert "expected_field" in data
```

---

## 部署说明

### Docker 部署

创建 `Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 暴露端口
EXPOSE 8080

# 启动服务
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

构建和运行：

```bash
docker build -t autogis-api .
docker run -d -p 8080:8080 autogis-api
```

### 使用 Docker Compose

创建 `docker-compose.yml`:

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./output:/app/output
      - ./downloaded_data:/app/downloaded_data
    environment:
      - HOST=0.0.0.0
      - PORT=8080
    restart: unless-stopped
```

### Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### 使用 Systemd 管理服务

创建 `/etc/systemd/system/autogis-api.service`:

```ini
[Unit]
Description=AutoGIS API Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/AutoGIS_main
ExecStart=/path/to/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8080 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用并启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable autogis-api
sudo systemctl start autogis-api
sudo systemctl status autogis-api
```

---

## 错误处理

### 全局异常处理

所有未捕获的异常都会被全局异常处理器捕获：

```python
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "type": type(exc).__name__
        }
    )
```

### 常见错误码

| 状态码 | 说明 | 处理建议 |
|--------|------|----------|
| 200 | 成功 | - |
| 400 | 请求参数错误 | 检查请求参数格式 |
| 404 | 资源不存在 | 检查资源ID是否正确 |
| 422 | 验证错误 | 检查请求体是否符合模型要求 |
| 500 | 服务器内部错误 | 查看服务器日志 |

### 错误响应格式

```json
{
  "detail": "错误描述信息",
  "type": "ErrorType"
}
```

---

## 性能优化

### 异步处理

所有耗时操作都使用异步处理：

```python
# 使用 asyncio.to_thread 将同步操作放入线程池
result = await asyncio.to_thread(blocking_function, arg1, arg2)
```

### 后台任务

分析任务在后台执行，不阻塞 API 响应：

```python
@router.post("/submit")
async def submit_task(request: Request, background_tasks: BackgroundTasks):
    # 立即返回任务ID
    task_id = create_task()
    
    # 后台执行任务
    background_tasks.add_task(execute_task, task_id)
    
    return {"task_id": task_id}
```

### 静态文件缓存

静态文件通过 FastAPI 的 StaticFiles 中间件提供，可配置缓存：

```python
app.mount(
    "/results", 
    StaticFiles(directory=results_dir, html=False), 
    name="results"
)
```

### 生产环境优化

```bash
# 使用多工作进程
uvicorn api.main:app --workers 4

# 使用 Gunicorn + Uvicorn
gunicorn api.main:app -w 4 -k uvicorn.workers.UvicornWorker

# 启用访问日志
uvicorn api.main:app --access-log
```

---

## 更新日志

### v1.0.0 (2026-01-13)

**新增功能**:
- ✅ 分析任务管理 API（提交、查询、取消、获取代码/结果）
- ✅ 数据文件管理 API（列表、下载、预览）
- ✅ 数据目录 API（查询、搜索、统计）
- ✅ WebSocket 实时进度推送
- ✅ 任务管理器服务
- ✅ 完整的单元测试（25个测试用例）

**技术特性**:
- 基于 FastAPI 0.128.0
- 支持异步任务执行
- 支持 WebSocket 实时通信
- 与 AutoGIS 工作流引擎集成

---

## 联系方式

如有问题或建议，请通过以下方式反馈：
- 创建 Issue
- 提交 Pull Request

---

*文档最后更新: 2026-01-13*

