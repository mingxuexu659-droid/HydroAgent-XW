"""Configurable anomaly rule evaluation for realtime water data."""
from typing import Any, Dict, Iterable, List, Optional


Rule = Dict[str, Any]
Row = Dict[str, str]


def evaluate_anomaly_rules(
    rows: List[Row],
    rules: Iterable[Rule],
    max_candidates: int = 20,
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    for rule in rules:
        rule_type = rule.get("type")
        if rule_type == "numeric_threshold":
            candidates.extend(evaluate_numeric_threshold(rows, rule, max_candidates - len(candidates)))
        elif rule_type == "allowed_values":
            candidates.extend(evaluate_allowed_values(rows, rule, max_candidates - len(candidates)))
        elif rule_type == "consecutive_same_value":
            candidates.extend(evaluate_consecutive_same_value(rows, rule, max_candidates - len(candidates)))

        if len(candidates) >= max_candidates:
            return candidates[:max_candidates]

    return candidates


def evaluate_numeric_threshold(rows: List[Row], rule: Rule, limit: int) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []

    field = str(rule.get("field", ""))
    operator = str(rule.get("operator", ""))
    threshold = parse_float(rule.get("threshold"))
    if not field or operator not in {">", ">=", "<", "<=", "==", "!="} or threshold is None:
        return []

    candidates = []
    for row_index, row in enumerate(rows, start=1):
        value = parse_float(row.get(field))
        if value is None or not compare(value, operator, threshold):
            continue

        candidates.append(build_candidate(
            rule=rule,
            row_index=row_index,
            field=field,
            value=value,
            anomaly_type="rule_numeric_threshold",
            reason=f"value_{operator}_threshold",
        ))
        if len(candidates) >= limit:
            return candidates

    return candidates


def evaluate_allowed_values(rows: List[Row], rule: Rule, limit: int) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []

    field = str(rule.get("field", ""))
    allowed_values = {str(value).strip().lower() for value in rule.get("allowed_values", [])}
    if not field or not allowed_values:
        return []

    candidates = []
    for row_index, row in enumerate(rows, start=1):
        value = str(row.get(field, "")).strip()
        if not value or value.lower() in allowed_values:
            continue

        candidates.append(build_candidate(
            rule=rule,
            row_index=row_index,
            field=field,
            value=value,
            anomaly_type="rule_allowed_values",
            reason="value_not_in_allowed_set",
        ))
        if len(candidates) >= limit:
            return candidates

    return candidates


def evaluate_consecutive_same_value(rows: List[Row], rule: Rule, limit: int) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []

    field = str(rule.get("field", ""))
    target_value = str(rule.get("value", "")).strip()
    min_count = int(rule.get("min_count", 2))
    group_by = rule.get("group_by")
    if not field or not target_value or min_count < 2:
        return []

    streaks: Dict[str, List[int]] = {}
    candidates = []

    for row_index, row in enumerate(rows, start=1):
        group_key = str(row.get(group_by, "__all__")) if group_by else "__all__"
        value = str(row.get(field, "")).strip()

        if value == target_value:
            streaks.setdefault(group_key, []).append(row_index)
        else:
            streaks[group_key] = []

        if len(streaks[group_key]) == min_count:
            candidates.append(build_candidate(
                rule=rule,
                row_index=row_index,
                field=field,
                value=value,
                anomaly_type="rule_consecutive_same_value",
                reason="consecutive_value_reached_min_count",
                extra={
                    "group": group_key,
                    "window_rows": streaks[group_key][:],
                },
            ))
            if len(candidates) >= limit:
                return candidates

    return candidates


def build_candidate(
    rule: Rule,
    row_index: int,
    field: str,
    value: Any,
    anomaly_type: str,
    reason: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    candidate = {
        "type": anomaly_type,
        "rule_id": str(rule.get("id", "")),
        "severity": str(rule.get("severity", "medium")),
        "row_index": row_index,
        "field": field,
        "value": value,
        "reason": reason,
    }
    if extra:
        candidate.update(extra)
    return candidate


def compare(value: float, operator: str, threshold: float) -> bool:
    if operator == ">":
        return value > threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<":
        return value < threshold
    if operator == "<=":
        return value <= threshold
    if operator == "==":
        return value == threshold
    if operator == "!=":
        return value != threshold
    return False


def parse_float(value: Any) -> Optional[float]:
    normalized = str(value).strip().replace(",", "")
    if not normalized:
        return None

    try:
        return float(normalized)
    except ValueError:
        return None
