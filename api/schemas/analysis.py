"""
分析任务相关的数据模型
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime


class TaskStatusEnum(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    ANALYZING = "analyzing"
    DOWNLOADING = "downloading"
    GENERATING = "generating"
    EXECUTING = "executing"
    OPTIMIZING = "optimizing"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisRequest(BaseModel):
    """分析请求模型"""
    query: str = Field(..., description="用户查询", min_length=1, max_length=2000)
    skip_download: bool = Field(False, description="是否跳过数据下载")
    auto_run: bool = Field(True, description="是否自动运行生成的脚本")
    auto_optimize: bool = Field(True, description="是否自动优化失败的代码")
    max_optimization_rounds: int = Field(3, ge=0, le=10, description="最大优化轮数")

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "下载北京的Sentinel-2影像并计算NDVI",
                "skip_download": False,
                "auto_run": True,
                "auto_optimize": True,
                "max_optimization_rounds": 3
            }
        }
    }


class OutputFile(BaseModel):
    """输出文件模型"""
    name: str = Field(..., description="文件名")
    path: str = Field(..., description="文件路径")
    url: str = Field(..., description="访问URL")
    type: str = Field(..., description="文件类型: vector, raster, script, other")
    size: int = Field(..., description="文件大小(字节)")


class LogEntry(BaseModel):
    """日志条目模型"""
    level: str = Field(..., description="日志级别: info, warning, error")
    message: str = Field(..., description="日志消息")
    timestamp: str = Field(..., description="时间戳")


class TaskResponse(BaseModel):
    """任务响应模型"""
    task_id: str = Field(..., description="任务ID")
    status: TaskStatusEnum = Field(..., description="任务状态")
    message: str = Field(..., description="状态消息")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    progress: int = Field(0, ge=0, le=100, description="进度百分比")
    current_step: Optional[str] = Field(None, description="当前步骤")
    output_files: List[OutputFile] = Field(default_factory=list, description="输出文件列表")
    logs: str = Field(default="", description="原始输出日志")
    script_path: Optional[str] = Field(None, description="生成的脚本路径")
    code: Optional[str] = Field(None, description="生成的代码")
    task_type: Optional[str] = Field(None, description="任务类型: data_download_only, data_and_code, code_only")
    downloaded_files: Optional[List[Dict[str, Any]]] = Field(None, description="下载的数据文件列表")

    model_config = {
        "json_schema_extra": {
            "example": {
                "task_id": "abc123",
                "status": "completed",
                "message": "分析完成！",
                "created_at": "2026-01-13T12:00:00",
                "updated_at": "2026-01-13T12:05:00",
                "progress": 100,
                "current_step": "完成",
                "output_files": [],
                "logs": []
            }
        }
    }


class TaskListResponse(BaseModel):
    """任务列表响应模型"""
    total: int = Field(..., description="总数")
    tasks: List[TaskResponse] = Field(..., description="任务列表")


class CodeResponse(BaseModel):
    """代码响应模型"""
    task_id: str = Field(..., description="任务ID")
    code: Optional[str] = Field(None, description="生成的代码")
    task_type: Optional[str] = Field(None, description="任务类型: data_download_only, data_and_code, code_only")
    downloaded_files: Optional[List[Dict[str, Any]]] = Field(None, description="下载的数据文件列表")
    language: str = Field("python", description="代码语言")
    script_path: Optional[str] = Field(None, description="脚本文件路径")


class TaskResultResponse(BaseModel):
    """任务结果响应模型"""
    task_id: str = Field(..., description="任务ID")
    status: TaskStatusEnum = Field(..., description="任务状态")
    output_files: List[OutputFile] = Field(default_factory=list, description="输出文件列表")
    geojson_data: Optional[Dict[str, Any]] = Field(None, description="GeoJSON数据（如果有）")

