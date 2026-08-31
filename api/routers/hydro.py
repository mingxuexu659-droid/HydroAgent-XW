"""HydroAgent-XW domain routes."""
from fastapi import APIRouter

from api.schemas.hydro import HydroQueryRequest, HydroQueryResponse
from hydro_agent.services.hydro_query_service import hydro_query_service


router = APIRouter()


@router.post("/query", response_model=HydroQueryResponse, summary="新吴区水务 Agent 查询")
async def query_hydro_agent(request: HydroQueryRequest) -> HydroQueryResponse:
    """Query the HydroAgent-XW MVP with Xinwu water-management data."""
    return hydro_query_service.answer(request)
