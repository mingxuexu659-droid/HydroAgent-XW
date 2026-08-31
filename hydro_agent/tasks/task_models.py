"""Task models for persistent HydroAgent-XW jobs."""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class HydroTaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class HydroTask:
    task_id: str
    query: str
    status: HydroTaskStatus
    user_id: Optional[str]
    result: Optional[Dict[str, Any]]
    error_message: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class HydroTaskPage:
    tasks: List[HydroTask]
    total: int
    limit: int
    offset: int
