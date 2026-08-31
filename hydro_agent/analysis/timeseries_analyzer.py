"""Realtime CSV profiling and anomaly candidate detection."""
import csv
import math
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple


NORMAL_STATUS_VALUES = {
    "正常",
    "运行",
    "在线",
    "ok",
    "normal",
    "running",
    "online",
    "0",
}

TIME_FIELD_KEYWORDS = ("time", "date", "时间", "日期")
STATUS_FIELD_KEYWORDS = ("status", "state", "状态")


def analyze_realtime_csv(processed_dir: Path, max_anomaly_candidates: int = 20) -> Dict[str, Any]:
    file_path = find_realtime_data_file(processed_dir)
    if file_path is None:
        return {
            "file": "",
            "row_count": 0,
            "column_count": 0,
            "columns": [],
            "numeric_fields": {},
            "status_fields": {},
            "time_fields": [],
            "anomaly_candidates": [],
        }

    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    columns = list(reader.fieldnames or [])
    numeric_values = collect_numeric_values(rows, columns)
    numeric_fields = summarize_numeric_fields(numeric_values)
    status_fields = summarize_status_fields(rows, columns)
    time_fields = detect_time_fields(columns)

    anomaly_candidates = []
    anomaly_candidates.extend(detect_status_anomalies(rows, status_fields.keys(), max_anomaly_candidates))
    remaining_limit = max_anomaly_candidates - len(anomaly_candidates)
    if remaining_limit > 0:
        anomaly_candidates.extend(detect_numeric_outliers(numeric_values, remaining_limit))

    return {
        "file": file_path.name,
        "row_count": len(rows),
        "column_count": len(columns),
        "columns": columns,
        "numeric_fields": numeric_fields,
        "status_fields": status_fields,
        "time_fields": time_fields,
        "anomaly_candidates": anomaly_candidates,
    }


def find_realtime_data_file(processed_dir: Path) -> Optional[Path]:
    csv_files = sorted(processed_dir.glob("*.csv"))
    sheet1_files = [file_path for file_path in csv_files if "Sheet1" in file_path.name]
    if sheet1_files:
        return sheet1_files[0]
    return csv_files[0] if csv_files else None


def collect_numeric_values(rows: List[Dict[str, str]], columns: List[str]) -> Dict[str, List[Tuple[int, float]]]:
    values: Dict[str, List[Tuple[int, float]]] = {column: [] for column in columns}

    for row_index, row in enumerate(rows, start=1):
        for column in columns:
            value = parse_float(row.get(column, ""))
            if value is not None:
                values[column].append((row_index, value))

    return {column: column_values for column, column_values in values.items() if column_values}


def summarize_numeric_fields(numeric_values: Dict[str, List[Tuple[int, float]]]) -> Dict[str, Dict[str, float]]:
    summaries = {}
    for column, indexed_values in numeric_values.items():
        values = [value for _, value in indexed_values]
        summaries[column] = {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": round(mean(values), 4),
        }
    return summaries


def summarize_status_fields(rows: List[Dict[str, str]], columns: List[str]) -> Dict[str, Dict[str, int]]:
    status_fields = {}
    for column in columns:
        if not is_status_field(column):
            continue

        counts: Dict[str, int] = {}
        for row in rows:
            value = str(row.get(column, "")).strip()
            if not value:
                continue
            counts[value] = counts.get(value, 0) + 1

        if counts:
            status_fields[column] = counts

    return status_fields


def detect_time_fields(columns: List[str]) -> List[str]:
    return [column for column in columns if any(keyword in column.lower() for keyword in TIME_FIELD_KEYWORDS)]


def detect_status_anomalies(
    rows: List[Dict[str, str]],
    status_columns,
    max_candidates: int,
) -> List[Dict[str, Any]]:
    candidates = []
    for row_index, row in enumerate(rows, start=1):
        for column in status_columns:
            value = str(row.get(column, "")).strip()
            if not value or value.lower() in NORMAL_STATUS_VALUES:
                continue

            candidates.append({
                "type": "status_anomaly",
                "row_index": row_index,
                "field": column,
                "value": value,
                "reason": "status_value_not_in_normal_set",
            })
            if len(candidates) >= max_candidates:
                return candidates
    return candidates


def detect_numeric_outliers(
    numeric_values: Dict[str, List[Tuple[int, float]]],
    max_candidates: int,
) -> List[Dict[str, Any]]:
    candidates = []
    for column, indexed_values in numeric_values.items():
        if len(indexed_values) < 4:
            continue

        values = [value for _, value in indexed_values]
        q1 = percentile(values, 0.25)
        q3 = percentile(values, 0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue

        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        for row_index, value in indexed_values:
            if value < lower_bound or value > upper_bound:
                candidates.append({
                    "type": "numeric_outlier",
                    "row_index": row_index,
                    "field": column,
                    "value": value,
                    "reason": "outside_iqr_range",
                    "lower_bound": round(lower_bound, 4),
                    "upper_bound": round(upper_bound, 4),
                })
                if len(candidates) >= max_candidates:
                    return candidates
    return candidates


def parse_float(value: str) -> Optional[float]:
    normalized = str(value).strip().replace(",", "")
    if not normalized:
        return None

    try:
        return float(normalized)
    except ValueError:
        return None


def percentile(values: List[float], ratio: float) -> float:
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * ratio
    lower_index = math.floor(position)
    upper_index = math.ceil(position)

    if lower_index == upper_index:
        return sorted_values[lower_index]

    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    weight = position - lower_index
    return lower_value + (upper_value - lower_value) * weight


def is_status_field(column: str) -> bool:
    normalized = column.lower()
    return any(keyword in normalized for keyword in STATUS_FIELD_KEYWORDS)
