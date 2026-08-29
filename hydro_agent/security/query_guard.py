"""Lightweight query safety guard for HydroAgent-XW."""
from typing import Any, Dict


SENSITIVE_KEYWORDS = [
    "身份证",
    "手机号",
    "电话",
    "住址",
    "家庭地址",
    "个人隐私",
    "个人信息",
    "用户信息",
    "居民信息",
    "导出全部",
    "全部原始数据",
    "原始数据打包",
    "下载原始数据",
    "vector_store",
    "绕过权限",
    "忽略规则",
    "忽略之前的规则",
    "ignore previous",
    "system prompt",
]


def check_query_safety(query: str) -> Dict[str, Any]:
    """Return a deterministic safety decision before retrieval or analysis."""
    normalized_query = query.lower()
    matched_keywords = [
        keyword for keyword in SENSITIVE_KEYWORDS
        if keyword.lower() in normalized_query
    ]

    if matched_keywords:
        return {
            "allowed": False,
            "risk_level": "high",
            "reason": "query_contains_sensitive_or_unauthorized_request",
            "matched_keywords": matched_keywords,
            "action": "refuse",
        }

    return {
        "allowed": True,
        "risk_level": "low",
        "reason": "query_passed_basic_safety_check",
        "matched_keywords": [],
        "action": "continue",
    }
