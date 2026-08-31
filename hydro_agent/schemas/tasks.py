"""Typed schemas for HydroAgent-XW async task APIs."""
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class HydroTaskSubmitRequest(BaseModel):
    query: str = Field(..., description="需要异步执行的新吴区水务分析任务", min_length=1)
    user_id: Optional[str] = Field(default=None, description="可选的上游用户标识")


class HydroTaskSubmitResponse(BaseModel):
    task_id: str
    status: str


class HydroTaskResponse(BaseModel):
    task_id: str
    query: str
    status: str
    user_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str
