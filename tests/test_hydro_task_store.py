from hydro_agent.tasks.task_models import HydroTaskStatus
from hydro_agent.tasks.task_store import HydroTaskStore


def test_task_store_creates_and_reads_pending_task(tmp_path):
    store = HydroTaskStore(tmp_path / "tasks.db")

    task = store.create_task(query="生成新吴区设备异常检测报告", user_id="user-1")

    assert task.task_id
    assert task.query == "生成新吴区设备异常检测报告"
    assert task.user_id == "user-1"
    assert task.status == HydroTaskStatus.PENDING
    assert task.result is None
    assert task.error_message is None

    loaded = store.get_task(task.task_id)

    assert loaded == task


def test_task_store_persists_status_and_result_across_instances(tmp_path):
    db_path = tmp_path / "tasks.db"
    store = HydroTaskStore(db_path)
    task = store.create_task(query="批量分析水质异常")

    store.mark_running(task.task_id)
    store.mark_completed(task.task_id, {"summary": "发现 2 个高风险站点"})

    reloaded_store = HydroTaskStore(db_path)
    loaded = reloaded_store.get_task(task.task_id)

    assert loaded is not None
    assert loaded.status == HydroTaskStatus.COMPLETED
    assert loaded.result == {"summary": "发现 2 个高风险站点"}
    assert loaded.error_message is None
    assert loaded.updated_at >= loaded.created_at


def test_task_store_persists_failed_task(tmp_path):
    store = HydroTaskStore(tmp_path / "tasks.db")
    task = store.create_task(query="重建报告向量库")

    store.mark_running(task.task_id)
    store.mark_failed(task.task_id, "vector store path is not configured")

    loaded = store.get_task(task.task_id)

    assert loaded is not None
    assert loaded.status == HydroTaskStatus.FAILED
    assert loaded.result is None
    assert loaded.error_message == "vector store path is not configured"
