"""A small rule-based HydroAgent-XW MVP.

This first version avoids LLM calls so the local API can work without an API key.
"""
import csv
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from hydro_agent.analysis.timeseries_analyzer import analyze_realtime_csv
from hydro_agent.security.query_guard import check_query_safety


BASE_DIR = Path(__file__).resolve().parents[2]
PROCESSED_DIR = BASE_DIR / "data_processed"
REPORT_FILE = PROCESSED_DIR / "reports.jsonl"

REPORT_KEYWORDS = {"报告", "整治", "目标", "工程", "河道", "水环境", "现状", "问题", "措施", "方案"}
DATA_KEYWORDS = {"实时", "数据", "水位", "闸站", "泵站", "字段", "表", "设备", "监测", "运行"}


def finalize_response(
    result: Dict[str, Any],
    safety: Dict[str, Any],
    started_at: float,
    request_id: str,
) -> Dict[str, Any]:
    result["safety"] = safety
    result["metadata"] = {
        "request_id": request_id,
        "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
    }
    return result


def answer_hydro_query(query: str) -> Dict[str, Any]:
    started_at = time.perf_counter()
    request_id = str(uuid.uuid4())
    safety = check_query_safety(query)

    if not safety["allowed"]:
        return finalize_response({
            "intent": "security_refusal",
            "answer": (
                "无法处理该请求：问题可能涉及个人隐私、越权访问、原始数据导出"
                "或提示词注入。请改为查询水务报告、字段含义、表结构或聚合分析方案。"
            ),
            "sources": [],
            "debug": {
                "safety": safety
            }
        }, safety, started_at, request_id)

    intent = classify_intent(query)

    if intent == "timeseries_data":
        if should_use_realtime_analysis(query):
            return finalize_response(answer_realtime_analysis(query), safety, started_at, request_id)

        if "水质" in query or "异常检测" in query or "时序分析" in query or "字段分类" in query:
            return finalize_response(answer_field_categories(query), safety, started_at, request_id)

        if any(field in query for field in
               ["device_value", "device_status", "create_time", "device_id", "type_name", "type_id"]):
            return finalize_response(answer_specific_field(query), safety, started_at, request_id)

        if "可以做哪些" in query or "能做哪些" in query or "分析方向" in query or "水务分析" in query:
            return finalize_response(answer_analysis_capabilities(), safety, started_at, request_id)

        if "干什么" in query or "用途" in query or "作用" in query:
            return finalize_response(answer_table_explanation(query), safety, started_at, request_id)

        if "哪些表" in query or "多少张表" in query or "数据表概览" in query:
            return finalize_response(answer_table_overview(), safety, started_at, request_id)

        if "字段" in query or "含义" in query or "数据表" in query:
            return finalize_response(answer_field_dictionary(), safety, started_at, request_id)

        return finalize_response(answer_from_csv(), safety, started_at, request_id)

    return finalize_response(answer_from_report(query), safety, started_at, request_id)


def classify_intent(query: str) -> str:
    data_score = sum(1 for keyword in DATA_KEYWORDS if keyword in query)
    report_score = sum(1 for keyword in REPORT_KEYWORDS if keyword in query)
    if data_score > report_score:
        return "timeseries_data"
    return "document_rag"


def should_use_realtime_analysis(query: str) -> bool:
    keywords = {
        "数据画像",
        "统计概览",
        "实时统计",
        "数据统计",
        "异常数据",
        "异常候选",
        "实际异常",
        "异常记录",
    }
    return any(keyword in query for keyword in keywords)


def answer_realtime_analysis(query: str) -> Dict[str, Any]:
    analysis = analyze_realtime_csv(PROCESSED_DIR)

    if analysis["row_count"] == 0:
        return {
            "intent": "timeseries_data",
            "answer": "我还没有在 data_processed 目录中找到可分析的实时数据 CSV。",
            "sources": [],
            "debug": {"analysis": analysis}
        }

    numeric_field_names = list(analysis["numeric_fields"].keys())
    status_field_names = list(analysis["status_fields"].keys())
    anomaly_count = len(analysis["anomaly_candidates"])
    rule_count = len(analysis.get("anomaly_rules", []))

    lines = [
        f"我读取了 {analysis['file']}，共 {analysis['row_count']} 行、{analysis['column_count']} 个字段。",
        f"识别到 {len(numeric_field_names)} 个数值字段、{len(status_field_names)} 个状态字段、{len(analysis['time_fields'])} 个时间字段。",
        f"已应用 {rule_count} 条异常规则，并结合 IQR 数值离群检测。",
        f"当前发现 {anomaly_count} 条异常候选记录。"
    ]

    if numeric_field_names:
        top_numeric_fields = []
        for field_name in numeric_field_names[:5]:
            stat = analysis["numeric_fields"][field_name]
            top_numeric_fields.append(
                f"{field_name}: min={stat['min']}, max={stat['max']}, avg={stat['avg']}"
            )
        lines.append("数值字段概览：" + "；".join(top_numeric_fields))

    if status_field_names:
        status_parts = []
        for field_name in status_field_names[:3]:
            counts = analysis["status_fields"][field_name]
            status_parts.append(
                f"{field_name}: " + "、".join(f"{key}={value}" for key, value in counts.items())
            )
        lines.append("状态字段分布：" + "；".join(status_parts))

    if anomaly_count:
        candidate_lines = []
        for candidate in analysis["anomaly_candidates"][:5]:
            rule_part = f"，规则：{candidate['rule_id']}" if candidate.get("rule_id") else ""
            candidate_lines.append(
                f"第 {candidate['row_index']} 行 {candidate['field']}={candidate['value']}{rule_part}，原因：{candidate['reason']}"
            )
        lines.append("异常候选示例：\n" + "\n".join(f"- {line}" for line in candidate_lines))

    return {
        "intent": "timeseries_data",
        "answer": "\n".join(lines),
        "sources": [{
            "source": analysis["file"],
            "location": "realtime_analysis",
            "preview": (
                f"rows={analysis['row_count']}, "
                f"numeric_fields={len(numeric_field_names)}, "
                f"rules={rule_count}, "
                f"anomaly_candidates={anomaly_count}"
            )
        }],
        "debug": {
            "analysis": analysis,
            "query": query
        }
    }


def answer_from_report(query: str) -> Dict[str, Any]:
    try:
        from hydro_agent.rag.report_retriever import retrieve_report_chunks

        matches = retrieve_report_chunks(query, top_k=5)
    except Exception as exc:
        records = load_report_records()
        matches = rank_report_records(query, records)[:5]

        if not matches:
            return {
                "intent": "document_rag",
                "answer": f"报告向量检索暂时不可用，且关键词检索也没有找到明显相关内容。错误信息：{exc}",
                "sources": [],
                "debug": {
                    "retrieval": "fallback_keyword",
                    "error": str(exc),
                    "records_scanned": len(records)
                }
            }

        evidence_lines = [f"{idx + 1}. {item['text']}" for idx, item in enumerate(matches[:3])]
        return {
            "intent": "document_rag",
            "answer": (
                "报告向量检索暂时不可用，已自动降级为关键词检索。相关内容如下：\n"
                + "\n".join(evidence_lines)
            ),
            "sources": [
                {
                    "source": item["source"],
                    "location": f"paragraph_index={item['paragraph_index']}",
                    "preview": item["text"][:160]
                }
                for item in matches
            ],
            "debug": {
                "retrieval": "fallback_keyword",
                "error": str(exc),
                "records_scanned": len(records),
                "matches": len(matches)
            }
        }

    if not matches:
        return {
            "intent": "document_rag",
            "answer": "我还没有在新吴区水环境整治报告向量库中找到明显相关内容。",
            "sources": [],
            "debug": {
                "retrieval": "vector",
                "matches": 0
            }
        }

    evidence_lines = [f"{idx + 1}. {item['text']}" for idx, item in enumerate(matches[:3])]
    answer = (
        "根据新吴区水环境整治报告的向量检索结果，和问题最相关的内容如下：\n"
        + "\n".join(evidence_lines)
    )

    return {
        "intent": "document_rag",
        "answer": answer,
        "sources": [
            {
                "source": item["source"],
                "location": f"paragraph_index={item['paragraph_index']}",
                "preview": item["text"][:160]
            }
            for item in matches
        ],
        "debug": {
            "retrieval": "vector",
            "matches": len(matches)
        }
    }
def answer_table_overview() -> Dict[str, Any]:
    csv_files = sorted(PROCESSED_DIR.glob("*.csv"))
    matched_files = [file_path for file_path in csv_files if "Sheet2" in file_path.name]

    if not matched_files:
        return {
            "intent": "timeseries_data",
            "answer": "我没有找到数据表字段说明文件。",
            "sources": [],
            "debug": {"table_overview_found": False}
        }

    file_path = matched_files[0]
    table_stats = {}
    current_table = None

    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            index_value = str(row.get("序号", "")).strip()
            field_name = str(row.get("字段名", "")).strip()
            comment = str(row.get("注释", "")).strip()

            # 真实 CSV 里，表名在“序号”这一列，例如：
            # public---gate_station_device_data[闸站设备数据表]
            if index_value.startswith("public---") and "[" in index_value and "]" in index_value:
                current_table = index_value
                table_stats[current_table] = {
                    "field_count": 0,
                    "comments": []
                }
                continue

            if current_table and index_value.isdigit() and field_name:
                table_stats[current_table]["field_count"] += 1
                if comment:
                    table_stats[current_table]["comments"].append(comment)

    if not table_stats:
        return {
            "intent": "timeseries_data",
            "answer": "我读取了字段说明文件，但没有识别出数据表结构。",
            "sources": [{
                "source": file_path.name,
                "location": "table_overview",
                "preview": "未识别出表名"
            }],
            "debug": {"table_count": 0}
        }

    lines = []
    for table_name, stat in table_stats.items():
        sample_comments = "；".join(stat["comments"][:3])
        lines.append(
            f"- {table_name}：字段数 {stat['field_count']}，示例含义：{sample_comments}"
        )

    answer = (
        f"我从 {file_path.name} 中识别出 {len(table_stats)} 张数据表：\n"
        + "\n".join(lines)
    )

    return {
        "intent": "timeseries_data",
        "answer": answer,
        "sources": [{
            "source": file_path.name,
            "location": "table_overview",
            "preview": f"识别出 {len(table_stats)} 张数据表"
        }],
        "debug": {
            "table_count": len(table_stats),
            "tables": table_stats
        }
    }
def answer_table_explanation(query: str) -> Dict[str, Any]:
    overview = answer_table_overview()
    tables = overview.get("debug", {}).get("tables", {})

    if not tables:
        return overview

    matched_table_name = None
    for table_name in tables:
        if "闸站设备数据" in query and "闸站设备数据表" in table_name:
            matched_table_name = table_name
            break
        if "闸站设备类型" in query and "闸站设备类型表" in table_name:
            matched_table_name = table_name
            break

    if matched_table_name is None:
        return {
            "intent": "timeseries_data",
            "answer": (
                "我还不能确定你问的是哪一张表。你可以明确问："
                "闸站设备数据表是干什么的？或者闸站设备类型表是干什么的？"
            ),
            "sources": overview.get("sources", []),
            "debug": {
                "matched_table": None,
                "available_tables": list(tables.keys())
            }
        }

    stat = tables[matched_table_name]
    comments = stat.get("comments", [])

    if "闸站设备数据表" in matched_table_name:
        purpose = (
            "这张表主要用于记录闸站设备的监测数据。"
            "从字段注释看，它包含设备数据 id、设备 id、设备值、设备状态、创建时间等信息，"
            "因此可以用于分析某个闸站设备在不同时间的运行状态、数值变化和异常情况。"
        )
    elif "闸站设备类型表" in matched_table_name:
        purpose = (
            "这张表主要用于维护闸站设备类型。"
            "它记录设备类型 id 和设备类型名称，可以作为设备数据表的辅助字典表，"
            "帮助解释不同 device_id 或 type_id 对应的设备类别。"
        )
    else:
        purpose = (
            "这张表记录的是新吴区水务系统中的一类结构化数据，"
            "可以结合字段注释进一步判断它在闸站运行分析中的作用。"
        )

    answer = (
        f"{matched_table_name} 的用途说明：\n"
        f"{purpose}\n\n"
        f"字段数量：{stat.get('field_count', 0)}\n"
        f"字段含义示例：{'；'.join(comments[:5])}"
    )

    return {
        "intent": "timeseries_data",
        "answer": answer,
        "sources": overview.get("sources", []),
        "debug": {
            "matched_table": matched_table_name,
            "field_count": stat.get("field_count", 0)
        }
    }
def answer_analysis_capabilities() -> Dict[str, Any]:
    overview = answer_table_overview()
    tables = overview.get("debug", {}).get("tables", {})

    if not tables:
        return {
            "intent": "timeseries_data",
            "answer": "我还没有识别出可用于分析的数据表，因此暂时无法推荐分析方向。",
            "sources": overview.get("sources", []),
            "debug": {"capability_count": 0}
        }

    capabilities = []

    for table_name, stat in tables.items():
        comments = "；".join(stat.get("comments", []))

        if "设备值" in comments:
            capabilities.append("设备值趋势分析：观察 device_value 随时间变化，用于发现设备读数异常或运行波动。")

        if "设备状态" in comments:
            capabilities.append("设备状态监测：基于 device_status 判断设备是否处于正常、异常或停用状态。")

        if "创建时间" in comments:
            capabilities.append("时间序列分析：基于 create_time 对闸站设备数据按小时、天、周进行聚合统计。")

        if "设备类型" in comments or "设备类型名称" in comments:
            capabilities.append("设备类型维度分析：结合设备类型表，比较不同类型设备的运行状态和数据分布。")

    if not capabilities:
        capabilities = [
            "字段字典解析：识别数据表、字段名、字段类型和业务注释。",
            "数据表结构分析：统计每张表的字段数量和核心字段。",
            "后续可扩展为水位、流量、泵闸状态等专题分析。"
        ]

    # 去重，同时保持顺序
    unique_capabilities = []
    for item in capabilities:
        if item not in unique_capabilities:
            unique_capabilities.append(item)

    answer = (
        "基于当前实时数据字段字典，HydroAgent-XW 可以支持以下水务分析方向：\n"
        + "\n".join(f"- {item}" for item in unique_capabilities)
    )

    return {
        "intent": "timeseries_data",
        "answer": answer,
        "sources": overview.get("sources", []),
        "debug": {
            "capability_count": len(unique_capabilities),
            "capabilities": unique_capabilities
        }
    }
def answer_field_dictionary() -> Dict[str, Any]:
    csv_files = sorted(PROCESSED_DIR.glob("*.csv"))
    matched_files = [file_path for file_path in csv_files if "Sheet2" in file_path.name]

    if not matched_files:
        return {
            "intent": "timeseries_data",
            "answer": "我没有找到字段字典表，通常它应该来自 新吴区实时数据_Sheet2.csv。",
            "sources": [],
            "debug": {"field_dictionary_found": False}
        }

    file_path = matched_files[0]
    fields = []

    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            field_name = row.get("字段名", "").strip()
            field_type = row.get("类型", "").strip()
            nullable = row.get("是否为空", "").strip()
            comment = row.get("注释", "").strip()

            if not field_name or field_name == "字段名":
                continue

            fields.append({
                "字段名": field_name,
                "类型": field_type,
                "是否为空": nullable,
                "注释": comment
            })

    if not fields:
        return {
            "intent": "timeseries_data",
            "answer": "我找到了字段字典表，但没有解析出有效字段。",
            "sources": [{
                "source": file_path.name,
                "location": "field_dictionary",
                "preview": "字段字典表为空或格式不符合预期"
            }],
            "debug": {"field_count": 0}
        }

    lines = []
    for item in fields[:20]:
        lines.append(
            f"- {item['字段名']}：类型 {item['类型']}，是否为空 {item['是否为空']}，含义：{item['注释']}"
        )

    answer = (
        f"我从 {file_path.name} 中解析出 {len(fields)} 个字段。前 20 个字段如下：\n"
        + "\n".join(lines)
    )

    return {
        "intent": "timeseries_data",
        "answer": answer,
        "sources": [{
            "source": file_path.name,
            "location": "field_dictionary",
            "preview": f"共解析字段 {len(fields)} 个"
        }],
        "debug": {
            "field_dictionary_found": True,
            "field_count": len(fields)
        }
    }


def answer_field_categories(query: str) -> Dict[str, Any]:
    csv_files = sorted(PROCESSED_DIR.glob("*.csv"))
    matched_files = [file_path for file_path in csv_files if "Sheet2" in file_path.name]

    if not matched_files:
        return {
            "intent": "timeseries_data",
            "answer": "我没有找到字段字典表，无法进行字段分类。",
            "sources": [],
            "debug": {"field_dictionary_found": False}
        }

    file_path = matched_files[0]

    categories = {
        "water_quality": {
            "name": "水质分析字段",
            "keywords": ["水质", "化学需氧量", "氨氮", "总磷", "溶解氧", "水质等级"],
            "fields": []
        },
        "device_anomaly": {
            "name": "设备异常检测字段",
            "keywords": ["设备值", "设备状态", "设备id", "设备类型", "设备名称"],
            "fields": []
        },
        "time_series": {
            "name": "时序分析字段",
            "keywords": ["创建时间", "更新时间", "时间"],
            "fields": []
        },
        "station_info": {
            "name": "站点/闸站信息字段",
            "keywords": ["闸站", "站点", "位置", "名称", "坐标", "信息"],
            "fields": []
        }
    }

    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            field_name = str(row.get("字段名", "")).strip()
            comment = str(row.get("注释", "")).strip()
            field_type = str(row.get("类型", "")).strip()

            if not field_name or field_name == "字段名":
                continue

            combined_text = f"{field_name} {comment}"

            for category in categories.values():
                if any(keyword in combined_text for keyword in category["keywords"]):
                    category["fields"].append({
                        "字段名": field_name,
                        "类型": field_type,
                        "注释": comment
                    })

    if "水质" in query:
        selected_keys = ["water_quality"]
    elif "异常" in query or "设备" in query:
        selected_keys = ["device_anomaly"]
    elif "时序" in query or "时间" in query or "趋势" in query:
        selected_keys = ["time_series"]
    elif "站点" in query or "闸站" in query or "位置" in query:
        selected_keys = ["station_info"]
    else:
        selected_keys = list(categories.keys())

    lines = []
    debug_categories = {}

    for key in selected_keys:
        category = categories[key]
        debug_categories[key] = category["fields"]

        if not category["fields"]:
            lines.append(f"{category['name']}：暂未从字段字典中识别到。")
            continue

        field_lines = []
        for item in category["fields"][:10]:
            field_lines.append(f"{item['字段名']}（{item['类型']}）：{item['注释']}")

        lines.append(
            f"{category['name']}：\n"
            + "\n".join(f"- {line}" for line in field_lines)
        )

    answer = "我根据字段名和字段注释，对新吴区实时数据字段做了语义分类：\n\n" + "\n\n".join(lines)

    return {
        "intent": "timeseries_data",
        "answer": answer,
        "sources": [{
            "source": file_path.name,
            "location": "field_categories",
            "preview": "基于字段名和注释进行语义分类"
        }],
        "debug": {
            "selected_categories": selected_keys,
            "categories": debug_categories
        }
    }
def answer_specific_field(query: str) -> Dict[str, Any]:
    csv_files = sorted(PROCESSED_DIR.glob("*.csv"))
    matched_files = [file_path for file_path in csv_files if "Sheet2" in file_path.name]

    if not matched_files:
        return {
            "intent": "timeseries_data",
            "answer": "我没有找到字段字典表，无法查询字段含义。",
            "sources": [],
            "debug": {"field_dictionary_found": False}
        }

    file_path = matched_files[0]
    fields = []

    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            field_name = str(row.get("字段名", "")).strip()
            field_type = str(row.get("类型", "")).strip()
            nullable = str(row.get("是否为空", "")).strip()
            comment = str(row.get("注释", "")).strip()

            if not field_name or field_name == "字段名":
                continue

            fields.append({
                "字段名": field_name,
                "类型": field_type,
                "是否为空": nullable,
                "注释": comment
            })

    matched_fields = []
    for item in fields:
        field_name = item["字段名"]
        comment = item["注释"]
        if field_name and field_name in query:
            matched_fields.append(item)
        elif comment and comment in query:
            matched_fields.append(item)

    if not matched_fields:
        return {
            "intent": "timeseries_data",
            "answer": "我没有在字段字典中找到你提到的字段。你可以尝试输入字段英文名，例如 device_value、device_status、create_time。",
            "sources": [{
                "source": file_path.name,
                "location": "field_dictionary",
                "preview": "未匹配到具体字段"
            }],
            "debug": {
                "matched_fields": [],
                "field_count": len(fields)
            }
        }

    lines = []
    for item in matched_fields:
        lines.append(
            f"- {item['字段名']}：类型 {item['类型']}，是否为空 {item['是否为空']}，含义：{item['注释']}"
        )

    answer = "字段解释如下：\n" + "\n".join(lines)

    return {
        "intent": "timeseries_data",
        "answer": answer,
        "sources": [{
            "source": file_path.name,
            "location": "field_dictionary",
            "preview": f"匹配到 {len(matched_fields)} 个字段"
        }],
        "debug": {
            "matched_fields": matched_fields,
            "field_count": len(fields)
        }
    }


def answer_from_csv() -> Dict[str, Any]:
    csv_files = sorted(PROCESSED_DIR.glob("*.csv"))
    summaries = []
    sources = []

    for file_path in csv_files:
        with file_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            rows = [row for _, row in zip(range(8), reader)]

        if not rows:
            continue

        header = rows[0]
        preview_rows = rows[1:4]

        summaries.append(
            f"数据表 {file_path.stem}：\n"
            f"- 字段/首行：{', '.join(header)}\n"
            f"- 预览行数：{len(preview_rows)}"
        )

        sources.append({
            "source": file_path.name,
            "location": "csv_header",
            "preview": " | ".join(header)[:160]
        })

    if not summaries:
        return {
            "intent": "timeseries_data",
            "answer": "我还没有在 data_processed 目录中找到已解析的实时数据 CSV。",
            "sources": [],
            "debug": {"csv_files": 0}
        }

    answer = (
        "我读取了新吴区实时数据的解析结果，当前发现以下数据表：\n\n"
        + "\n\n".join(summaries)
        + "\n\n下一步可以继续增加：字段语义识别、水位统计、闸站筛选、异常检测。"
    )

    return {
        "intent": "timeseries_data",
        "answer": answer,
        "sources": sources,
        "debug": {"csv_files": len(csv_files)}
    }


def load_report_records() -> List[Dict[str, Any]]:
    if not REPORT_FILE.exists():
        return []

    records = []
    with REPORT_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def rank_report_records(query: str, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    query_terms = {char for char in query if not char.isspace()}
    scored = []
    for record in records:
        text = record.get("text", "")
        score = sum(1 for term in query_terms if term in text)
        if score:
            scored.append((score, len(text), record))

    scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    return [record for _, _, record in scored]
