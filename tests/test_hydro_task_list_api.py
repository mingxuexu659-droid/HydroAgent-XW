from fastapi.testclient import TestClient

from api.main import app
from api.routers import hydro_tasks
from hydro_agent.tasks.task_runner import HydroTaskRunner
from hydro_agent.tasks.task_store import HydroTaskStore


def test_task_store_lists_tasks_newest_first_with_pagination(tmp_path):
    store = HydroTaskStore(tmp_path / "tasks.db")
    first = store.create_task("第一个任务")
    second = store.create_task("第二个任务")
    third = store.create_task("第三个任务")

    page = store.list_tasks(limit=2, offset=0)

    assert page.total == 3
    assert [task.task_id for task in page.tasks] == [third.task_id, second.task_id]

    next_page = store.list_tasks(limit=2, offset=2)

    assert next_page.total == 3
    assert [task.task_id for task in next_page.tasks] == [first.task_id]


def test_task_store_filters_tasks_by_status(tmp_path):
    store = HydroTaskStore(tmp_path / "tasks.db")
    pending = store.create_task("待执行任务")
    completed = store.create_task("已完成任务")
    store.mark_completed(completed.task_id, {"answer": "done"})

    page = store.list_tasks(status="COMPLETED", limit=10, offset=0)

    assert page.total == 1
    assert [task.task_id for task in page.tasks] == [completed.task_id]
    assert pending.task_id not in [task.task_id for task in page.tasks]


def test_task_list_api_returns_paginated_tasks(tmp_path, monkeypatch):
    runner = HydroTaskRunner(HydroTaskStore(tmp_path / "tasks.db"))
    monkeypatch.setattr(hydro_tasks, "hydro_task_runner", runner)
    client = TestClient(app)

    for index in range(3):
        client.post("/api/hydro/tasks", json={"query": f"批量分析任务 {index}"})

    response = client.get("/api/hydro/tasks?limit=2&offset=0")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["tasks"]) == 2


def test_task_list_api_filters_by_status(tmp_path, monkeypatch):
    runner = HydroTaskRunner(HydroTaskStore(tmp_path / "tasks.db"))
    monkeypatch.setattr(hydro_tasks, "hydro_task_runner", runner)
    client = TestClient(app)

    client.post("/api/hydro/tasks", json={"query": "批量分析任务"})

    response = client.get("/api/hydro/tasks?status=COMPLETED")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["tasks"][0]["status"] == "COMPLETED"
