"""Execution-mode classifier for HydroAgent-XW tasks."""
from dataclasses import dataclass
from enum import Enum
from typing import List

from hydro_agent.security.query_guard import check_query_safety


class HydroExecutionMode(str, Enum):
    SYNC = "sync"
    ASYNC = "async"
    REJECT = "reject"


@dataclass(frozen=True)
class HydroExecutionDecision:
    mode: HydroExecutionMode
    reason: str
    matched_keywords: List[str]


ASYNC_KEYWORDS = [
    "批量",
    "全量",
    "所有站点",
    "长期趋势",
    "生成报告",
    "生成完整报告",
    "完整报告",
    "重建",
    "重建向量库",
    "向量库重建",
    "多源融合",
    "多阶段",
]

SYNC_KEYWORDS = [
    "字段",
    "是什么意思",
    "有哪些表",
    "哪些字段",
    "表结构",
    "表用途",
    "报告里",
    "治理措施",
]


def classify_execution_mode(query: str) -> HydroExecutionDecision:
    """Classify whether a HydroAgent query should run sync, async, or be rejected."""
    safety = check_query_safety(query)
    if not safety["allowed"]:
        return HydroExecutionDecision(
            mode=HydroExecutionMode.REJECT,
            reason="query_failed_safety_check",
            matched_keywords=safety["matched_keywords"],
        )

    async_matches = _match_keywords(query, ASYNC_KEYWORDS)
    if async_matches:
        return HydroExecutionDecision(
            mode=HydroExecutionMode.ASYNC,
            reason="query_matches_long_running_task",
            matched_keywords=async_matches,
        )

    sync_matches = _match_keywords(query, SYNC_KEYWORDS)
    if sync_matches:
        return HydroExecutionDecision(
            mode=HydroExecutionMode.SYNC,
            reason="query_matches_lightweight_interactive_task",
            matched_keywords=sync_matches,
        )

    return HydroExecutionDecision(
        mode=HydroExecutionMode.SYNC,
        reason="query_defaults_to_sync",
        matched_keywords=[],
    )


def _match_keywords(query: str, keywords: List[str]) -> List[str]:
    normalized_query = query.lower()
    return [
        keyword for keyword in keywords
        if keyword.lower() in normalized_query
    ]
