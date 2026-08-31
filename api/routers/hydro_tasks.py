"""HydroAgent-XW asynchronous task routes."""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from hydro_agent.schemas.tasks import (
    HydroTaskListResponse,
    HydroTaskResponse,
    HydroTaskSubmitRequest,
    HydroTaskSubmitResponse,
)
from hydro_agent.tasks.task_models import HydroTask
from hydro_agent.tasks.task_runner import hydro_task_runner


router = APIRouter()


@router.post("/tasks", response_model=HydroTaskSubmitResponse, summary="提交水务异步分析任务")
async def submit_hydro_task(
    request: HydroTaskSubmitRequest,
    background_tasks: BackgroundTasks,
) -> HydroTaskSubmitResponse:
    """Submit a long-running HydroAgent-XW task and return its task id."""
    task = hydro_task_runner.submit(query=request.query, user_id=request.user_id)
    background_tasks.add_task(hydro_task_runner.run, task.task_id)
    return HydroTaskSubmitResponse(task_id=task.task_id, status=task.status.value)


@router.get("/tasks", response_model=HydroTaskListResponse, summary="分页查询水务异步分析任务")
async def list_hydro_tasks(
    status: Optional[str] = Query(default=None, description="可选任务状态过滤"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> HydroTaskListResponse:
    """List persisted HydroAgent-XW tasks for operational visibility."""
    try:
        page = hydro_task_runner.list(status=status, limit=limit, offset=offset)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return HydroTaskListResponse(
        tasks=[_task_to_response(task) for task in page.tasks],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/tasks/{task_id}", response_model=HydroTaskResponse, summary="查询水务异步分析任务")
async def get_hydro_task(task_id: str) -> HydroTaskResponse:
    """Read the latest persisted state for a HydroAgent-XW task."""
    task = hydro_task_runner.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Hydro task not found")
    return _task_to_response(task)


def _task_to_response(task: HydroTask) -> HydroTaskResponse:
    return HydroTaskResponse(
        task_id=task.task_id,
        query=task.query,
        status=task.status.value,
        user_id=task.user_id,
        result=task.result,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )
