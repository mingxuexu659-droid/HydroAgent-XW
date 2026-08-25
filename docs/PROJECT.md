# AutoGIS 空间分析系统项目文档

## 📋 项目概述

AutoGIS 空间分析系统是一个自动化的地理空间分析平台，能够根据用户输入的空间分析需求，自动完成数据获取、QGIS代码生成和执行。

### 核心功能

1. **意图识别** - 自动判断任务类型（数据下载/代码生成）
2. **数据获取** - 自动下载所需的空间数据（遥感影像、OSM数据、POI等）
3. **代码生成** - 生成可执行的QGIS/PyQGIS空间分析代码
4. **代码执行** - 在QGIS环境中自动运行生成的代码
5. **智能优化** - 执行失败时自动分析错误并优化代码
6. **数据目录** - 自动扫描数据目录生成catalog和向量数据库

---

## 🏗️ 系统架构

```
AutoGIS_main/
├── spatial_analysis_system/     # 空间分析系统模块
│   ├── __init__.py
│   ├── config.py               # 配置管理
│   ├── config.yaml             # 配置文件
│   ├── llm_client.py           # LLM客户端
│   ├── intent_analyzer.py      # 意图分析器
│   ├── code_generator.py       # 代码生成器
│   ├── code_executor.py        # 代码执行器
│   ├── code_optimizer.py       # 代码优化器
│   ├── algorithm_helper.py     # 算法帮助模块
│   ├── workflow_engine.py      # 工作流引擎
│   └── catalog_builder.py      # 数据目录构建器
│
├── core/                        # 核心数据引擎模块
│   ├── __init__.py
│   ├── geo_query_engine.py     # 地理查询引擎
│   ├── data_retrieval_engine.py# 数据获取引擎
│   ├── local_vector_matcher.py # 本地数据匹配
│   ├── vector_database.py      # 向量数据库
│   ├── vector_embedding.py     # 向量嵌入
│   └── metadata_generator.py   # 元数据生成器
│
├── config/                      # 配置模块
│   ├── __init__.py
│   └── local_settings.py       # 本地敏感配置（API密钥等）
│
├── data/                        # 数据存储
│   ├── data_catalog.json       # 数据目录
│   ├── data_catalog_test.json  # 测试数据目录
│   ├── qgis_alg_detail.3.44.5.csv  # QGIS算法详情（代码优化用）
│   └── vector_db.json          # 向量数据库
│
├── tests/                       # 单元测试
│   ├── __init__.py
│   ├── test_intent_analyzer.py
│   ├── test_code_generator.py
│   ├── test_code_executor.py
│   ├── test_algorithm_helper.py
│   ├── test_complex_queries.py
│   └── test_routing_task.py
│
├── docs/                        # 项目文档
│   ├── PROJECT.md
│   └── REFACTORING_SUMMARY.md
│
├── output/                      # 输出目录
│   ├── generated_scripts/      # 生成的脚本
│   ├── results/                # 分析结果
│   └── logs/                   # 日志文件
│
├── downloaded_data/             # 下载的数据
│
├── scripts/                     # 目录、检索、维护和开发工具
│   ├── build_catalog.py         # 数据目录构建工具
│   ├── query_data.py            # 数据检索入口
│   ├── maintenance/             # 本地数据维护工具
│   ├── development/             # 手动诊断工具
│   └── migrations/              # 历史一次性迁移工具
└── run_analysis.py              # 空间分析主入口
```

---

## 🔧 模块说明

### 1. 配置管理 (`config.py`)

管理系统所有配置，支持YAML文件和环境变量。

**主要配置项：**
- `llm` - LLM模型配置（API Key、URL、模型名称等）
- `llm_code_generator` - 代码生成专用LLM配置（可独立配置）
- `vector_embedding` - 向量检索模型配置（API Key、URL、模型名称等）
- `workflow` - 工作流配置（是否跳过下载、是否自动运行等）
- `qgis` - QGIS配置（路径、超时等）
- `data` - 数据配置（本地数据目录、目录路径等）
- `output` - 输出配置（脚本目录、结果目录等）

### 2. LLM客户端 (`llm_client.py`)

封装与大语言模型的交互，支持OpenAI兼容的API。

**主要功能：**
- `chat()` - 发送聊天请求
- `chat_json()` - 发送请求并解析JSON响应
- `extract_code_from_response()` - 从响应中提取代码

### 3. 意图分析器 (`intent_analyzer.py`)

分析用户输入，判断任务类型。

**任务类型：**
- `DATA_DOWNLOAD_ONLY` - 仅数据下载
- `DATA_AND_CODE` - 数据下载+代码生成
- `CODE_ONLY` - 仅代码生成

**主要功能：**
- `analyze()` - 分析用户查询
- `format_data_query()` - 格式化数据下载查询

### 4. 代码生成器 (`code_generator.py`)

根据需求和数据信息生成QGIS空间分析代码。

**主要功能：**
- `generate()` - 生成空间分析代码
- `generate_from_template()` - 基于模板生成代码
- `save_code()` - 保存代码到文件

**支持的分析模板：**
- 缓冲区分析 (buffer)
- 裁剪分析 (clip)
- 相交分析 (intersection)
- 融合分析 (dissolve)
- NDVI计算 (ndvi)

### 5. 代码执行器 (`code_executor.py`)

在QGIS环境中执行生成的代码。

**主要功能：**
- `execute()` - 执行代码
- `execute_file()` - 执行脚本文件
- `validate_code()` - 验证代码语法
- `calculate_timeout()` - 计算超时时间

### 6. 代码优化器 (`code_optimizer.py`)

当代码执行失败时，使用LLM优化代码。严格参考 `rag_code_optimization_en.py` 实现。

**核心功能：**
- `optimize()` - 优化失败的代码，包含完整的RAG流程
- `save_optimization_history()` - 保存优化历史

**数据检索流程：**
1. **文件路径提取** - `extract_file_paths_from_code()` 从代码中提取数据文件路径
2. **元数据检索** - `search_metadata_by_path()` 从数据目录检索文件元数据
3. **算法ID提取** - `extract_algorithm_ids_from_code()` 从代码中提取QGIS算法ID
4. **算法文档检索** - 从 `data/qgis_alg_detail.3.44.5.csv` 检索算法详细文档
5. **模糊匹配** - 对于不存在的算法（幻觉算法），进行模糊匹配推荐替代算法

**优化Prompt构建：**
- `metadata_text` - 输入文件的元数据信息（从data目录下的catalog检索）
- `algorithm_text` - 代码中使用的算法文档（从算法CSV检索）
- `not_found_algorithms` - 不存在的算法及推荐的替代算法

**配置项：**
- `data.data_catalog_path` - 数据目录JSON路径
- `data.global_data_catalog_path` - 全局数据目录路径（可选，用于合并多个catalog）
- `qgis.algorithm_csv_path` - 算法详情CSV文件路径（`data/qgis_alg_detail.3.44.5.csv`）

### 7. 算法帮助模块 (`algorithm_helper.py`)

提供QGIS Processing算法的文档检索。

**主要功能：**
- `load_algorithm_help_cache()` - 加载算法文档
- `extract_algorithm_ids_from_code()` - 从代码中提取算法ID
- `fuzzy_match_algorithm()` - 模糊匹配算法
- `search_algorithms_by_keywords()` - 按关键词搜索算法

### 8. 工作流引擎 (`workflow_engine.py`)

整合所有模块，提供完整的工作流执行。

**主要功能：**
- `process()` - 处理用户请求
- `save_result()` - 保存执行结果
- `_handle_data_and_code()` - 处理数据下载+代码生成任务
  - 区分新下载文件和本地使用文件
  - 优化输出显示，清晰展示文件来源

### 9. 向量嵌入模块 (`vector_embedding.py`)

提供文本向量化功能，用于本地数据向量匹配。

**主要功能：**
- `embed_text()` - 将文本转换为向量
- `embed_batch()` - 批量向量化文本
- `cosine_similarity()` - 计算余弦相似度

**配置支持：**
- 支持通过 `config.yaml` 配置API地址、模型名称和超时时间
- 默认使用百炼API的 `text-embedding-v2` 模型

### 10. 本地向量匹配器 (`local_vector_matcher.py`)

基于向量相似度搜索本地数据，优先使用本地数据避免重复下载。

**主要功能：**
- `search_local_data()` - 向量搜索本地数据
- `check_if_satisfies_requirement()` - 使用LLM判断数据是否满足需求
- `_build_vector_index_from_catalog()` - 延迟构建向量索引（仅在需要时构建）

**优化特性：**
- 延迟构建向量索引，避免不必要的token消耗
- 如果所有数据集已存在于向量数据库，不打印构建消息
- 使用本地数据时不显示下载相关输出

---

## 📝 使用指南

### 快速开始

```bash
# 1. 配置API Key
# 编辑 spatial_analysis_system/config.yaml，设置 llm.api_key

# 2. 运行系统
python run_analysis.py

# 3. 输入需求
# 例如：下载北京的Sentinel-2影像并计算NDVI
```

### 命令行参数

```bash
python run_analysis.py [OPTIONS] [QUERY]

选项：
  --config, -c PATH     指定配置文件路径
  --skip-download       跳过数据下载步骤
  --no-run              不自动运行生成的脚本
  --no-optimize         不自动优化失败的代码
  --max-rounds N        设置最大优化轮数
  --api-key KEY         设置LLM API Key
  --model NAME          设置LLM模型名称
```

### 示例用法

```bash
# 交互模式
python run_analysis.py

# 直接执行任务
python run_analysis.py "下载北京的Sentinel-2影像"

# 跳过数据下载
python run_analysis.py --skip-download "对已有数据计算缓冲区"

# 只生成代码不运行
python run_analysis.py --no-run "下载并分析上海道路数据"
```

---

## 📁 数据目录构建

系统支持自动扫描指定目录，生成数据目录(data_catalog.json)和向量数据库。

### 使用方法

```bash
# 使用配置文件中的目录设置
python scripts/build_catalog.py

# 指定要扫描的目录
python scripts/build_catalog.py --dir "D:/GIS_Data/vector" --dir "D:/GIS_Data/raster"

# 不使用LLM生成描述（更快）
python scripts/build_catalog.py --no-llm

# 指定输出路径
python scripts/build_catalog.py --output "data/my_catalog.json"
```

### 配置项

在 `config.yaml` 中配置数据目录设置：

```yaml
data:
  # 原始数据目录列表
  raw_data_dirs:
    - "D:\\AutoGIS\\AutoGIS_main\\downloaded_data"
    - "D:\\GIS_Data\\vector"
  
  # 支持的文件扩展名
  supported_extensions:
    vector: [".shp", ".geojson", ".gpkg", ".gdb"]
    raster: [".tif", ".tiff", ".img", ".jp2"]
  
  # 是否在启动时自动扫描
  auto_scan_on_startup: false
  
  # 是否使用LLM生成描述
  use_llm_for_description: true
  
  # 是否递归扫描子目录
  recursive_scan: true
```

---

## ⚙️ 配置说明

### config.yaml 配置项

```yaml
# LLM配置 - 通用
llm:
  api_key: ""                    # API Key (必填)
  base_url: "https://..."        # API地址
  model_name: "qwen-max"         # 模型名称
  temperature: 0.3               # 温度参数
  max_tokens: 15000              # 最大token数
  timeout: 120                    # 请求超时时间(秒)

# LLM配置 - 代码生成专用
llm_code_generator:
  enabled: true                  # 是否使用独立的代码生成模型
  api_key: ""                    # API Key (留空则使用通用llm的api_key)
  base_url: ""                   # API地址 (留空则使用通用llm的base_url)
  model_name: "QGIS-GPT"         # 代码生成专用模型名称
  temperature: 0.2               # 温度参数 (代码生成建议使用较低温度)
  max_tokens: 15000              # 最大token数
  timeout: 180                   # 请求超时时间(秒)

# 向量检索模型配置
vector_embedding:
  api_key: ""                    # API Key (留空则使用通用llm的api_key)
  api_url: "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
  model_name: "text-embedding-v2" # 向量检索模型名称 (可选: text-embedding-v1)
  timeout: 10                    # 请求超时时间(秒)

# 工作流配置
workflow:
  skip_data_download: false      # 是否跳过数据下载
  auto_run_script: true          # 是否自动运行脚本
  auto_optimize_on_failure: true # 失败时是否自动优化
  max_optimization_rounds: 3     # 最大优化轮数
  use_rag_for_optimization: true # 是否在优化时使用RAG检索算法文档

# QGIS配置
qgis:
  root_path: "D:\\QGIS 3.44.5"   # QGIS安装路径
  runqgis_bat_path: "..."        # runqgis.bat路径
  script_timeout: 300            # 脚本超时时间(秒)

# 数据配置
data:
  local_data_dir: "..."          # 本地数据目录
  data_catalog_path: "..."       # 数据目录JSON路径
  vector_db_path: "..."          # 向量数据库路径

# 输出配置
output:
  script_output_dir: "..."       # 脚本输出目录
  result_output_dir: "..."       # 结果输出目录
```

### 向量检索模型配置

系统使用向量检索技术进行本地数据匹配，优先使用本地数据避免重复下载。

**配置示例：**

```yaml
vector_embedding:
  # API Key (留空则使用通用llm的api_key)
  api_key: ""
  
  # 向量检索API地址（百炼API）
  api_url: "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
  
  # 向量检索模型名称
  # 可选值:
  #   - "text-embedding-v2" (推荐，默认)
  #   - "text-embedding-v1"
  model_name: "text-embedding-v2"
  
  # 请求超时时间（秒），默认10秒
  timeout: 10
```

**工作原理：**
1. 系统将本地数据集的描述信息向量化并存储到向量数据库
2. 用户查询时，将查询需求向量化
3. 通过余弦相似度计算，找到最匹配的本地数据集
4. 使用LLM判断匹配的数据集是否满足用户需求
5. 如果本地数据满足需求，直接使用；否则执行在线下载

**优化特性：**
- 延迟构建向量索引，仅在首次使用时构建
- 如果所有数据集已存在于向量数据库，不打印构建消息
- 使用本地数据时不显示下载相关输出，避免混淆

### 环境变量

- `AUTOGIS_API_KEY` 或 `OPENAI_API_KEY` - LLM API Key
- `AUTOGIS_BASE_URL` 或 `OPENAI_BASE_URL` - API地址
- `AUTOGIS_MODEL` - 模型名称
- `AUTOGIS_SKIP_DOWNLOAD` - 是否跳过下载 (true/false)
- `AUTOGIS_AUTO_RUN` - 是否自动运行 (true/false)
- `AUTOGIS_AUTO_OPTIMIZE` - 是否自动优化 (true/false)
- `AUTOGIS_MAX_OPT_ROUNDS` - 最大优化轮数

---

## 🧪 测试

### 运行单元测试

```bash
# 运行所有测试
cd AutoGIS_main
python -m pytest tests/

# 运行特定测试
python -m pytest tests/test_intent_analyzer.py -v

# 运行测试并显示覆盖率
python -m pytest tests/ --cov=spatial_analysis_system
```

### 测试覆盖的功能

- 意图分析器：任务类型识别、数据需求解析
- 代码生成器：模板生成、元数据格式化
- 代码执行器：语法验证、超时计算
- 算法帮助：算法ID提取、模糊匹配

---

## 📊 开发日志

### v1.0.2 (2026-01-12)

**新增功能：**
- ✅ 向量检索模型配置支持
  - 在 `config.yaml` 中新增 `vector_embedding` 配置项
  - 支持配置向量检索API地址、模型名称和超时时间
  - 默认使用百炼API的 `text-embedding-v2` 模型
  - 可通过配置灵活切换不同的向量检索模型

**系统优化：**
- ✅ 优化向量索引构建逻辑
  - 如果所有数据集已存在于向量数据库，不打印构建消息
  - 避免不必要的token消耗，提升系统性能
- ✅ 优化本地数据使用输出
  - 使用本地数据时不显示下载相关输出
  - 只有真正新下载的文件才显示"自动处理下载的文件"消息
- ✅ 优化文件使用情况总结
  - 区分新下载文件和本地使用的文件
  - 输出格式更清晰，分别显示新下载和本地使用的文件数量和详细信息
- ✅ 修复GeoJSON文件覆盖问题
  - 代码生成器添加文件删除逻辑，避免GeoJSON驱动无法覆盖已存在文件的问题
  - 在保存文件前检查并删除已存在的文件

**技术改进：**
- `vector_embedding.py` 支持从配置读取API地址、模型名称和超时时间
- `local_vector_matcher.py` 支持传递向量嵌入配置参数
- `data_retrieval_engine.py` 支持向量嵌入配置传递
- `workflow_engine.py` 从配置读取并传递向量嵌入配置
- `catalog_builder.py` 使用配置中的向量嵌入设置

### v1.0.1 (2026-01-11)

**修复问题：**
- ✅ 修复下载文件路径未传递给代码生成器的问题
  - 边界文件从 `query_result.osm_data['geojson_file']` 中提取
  - 遥感数据从 `query_result.remote_sensing_data` 中提取
  - 所有路径转换为绝对路径确保代码可正确执行
- ✅ 优化 LLM prompt 正确判断地理范围覆盖（陆家嘴 ≠ 上海）
- ✅ 修复多数据需求处理失败的问题
  - 将复合查询拆分为独立查询逐个处理
  - 新增 `format_data_queries_list()` 方法返回查询列表
  - 每个数据需求独立进行意图识别和下载
- ✅ 增强数据描述语义化
  - 从文件名提取数据类型关键词（hotel, roads, boundary 等）
  - 将语义信息添加到向量数据库描述前缀
  - 提高本地数据向量搜索匹配准确率
- ✅ 修复缓冲区分析坐标系单位问题
  - EPSG:4326 数据使用度为单位，导致缓冲区异常大
  - 代码生成器添加坐标系检查和自动重投影逻辑
  - 先投影到 EPSG:3857 再执行米单位的空间分析

**技术改进：**
- `workflow_engine.py` 中的 `_handle_data_and_code` 方法增强数据文件提取逻辑
- `data_retrieval_engine.py` 增强描述生成逻辑
- `metadata_generator.py` 新增 `update_description_in_catalog()` 方法
- 增加调试输出显示数据文件信息

### v1.0.0 (2026-01-10)

**新增功能：**
- ✅ 完整的意图分析系统
- ✅ QGIS代码生成器
- ✅ 代码执行和超时控制
- ✅ 智能代码优化
- ✅ 算法文档检索
- ✅ 配置管理系统
- ✅ 交互式命令行界面
- ✅ 单元测试覆盖

**技术栈：**
- Python 3.10+
- OpenAI API (兼容格式)
- QGIS 3.44+
- PyQGIS

---

## 🌐 API 服务

系统提供 RESTful API 和 WebSocket 接口，支持前后端分离架构。

### API 模块结构

```
api/
├── main.py                 # FastAPI 主入口
├── routers/                # 路由模块
│   ├── analysis.py         # 分析任务 API
│   ├── data.py             # 数据管理 API
│   └── catalog.py          # 数据目录 API
├── schemas/                # 数据模型
├── services/               # 服务层
│   └── task_manager.py     # 任务管理服务
└── websocket/              # WebSocket 模块
    └── task_progress.py    # 进度推送
```

### 主要端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/analysis/submit` | POST | 提交分析任务 |
| `/api/analysis/task/{id}` | GET | 获取任务状态 |
| `/api/data/files` | GET | 获取文件列表 |
| `/api/catalog` | GET | 获取数据目录 |
| `/ws/task/{id}` | WS | 实时进度推送 |

### 启动服务

```bash
cd AutoGIS_main
python -m uvicorn api.main:app --host 0.0.0.0 --port 8080
```

详细文档请参阅 [API 开发文档](../api/README.md)

---

## 🔜 待开发功能

- [x] RESTful API 服务 ✅ (v1.1.0)
- [x] WebSocket 实时进度推送 ✅ (v1.1.0)
- [ ] Web UI界面
- [ ] 批量任务处理
- [ ] 任务队列管理
- [ ] 结果可视化
- [ ] 更多分析模板
- [ ] 多语言支持

---

## 📞 问题反馈

如有问题或建议，请通过以下方式反馈：
- 创建Issue
- 提交Pull Request

---

## 📜 更新记录

| 日期 | 版本 | 更新内容 |
|------|------|----------|
| 2026-01-13 | v1.1.0 | 新增 FastAPI 后端 API 服务，支持任务管理、数据管理、WebSocket 进度推送 |
| 2026-01-12 | v1.0.2 | 新增向量检索模型配置支持，优化系统输出和文件处理 |
| 2026-01-11 | v1.0.1 | 修复下载文件路径传递问题，优化数据描述语义化 |
| 2026-01-10 | v1.0.0 | 初始版本发布 |

---

*最后更新: 2026-01-13*

