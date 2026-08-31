from pathlib import Path

from hydro_agent.agents import simple_hydro_agent
from hydro_agent.analysis.report_builder import build_analysis_report
from hydro_agent.analysis.timeseries_analyzer import analyze_realtime_csv


def write_report_csv(processed_dir: Path) -> Path:
    csv_path = processed_dir / "realtime_Sheet1.csv"
    csv_path.write_text(
        "\n".join([
            "device_id,device_value,device_status,create_time",
            "gate_001,10,正常,2026-08-31 10:00:00",
            "gate_001,55,正常,2026-08-31 10:05:00",
            "gate_002,70,故障,2026-08-31 10:10:00",
            "gate_002,72,故障,2026-08-31 10:15:00",
        ]),
        encoding="utf-8",
    )
    return csv_path


def test_build_analysis_report_returns_business_report_sections(tmp_path):
    write_report_csv(tmp_path)
    analysis = analyze_realtime_csv(
        tmp_path,
        anomaly_rules=[
            {
                "id": "device_value_high",
                "type": "numeric_threshold",
                "field": "device_value",
                "operator": ">",
                "threshold": 50,
                "severity": "high",
            },
            {
                "id": "consecutive_device_fault",
                "type": "consecutive_same_value",
                "field": "device_status",
                "value": "故障",
                "min_count": 2,
                "group_by": "device_id",
                "severity": "critical",
            },
        ],
    )

    report = build_analysis_report(analysis, topic="device_anomaly")

    assert report["title"] == "设备异常专题分析报告"
    assert report["risk_level"] == "critical"
    assert report["summary"]
    assert report["key_findings"]
    assert report["recommended_actions"]
    assert report["evidence"]


def test_answer_hydro_query_generates_analysis_report(tmp_path, monkeypatch):
    write_report_csv(tmp_path)
    monkeypatch.setattr(simple_hydro_agent, "PROCESSED_DIR", tmp_path)

    result = simple_hydro_agent.answer_hydro_query("请基于实时数据生成设备异常专题报告")

    assert result["intent"] == "timeseries_data"
    assert "设备异常专题分析报告" in result["answer"]
    assert result["sources"][0]["location"] == "analysis_report"
    assert result["debug"]["report"]["risk_level"] in {"medium", "high", "critical"}
