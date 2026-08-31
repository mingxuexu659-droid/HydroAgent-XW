"""Task runner for HydroAgent-XW asynchronous jobs."""
from pathlib import Path

from hydro_agent.schemas.hydro import HydroQueryRequest
from hydro_agent.services.hydro_query_service import hydro_query_service
from hydro_agent.tasks.report_artifact_store import maybe_save_report_artifact
from hydro_agent.tasks.task_models import HydroTask, HydroTaskPage, HydroTaskStatus
from hydro_agent.tasks.task_store import HydroTaskStore


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_TASK_DB = BASE_DIR / "runtime" / "hydro_tasks.db"
DEFAULT_REPORT_DIR = BASE_DIR / "runtime" / "reports"


class HydroTaskRunner:
    """Submit and execute persisted HydroAgent tasks."""

    def __init__(self, task_store: HydroTaskStore, report_dir: Path | None = None):
        self.task_store = task_store
        self.report_dir = report_dir or DEFAULT_REPORT_DIR

    def submit(self, query: str, user_id: str | None = None) -> HydroTask:
        return self.task_store.create_task(query=query, user_id=user_id)

    def run(self, task_id: str) -> None:
        task = self.task_store.get_task(task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")
        if task.status == HydroTaskStatus.CANCELLED:
            return

        try:
            self.task_store.mark_running(task_id)
            response = hydro_query_service.answer(
                HydroQueryRequest(query=task.query, user_id=task.user_id)
            )
            result = response.model_dump()
            report_artifact = maybe_save_report_artifact(task_id, result, self.report_dir)
            if report_artifact is not None:
                result["report_artifact"] = report_artifact
            self.task_store.mark_completed(task_id, result)
        except Exception as exc:
            self.task_store.mark_failed(task_id, str(exc))

    def get(self, task_id: str) -> HydroTask | None:
        return self.task_store.get_task(task_id)

    def list(self, status: str | None = None, limit: int = 20, offset: int = 0) -> HydroTaskPage:
        return self.task_store.list_tasks(status=status, limit=limit, offset=offset)

    def cancel(self, task_id: str) -> HydroTask:
        return self.task_store.cancel_task(task_id)


hydro_task_runner = HydroTaskRunner(HydroTaskStore(DEFAULT_TASK_DB))
