"""
AutoGIS API 服务主入口
"""
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

# 确保项目根目录在路径中
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from api.routers import analysis, data, catalog, hydro
from api.websocket.task_progress import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    print("HydroAgent-XW API 服务启动中...")
    print(f"项目目录: {BASE_DIR}")
    yield
    print("HydroAgent-XW API 服务关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="HydroAgent-XW API",
    description="""
## 新吴区水务多源数据智能分析 Agent API

HydroAgent-XW 是一个面向新吴区水务治理场景的多源数据智能分析 Agent，
能够分析水环境整治报告、泵闸位置、实时水务数据、运行记录、管网资料和现场照片。

### 核心功能

- **分析任务管理** - 提交、查询、取消分析任务
- **实时进度推送** - 通过 WebSocket 获取任务执行进度
- **数据文件管理** - 查看和下载分析结果
- **数据目录查询** - 搜索和浏览可用数据集

### WebSocket 端点

连接 `/ws/task/{task_id}` 可实时接收任务进度更新。
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(analysis.router, prefix="/api/analysis", tags=["分析任务"])
app.include_router(data.router, prefix="/api/data", tags=["数据管理"])
app.include_router(catalog.router, prefix="/api/catalog", tags=["数据目录"])
app.include_router(hydro.router, prefix="/api/hydro", tags=["HydroAgent-XW"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])

# 静态文件服务
results_dir = os.path.join(BASE_DIR, "output", "results")
scripts_dir = os.path.join(BASE_DIR, "output", "generated_scripts")
downloaded_dir = os.path.join(BASE_DIR, "downloaded_data")
output_dir = os.path.join(BASE_DIR, "output")

# An optional directory can be exposed only when the deployer opts in.
external_output_dir = os.environ.get("AUTOGIS_EXTERNAL_OUTPUT_DIR", "")

# COG 缓存目录
cog_cache_dir = os.path.join(output_dir, "cog_cache")

# PNG 缓存目录
png_cache_dir = os.path.join(output_dir, "png_cache")

# 确保目录存在
for dir_path in [results_dir, scripts_dir, downloaded_dir, output_dir, cog_cache_dir, png_cache_dir]:
    os.makedirs(dir_path, exist_ok=True)

# 挂载静态文件目录
app.mount("/results", StaticFiles(directory=results_dir), name="results")
app.mount("/scripts", StaticFiles(directory=scripts_dir), name="scripts")
app.mount("/downloaded", StaticFiles(directory=downloaded_dir), name="downloaded")
app.mount("/output", StaticFiles(directory=output_dir), name="output")
app.mount("/cog", StaticFiles(directory=cog_cache_dir), name="cog")
app.mount("/png", StaticFiles(directory=png_cache_dir), name="png")

# 如果外部输出目录存在，也挂载它
if os.path.exists(external_output_dir):
    os.makedirs(external_output_dir, exist_ok=True)
    app.mount("/ext-output", StaticFiles(directory=external_output_dir), name="ext-output")


@app.get("/", tags=["系统"])
async def root():
    """API 根路径，返回服务状态"""
    return {
        "service": "HydroAgent-XW API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health", tags=["系统"])
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "HydroAgent-XW API"
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "type": type(exc).__name__
        }
    )


def run_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = True):
    """运行服务器"""
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=reload
    )


if __name__ == "__main__":
    run_server()

