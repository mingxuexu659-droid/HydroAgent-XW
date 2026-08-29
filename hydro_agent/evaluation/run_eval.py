"""Run a small local evaluation for HydroAgent-XW."""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


BASE_DIR = Path(__file__).resolve().parents[2]
TESTSET_FILE = BASE_DIR / "hydro_agent" / "evaluation" / "testset.jsonl"

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hydro_agent.agents.simple_hydro_agent import answer_hydro_query


def load_testset() -> List[Dict[str, Any]]:
    cases = []
    with TESTSET_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def has_required_response_shape(result: Dict[str, Any]) -> bool:
    safety = result.get("safety")
    metadata = result.get("metadata")

    return (
        isinstance(result, dict)
        and isinstance(result.get("intent"), str)
        and isinstance(result.get("answer"), str)
        and isinstance(result.get("sources"), list)
        and isinstance(result.get("debug"), dict)
        and isinstance(safety, dict)
        and isinstance(safety.get("allowed"), bool)
        and isinstance(safety.get("risk_level"), str)
        and isinstance(safety.get("action"), str)
        and isinstance(metadata, dict)
        and isinstance(metadata.get("request_id"), str)
        and isinstance(metadata.get("latency_ms"), (int, float))
    )


def source_type_ok(result: Dict[str, Any], expected_source_type: str) -> bool:
    sources = result.get("sources", [])

    if expected_source_type == "report":
        return any("报告" in item.get("source", "") or item.get("source", "").endswith(".docx") for item in sources)

    if expected_source_type == "field_dictionary":
        return any("Sheet2" in item.get("source", "") or "field" in item.get("location", "") for item in sources)

    if expected_source_type == "field_categories":
        return any("field_categories" in item.get("location", "") for item in sources)

    if expected_source_type == "none":
        return not sources

    return bool(sources)


def evaluate_case(case: Dict[str, Any]) -> Dict[str, Any]:
    result = answer_hydro_query(case["query"])

    router_correct = result.get("intent") == case["expected_intent"]
    response_valid = has_required_response_shape(result)
    source_correct = source_type_ok(result, case["expected_source_type"])

    return {
        "id": case["id"],
        "query": case["query"],
        "expected_intent": case["expected_intent"],
        "actual_intent": result.get("intent"),
        "router_correct": router_correct,
        "response_valid": response_valid,
        "source_correct": source_correct,
        "passed": router_correct and response_valid and source_correct,
        "debug": result.get("debug", {})
    }


def main():
    cases = load_testset()
    results = [evaluate_case(case) for case in cases]

    total = len(results)
    router_acc = sum(item["router_correct"] for item in results) / total
    response_valid_rate = sum(item["response_valid"] for item in results) / total
    source_correct_rate = sum(item["source_correct"] for item in results) / total
    task_success_rate = sum(item["passed"] for item in results) / total

    print("HydroAgent-XW Evaluation")
    print("=" * 32)
    print(f"Total cases: {total}")
    print(f"Router Accuracy: {router_acc:.2%}")
    print(f"Response Validity: {response_valid_rate:.2%}")
    print(f"Source Correctness: {source_correct_rate:.2%}")
    print(f"Task Success Rate: {task_success_rate:.2%}")
    print()

    for item in results:
        status = "PASS" if item["passed"] else "FAIL"
        print(f"[{status}] {item['id']} | expected={item['expected_intent']} actual={item['actual_intent']}")
        if not item["passed"]:
            print(f"  query: {item['query']}")
            print(f"  debug: {item['debug']}")


if __name__ == "__main__":
    main()
