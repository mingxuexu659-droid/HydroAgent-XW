"""HydroAgent-XW intelligent dispatch routes."""
from fastapi import APIRouter, BackgroundTasks

from hydro_agent.schemas.dispatch import HydroDispatchRequest, HydroDispatchResponse
from hydro_agent.schemas.hydro import HydroQueryRequest
from hydro_agent.services.hydro_query_service import hydro_query_service
from hydro_agent.tasks.task_classifier import HydroExecutionMode, classify_execution_mode
from hydro_agent.tasks.task_runner import hydro_task_runner


router = APIRouter()


@router.post("/dispatch", response_model=HydroDispatchResponse, summary="智能分流水务请求")
async def dispatch_hydro_request(
    request: HydroDispatchRequest,
    background_tasks: BackgroundTasks,
) -> HydroDispatchResponse:
    """Dispatch a HydroAgent-XW request to sync handling, async task, or refusal."""
    decision = classify_execution_mode(request.query)

    if decision.mode == HydroExecutionMode.ASYNC:
        task = hydro_task_runner.submit(query=request.query, user_id=request.user_id)
        background_tasks.add_task(hydro_task_runner.run, task.task_id)
        return HydroDispatchResponse(
            mode=decision.mode.value,
            reason=decision.reason,
            matched_keywords=decision.matched_keywords,
            task_id=task.task_id,
            response=None,
        )

    response = hydro_query_service.answer(
        HydroQueryRequest(query=request.query, user_id=request.user_id)
    )
    return HydroDispatchResponse(
        mode=decision.mode.value,
        reason=decision.reason,
        matched_keywords=decision.matched_keywords,
        task_id=None,
        response=response,
    )
