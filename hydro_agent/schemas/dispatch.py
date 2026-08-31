"""Typed schemas for HydroAgent-XW dispatch APIs."""
from typing import Optional

from pydantic import BaseModel, Field

from hydro_agent.schemas.hydro import HydroQueryResponse


class HydroDispatchRequest(BaseModel):
    query: str = Field(..., description="需要智能分流的新吴区水务请求", min_length=1)
    user_id: Optional[str] = Field(default=None, description="可选的上游用户标识")


class HydroDispatchResponse(BaseModel):
    mode: str = Field(..., description="执行模式：sync、async 或 reject")
    reason: str = Field(..., description="执行模式判定原因")
    matched_keywords: list[str] = Field(default_factory=list, description="命中的分流关键词")
    task_id: Optional[str] = Field(default=None, description="异步任务 ID")
    response: Optional[HydroQueryResponse] = Field(default=None, description="同步或拒绝请求的直接响应")
