from hydro_agent.analysis.anomaly_rules import evaluate_anomaly_rules
from hydro_agent.analysis.timeseries_analyzer import analyze_realtime_csv


def test_evaluate_anomaly_rules_detects_threshold_status_and_consecutive_events():
    rows = [
        {"device_id": "gate_001", "device_value": "10", "device_status": "正常"},
        {"device_id": "gate_001", "device_value": "55", "device_status": "正常"},
        {"device_id": "gate_002", "device_value": "70", "device_status": "故障"},
        {"device_id": "gate_002", "device_value": "72", "device_status": "故障"},
    ]
    rules = [
        {
            "id": "device_value_high",
            "type": "numeric_threshold",
            "field": "device_value",
            "operator": ">",
            "threshold": 50,
            "severity": "high",
        },
        {
            "id": "device_status_allowed",
            "type": "allowed_values",
            "field": "device_status",
            "allowed_values": ["正常"],
            "severity": "medium",
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
    ]

    candidates = evaluate_anomaly_rules(rows, rules)

    assert any(item["rule_id"] == "device_value_high" and item["row_index"] == 2 for item in candidates)
    assert any(item["rule_id"] == "device_status_allowed" and item["row_index"] == 3 for item in candidates)
    assert any(item["rule_id"] == "consecutive_device_fault" and item["severity"] == "critical" for item in candidates)


def test_analyze_realtime_csv_accepts_custom_anomaly_rules(tmp_path):
    csv_path = tmp_path / "realtime_Sheet1.csv"
    csv_path.write_text(
        "\n".join([
            "device_id,water_level,device_status",
            "gate_001,2.1,正常",
            "gate_001,3.8,正常",
        ]),
        encoding="utf-8",
    )

    result = analyze_realtime_csv(
        tmp_path,
        anomaly_rules=[{
            "id": "water_level_high",
            "type": "numeric_threshold",
            "field": "water_level",
            "operator": ">=",
            "threshold": 3.5,
            "severity": "high",
        }],
    )

    assert any(item["rule_id"] == "water_level_high" for item in result["anomaly_candidates"])
