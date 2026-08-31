import json
from pathlib import Path

from hydro_agent.agents import simple_hydro_agent
from hydro_agent.analysis.anomaly_rule_loader import load_anomaly_rules


def write_realtime_csv(processed_dir: Path) -> Path:
    csv_path = processed_dir / "realtime_Sheet1.csv"
    csv_path.write_text(
        "\n".join([
            "device_id,water_level,device_status,create_time",
            "gate_001,2.1,正常,2026-08-31 10:00:00",
            "gate_001,3.8,正常,2026-08-31 10:05:00",
        ]),
        encoding="utf-8",
    )
    return csv_path


def write_rules(path: Path, rule_id: str, threshold: float) -> None:
    path.write_text(
        json.dumps({
            "rules": [{
                "id": rule_id,
                "type": "numeric_threshold",
                "field": "water_level",
                "operator": ">=",
                "threshold": threshold,
                "severity": "high",
            }]
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_load_anomaly_rules_prefers_local_config_over_example(tmp_path):
    write_rules(tmp_path / "hydro_anomaly_rules.example.json", "example_rule", 9.0)
    write_rules(tmp_path / "hydro_anomaly_rules.local.json", "local_rule", 3.5)

    rules = load_anomaly_rules(tmp_path)

    assert [rule["id"] for rule in rules] == ["local_rule"]


def test_answer_hydro_query_uses_configured_anomaly_rules(tmp_path, monkeypatch):
    processed_dir = tmp_path / "data_processed"
    config_dir = tmp_path / "config"
    processed_dir.mkdir()
    config_dir.mkdir()
    write_realtime_csv(processed_dir)
    write_rules(config_dir / "hydro_anomaly_rules.local.json", "water_level_high", 3.5)
    monkeypatch.setattr(simple_hydro_agent, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(simple_hydro_agent, "CONFIG_DIR", config_dir)

    result = simple_hydro_agent.answer_hydro_query("请分析实时数据中的异常候选记录")

    candidates = result["debug"]["analysis"]["anomaly_candidates"]
    assert any(candidate.get("rule_id") == "water_level_high" for candidate in candidates)
