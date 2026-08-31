"""Build business-facing analysis reports from realtime data profiles."""
from collections import Counter
from typing import Any, Dict, List


RISK_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

TOPIC_TITLES = {
    "device_anomaly": "设备异常专题分析报告",
    "water_quality": "水质风险专题分析报告",
    "realtime_profile": "实时数据运行分析报告",
}


def build_analysis_report(analysis: Dict[str, Any], topic: str = "realtime_profile") -> Dict[str, Any]:
    candidates = analysis.get("anomaly_candidates", [])
    risk_level = infer_risk_level(candidates)
    title = TOPIC_TITLES.get(topic, TOPIC_TITLES["realtime_profile"])

    return {
        "title": title,
        "topic": topic,
        "risk_level": risk_level,
        "summary": build_summary(analysis, risk_level),
        "key_findings": build_key_findings(analysis, candidates),
        "recommended_actions": build_recommended_actions(risk_level, candidates),
        "evidence": build_evidence(candidates),
    }


def infer_risk_level(candidates: List[Dict[str, Any]]) -> str:
    if not candidates:
        return "low"

    severities = [str(candidate.get("severity", "medium")) for candidate in candidates]
    max_severity = max(severities, key=lambda value: RISK_ORDER.get(value, 2))
    if RISK_ORDER.get(max_severity, 2) >= RISK_ORDER["critical"]:
        return "critical"
    if RISK_ORDER.get(max_severity, 2) >= RISK_ORDER["high"]:
        return "high"
    if len(candidates) >= 3:
        return "high"
    return "medium"


def build_summary(analysis: Dict[str, Any], risk_level: str) -> str:
    return (
        f"本次分析读取 {analysis.get('file', '')}，覆盖 {analysis.get('row_count', 0)} 条记录、"
        f"{analysis.get('column_count', 0)} 个字段，综合风险等级为 {risk_level}。"
    )


def build_key_findings(analysis: Dict[str, Any], candidates: List[Dict[str, Any]]) -> List[str]:
    findings = [
        f"识别到 {len(analysis.get('numeric_fields', {}))} 个数值字段，可用于阈值、趋势和离群分析。",
        f"识别到 {len(analysis.get('status_fields', {}))} 个状态字段，可用于设备运行状态监测。",
        f"共发现 {len(candidates)} 条异常候选记录。",
    ]

    if candidates:
        by_type = Counter(candidate.get("type", "unknown") for candidate in candidates)
        by_severity = Counter(candidate.get("severity", "medium") for candidate in candidates)
        findings.append(
            "异常类型分布：" + "；".join(f"{key}={value}" for key, value in sorted(by_type.items()))
        )
        findings.append(
            "异常等级分布：" + "；".join(f"{key}={value}" for key, value in sorted(by_severity.items()))
        )

    return findings


def build_recommended_actions(risk_level: str, candidates: List[Dict[str, Any]]) -> List[str]:
    if not candidates:
        return [
            "保持现有监测频率，继续积累时间序列样本。",
            "为核心水位、流量、设备状态字段补充业务阈值规则。",
        ]

    actions = [
        "优先核查高等级异常候选对应的设备、站点和采集时间。",
        "将规则命中的异常记录进入人工复核队列，避免直接作为最终故障结论。",
        "对连续异常设备增加短周期复测或现场巡检动作。",
    ]

    if risk_level in {"high", "critical"}:
        actions.insert(0, "建议触发运维告警，并在处置前保留原始采集记录和规则命中证据。")

    return actions


def build_evidence(candidates: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    evidence = []
    for candidate in candidates[:limit]:
        evidence.append({
            "row_index": candidate.get("row_index"),
            "field": candidate.get("field"),
            "value": candidate.get("value"),
            "rule_id": candidate.get("rule_id", ""),
            "severity": candidate.get("severity", "medium"),
            "reason": candidate.get("reason", ""),
        })
    return evidence
