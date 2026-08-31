"""Persist generated HydroAgent report artifacts outside the task database."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def maybe_save_report_artifact(
    task_id: str,
    result: Dict[str, Any],
    report_dir: Path,
) -> Optional[Dict[str, Any]]:
    report = result.get("debug", {}).get("report")
    if not isinstance(report, dict):
        return None
    return save_report_artifact(task_id, result, report_dir)


def save_report_artifact(task_id: str, result: Dict[str, Any], report_dir: Path) -> Dict[str, Any]:
    report = result.get("debug", {}).get("report")
    if not isinstance(report, dict):
        raise ValueError("result does not contain debug.report")

    report_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = report_dir / f"{task_id}_report.json"
    payload = {
        "task_id": task_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "report": report,
        "result": result,
    }

    artifact_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "type": "analysis_report",
        "format": "json",
        "path": str(artifact_path),
        "report_title": str(report.get("title", "")),
        "risk_level": str(report.get("risk_level", "")),
    }
