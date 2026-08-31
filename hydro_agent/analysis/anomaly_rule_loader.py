"""Load configurable anomaly rules for HydroAgent-XW."""
import json
from pathlib import Path
from typing import Any, Dict, List


LOCAL_RULE_FILE = "hydro_anomaly_rules.local.json"
EXAMPLE_RULE_FILE = "hydro_anomaly_rules.example.json"


def load_anomaly_rules(config_dir: Path) -> List[Dict[str, Any]]:
    rule_file = resolve_rule_file(config_dir)
    if rule_file is None:
        return []

    payload = json.loads(rule_file.read_text(encoding="utf-8"))
    rules = payload.get("rules", [])
    if not isinstance(rules, list):
        raise ValueError("anomaly rule config must contain a list field named 'rules'")

    return [normalize_rule(rule) for rule in rules if isinstance(rule, dict)]


def resolve_rule_file(config_dir: Path) -> Path | None:
    local_file = config_dir / LOCAL_RULE_FILE
    if local_file.exists():
        return local_file

    example_file = config_dir / EXAMPLE_RULE_FILE
    if example_file.exists():
        return example_file

    return None


def normalize_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(rule)
    normalized["id"] = str(normalized.get("id", "")).strip()
    normalized["type"] = str(normalized.get("type", "")).strip()
    normalized["field"] = str(normalized.get("field", "")).strip()
    normalized["severity"] = str(normalized.get("severity", "medium")).strip() or "medium"
    return normalized
