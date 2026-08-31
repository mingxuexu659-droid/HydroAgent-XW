"""Typed request and response schemas for HydroAgent-XW."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HydroQueryRequest(BaseModel):
    query: str = Field(..., description="用户提出的新吴区水务分析问题", min_length=1)
    user_id: Optional[str] = Field(default=None, description="可选的上游用户标识")


class HydroSource(BaseModel):
    source: str = Field(..., description="来源文件")
    location: str = Field(default="", description="来源位置，如段落编号或数据表名")
    preview: str = Field(default="", description="证据预览")


class HydroSafety(BaseModel):
    allowed: bool = Field(..., description="安全策略是否允许继续处理")
    risk_level: str = Field(..., description="查询风险等级")
    reason: str = Field(default="", description="安全决策原因")
    matched_keywords: List[str] = Field(default_factory=list, description="命中的安全关键词")
    action: str = Field(..., description="安全动作，例如 continue 或 refuse")


class HydroMetadata(BaseModel):
    request_id: str = Field(..., description="请求唯一标识")
    latency_ms: float = Field(..., description="Agent 处理耗时，单位毫秒")


class HydroQueryResponse(BaseModel):
    intent: str = Field(..., description="识别出的任务类型")
    answer: str = Field(..., description="回答内容")
    sources: List[HydroSource] = Field(default_factory=list, description="证据来源")
    debug: Dict[str, Any] = Field(default_factory=dict, description="调试信息")
    safety: HydroSafety = Field(..., description="安全检查结果")
    metadata: HydroMetadata = Field(..., description="请求元数据")
