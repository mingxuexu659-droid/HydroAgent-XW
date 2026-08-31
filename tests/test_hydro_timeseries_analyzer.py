from pathlib import Path

from hydro_agent.agents import simple_hydro_agent
from hydro_agent.analysis.timeseries_analyzer import analyze_realtime_csv


def write_realtime_csv(processed_dir: Path) -> Path:
    csv_path = processed_dir / "realtime_Sheet1.csv"
    csv_path.write_text(
        "\n".join([
            "device_id,device_value,device_status,create_time",
            "gate_001,10,正常,2026-08-31 10:00:00",
            "gate_001,11,正常,2026-08-31 10:05:00",
            "gate_001,12,正常,2026-08-31 10:10:00",
            "gate_002,100,故障,2026-08-31 10:15:00",
        ]),
        encoding="utf-8",
    )
    return csv_path


def test_analyze_realtime_csv_returns_profile_and_anomaly_candidates(tmp_path):
    write_realtime_csv(tmp_path)

    result = analyze_realtime_csv(tmp_path)

    assert result["row_count"] == 4
    assert result["column_count"] == 4
    assert result["numeric_fields"]["device_value"]["min"] == 10
    assert result["numeric_fields"]["device_value"]["max"] == 100
    assert result["time_fields"] == ["create_time"]
    assert result["status_fields"]["device_status"]["故障"] == 1
    assert any(item["type"] == "status_anomaly" for item in result["anomaly_candidates"])
    assert any(item["type"] == "numeric_outlier" for item in result["anomaly_candidates"])


def test_answer_hydro_query_uses_realtime_analysis_for_profile_queries(tmp_path, monkeypatch):
    write_realtime_csv(tmp_path)
    monkeypatch.setattr(simple_hydro_agent, "PROCESSED_DIR", tmp_path)

    result = simple_hydro_agent.answer_hydro_query("请分析实时数据中的异常候选记录")

    assert result["intent"] == "timeseries_data"
    assert "已应用" in result["answer"]
    assert "异常候选" in result["answer"]
    assert result["sources"][0]["location"] == "realtime_analysis"
    assert result["debug"]["analysis"]["row_count"] == 4
    assert result["debug"]["analysis"]["anomaly_rules"]
