"""HydroAgent-XW API schemas."""
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class HydroQueryRequest(BaseModel):
    query: str = Field(..., description="用户提出的新吴区水务分析问题", min_length=1)


class HydroSource(BaseModel):
    source: str = Field(..., description="来源文件")
    location: str = Field(..., description="来源位置，如段落编号或数据表名")
    preview: str = Field(..., description="证据预览")


class HydroQueryResponse(BaseModel):
    intent: str = Field(..., description="识别出的任务类型")
    answer: str = Field(..., description="回答内容")
    sources: List[HydroSource] = Field(default_factory=list, description="证据来源")
    debug: Dict[str, Any] = Field(default_factory=dict, description="调试信息")
