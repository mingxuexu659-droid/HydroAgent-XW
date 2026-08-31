"""HydroAgent-XW API schemas.

The API layer re-exports the domain schemas so FastAPI and internal services
share one response contract.
"""
from hydro_agent.schemas.hydro import (
    HydroMetadata,
    HydroQueryRequest,
    HydroQueryResponse,
    HydroSafety,
    HydroSource,
)


__all__ = [
    "HydroMetadata",
    "HydroQueryRequest",
    "HydroQueryResponse",
    "HydroSafety",
    "HydroSource",
]
