# -*- coding: utf-8 -*-
"""
代码优化器模块

当代码执行失败时，使用LLM根据错误信息和上下文优化代码。
"""

import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import Config, get_config, LLMConfig
from .llm_client import LLMClient
from .algorithm_helper import (
    AlgorithmHelper, 
    extract_algorithm_ids_from_code,
    load_algorithm_help_cache,
    get_algorithm_help_text,
    fuzzy_match_algorithm
)
from .code_executor import ExecutionResult


# ============================================================================
# 数据目录加载和元数据检索函数
# ============================================================================

def load_data_catalog(catalog_path: str) -> Dict[str, Any]:
    """
    加载数据目录
    
    Args:
        catalog_path: 数据目录JSON文件路径
    
    Returns:
        数据目录字典
    """
    try:
        with open(catalog_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Failed to load data catalog: {e}")
        return {}


def search_metadata_by_path(catalog: Dict[str, Any], file_path: str) -> Optional[Dict[str, Any]]:
    """
    在数据目录中根据绝对文件路径搜索元数据
    直接遍历目录中的所有项目，不依赖于类别关键字
    
    Args:
        catalog: 数据目录字典
        file_path: 文件的绝对路径
    
    Returns:
        文件元数据，如果未找到则返回None
    """
    # 标准化路径（统一使用正斜杠）
    normalized_path = file_path.replace('\\', '/')
    file_name = os.path.basename(normalized_path).lower()
    
    # 跳过的键
    skip_keys = {'metadata', 'layer_index'}
    
    # 遍历所有顶级键
    for key, value in catalog.items():
        if key in skip_keys:
            continue
        
        # 如果值是字典（如 vector_data, raster_data），遍历其值
        if isinstance(value, dict):
            # 检查是否有 datasets 列表
            if 'datasets' in value:
                for item in value['datasets']:
                    if isinstance(item, dict):
                        item_path = item.get('absolute_path', '')
                        if item_path and item_path.replace('\\', '/').lower() == normalized_path.lower():
                            return item
                        # 也尝试匹配文件名
                        if item_path and os.path.basename(item_path).lower() == file_name:
                            return item
            else:
                # 遍历子字典
                for category_items in value.values():
                    if isinstance(category_items, list):
                        for item in category_items:
                            if isinstance(item, dict):
                                item_path = item.get('absolute_path', '')
                                if item_path and item_path.replace('\\', '/').lower() == normalized_path.lower():
                                    return item
                                if item_path and os.path.basename(item_path).lower() == file_name:
                                    return item
        
        # 如果值是列表
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    item_path = item.get('absolute_path', '')
                    if item_path and item_path.replace('\\', '/').lower() == normalized_path.lower():
                        return item
                    if item_path and os.path.basename(item_path).lower() == file_name:
                        return item
    
    return None


def extract_file_paths_from_code(code: str) -> List[str]:
    """
    从代码中提取文件路径
    
    Args:
        code: Python代码字符串
    
    Returns:
        文件路径列表
    """
    paths = []
    
    # Windows绝对路径模式
    windows_pattern = r'["\']([A-Za-z]:[/\\][^"\']+\.[a-zA-Z0-9]+)["\']'
    paths.extend(re.findall(windows_pattern, code))
    
    # Unix绝对路径模式
    unix_pattern = r'["\'](/[^"\']+\.[a-zA-Z0-9]+)["\']'
    paths.extend(re.findall(unix_pattern, code))
    
    # 去重
    unique_paths = list(set(paths))
    
    # 标准化路径
    normalized_paths = [p.replace('\\', '/') for p in unique_paths]
    
    return normalized_paths


def extract_file_paths_from_instruction(instruction: str, llm_client: Optional[LLMClient] = None) -> List[str]:
    """
    从用户指令中提取文件路径
    
    Args:
        instruction: 用户指令
        llm_client: LLM客户端，如果提供则使用LLM辅助提取
    
    Returns:
        文件路径列表
    """
    paths = []
    
    # 使用正则表达式匹配文件路径
    # Windows路径
    windows_pattern = r'[A-Za-z]:[/\\][^\s"\'<>|*?]+\.[a-zA-Z0-9]+'
    paths.extend(re.findall(windows_pattern, instruction))
    
    # Unix路径
    unix_pattern = r'/[^\s"\'<>|*?]+\.[a-zA-Z0-9]+'
    paths.extend(re.findall(unix_pattern, instruction))
    
    # 去重并标准化
    unique_paths = list(set(p.replace('\\', '/') for p in paths))
    
    # 如果没有找到路径且提供了LLM客户端，使用LLM提取
    if not unique_paths and llm_client:
        prompt = f"""请从以下用户需求描述中提取所有绝对文件路径。

用户需求：
{instruction}

请只输出文件路径，每行一个路径。如果有多个路径，分多行列出。
只输出路径，不要包含其他解释文字。

示例输出格式：
C:/data/vector/points.geojson
/data/vector/buildings.geojson
"""
        
        response, tokens = llm_client.chat(prompt, temperature=0.1)
        if response:
            # 提取路径（支持Windows路径格式）
            for line in response.strip().split('\n'):
                line = line.strip()
                # 匹配Windows绝对路径格式
                if re.match(r'^[A-Za-z]:[/\\]', line):
                    path = line.replace('\\', '/')
                    unique_paths.append(path)
    
    return unique_paths


# ============================================================================
# 优化Prompt构建函数
# ============================================================================

def build_optimization_prompt(
    instruction: str, 
    original_code: str, 
    error_reason: str, 
    file_metadata_list: List[Dict[str, Any]],
    algorithm_help_list: List[Dict[str, str]],
    not_found_algorithms: List[Dict[str, Any]] = None
) -> str:
    """
    构建代码优化的Prompt
    严格参考 rag_code_optimization_en.py 的 build_optimization_prompt 函数
    
    Args:
        instruction: 用户原始需求
        original_code: 原始代码
        error_reason: 运行时错误信息
        file_metadata_list: 文件元数据列表
        algorithm_help_list: 算法Help Text列表
        not_found_algorithms: 未找到的算法列表（可能是幻觉算法）
    
    Returns:
        完整的优化Prompt
    """
    # 格式化文件元数据
    metadata_text = ""
    if file_metadata_list:
        metadata_text = "\n## Input File Metadata\n"
        for i, metadata in enumerate(file_metadata_list, 1):
            metadata_text += f"\n### File {i}: {metadata.get('name', 'Unknown')}\n"
            metadata_text += f"- Absolute Path: {metadata.get('absolute_path', 'N/A')}\n"
            metadata_text += f"- Format: {metadata.get('format', 'N/A')}\n"
            metadata_text += f"- Geometry Type: {metadata.get('geometry_type', 'N/A')}\n"
            metadata_text += f"- CRS: {metadata.get('crs', 'N/A')}\n"
            if 'feature_count' in metadata:
                metadata_text += f"- Feature Count: {metadata.get('feature_count', 'N/A')}\n"
            if 'attributes' in metadata:
                attrs = metadata['attributes']
                if attrs:
                    if isinstance(attrs, list):
                        attr_names = [attr.get('name', str(attr)) if isinstance(attr, dict) else str(attr) for attr in attrs[:10]]
                        metadata_text += f"- Attribute Fields: {', '.join(attr_names)}\n"
            if 'description' in metadata:
                metadata_text += f"- Description: {metadata.get('description', 'N/A')}\n"
    else:
        metadata_text = "\n## Note: Input file metadata not found\n"
    
    # 格式化算法Help Text
    algorithm_text = ""
    if algorithm_help_list:
        algorithm_text = "\n## QGIS Processing Algorithm Documentation\n"
        algorithm_text += "The following is detailed documentation for QGIS processing algorithms used in the code. Please refer to this information to use the algorithms correctly. Note: If you determine based on the algorithm documentation that the algorithm is not suitable for processing, please use other algorithms:\n"
        for i, alg_info in enumerate(algorithm_help_list, 1):
            alg_id = alg_info.get('algorithm_id', 'Unknown')
            display_name = alg_info.get('display_name', 'Unknown')
            group = alg_info.get('group', 'N/A')
            provider = alg_info.get('provider', 'N/A')
            help_text = alg_info.get('help_text', 'N/A')
            
            algorithm_text += f"\n### Algorithm {i}: {alg_id} ({display_name})\n"
            algorithm_text += f"- Documentation:\n{help_text}\n"
    
    # 处理未找到的算法（幻觉算法）
    if not_found_algorithms:
        algorithm_text += "\n## ⚠️ Important: Code uses non-existent algorithms\n"
        algorithm_text += "The following algorithms do not exist in QGIS (may be hallucinated algorithms generated by the model). Please use the recommended similar algorithms as replacements:\n"
        for i, not_found_info in enumerate(not_found_algorithms, 1):
            original_alg_id = not_found_info.get('original_algorithm_id', 'Unknown')
            similar_algorithms = not_found_info.get('similar_algorithms', [])
            
            algorithm_text += f"\n### Non-existent Algorithm {i}: {original_alg_id}\n"
            algorithm_text += f"**This algorithm does not exist. Please read the documentation of the following similar algorithms and consider whether replacing this algorithm is appropriate:**\n"
            
            if similar_algorithms:
                for j, similar_alg in enumerate(similar_algorithms, 1):
                    similar_alg_id = similar_alg.get('algorithm_id', 'Unknown')
                    similar_display_name = similar_alg.get('display_name', 'Unknown')
                    similar_help_text = similar_alg.get('help_text', 'N/A')
                    
                    algorithm_text += f"\n**Recommended Algorithm {j}: {similar_alg_id} ({similar_display_name})**\n"
                    algorithm_text += f"- Documentation:\n{similar_help_text[:500]}{'...' if len(similar_help_text) > 500 else ''}\n"
            else:
                algorithm_text += "  No similar algorithms found. Please select an appropriate algorithm based on user requirements and error information.\n"
    
    if not algorithm_text:
        algorithm_text = "\n## Note: Algorithm documentation for algorithms used in code not found\n"
    
    # 构建完整的Prompt
    prompt = f"""You are a professional PyQGIS code optimization expert. Please optimize the following code based on file metadata, algorithm documentation, and runtime error information.

## Original User Requirement
{instruction}

{metadata_text}

{algorithm_text}

## Original Code
```python
{original_code}
```

## Runtime Error Information
```
{error_reason}
```

## Optimization Requirements
1. **Must use file metadata information**: Use CRS, geometry type, attribute fields, and other information from metadata to correct the code
2. **Must refer to algorithm documentation**: Carefully read the above algorithm documentation to ensure correct algorithm ID, parameter names, and parameter values are used
3. **Must fix errors**: Carefully analyze the error cause to ensure the optimized code can run successfully
4. **Maintain code style**: Keep similar style and structure as the original code
5. **Ensure code is executable**: All parameters must have valid values, no empty strings or None
6. **Follow QGIS best practices**: Use correct algorithm IDs and parameters, refer to instructions in algorithm documentation

## Output Requirements
**Important: Output only the optimized Python code, do not include any markdown code block markers (such as ```python or ```). Start directly with code, for example:**

from qgis.core import QgsVectorLayer
import processing

Please ensure:
- Code can run directly in QGIS Python console
- All paths are absolute paths, and consistently use forward slashes (/) as path separators, do not use backslashes (\\)
- When using os.path.join(), if the base path uses forward slashes, ensure the result path also consistently uses forward slashes (can use .replace('\\\\', '/') for normalization)
- All processing.run() calls have valid parameter values that meet algorithm documentation requirements
- Code includes necessary comments

Now please output the optimized code:
"""
    
    return prompt


class CodeOptimizer:
    """
    代码优化器
    
    根据执行错误信息、数据元信息和算法文档优化失败的代码。
    严格参考 rag_code_optimization_en.py 实现。
    """
    
    SYSTEM_PROMPT = """You are a professional PyQGIS code optimization expert. Your task is to fix and optimize QGIS spatial analysis code based on error information, file metadata, and algorithm documentation.

You are skilled at:
1. Analyzing Python error stacks to locate the root cause of problems
2. Understanding parameter requirements of QGIS Processing algorithms
3. Handling coordinate systems, geometry types, and other geographic data issues
4. Optimizing code structure and performance

When fixing code, please ensure:
1. All paths use absolute paths with forward slashes (/)
2. All processing.run() parameters have valid values
3. Correctly handle coordinate system transformations
4. Code includes necessary error handling
5. When `processing.run()` OUTPUT is a file path (not `'memory:'`), it returns a **file path string**, NOT a layer object.
6. For random points inside polygons, use `native:randompointsinpolygons`.

## Note on `gdal:rastercalculator`
- `gdal:rastercalculator` with 3+ inputs (INPUT_A/B/C+) has been patched at runtime to use numpy fallback.
- It is safe to use with any number of inputs; the runtime will automatically handle multi-input cases.

## Sentinel-2 band mapping (CRITICAL — fix if wrong)
- 12-band GeoTIFF: B1=Coastal, B2=Blue, B3=Green, B4=**Red**, B5-B7=RedEdge, B8=**NIR**, B9=WaterVapour, B10=SWIRCirrus, B11=**SWIR1**, B12=SWIR2
- **Band 4 is RED, NOT NIR!  Band 8 is NIR!**
- Correct formulas: NDVI=(B8−B4)/(B8+B4), NDBI=(B11−B8)/(B11+B8), NDWI=(B3−B8)/(B3+B8)
- If the code uses wrong bands (e.g., B4−B3 for NDVI, or B5 for SWIR), fix them immediately.

## Classification rules
- Class numbering: 1=Water, 2=Vegetation, 3=Built-up, 4=Bare Soil, 5=Cropland.
- Nodata masking: detect nodata pixels (`band4==0 & band8==0`), set to 0 in output, exclude from stats.
- Area for EPSG:4326: `lat_rad=math.radians(abs(gt[3])); area_km2 = count*(abs(gt[1])*111320*math.cos(lat_rad))*(abs(gt[5])*110540)/1e6`. Must include cos(lat) for longitude correction."""

    def __init__(self, config: Optional[Config] = None, llm_client: Optional[LLMClient] = None):
        """
        初始化代码优化器
        
        Args:
            config: 配置对象
            llm_client: LLM客户端（如果未提供，将根据配置创建专用或通用客户端）
        """
        self.config = config or get_config()
        
        # 如果没有提供 llm_client，根据配置创建
        if llm_client is None:
            # 检查是否启用了独立的代码优化模型
            if self.config.llm_code_optimizer.enabled and self.config.llm_code_optimizer.api_key:
                # 创建专用的代码优化 LLM 客户端
                optimizer_config = LLMConfig(
                    api_key=self.config.llm_code_optimizer.api_key or self.config.llm.api_key,
                    base_url=self.config.llm_code_optimizer.base_url or self.config.llm.base_url,
                    model_name=self.config.llm_code_optimizer.model_name or self.config.llm.model_name,
                    temperature=self.config.llm_code_optimizer.temperature,
                    max_tokens=self.config.llm_code_optimizer.max_tokens,
                    timeout=self.config.llm_code_optimizer.timeout,
                )
                print(f"Code optimizer using dedicated model: {optimizer_config.model_name}")
                self.llm_client = LLMClient(self.config, llm_config_override=optimizer_config)
            else:
                # 使用通用 LLM 客户端
                self.llm_client = LLMClient(self.config)
        else:
            self.llm_client = llm_client
        
        # 加载数据目录
        self.catalog = self._load_catalog()
        
        # 加载算法缓存
        self.algorithm_cache = self._load_algorithm_cache()
    
    def _load_catalog(self) -> Dict[str, Any]:
        """Load data catalog"""
        catalog = {}
        
        # Load data catalog
        catalog_path = self.config.data.data_catalog_path
        if os.path.exists(catalog_path):
            print(f"Loading data catalog: {catalog_path}")
            catalog = load_data_catalog(catalog_path)
        else:
            print(f"⚠️ Data catalog file not found: {catalog_path}")
        
        return catalog
    
    def _load_algorithm_cache(self) -> Dict[str, Dict[str, str]]:
        """Load algorithm cache"""
        csv_path = self.config.qgis.algorithm_csv_path
        if not os.path.exists(csv_path):
            print(f"⚠️ Algorithm CSV file not found: {csv_path}")
            return {}
        
        return load_algorithm_help_cache(csv_path)
    
    def optimize(
        self,
        original_code: str,
        error_result: ExecutionResult,
        instruction: str,
        file_metadata: Optional[List[Dict[str, Any]]] = None,
        round_num: int = 1
    ) -> Optional[str]:
        """
        优化失败的代码
        严格参考 rag_code_optimization_en.py 的 optimize_code 函数
        
        Args:
            original_code: 原始代码
            error_result: 执行结果（包含错误信息）
            instruction: 用户原始需求
            file_metadata: 输入文件的元数据列表（如果提供则优先使用）
            round_num: 当前优化轮次
        
        Returns:
            优化后的代码，如果优化失败则返回None
        """
        print(f"\n{'='*60}")
        print(f"🔧 Code Optimization (Round {round_num})")
        print(f"{'='*60}")
        
        # 准备错误信息
        error_info = self._format_error_info(error_result)
        
        # Step 1: Extract file paths
        print(f"  Step 1: Extracting file paths...")
        file_paths = []
        
        # 从代码中提取路径
        code_paths = extract_file_paths_from_code(original_code)
        file_paths.extend(code_paths)
        
        # 从指令中提取路径
        instruction_paths = extract_file_paths_from_instruction(instruction, self.llm_client)
        for p in instruction_paths:
            if p not in file_paths:
                file_paths.append(p)
        
        print(f"    Found {len(file_paths)} file paths")
        for path in file_paths[:5]:  # Only show first 5
            print(f"      - {path}")
        if len(file_paths) > 5:
            print(f"      ... and {len(file_paths) - 5} more paths")
        
        # Step 2: Retrieve file metadata
        print(f"  Step 2: Retrieving file metadata...")
        file_metadata_list = []
        
        # 如果提供了file_metadata，优先使用
        if file_metadata:
            file_metadata_list = file_metadata
            print(f"    Using {len(file_metadata_list)} provided file metadata")
        else:
            # 从catalog中检索
            for file_path in file_paths:
                metadata = search_metadata_by_path(self.catalog, file_path)
                if metadata:
                    file_metadata_list.append(metadata)
                    print(f"    ✓ Found metadata: {metadata.get('name', 'Unknown')}")
                else:
                    print(f"    ⚠ Metadata not found: {os.path.basename(file_path)}")
        
        # Step 3: Extract algorithm IDs and retrieve Help Text
        print(f"  Step 3: Extracting QGIS processing algorithms...")
        algorithm_ids = extract_algorithm_ids_from_code(original_code)
        
        if algorithm_ids:
            print(f"    Found {len(algorithm_ids)} algorithms: {', '.join(algorithm_ids)}")
        else:
            print(f"    Found 0 algorithms")
            # Debug: 检查代码是否包含processing.run调用
            if 'processing.run' in original_code:
                matches = list(re.finditer(r'processing\.run\s*\(', original_code))
                print(f"    ⚠️ Debug: Code contains {len(matches)} processing.run calls, but no algorithm IDs extracted")
                for i, match in enumerate(matches[:3]):
                    start = max(0, match.start() - 20)
                    end = min(len(original_code), match.end() + 100)
                    snippet = original_code[start:end].replace('\n', '\\n')
                    print(f"      Position {i+1}: ...{snippet}...")
        
        algorithm_help_list = []
        not_found_algorithms = []
        
        for alg_id in algorithm_ids:
            alg_info = get_algorithm_help_text(alg_id, self.algorithm_cache)
            if alg_info:
                algorithm_help_list.append({
                    'algorithm_id': alg_id,
                    'display_name': alg_info.get('display_name', ''),
                    'group': alg_info.get('group', ''),
                    'provider': alg_info.get('provider', ''),
                    'help_text': alg_info.get('help_text', '')
                })
                print(f"    ✓ Found algorithm doc: {alg_id} ({alg_info.get('display_name', '')})")
            else:
                print(f"    ⚠ Algorithm doc not found: {alg_id}, performing fuzzy match...")
                # 进行模糊匹配
                similar_algorithms = fuzzy_match_algorithm(alg_id, self.algorithm_cache, max_results=3)
                if similar_algorithms:
                    # 获取相似算法的完整信息（包括help_text）
                    similar_algorithms_full = []
                    for similar_alg in similar_algorithms:
                        similar_alg_id = similar_alg['algorithm_id']
                        similar_alg_info = get_algorithm_help_text(similar_alg_id, self.algorithm_cache)
                        if similar_alg_info:
                            similar_algorithms_full.append({
                                'algorithm_id': similar_alg_id,
                                'display_name': similar_alg_info.get('display_name', ''),
                                'group': similar_alg_info.get('group', ''),
                                'provider': similar_alg_info.get('provider', ''),
                                'help_text': similar_alg_info.get('help_text', '')
                            })
                            print(f"      → Recommended similar algorithm: {similar_alg_id} ({similar_alg_info.get('display_name', '')})")
                    
                    not_found_algorithms.append({
                        'original_algorithm_id': alg_id,
                        'similar_algorithms': similar_algorithms_full
                    })
                else:
                    print(f"      → No similar algorithms found")
                    not_found_algorithms.append({
                        'original_algorithm_id': alg_id,
                        'similar_algorithms': []
                    })
        
        # Step 4: Build optimization prompt and call LLM
        print(f"  Step 4: Optimizing code...")
        optimization_prompt = build_optimization_prompt(
            instruction, 
            original_code, 
            error_info, 
            file_metadata_list, 
            algorithm_help_list, 
            not_found_algorithms
        )
        
        response_text, token_stats = self.llm_client.chat(
            prompt=optimization_prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.3
        )
        
        if response_text is None:
            print("❌ Code optimization failed: LLM call failed")
            return None
        
        # 清理代码
        optimized_code = self._clean_code(response_text)
        
        # 标准化路径：确保所有路径使用正斜杠
        optimized_code = self._normalize_paths(optimized_code)
        
        print(f"    ✓ Code optimization complete (input tokens: {token_stats['input_tokens']}, output tokens: {token_stats['output_tokens']})")
        print(f"  Code lines: {len(optimized_code.splitlines())}")
        
        return optimized_code
    
    def _format_error_info(self, error_result: ExecutionResult) -> str:
        """格式化错误信息"""
        lines = []
        
        if error_result.error:
            lines.append(f"Error output:\n{error_result.error}")
        
        if error_result.output:
            # 检查标准输出中是否有错误信息
            if 'error' in error_result.output.lower() or 'traceback' in error_result.output.lower():
                lines.append(f"\nError in standard output:\n{error_result.output}")
        
        lines.append(f"\nReturn code: {error_result.return_code}")
        lines.append(f"Execution time: {error_result.execution_time:.2f}s")
        
        return '\n'.join(lines)
    
    def _clean_code(self, code: str) -> str:
        """清理代码中的markdown标记等"""
        code = code.strip()
        
        # 移除markdown代码块标记
        code = re.sub(r'^```(?:python)?\s*\n?', '', code, flags=re.MULTILINE)
        code = re.sub(r'\n?```\s*$', '', code, flags=re.MULTILINE)
        
        # 移除开头的非代码内容
        lines = code.split('\n')
        code_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(('import ', 'from ', '#', 'def ', 'class ', '"""', "'''")):
                code_start = i
                break
        
        return '\n'.join(lines[code_start:]).strip()
    
    def _normalize_paths(self, code: str) -> str:
        """
        标准化代码中的路径
        处理os.path.join()结果，将反斜杠替换为正斜杠
        """
        lines = code.split('\n')
        normalized_lines = []
        
        for line in lines:
            # 检查是否是os.path.join()赋值语句
            if 'os.path.join' in line and '=' in line:
                # 如果行中没有.replace('\\', '/')，添加它
                if ".replace('\\\\', '/')" not in line and ".replace('\\', '/')" not in line:
                    # 在os.path.join()调用后添加.replace('\\', '/')
                    line = re.sub(
                        r'(os\.path\.join\([^)]+\))',
                        lambda m: f"{m.group(1)}.replace('\\\\', '/')",
                        line
                    )
            normalized_lines.append(line)
        
        return '\n'.join(normalized_lines)
    
    def save_optimization_history(
        self,
        original_code: str,
        optimized_code: str,
        error_info: str,
        round_num: int,
        output_dir: Optional[str] = None
    ) -> str:
        """
        保存优化历史
        
        Args:
            original_code: 原始代码
            optimized_code: 优化后的代码
            error_info: 错误信息
            round_num: 优化轮次
            output_dir: 输出目录
        
        Returns:
            保存的文件路径
        """
        if output_dir is None:
            output_dir = self.config.output.log_dir
        
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"optimization_round{round_num}_{timestamp}.json"
        filepath = Path(output_dir) / filename
        
        history = {
            'timestamp': timestamp,
            'round': round_num,
            'original_code': original_code,
            'optimized_code': optimized_code,
            'error_info': error_info,
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        
        print(f"    Optimization history saved: {filepath}")
        
        return str(filepath)
    
    def reload_catalog(self) -> None:
        """重新加载数据目录"""
        self.catalog = self._load_catalog()
    
    def reload_algorithm_cache(self) -> None:
        """重新加载算法缓存"""
        global _algorithm_help_cache
        from .algorithm_helper import _algorithm_help_cache
        _algorithm_help_cache.clear()
        self.algorithm_cache = self._load_algorithm_cache()
