import json
from pathlib import Path

from hydro_agent.agents import simple_hydro_agent
from hydro_agent.tasks.report_artifact_store import save_report_artifact
from hydro_agent.tasks.task_models import HydroTaskStatus
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


def test_save_report_artifact_writes_structured_report_file(tmp_path):
    result = {
        "intent": "timeseries_data",
        "debug": {
            "report": {
                "title": "设备异常专题分析报告",
                "risk_level": "high",
                "key_findings": ["发现 1 条异常候选记录"],
            }
        },
    }

    artifact = save_report_artifact("task-001", result, tmp_path / "reports")

    artifact_path = Path(artifact["path"])
    assert artifact_path.exists()
    assert artifact["format"] == "json"
    assert artifact["report_title"] == "设备异常专题分析报告"

    saved = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert saved["task_id"] == "task-001"
    assert saved["report"]["risk_level"] == "high"
    assert saved["result"]["intent"] == "timeseries_data"


def test_task_runner_saves_report_artifact_for_analysis_report_tasks(tmp_path, monkeypatch):
    write_report_csv(tmp_path)
    monkeypatch.setattr(simple_hydro_agent, "PROCESSED_DIR", tmp_path)
    runner = HydroTaskRunner(
        HydroTaskStore(tmp_path / "tasks.db"),
        report_dir=tmp_path / "reports",
    )

    task = runner.submit("请基于实时数据生成设备异常专题报告")
    runner.run(task.task_id)

    loaded = runner.get(task.task_id)
    assert loaded is not None
    assert loaded.status == HydroTaskStatus.COMPLETED
    assert loaded.result is not None
    assert loaded.result["report_artifact"]["path"]
    assert Path(loaded.result["report_artifact"]["path"]).exists()
    assert loaded.result["report_artifact"]["report_title"] == "设备异常专题分析报告"
