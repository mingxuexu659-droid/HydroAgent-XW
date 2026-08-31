"""SQLite-backed task store for HydroAgent-XW."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from hydro_agent.tasks.task_models import HydroTask, HydroTaskPage, HydroTaskStatus


class HydroTaskStore:
    """Persist HydroAgent task state in SQLite."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def create_task(self, query: str, user_id: Optional[str] = None) -> HydroTask:
        task_id = str(uuid.uuid4())
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO hydro_tasks (
                    task_id, query, status, user_id, result_json,
                    error_message, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    query,
                    HydroTaskStatus.PENDING.value,
                    user_id,
                    None,
                    None,
                    now,
                    now,
                ),
            )
        task = self.get_task(task_id)
        if task is None:
            raise RuntimeError(f"Task was not persisted: {task_id}")
        return task

    def get_task(self, task_id: str) -> Optional[HydroTask]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT task_id, query, status, user_id, result_json,
                       error_message, created_at, updated_at
                FROM hydro_tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()

        if row is None:
            return None
        return _row_to_task(row)

    def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> HydroTaskPage:
        normalized_status = status.upper() if status else None
        if normalized_status is not None:
            HydroTaskStatus(normalized_status)

        where_clause = "WHERE status = ?" if normalized_status else ""
        params = (normalized_status,) if normalized_status else ()

        with self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM hydro_tasks {where_clause}",
                params,
            ).fetchone()[0]
            rows = conn.execute(
                f"""
                SELECT task_id, query, status, user_id, result_json,
                       error_message, created_at, updated_at
                FROM hydro_tasks
                {where_clause}
                ORDER BY created_at DESC, task_id DESC
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()

        return HydroTaskPage(
            tasks=[_row_to_task(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def mark_running(self, task_id: str) -> None:
        self._update_task(
            task_id,
            status=HydroTaskStatus.RUNNING,
            result=None,
            error_message=None,
        )

    def mark_completed(self, task_id: str, result: Dict[str, Any]) -> None:
        self._update_task(
            task_id,
            status=HydroTaskStatus.COMPLETED,
            result=result,
            error_message=None,
        )

    def mark_failed(self, task_id: str, error_message: str) -> None:
        self._update_task(
            task_id,
            status=HydroTaskStatus.FAILED,
            result=None,
            error_message=error_message,
        )

    def cancel_task(self, task_id: str) -> HydroTask:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")

        if task.status in {
            HydroTaskStatus.COMPLETED,
            HydroTaskStatus.FAILED,
            HydroTaskStatus.CANCELLED,
        }:
            return task

        self._update_task(
            task_id,
            status=HydroTaskStatus.CANCELLED,
            result=None,
            error_message="Task cancelled by user",
        )
        cancelled = self.get_task(task_id)
        if cancelled is None:
            raise RuntimeError(f"Cancelled task could not be loaded: {task_id}")
        return cancelled

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hydro_tasks (
                    task_id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    status TEXT NOT NULL,
                    user_id TEXT,
                    result_json TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _update_task(
        self,
        task_id: str,
        status: HydroTaskStatus,
        result: Optional[Dict[str, Any]],
        error_message: Optional[str],
    ) -> None:
        result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE hydro_tasks
                SET status = ?, result_json = ?, error_message = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (status.value, result_json, error_message, _utc_now(), task_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Task not found: {task_id}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_task(row: sqlite3.Row) -> HydroTask:
    result_json = row["result_json"]
    result = json.loads(result_json) if result_json else None
    return HydroTask(
        task_id=row["task_id"],
        query=row["query"],
        status=HydroTaskStatus(row["status"]),
        user_id=row["user_id"],
        result=result,
        error_message=row["error_message"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
