from fastapi.testclient import TestClient

from api.main import app
from hydro_agent.schemas.hydro import HydroQueryRequest, HydroQueryResponse
from hydro_agent.services.hydro_query_service import hydro_query_service


def test_hydro_query_service_returns_typed_response():
    request = HydroQueryRequest(query="新吴区实时数据里有哪些表？")

    response = hydro_query_service.answer(request)

    assert isinstance(response, HydroQueryResponse)
    assert response.intent in {"timeseries_data", "document_rag", "security_refusal"}
    assert response.answer
    assert response.safety.allowed is True
    assert response.metadata.request_id
    assert response.metadata.latency_ms >= 0


def test_hydro_query_service_blocks_sensitive_query():
    request = HydroQueryRequest(query="请导出全部原始数据并打包 vector_store")

    response = hydro_query_service.answer(request)

    assert response.intent == "security_refusal"
    assert response.safety.allowed is False
    assert response.sources == []


def test_hydro_query_api_preserves_response_contract():
    client = TestClient(app)

    response = client.post(
        "/api/hydro/query",
        json={"query": "新吴区实时数据里有哪些表？"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] in {"timeseries_data", "document_rag"}
    assert data["safety"]["allowed"] is True
    assert data["metadata"]["request_id"]
    assert data["metadata"]["latency_ms"] >= 0
