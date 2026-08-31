"""Task runner for HydroAgent-XW asynchronous jobs."""
from pathlib import Path

from hydro_agent.schemas.hydro import HydroQueryRequest
from hydro_agent.services.hydro_query_service import hydro_query_service
from hydro_agent.tasks.task_models import HydroTask, HydroTaskPage
from hydro_agent.tasks.task_store import HydroTaskStore


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_TASK_DB = BASE_DIR / "runtime" / "hydro_tasks.db"


class HydroTaskRunner:
    """Submit and execute persisted HydroAgent tasks."""

    def __init__(self, task_store: HydroTaskStore):
        self.task_store = task_store

    def submit(self, query: str, user_id: str | None = None) -> HydroTask:
        return self.task_store.create_task(query=query, user_id=user_id)

    def run(self, task_id: str) -> None:
        task = self.task_store.get_task(task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")

        try:
            self.task_store.mark_running(task_id)
            response = hydro_query_service.answer(
                HydroQueryRequest(query=task.query, user_id=task.user_id)
            )
            self.task_store.mark_completed(task_id, response.model_dump())
        except Exception as exc:
            self.task_store.mark_failed(task_id, str(exc))

    def get(self, task_id: str) -> HydroTask | None:
        return self.task_store.get_task(task_id)

    def list(self, status: str | None = None, limit: int = 20, offset: int = 0) -> HydroTaskPage:
        return self.task_store.list_tasks(status=status, limit=limit, offset=offset)


hydro_task_runner = HydroTaskRunner(HydroTaskStore(DEFAULT_TASK_DB))
