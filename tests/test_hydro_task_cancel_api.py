from fastapi.testclient import TestClient

from api.main import app
from api.routers import hydro_tasks
from hydro_agent.tasks.task_models import HydroTaskStatus
from hydro_agent.tasks.task_runner import HydroTaskRunner
from hydro_agent.tasks.task_store import HydroTaskStore


def test_task_store_cancels_pending_task(tmp_path):
    store = HydroTaskStore(tmp_path / "tasks.db")
    task = store.create_task("待取消任务")

    cancelled = store.cancel_task(task.task_id)

    assert cancelled.status == HydroTaskStatus.CANCELLED
    assert cancelled.error_message == "Task cancelled by user"
    assert store.get_task(task.task_id).status == HydroTaskStatus.CANCELLED


def test_task_store_does_not_cancel_completed_task(tmp_path):
    store = HydroTaskStore(tmp_path / "tasks.db")
    task = store.create_task("已完成任务")
    store.mark_completed(task.task_id, {"answer": "done"})

    cancelled = store.cancel_task(task.task_id)

    assert cancelled.status == HydroTaskStatus.COMPLETED
    assert cancelled.result == {"answer": "done"}


def test_task_cancel_api_cancels_existing_task(tmp_path, monkeypatch):
    runner = HydroTaskRunner(HydroTaskStore(tmp_path / "tasks.db"))
    monkeypatch.setattr(hydro_tasks, "hydro_task_runner", runner)
    task = runner.submit("待取消任务")
    client = TestClient(app)

    response = client.post(f"/api/hydro/tasks/{task.task_id}/cancel")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "CANCELLED"
    assert data["error_message"] == "Task cancelled by user"


def test_task_cancel_api_returns_404_for_unknown_task(tmp_path, monkeypatch):
    runner = HydroTaskRunner(HydroTaskStore(tmp_path / "tasks.db"))
    monkeypatch.setattr(hydro_tasks, "hydro_task_runner", runner)
    client = TestClient(app)

    response = client.post("/api/hydro/tasks/not-found/cancel")

    assert response.status_code == 404
