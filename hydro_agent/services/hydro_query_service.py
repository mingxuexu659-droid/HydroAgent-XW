"""Service layer for HydroAgent-XW query handling."""
from hydro_agent.agents.simple_hydro_agent import answer_hydro_query
from hydro_agent.schemas.hydro import HydroQueryRequest, HydroQueryResponse


class HydroQueryService:
    """Coordinate request validation and HydroAgent execution."""

    def answer(self, request: HydroQueryRequest) -> HydroQueryResponse:
        raw_result = answer_hydro_query(request.query)
        return HydroQueryResponse.model_validate(raw_result)


hydro_query_service = HydroQueryService()
