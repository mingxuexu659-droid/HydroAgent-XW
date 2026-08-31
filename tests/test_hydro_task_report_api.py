from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from api.routers import hydro_tasks
from hydro_agent.agents import simple_hydro_agent
from hydro_agent.tasks.task_runner import HydroTaskRunner
from hydro_agent.tasks.task_store import HydroTaskStore


def write_report_csv(processed_dir: Path) -> Path:
    csv_path = processed_dir / "realtime_Sheet1.csv"
    csv_path.write_text(
        "\n".join([
            "device_id,device_value,device_status,create_time",
            "gate_001,10,正常,2026-08-31 10:00:00",
            "gate_002,70,故障,2026-08-31 10:10:00",
        ]),
        encoding="utf-8",
    )
    return csv_path


def test_task_report_api_returns_persisted_report_payload(tmp_path, monkeypatch):
    write_report_csv(tmp_path)
    monkeypatch.setattr(simple_hydro_agent, "PROCESSED_DIR", tmp_path)
    runner = HydroTaskRunner(
        HydroTaskStore(tmp_path / "tasks.db"),
        report_dir=tmp_path / "reports",
    )
    monkeypatch.setattr(hydro_tasks, "hydro_task_runner", runner)
    client = TestClient(app)

    submit_response = client.post(
        "/api/hydro/tasks",
        json={"query": "请基于实时数据生成设备异常专题报告"},
    )
    task_id = submit_response.json()["task_id"]

    report_response = client.get(f"/api/hydro/tasks/{task_id}/report")

    assert report_response.status_code == 200
    data = report_response.json()
    assert data["task_id"] == task_id
    assert data["report"]["title"] == "设备异常专题分析报告"
    assert data["report"]["risk_level"] in {"medium", "high", "critical"}
    assert data["artifact"]["format"] == "json"


def test_task_report_api_returns_404_when_task_has_no_report(tmp_path, monkeypatch):
    runner = HydroTaskRunner(
        HydroTaskStore(tmp_path / "tasks.db"),
        report_dir=tmp_path / "reports",
    )
    monkeypatch.setattr(hydro_tasks, "hydro_task_runner", runner)
    client = TestClient(app)

    submit_response = client.post(
        "/api/hydro/tasks",
        json={"query": "新吴区实时数据里有哪些表？"},
    )
    task_id = submit_response.json()["task_id"]

    report_response = client.get(f"/api/hydro/tasks/{task_id}/report")

    assert report_response.status_code == 404


def test_task_report_api_returns_404_for_unknown_task(tmp_path, monkeypatch):
    runner = HydroTaskRunner(
        HydroTaskStore(tmp_path / "tasks.db"),
        report_dir=tmp_path / "reports",
    )
    monkeypatch.setattr(hydro_tasks, "hydro_task_runner", runner)
    client = TestClient(app)

    response = client.get("/api/hydro/tasks/not-found/report")

    assert response.status_code == 404
