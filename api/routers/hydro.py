"""HydroAgent-XW domain routes."""
from fastapi import APIRouter

from api.schemas.hydro import HydroQueryRequest, HydroQueryResponse
from hydro_agent.agents.simple_hydro_agent import answer_hydro_query


router = APIRouter()


@router.post("/query", response_model=HydroQueryResponse, summary="新吴区水务 Agent 查询")
async def query_hydro_agent(request: HydroQueryRequest):
    """Query the HydroAgent-XW MVP with Xinwu water-management data."""
    return answer_hydro_query(request.query)
