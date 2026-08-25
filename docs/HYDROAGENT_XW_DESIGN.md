# HydroAgent-XW 设计说明

## 1. 项目定位

HydroAgent-XW 是一个面向无锡市新吴区水务治理场景的多源数据智能分析 Agent。

项目基于 AutoGIS 的后端和空间分析框架进行改造，接入新吴区水环境整治报告和实时水务数据，构建面向水环境治理、闸站设备数据理解和后续 GIS 分析的智能分析系统。

## 2. 当前数据源

当前 MVP 已接入两类数据：

1. 新吴区水环境整治初步报告
   - 文件类型：docx
   - 处理方式：使用 python-docx 抽取段落文本
   - 输出文件：data_processed/reports.jsonl
   - 当前能力：根据用户问题检索相关报告段落

2. 新吴区实时数据
   - 文件类型：xlsx
   - 处理方式：使用 pandas/openpyxl 解析 sheet
   - 输出文件：data_processed/新吴区实时数据_Sheet1.csv、data_processed/新吴区实时数据_Sheet2.csv
   - 当前能力：识别数据表、字段字典、字段含义和可支持的分析方向

## 3. MVP 架构

当前系统采用规则版 Agent 作为第一阶段 MVP，避免依赖 LLM API Key，优先保证本地可运行、可解释、可调试。

整体流程：

```text
用户问题
  -> /api/hydro/query
  -> HydroQueryRequest
  -> simple_hydro_agent.answer_hydro_query()
  -> classify_intent()
  -> document_rag 或 timeseries_data
  -> 返回 HydroQueryResponse