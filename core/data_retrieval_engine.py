#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data Retrieval Engine Module (data_retrieval_engine.py)

Provides VectorLocalFirstGeoQueryEngine class, inheriting from GeoQueryEngine,
implementing vector matching local-first query logic.

Based on data_search_with_clip_online.py, modified local data lookup logic:
1. Decompose tasks into DAG
2. Each DAG node first checks if downloaded data exists in local data directory
3. Use vector matching: convert node requirements to vectors, match with local data description fields
4. Select Top N data, let LLM judge if requirements can be satisfied
5. If local data cannot satisfy, then use online retrieval
"""

import json
import math
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

# Import original script components
import sys
parent_dir = Path(__file__).parent
sys.path.insert(0, str(parent_dir))
from .geo_query_engine import (
    GeoQueryEngine, IntentAnalysis, UnifiedQueryResult,
    QueryIntent, SubTaskResult
)

# Try to import API Key from config directory
try:
    from config.local_settings import QWEN_API_KEY as DASHSCOPE_API_KEY
except ImportError:
    DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")

# Import local modules
from .local_vector_matcher import LocalDataVectorMatcher
from .metadata_generator import MetadataGenerator

# 尝试加载系统配置 (包含云量阈值等遥感参数)
try:
    from spatial_analysis_system.config import get_config as get_system_config
    _system_config = get_system_config()
    DEFAULT_CLOUD_COVER_MAX = _system_config.remote_sensing.cloud_cover_max
except ImportError:
    DEFAULT_CLOUD_COVER_MAX = 70.0  # 默认值


# ============================================================================
# Vector Matching Local-First Geographic Query Engine
# ============================================================================

class VectorLocalFirstGeoQueryEngine(GeoQueryEngine):
    """Vector matching local-first geographic query engine"""
    
    def __init__(self, catalog_path: str = None, output_dir: str = "downloaded_data",
                 use_llm: bool = True, api_key: str = None,
                 embedding_api_url: str = None, embedding_model_name: str = None, embedding_timeout: float = None):
        """
        Initialize engine
        
        Args:
            catalog_path: Data catalog file path
            output_dir: Output directory
            use_llm: Whether to use LLM
            api_key: API key
            embedding_api_url: Vector retrieval API URL (optional)
            embedding_model_name: Vector retrieval model name (optional)
            embedding_timeout: Vector retrieval request timeout in seconds (optional)
        """
        # Call parent initialization
        super().__init__(catalog_path=catalog_path, output_dir=output_dir, use_llm=use_llm)
        
        # Save api_key for vector matcher and metadata generator
        self.api_key = api_key or DASHSCOPE_API_KEY
        
        # Initialize vector matcher (lazy build vector index)
        if catalog_path and Path(catalog_path).exists():
            vector_db_path = Path(catalog_path).parent / "vector_db.json"
            print(f"\nInitializing vector matcher (vector DB: {vector_db_path.name})...")
            self.vector_matcher = LocalDataVectorMatcher(
                catalog_path, 
                str(vector_db_path), 
                self.api_key,
                embedding_api_url=embedding_api_url,
                embedding_model_name=embedding_model_name,
                embedding_timeout=embedding_timeout
            )
            self.catalog_path = Path(catalog_path)
        else:
            self.vector_matcher = None
            self.catalog_path = None
            print("⚠️ Data catalog not found, vector matching unavailable")
        
        # Initialize metadata generator
        llm_client = self.vector_matcher.llm_client if self.vector_matcher else None
        self.metadata_generator = MetadataGenerator(llm_client=llm_client)
    
    def _handle_complex_query(self, intent: IntentAnalysis, 
                               result: UnifiedQueryResult, user_query: str):
        """
        Handle complex query - task decomposition and execution (vector matching local-first version)
        
        For each DAG node:
        1. First try local vector matching
        2. If local data cannot satisfy, then use online retrieval
        """
        print("\nExecuting complex query (task decomposition + vector matching local-first)...")
        
        # Get sub-task list
        sub_tasks = intent.sub_tasks
        
        # If intent analysis didn't provide sub-tasks, use task decomposer
        if not sub_tasks and self.task_decomposer:
            print("   Decomposing tasks...")
            sub_tasks = self.task_decomposer.decompose(user_query)
        
        if not sub_tasks:
            result.warnings.append("Cannot decompose complex query")
            # Fallback to hybrid query
            self._handle_hybrid_query(intent, result, top_k=5)
            return
        
        print(f"   ✓ Decomposed into {len(sub_tasks)} sub-tasks")
        
        # Store intermediate results
        task_outputs = {}
        
        # Execute sub-tasks in order
        for task in sorted(sub_tasks, key=lambda x: x.get('order', 0)):
            task_id = task.get('order', 0)
            task_type = task.get('type', '')
            task_desc = task.get('description', '')
            task_params = task.get('params', {})
            depends_on = task.get('depends_on')
            output_name = task.get('output_name', f'task_{task_id}')
            
            print(f"\n   [{task_id}] {task_desc}")
            
            sub_result = SubTaskResult(
                task_id=task_id,
                task_type=task_type,
                description=task_desc
            )
            
            try:
                # ============================================================
                # Step 1: First try local vector matching
                # ============================================================
                local_data_used = False
                if self.vector_matcher:
                    print(f"      🔍 [Step 1] Checking local data...")
                    candidate_datasets = self.vector_matcher.search_local_data(task_desc, top_n=10)
                    
                    if candidate_datasets:
                        # 🔧 优化：对于 osm_data 类型，先通过文件名匹配检查
                        # 这样可以避免 LLM 误判几何类型的问题
                        if task_type == 'osm_data':
                            task_desc_lower = task_desc.lower()
                            # 确定需要的数据类型
                            needed_types = []
                            if 'road' in task_desc_lower or '道路' in task_desc:
                                needed_types.append('roads')
                            if 'building' in task_desc_lower or '建筑' in task_desc:
                                needed_types.append('building')
                            if 'boundary' in task_desc_lower or '边界' in task_desc:
                                needed_types.append('boundary')
                            if not needed_types:
                                needed_types = ['roads']  # 默认道路
                            
                            # 遍历所有候选，通过文件名匹配找到合适的数据
                            for match in candidate_datasets:
                                dataset = match['dataset']
                                dataset_name_lower = dataset.get('name', '').lower()
                                file_name_lower = dataset.get('file_name', '').lower()
                                
                                for needed_type in needed_types:
                                    if needed_type in dataset_name_lower or needed_type in file_name_lower:
                                        file_path = dataset.get('absolute_path', '')
                                        print(f"      ✓ Using local {needed_type} data: {Path(file_path).name}")
                                        print(f"         Path: {file_path}")
                                        local_data_used = True
                                        sub_result.result = [file_path]
                                        result.downloaded_files.append(file_path)
                                        break
                                if local_data_used:
                                    break
                        
                        # 对于其他类型，使用 LLM 判断
                        if not local_data_used:
                            selected_dataset = self.vector_matcher.check_if_satisfies_requirement(
                                task_desc, candidate_datasets[:5]
                            )
                            
                            if selected_dataset:
                                # 本地数据可以满足需求
                                dataset = selected_dataset['dataset']
                                file_path = dataset.get('absolute_path', '')
                                
                                print(f"      ✓ Using local data: {Path(file_path).name}")
                                print(f"         Path: {file_path}")
                                
                                # 根据任务类型处理本地数据
                                if task_type in ['poi_search', 'spatial_proximity']:
                                    # For POI queries, local data may not apply, continue online search
                                    print(f"      ⚠️ POI query needs online data, continuing online search...")
                                elif task_type == 'routing':
                                    # Fix: routing task needs route calculation even if local data found
                                    print(f"      ⚠️ Routing task needs route calculation, continuing...")
                                else:
                                    # 其他类型任务，标记为使用本地数据
                                    local_data_used = True
                                    sub_result.result = {
                                        'local_file': file_path,
                                        'dataset': dataset,
                                        'reason': selected_dataset.get('reason', '')
                                    }
                                    result.local_results.append({
                                        'id': dataset.get('id', ''),
                                        'name': dataset.get('name', ''),
                                        'file': file_path,
                                        'score': 1.0,
                                        'metadata': dataset,
                                        'recommendation': selected_dataset.get('reason', '')
                                    })
                
                # ============================================================
                # 步骤2: 如果本地数据无法满足，执行在线检索
                # ============================================================
                if not local_data_used:
                    print(f"     [Step 2] Local data insufficient, executing online search...")
                    
                    # 🔧 修复：替换依赖参数（支持多种匹配方式）
                    if depends_on:
                        # 🔧 修复：如果depends_on是列表，取第一个元素
                        if isinstance(depends_on, list):
                            depends_on = depends_on[0] if depends_on else None
                        
                        if depends_on:
                            prev_output = None
                            depends_on_str = str(depends_on)
                            
                            # 方式1: 直接匹配
                            if depends_on in task_outputs:
                                prev_output = task_outputs[depends_on]
                            # 方式2: 字符串匹配
                            elif depends_on_str in task_outputs:
                                prev_output = task_outputs[depends_on_str]
                            # 方式3: 尝试匹配 output_name (如 'task_1')
                            else:
                                for key in task_outputs.keys():
                                    if str(depends_on) in str(key) or str(key) == f'task_{depends_on}':
                                        prev_output = task_outputs[key]
                                        break
                            
                            if prev_output and isinstance(prev_output, dict) and 'lat' in prev_output:
                                task_params['reference_coords'] = prev_output
                    
                    # 执行子任务（调用父类的原有逻辑）
                    self._execute_subtask(task, task_outputs, result, sub_result, user_query)
                else:
                    sub_result.success = True
                    print(f"      ✓ Task complete (using local data)")
                
            except Exception as e:
                sub_result.success = False
                sub_result.error = str(e)
                result.warnings.append(f"Subtask {task_id} execution failed: {e}")
                print(f"      ❌ Task execution failed: {e}")
            
            result.sub_task_results.append(sub_result)
        
        # 总结执行结果
        success_count = sum(1 for t in result.sub_task_results if t.success)
        # 🔧 修复：正确统计使用本地数据的任务数
        # 包括：1) result是dict且包含'local_file'  2) 任务描述中显示"使用本地"
        local_count = 0
        for t in result.sub_task_results:
            if not t.success:
                continue
            # 检查 result 类型
            if isinstance(t.result, dict) and 'local_file' in t.result:
                local_count += 1
            elif isinstance(t.result, list) and t.result:
                # 对于 osm_data 类型，检查文件是否来自本地（已存在于catalog）
                # 通过检查文件路径判断
                file_path = str(t.result[0]) if t.result else ''
                if 'downloaded_data' in file_path and any(
                    x in file_path.lower() for x in ['osm_roads', 'osm_building', 'boundary']
                ):
                    local_count += 1
        online_count = success_count - local_count
        
        print(f"\n   ✓ Completed {success_count}/{len(result.sub_task_results)} subtasks")
        print(f"      Local data: {local_count}")
        print(f"      Online search: {online_count}")
    
    def _execute_subtask(self, task: Dict[str, Any], task_outputs: Dict[str, Any],
                        result: UnifiedQueryResult, sub_result: SubTaskResult, user_query: str):
        """
        执行子任务（调用父类的原有逻辑）
        
        参考 data_search_with_clip_online.py 的实现方式
        """
        task_type = task.get('type', '')
        task_desc = task.get('description', '')
        task_params = task.get('params', {})
        depends_on = task.get('depends_on')
        output_name = task.get('output_name', f'task_{task.get("order", 0)}')
        
        if task_type == 'spatial_proximity':
            # 调用父类的空间邻近查询方法
            poi_type = task_params.get('poi_type', '')
            ref_location = task_params.get('reference_location', '')
            radius = task_params.get('radius_meters', 500)
            
            sub_intent = IntentAnalysis(
                intent=QueryIntent.SPATIAL_PROXIMITY,
                confidence=1.0,
                summary=task_desc,
                poi_type=poi_type,
                reference_location=ref_location,
                radius_meters=radius
            )
            temp_result = UnifiedQueryResult(
                query=task_desc, intent=sub_intent, source="osm"
            )
            self._handle_proximity_query(sub_intent, temp_result)
            sub_result.result = temp_result.poi_results
            result.poi_results.extend(temp_result.poi_results)
            
            if temp_result.poi_results:
                # 🔧 修复：保存POI结果到task_outputs，供后续routing任务使用
                first_poi = temp_result.poi_results[0]
                task_outputs[output_name] = {
                    'lat': first_poi.lat, 
                    'lon': first_poi.lon,
                    'name': first_poi.name,
                    'poi_results': temp_result.poi_results  # 保存完整的POI列表
                }
                print(f"      ✓ Found {len(temp_result.poi_results)} POIs")
                print(f"      ✓ Saved to task_outputs[{output_name}]: {len(temp_result.poi_results)} POIs")
                sub_result.success = True
            else:
                sub_result.success = False
                sub_result.error = "No POI found"
                print(f"      ⚠️ No POI found, possible reasons:")
                print(f"         - poi_type={poi_type}")
                print(f"         - reference_location={ref_location}")
                print(f"         - radius={radius}")
        
        elif task_type == 'poi_search':
            # 调用父类的POI搜索方法
            poi_type = task_params.get('poi_type', '')
            search_region = task_params.get('search_region', '')
            
            print(f"      [Debug] poi_search task params: poi_type={poi_type}, search_region={search_region}")
            print(f"      [Debug] task_params: {task_params}")
            print(f"      [Debug] task_desc: {task_desc}")
            
            # 🔧 修复：如果参数缺失，尝试从描述中提取（参考父类逻辑）
            if not poi_type or not search_region:
                print(f"      [Debug] Parameters missing, extracting from description...")
                extracted = self._extract_params_from_description(task_desc, 'poi_search')
                poi_type = poi_type or extracted.get('poi_type', '')
                search_region = search_region or extracted.get('search_region', '')
                print(f"      [Debug] Extracted parameters: poi_type={poi_type}, search_region={search_region}")
            
            if search_region:
                sub_intent = IntentAnalysis(
                    intent=QueryIntent.POI_SEARCH,
                    confidence=1.0,
                    summary=task_desc,
                    poi_type=poi_type,
                    search_region=search_region
                )
                temp_result = UnifiedQueryResult(
                    query=task_desc, intent=sub_intent, source="osm"
                )
                print(f"      [Debug] Calling _handle_poi_search_query...")
                self._handle_poi_search_query(sub_intent, temp_result)
                print(f"      [Debug] _handle_poi_search_query returned: {len(temp_result.poi_results) if temp_result.poi_results else 0} POIs")
                
                sub_result.result = temp_result.poi_results
                result.poi_results.extend(temp_result.poi_results)
                
                if temp_result.poi_results:
                    print(f"      ✓ Found {len(temp_result.poi_results)} POIs")
                    sub_result.success = True
                    # 🔧 Fix: Save POI results to task_outputs for subsequent routing tasks
                    first_poi = temp_result.poi_results[0]
                    task_outputs[output_name] = {
                        'lat': first_poi.lat, 
                        'lon': first_poi.lon,
                        'name': first_poi.name,
                        'poi_results': temp_result.poi_results  # Save complete POI list
                    }
                    print(f"      ✓ Saved to task_outputs[{output_name}]: {len(temp_result.poi_results)} POIs")
                else:
                    sub_result.success = False
                    sub_result.error = "No POI found"
                    print(f"      ⚠️ [Debug] No POI found, possible reasons:")
                    print(f"         - search_region={search_region}")
                    print(f"         - poi_type={poi_type}")
                    print(f"         - Please check if OSM query succeeded")
            else:
                sub_result.success = False
                sub_result.error = "Missing search region (search_region)"
                print(f"      ⚠️ [Debug] Missing search_region parameter")
        
        elif task_type == 'routing':
            # 调用父类的路由计算方法
            origin = task_params.get('origin', '')
            destination = task_params.get('destination', '')
            mode = task_params.get('transport_mode', 'walking')
            
            # 🔧 修复：处理依赖，从task_outputs中获取前一个任务的结果
            # 如果依赖任务失败，尝试从所有之前的任务中查找POI信息
            prev = None
            if depends_on:
                # 🔧 修复：如果depends_on是列表，取第一个元素
                if isinstance(depends_on, list):
                    depends_on = depends_on[0] if depends_on else None
                
                if depends_on:
                    # 尝试多种方式匹配depends_on（可能是数字或字符串）
                    depends_on_str = str(depends_on)
                    
                    print(f"      [Debug] Looking for dependent task {depends_on} result...")
                    print(f"      [Debug] task_outputs keys: {list(task_outputs.keys())}")
                    
                    # 方式1: 直接匹配
                    if depends_on in task_outputs:
                        prev = task_outputs[depends_on]
                        print(f"      ✓ Method 1 match success: depends_on={depends_on}")
                    # 方式2: 字符串匹配
                    elif depends_on_str in task_outputs:
                        prev = task_outputs[depends_on_str]
                        print(f"      ✓ Method 2 match succeeded: depends_on_str={depends_on_str}")
                    # 方式3: 尝试匹配 output_name (如 'task_1')
                    else:
                        for key in task_outputs.keys():
                            if str(depends_on) in str(key) or str(key) == f'task_{depends_on}':
                                prev = task_outputs[key]
                                print(f"      ✓ Method 3 match succeeded: key={key}")
                                break
            
            # Fix: If dependent task has no result, try to find POI info from all previous tasks
            if not prev or not isinstance(prev, dict) or 'poi_results' not in prev or not prev['poi_results']:
                print(f"      [Debug] Dependent task has no result, trying to find POI from all previous tasks...")
                # 遍历所有task_outputs，查找包含poi_results的任务
                for key, value in task_outputs.items():
                    if isinstance(value, dict) and 'poi_results' in value and value['poi_results']:
                        prev = value
                        print(f"      ✓ Found POI results from task {key}: {len(value['poi_results'])} POIs")
                        break
            
            if prev and isinstance(prev, dict):
                print(f"      ✓ Found task result: {list(prev.keys())}")
                # 如果前一个任务是poi_search/knowledge/semantic_analysis，使用POI结果
                if 'poi_results' in prev and prev['poi_results']:
                    poi_list = prev['poi_results']
                    print(f"      ✓ Found {len(poi_list)} POIs in task result")
                    # 🔧 修复：过滤掉"未命名"的POI，选择有名称的POI作为起点和终点
                    named_pois = [p for p in poi_list if hasattr(p, 'name') and p.name and p.name != 'Unnamed']
                    if not named_pois:
                        # 如果没有有名称的POI，使用所有POI
                        named_pois = poi_list
                    
                    # 对于"规划参观路线"这类查询，使用第一个有名称的POI作为起点，最后一个有名称的POI作为终点
                    if not origin and len(named_pois) > 0:
                        first_poi = named_pois[0]
                        origin = first_poi.name
                        print(f"      📍 Getting origin from task result: {origin}")
                    if not destination and len(named_pois) > 1:
                        last_poi = named_pois[-1]
                        destination = last_poi.name
                        print(f"      📍 Getting destination from task result: {destination}")
                    elif not destination and len(named_pois) == 1:
                        # 如果只有一个有名称的POI，使用它作为终点
                        first_poi = named_pois[0]
                        destination = destination or first_poi.name
                        print(f"      📍 Getting destination from task result (single POI): {destination}")
                elif 'name' in prev:
                    destination = destination or prev.get('name', '')
                    print(f"      📍 Getting destination from task result (name field): {destination}")
            else:
                print(f"      ⚠️ No task result found containing POI info")
            
            # 🔧 修复：如果还没有起点/终点，尝试从result.poi_results中获取（父类的逻辑）
            if not origin and result.poi_results:
                # 使用第一个 POI 作为起点
                first_poi = result.poi_results[0]
                origin = first_poi.name if first_poi.name and first_poi.name != 'Unnamed' else 'Nearest POI'
                print(f"      📍 Getting origin from result.poi_results: {origin} (total {len(result.poi_results)} POIs)")
            
            if not destination and result.poi_results:
                # 如果有多个POI，使用最后一个作为终点；否则使用第一个
                if len(result.poi_results) > 1:
                    last_poi = result.poi_results[-1]
                    destination = last_poi.name if last_poi.name and last_poi.name != 'Unnamed' else 'Nearest POI'
                else:
                    nearest_poi = result.poi_results[0]
                    destination = nearest_poi.name if nearest_poi.name and nearest_poi.name != 'Unnamed' else 'Nearest POI'
                print(f"      📍 Getting destination from result.poi_results: {destination} (total {len(result.poi_results)} POIs)")
            
            # 调试输出
            if not origin or not destination:
                print(f"      ⚠️ [Debug] Current state: origin={origin}, destination={destination}")
                print(f"      ⚠️ [Debug] result.poi_results count: {len(result.poi_results) if result.poi_results else 0}")
                if result.poi_results:
                    print(f"      ⚠️ [Debug] POI list: {[p.name for p in result.poi_results[:3]]}")
            
            if origin and destination:
                # 🔧 修复：优先使用POI坐标，而不是地理编码POI名称
                origin_coords = None
                dest_coords = None
                origin_name_for_display = origin
                dest_name_for_display = destination
                
                # 优先从task_outputs中获取POI坐标（如果依赖任务提供了POI列表）
                if prev and isinstance(prev, dict) and 'poi_results' in prev and prev['poi_results']:
                    poi_list = prev['poi_results']
                    
                    # 🔧 修复：过滤掉不在同一地理区域的POI（距离第一个POI超过10km的POI）
                    if len(poi_list) > 1:
                        first_poi = poi_list[0]
                        if hasattr(first_poi, 'lat') and hasattr(first_poi, 'lon'):
                            # 计算所有POI到第一个POI的距离
                            filtered_pois = [first_poi]
                            for poi in poi_list[1:]:
                                if hasattr(poi, 'lat') and hasattr(poi, 'lon'):
                                    # 计算距离（使用Haversine公式）
                                    lat1, lon1 = math.radians(first_poi.lat), math.radians(first_poi.lon)
                                    lat2, lon2 = math.radians(poi.lat), math.radians(poi.lon)
                                    dlat, dlon = lat2 - lat1, lon2 - lon1
                                    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
                                    distance_km = 2 * math.asin(math.sqrt(a)) * 6371
                                    
                                    # 只保留距离第一个POI在10km以内的POI
                                    if distance_km <= 10:
                                        filtered_pois.append(poi)
                                    else:
                                        print(f"      ⚠️ Filtered out POI too far away: {getattr(poi, 'name', 'Unnamed')} (distance {distance_km:.2f}km)")
                            
                            poi_list = filtered_pois
                            print(f"      ℹ After filtering, kept {len(poi_list)} POIs in same region (original {len(prev['poi_results'])})")
                    
                    # 如果有多个POI，使用第一个作为起点，最后一个作为终点
                    if len(poi_list) > 0:
                        first_poi = poi_list[0]
                        if hasattr(first_poi, 'lat') and hasattr(first_poi, 'lon'):
                            origin_coords = {'lat': first_poi.lat, 'lon': first_poi.lon}
                            origin_name_for_display = getattr(first_poi, 'name', origin)
                            print(f"      📍 Using first POI coordinates from dependent task as origin: {origin_name_for_display} ({first_poi.lat}, {first_poi.lon})")
                    
                    if len(poi_list) > 1:
                        last_poi = poi_list[-1]
                        if hasattr(last_poi, 'lat') and hasattr(last_poi, 'lon'):
                            dest_coords = {'lat': last_poi.lat, 'lon': last_poi.lon}
                            dest_name_for_display = getattr(last_poi, 'name', destination)
                            print(f"      📍 Using last POI coordinates from dependent task as destination: {dest_name_for_display} ({last_poi.lat}, {last_poi.lon})")
                    elif len(poi_list) == 1:
                        # 如果只有一个POI，也用它作为终点
                        first_poi = poi_list[0]
                        if hasattr(first_poi, 'lat') and hasattr(first_poi, 'lon'):
                            dest_coords = {'lat': first_poi.lat, 'lon': first_poi.lon}
                            dest_name_for_display = getattr(first_poi, 'name', destination)
                            print(f"      📍 Using only POI coordinates from dependent task as destination: {dest_name_for_display} ({first_poi.lat}, {first_poi.lon})")
                
                # 如果还没有找到坐标，尝试从result.poi_results中查找（按名称匹配）
                if not origin_coords and result.poi_results:
                    for poi in result.poi_results:
                        if hasattr(poi, 'name') and poi.name == origin:
                            origin_coords = {'lat': poi.lat, 'lon': poi.lon}
                            origin_name_for_display = poi.name
                            print(f"      📍 Using POI coordinates from result.poi_results as origin: {poi.name} ({poi.lat}, {poi.lon})")
                            break
                    # 如果按名称没找到，使用第一个POI
                    if not origin_coords and len(result.poi_results) > 0:
                        first_poi = result.poi_results[0]
                        origin_coords = {'lat': first_poi.lat, 'lon': first_poi.lon}
                        origin_name_for_display = getattr(first_poi, 'name', origin)
                        print(f"      📍 Using first POI coordinates from result.poi_results as origin: {origin_name_for_display} ({first_poi.lat}, {first_poi.lon})")
                
                if not dest_coords and result.poi_results:
                    for poi in result.poi_results:
                        if hasattr(poi, 'name') and poi.name == destination:
                            dest_coords = {'lat': poi.lat, 'lon': poi.lon}
                            dest_name_for_display = poi.name
                            print(f"      📍 Using POI coordinates from result.poi_results as destination: {poi.name} ({poi.lat}, {poi.lon})")
                            break
                    # 如果按名称没找到，使用最后一个POI（如果有多个）或第一个POI
                    if not dest_coords:
                        if len(result.poi_results) > 1:
                            last_poi = result.poi_results[-1]
                            dest_coords = {'lat': last_poi.lat, 'lon': last_poi.lon}
                            dest_name_for_display = getattr(last_poi, 'name', destination)
                            print(f"      📍 Using last POI coordinates from result.poi_results as destination: {dest_name_for_display} ({last_poi.lat}, {last_poi.lon})")
                        elif len(result.poi_results) == 1:
                            first_poi = result.poi_results[0]
                            dest_coords = {'lat': first_poi.lat, 'lon': first_poi.lon}
                            dest_name_for_display = getattr(first_poi, 'name', destination)
                            print(f"      📍 Using only POI coordinates from result.poi_results as destination: {dest_name_for_display} ({first_poi.lat}, {first_poi.lon})")
                
                # 如果还没有坐标，使用地理编码（回退方案）
                if not origin_coords:
                    print(f"      🔍 Geocoding origin: {origin}")
                    origin_coords = self.osm.geocode(origin) if origin else None
                
                if not dest_coords:
                    print(f"      🔍 Geocoding destination: {destination}")
                    dest_coords = self.osm.geocode(destination) if destination else None
                
                if origin_coords and dest_coords:
                    # 计算两点间的直线距离，如果超过50km，给出警告
                    lat1, lon1 = math.radians(origin_coords['lat']), math.radians(origin_coords['lon'])
                    lat2, lon2 = math.radians(dest_coords['lat']), math.radians(dest_coords['lon'])
                    dlat, dlon = lat2 - lat1, lon2 - lon1
                    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
                    straight_distance_km = 2 * math.asin(math.sqrt(a)) * 6371  # 地球半径6371km
                    
                    if straight_distance_km > 50:
                        print(f"      ⚠️ Warning: straight-line distance between origin and destination is {straight_distance_km:.2f}km, possible geocoding error")
                        print(f"         Origin: {origin_name_for_display} ({origin_coords['lat']}, {origin_coords['lon']})")
                        print(f"         Destination: {dest_name_for_display} ({dest_coords['lat']}, {dest_coords['lon']})")
                    
                    route = self.osm.calculate_route(
                        origin_coords['lat'], origin_coords['lon'],
                        dest_coords['lat'], dest_coords['lon'],
                        mode
                    )
                    if route:
                        route.origin = origin_name_for_display
                        route.destination = dest_name_for_display
                        result.route_result = route
                        sub_result.result = route
                        sub_result.success = True
                        print(f"      ✓ Route calculation successful: {route.distance_meters/1000:.2f}km")
                    else:
                        sub_result.error = "Route calculation failed"
                else:
                    sub_result.error = "Unable to get origin or destination coordinates"
            else:
                sub_result.error = f"Missing origin or destination (origin={origin}, destination={destination})"
        
        elif task_type == 'knowledge':
            # 调用父类的知识查询方法
            entity_name = task_params.get('entity_name', '')
            entity_type = task_params.get('entity_type', '')
            location_filter = task_params.get('location_filter', '')
            
            # 🔧 修复：如果参数缺失，尝试从描述中提取
            if not entity_name and not entity_type:
                print(f"      🔍 [Debug] Parameters missing, extracting from description...")
                extracted = self._extract_params_from_description(task_desc, 'knowledge')
                entity_name = entity_name or extracted.get('entity_name', '')
                entity_type = entity_type or extracted.get('entity_type', '')
                location_filter = location_filter or extracted.get('location_filter', '')
                print(f"      🔍 [Debug] Extracted parameters: entity_name={entity_name}, entity_type={entity_type}, location_filter={location_filter}")
            
            sub_intent = IntentAnalysis(
                intent=QueryIntent.KNOWLEDGE,
                confidence=1.0,
                summary=task_desc,
                entity_name=entity_name,
                entity_type=entity_type,
                location_filter=location_filter
            )
            temp_result = UnifiedQueryResult(
                query=task_desc, intent=sub_intent, source="wikidata"
            )
            self._handle_knowledge_query(sub_intent, temp_result)
            sub_result.result = temp_result.knowledge_results
            result.knowledge_results.extend(temp_result.knowledge_results)
            
            # 🔧 修复：检查Wikidata结果和Overpass API回退结果
            poi_results = []
            from geo_query_engine import POIResult
            
            # 方式1: 如果有Wikidata结果，转换为POIResult
            if temp_result.knowledge_results:
                print(f"      ✓ Found {len(temp_result.knowledge_results)} Wikidata entities")
                for entity in temp_result.knowledge_results[:10]:  # 只取前10个
                    if entity.lat and entity.lon:
                        poi_result = POIResult(
                            osm_id=0,
                            name=entity.name,
                            poi_type=entity.entity_type or 'landmark',
                            lat=entity.lat,
                            lon=entity.lon,
                            distance_meters=0.0,
                            tags={},
                            address=entity.description or ''
                        )
                        poi_results.append(poi_result)
            
            # 方式2: 如果Wikidata失败但Overpass API回退成功，使用POI结果
            original_poi_count = 0
            if not poi_results and temp_result.poi_results:
                original_poi_count = len(temp_result.poi_results)
                print(f"      ✓ Wikidata failed, but Overpass API found {original_poi_count} POIs")
                poi_results = temp_result.poi_results[:10]  # 只取前10个
            
            if poi_results:
                # 🔧 修复：过滤掉不在同一地理区域的POI（距离第一个POI超过10km的POI）
                original_count = len(poi_results)
                if len(poi_results) > 1:
                    first_poi = poi_results[0]
                    if hasattr(first_poi, 'lat') and hasattr(first_poi, 'lon'):
                        filtered_pois = [first_poi]
                        for poi in poi_results[1:]:
                            if hasattr(poi, 'lat') and hasattr(poi, 'lon'):
                                # 计算距离（使用Haversine公式）
                                lat1, lon1 = math.radians(first_poi.lat), math.radians(first_poi.lon)
                                lat2, lon2 = math.radians(poi.lat), math.radians(poi.lon)
                                dlat, dlon = lat2 - lat1, lon2 - lon1
                                a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
                                distance_km = 2 * math.asin(math.sqrt(a)) * 6371
                                
                                # 只保留距离第一个POI在10km以内的POI
                                if distance_km <= 10:
                                    filtered_pois.append(poi)
                                else:
                                    print(f"      ⚠️ Filtered out POI too far away: {getattr(poi, 'name', 'Unnamed')} (distance {distance_km:.2f}km)")
                        
                        poi_results = filtered_pois
                        if original_count > len(poi_results):
                            print(f"      ℹ️ After filtering, kept {len(poi_results)} POIs in same region (original {original_count})")
                
                result.poi_results.extend(poi_results)
                # 保存到task_outputs（过滤掉"未命名"的POI）
                named_pois = [p for p in poi_results if hasattr(p, 'name') and p.name and p.name != 'Unnamed']
                if not named_pois:
                    # 如果没有有名称的POI，使用所有POI
                    named_pois = poi_results
                
                if named_pois:
                    first_poi = named_pois[0]
                    task_outputs[output_name] = {
                        'lat': first_poi.lat,
                        'lon': first_poi.lon,
                        'name': first_poi.name,
                        'poi_results': named_pois,  # 只保存有名称的POI
                        'knowledge_results': temp_result.knowledge_results if temp_result.knowledge_results else []  # 也保存原始知识结果（如果有）
                    }
                    print(f"      ✓ Saved {len(named_pois)} named entities/POIs to task_outputs for subsequent routing tasks")
                    sub_result.success = True
                else:
                    # 如果没有有名称的POI，至少保存第一个（即使未命名）
                    first_poi = poi_results[0]
                    task_outputs[output_name] = {
                        'lat': first_poi.lat,
                        'lon': first_poi.lon,
                        'name': first_poi.name,
                        'poi_results': poi_results,
                        'knowledge_results': temp_result.knowledge_results if temp_result.knowledge_results else []
                    }
                    print(f"      ⚠️ Saved {len(poi_results)} entities/POIs to task_outputs (some unnamed)")
                    sub_result.success = True
            else:
                sub_result.error = "Wikidata query returned no results"
                print(f"      ⚠️ [Debug] Wikidata query returned no results, possible reasons:")
                print(f"         - entity_name={entity_name}")
                print(f"         - entity_type={entity_type}")
                print(f"         - location_filter={location_filter}")
                print(f"         - Please check if Wikidata query succeeded")
        
        elif task_type == 'osm_data':
            # 调用父类的OSM数据下载方法
            region = task_params.get('region', '') or task_params.get('osm_region', '')
            data_types = task_params.get('data_types', ['roads', 'buildings'])
            
            # 🔧 修复：如果参数缺失，尝试从描述中提取（参考semantic_analysis的逻辑）
            if not region:
                print(f"      🔍 [Debug] Parameters missing, extracting region from description...")
                extracted = self._extract_params_from_description(task_desc, 'osm_data')
                region = extracted.get('region', '') or extracted.get('osm_region', '')
                if extracted.get('data_types'):
                    data_types = extracted.get('data_types', data_types)
                print(f"      🔍 [Debug] Extracted parameters: region={region}, data_types={data_types}")
            
            if region:
                sub_intent = IntentAnalysis(
                    intent=QueryIntent.OSM_DATA,
                    confidence=1.0,
                    summary=task_desc,
                    osm_region=region,
                    osm_data_types=data_types
                )
                temp_result = UnifiedQueryResult(
                    query=task_desc, intent=sub_intent, source="osm"
                )
                self._handle_osm_data_query(sub_intent, temp_result)
                sub_result.result = temp_result.downloaded_files
                result.downloaded_files.extend(temp_result.downloaded_files)
                
                if temp_result.downloaded_files:
                    print(f"      ✓ Downloaded {len(temp_result.downloaded_files)} files")
                else:
                    sub_result.error = "OSM data download failed"
            else:
                sub_result.error = "Unable to extract region from description"
                print(f"      ⚠️ [Debug] Unable to extract region, task_params={task_params}, task_desc={task_desc}")
        
        elif task_type == 'semantic_analysis':
            # 🆕 调用父类的语义分析方法
            region = task_params.get('region', '') or task_params.get('osm_region', '')
            
            # 如果参数缺失，尝试从描述中提取
            if not region:
                extracted = self._extract_params_from_description(task_desc, 'semantic_analysis')
                region = extracted.get('region', '') or extracted.get('osm_region', '')
            
            if region:
                sub_intent = IntentAnalysis(
                    intent=QueryIntent.SEMANTIC_ANALYSIS,
                    confidence=1.0,
                    summary=task_desc,
                    osm_region=region,
                    location_filter=region
                )
                temp_result = UnifiedQueryResult(
                    query=task_desc, intent=sub_intent, source="worldkg"
                )
                self._handle_semantic_analysis_query(sub_intent, temp_result)
                
                if temp_result.properties.get('semantic_analysis'):
                    sub_result.result = temp_result.properties['semantic_analysis']
                    result.properties['semantic_analysis'] = temp_result.properties['semantic_analysis']
                    sub_result.success = True
                    print(f"      ✓ Semantic analysis completed")
                    
                    # Show type statistics summary
                    analysis = temp_result.properties['semantic_analysis']
                    if 'type_counts' in analysis:
                        top_types = sorted(analysis['type_counts'].items(), 
                                          key=lambda x: x[1], reverse=True)[:3]
                        print(f"         Main types: {', '.join([f'{t[0]}({t[1]})' for t in top_types])}")
                    
                    # 🔧 修复：保存语义分析结果中的POI信息到task_outputs，供后续routing任务使用
                    # 语义分析结果可能包含在 'entities' 或 'pois' 字段中
                    poi_list = analysis.get('pois', []) or analysis.get('entities', [])
                    
                    # 🔧 修复：即使poi_list为空，也尝试从temp_result.poi_results中获取（如果语义分析过程中生成了POI）
                    if not poi_list and temp_result.poi_results:
                        print(f"      ℹ️ No pois/entities field in semantic analysis results, but found {len(temp_result.poi_results)} POIs")
                        # 将POIResult转换为字典格式以便统一处理
                        poi_list = [{'name': p.name, 'lat': p.lat, 'lon': p.lon, 'type': p.poi_type, 'osm_id': p.osm_id, 'tags': p.tags, 'address': p.address} 
                                   for p in temp_result.poi_results[:10]]
                    
                    if poi_list:
                        # 将POI转换为POIResult格式（如果还不是）
                        from geo_query_engine import POIResult
                        poi_results = []
                        for poi in poi_list[:10]:  # 只取前10个
                            if isinstance(poi, dict):
                                poi_result = POIResult(
                                    osm_id=poi.get('osm_id', 0),
                                    name=poi.get('name', poi.get('label', 'Unnamed')),
                                    poi_type=poi.get('type', poi.get('category', '')),
                                    lat=poi.get('lat', poi.get('latitude', 0.0)),
                                    lon=poi.get('lon', poi.get('longitude', 0.0)),
                                    distance_meters=0.0,
                                    tags=poi.get('tags', {}),
                                    address=poi.get('address', '')
                                )
                                poi_results.append(poi_result)
                            elif hasattr(poi, 'name'):  # 如果已经是POIResult对象
                                poi_results.append(poi)
                        
                        if poi_results:
                            result.poi_results.extend(poi_results)
                            # 保存到task_outputs（过滤掉"未命名"的POI）
                            named_pois = [p for p in poi_results if hasattr(p, 'name') and p.name and p.name != 'Unnamed']
                            if named_pois:
                                first_poi = named_pois[0]
                                task_outputs[output_name] = {
                                    'lat': first_poi.lat,
                                    'lon': first_poi.lon,
                                    'name': first_poi.name,
                                    'poi_results': named_pois  # 只保存有名称的POI
                                }
                                print(f"      ✓ Saved {len(named_pois)} named POIs to task_outputs for subsequent routing tasks")
                            else:
                                # 如果没有有名称的POI，至少保存第一个（即使未命名）
                                first_poi = poi_results[0]
                                task_outputs[output_name] = {
                                    'lat': first_poi.lat,
                                    'lon': first_poi.lon,
                                    'name': first_poi.name,
                                    'poi_results': poi_results
                                }
                                print(f"      ⚠️ Saved {len(poi_results)} POIs to task_outputs (some unnamed)")
                    else:
                        print(f"      ⚠️ No POI info found in semantic analysis results (pois/entities field is empty)")
                else:
                    sub_result.error = "Semantic analysis returned no results"
                    if temp_result.warnings:
                        print(f"      ⚠️ {temp_result.warnings[0]}")
            else:
                sub_result.error = "Unable to extract region from description"
        
        elif task_type == 'remote_sensing_data':
            # 🆕 遥感数据下载子任务
            satellite = task_params.get('satellite', 'sentinel-2')
            time_range = task_params.get('time_range', '')
            region = task_params.get('region', '') or task_params.get('remote_sensing_region', '')
            cloud_cover_max = task_params.get('cloud_cover_max', DEFAULT_CLOUD_COVER_MAX)
            processing = task_params.get('processing', '')
            
            # 如果参数缺失，尝试从描述中提取
            if not region or not time_range:
                extracted = self._extract_params_from_description(task_desc, 'remote_sensing_data')
                region = region or extracted.get('region', '') or extracted.get('remote_sensing_region', '')
                time_range = time_range or extracted.get('time_range', '')
                satellite = satellite or extracted.get('satellite', 'sentinel-2')
            
            # 如果还没有时间范围，使用默认值（最近3个月）
            if not time_range:
                from datetime import datetime, timedelta
                end_date = datetime.now()
                start_date = end_date - timedelta(days=90)
                time_range = f"{start_date.strftime('%Y-%m-%d')},{end_date.strftime('%Y-%m-%d')}"
                print(f"      ℹ️ No time range specified, using default: {time_range}")
            
            if region:
                sub_intent = IntentAnalysis(
                    intent=QueryIntent.REMOTE_SENSING_DATA,
                    confidence=1.0,
                    summary=task_desc,
                    satellite=satellite,
                    time_range=time_range,
                    cloud_cover_max=cloud_cover_max,
                    processing=processing,
                    remote_sensing_region=region
                )
                temp_result = UnifiedQueryResult(
                    query=task_desc, intent=sub_intent, source="remote_sensing"
                )
                self._handle_remote_sensing_query(sub_intent, temp_result)
                
                if temp_result.remote_sensing_data:
                    sub_result.result = temp_result.remote_sensing_data
                    result.remote_sensing_data = temp_result.remote_sensing_data
                    result.downloaded_files.extend(temp_result.downloaded_files)
                    print(f"      ✓ Remote sensing data download successful:")
                    print(f"         📁 {os.path.basename(temp_result.remote_sensing_data)}")
                    sub_result.success = True
                else:
                    sub_result.error = "Remote sensing data download failed"
                    if temp_result.warnings:
                        sub_result.error += f": {temp_result.warnings[0]}"
            else:
                sub_result.success = False
                sub_result.error = "Unable to extract region from description"
        
        elif task_type == 'geocode':
            # 🆕 Geocoding subtask
            location = task_params.get('location', '')
            
            # If parameters are missing, try to extract from description
            if not location:
                # Simple extraction: try to find location name from description
                import re
                # Chinese: 获取XX的坐标
                match = re.search(r'获取(.+?)的坐标|(.+?)的坐标', task_desc)
                if match:
                    location = match.group(1) or match.group(2)
                # 英文: geocode X, coordinates of X
                match = re.search(r'geocode\s+(.+?)(?:\s|$)|coordinates?\s+of\s+(.+?)(?:\s|$)', task_desc, re.IGNORECASE)
                if match:
                    location = match.group(1) or match.group(2)
            
            if location:
                coords = self.osm.geocode(location)
                if coords:
                    sub_result.result = coords
                    task_outputs[output_name] = coords
                    print(f"      ✓ {location} -> ({coords['lat']:.4f}, {coords['lon']:.4f})")
                    sub_result.success = True
                else:
                    sub_result.success = False
                    sub_result.error = f"Unable to geocode location: {location}"
            else:
                sub_result.success = False
                sub_result.error = "Unable to extract location from description"
        
        elif task_type == 'worldkg':
            # 🆕 WorldKG 语义查询（兼容旧版本）
            entity_type = task_params.get('entity_type', '')
            region = task_params.get('region', '')
            
            if not entity_type or not region:
                extracted = self._extract_params_from_description(task_desc, 'worldkg')
                entity_type = entity_type or extracted.get('entity_type', '')
                region = region or extracted.get('region', '')
            
            # 【重要】如果区域仍为空，尝试从上游任务继承
            if not region:
                if 'query_region' in task_outputs:
                    region = task_outputs['query_region']
                    print(f"      📍 Inherited region from upstream: {region}")
                elif depends_on and str(depends_on) in task_outputs:
                    prev = task_outputs[str(depends_on)]
                    if isinstance(prev, dict) and 'name' in prev:
                        entity_name = prev.get('name', '')
                        inferred = self._infer_region_from_context(entity_name, task_desc)
                        if inferred:
                            region = inferred
                            print(f"      📍 Inferred region from context: {region}")
            
            if region:
                sub_intent = IntentAnalysis(
                    intent=QueryIntent.WORLDKG,
                    confidence=1.0,
                    summary=task_desc,
                    entity_type=entity_type,
                    osm_region=region
                )
                temp_result = UnifiedQueryResult(
                    query=task_desc, intent=sub_intent, source="worldkg"
                )
                self._handle_worldkg_query(sub_intent, temp_result)
                sub_result.result = temp_result.knowledge_results
                result.knowledge_results.extend(temp_result.knowledge_results)
                
                if temp_result.knowledge_results:
                    print(f"      ✓ Found {len(temp_result.knowledge_results)} WorldKG entities")
                    sub_result.success = True
                else:
                    sub_result.error = "WorldKG query returned no results"
            else:
                sub_result.success = False
                sub_result.error = "Unable to extract region from description"
        
        elif task_type == 'recommendation':
            # 🆕 推荐查询子任务（多条件筛选，使用 Wikidata）
            facility_type = task_params.get('facility_type', '')
            criteria = task_params.get('criteria', [])
            location_context = task_params.get('location_context', '')
            
            # 如果参数缺失，尝试从描述中提取
            if not facility_type:
                extracted = self._extract_params_from_description(task_desc, 'recommendation')
                facility_type = facility_type or extracted.get('facility_type', '')
                criteria = criteria or extracted.get('criteria', [])
                location_context = location_context or extracted.get('location_context', '')
            
            if facility_type:
                sub_intent = IntentAnalysis(
                    intent=QueryIntent.RECOMMENDATION,
                    confidence=1.0,
                    summary=task_desc,
                    facility_type=facility_type,
                    criteria=criteria,
                    location_context=location_context
                )
                temp_result = UnifiedQueryResult(
                    query=task_desc, intent=sub_intent, source="wikidata+osm"
                )
                self._handle_recommendation_query(sub_intent, temp_result)
                sub_result.result = temp_result.poi_results or temp_result.knowledge_results
                result.poi_results.extend(temp_result.poi_results or [])
                result.knowledge_results.extend(temp_result.knowledge_results or [])
                
                if temp_result.poi_results or temp_result.knowledge_results:
                    print(f"      ✓ Found {len(temp_result.poi_results or temp_result.knowledge_results)} recommendation results")
                    sub_result.success = True
                else:
                    sub_result.error = "Recommendation query returned no results"
            else:
                sub_result.success = False
                sub_result.error = "Unable to extract facility type from description"
        
        else:
            sub_result.error = f"Unknown task type: {task_type}"
        
        if not sub_result.error and sub_result.result:
            sub_result.success = True
    
    def _handle_osm_data_query(self, intent: IntentAnalysis, result: UnifiedQueryResult):
        """
        重写父类的_handle_osm_data_query方法，先检查本地数据
        
        Args:
            intent: 意图分析结果
            result: 查询结果
        """
        # 先尝试本地数据匹配
        if self.vector_matcher and intent.osm_region:
            print(f"   🔍 [Step 1] Checking local data (region: {intent.osm_region})...")
            task_desc = f"Download vector boundary for {intent.osm_region}"
            candidate_datasets = self.vector_matcher.search_local_data(task_desc, top_n=5)
            
            if candidate_datasets:
                selected_dataset = self.vector_matcher.check_if_satisfies_requirement(
                    task_desc, candidate_datasets
                )
                
                if selected_dataset:
                    dataset = selected_dataset['dataset']
                    file_path = dataset.get('absolute_path', '')
                    
                    # 检查是否是边界数据
                    if 'boundary' in dataset.get('name', '').lower() or 'boundary' in dataset.get('description', '').lower():
                        print(f"   ✓ Using local boundary data: {Path(file_path).name}")
                        result.downloaded_files.append(file_path)
                        result.message = f"Using local data: {Path(file_path).name}"
                        return
        
        # If local data cannot satisfy, call parent method for online download
        print(f"   🌐 [Step 2] Local data insufficient, executing online download...")
        super()._handle_osm_data_query(intent, result)
        
        # 🔧 修复：检查是否有边界文件被保存，如果有，添加到 downloaded_files
        if intent.osm_region:
            # 构建可能的边界文件路径（处理中文区域名）
            region_safe = intent.osm_region.replace(' ', '_').replace('/', '_')[:30]
            # 尝试多个可能的路径
            boundary_file_candidates = [
                Path(self.output_dir) / 'boundaries' / f'boundary_{region_safe}.geojson',
                Path.cwd() / 'downloaded_data' / 'boundaries' / f'boundary_{region_safe}.geojson',
                Path.cwd() / self.output_dir / 'boundaries' / f'boundary_{region_safe}.geojson',
            ]
            
            # 也尝试直接搜索 boundaries 目录下的所有 boundary_*.geojson 文件
            boundaries_dir = Path(self.output_dir) / 'boundaries'
            if not boundaries_dir.exists():
                boundaries_dir = Path.cwd() / 'downloaded_data' / 'boundaries'
            
            if boundaries_dir.exists():
                # 查找所有 boundary_*.geojson 文件，匹配区域名（处理中文）
                for boundary_file in boundaries_dir.glob('boundary_*.geojson'):
                    # 检查文件名是否包含区域名（处理中文）
                    if region_safe in boundary_file.stem or intent.osm_region in boundary_file.stem:
                        boundary_path = str(boundary_file.absolute())
                        # 如果还没有添加到 downloaded_files，则添加
                        if boundary_path not in result.downloaded_files:
                            print(f"   🔧 [Fix] Found boundary file, adding to downloaded_files: {boundary_file.name}")
                            result.downloaded_files.append(boundary_path)
                        break
            
            # 如果上面没找到，再尝试候选路径
            if not result.downloaded_files:
                for boundary_file in boundary_file_candidates:
                    if boundary_file.exists():
                        boundary_path = str(boundary_file.absolute())
                        print(f"   🔧 [Fix] Found boundary file, adding to downloaded_files: {boundary_file.name}")
                        result.downloaded_files.append(boundary_path)
                        break
        
        # 调试输出：查看最终的文件路径
        if result.downloaded_files:
            print(f"   🔍 [Debug] Final {len(result.downloaded_files)} files in result.downloaded_files:")
            for fp in result.downloaded_files:
                print(f"      - {fp}")
        else:
            print(f"   ⚠️ [Debug] result.downloaded_files is still empty")
    
    def _handle_remote_sensing_query(self, intent: 'IntentAnalysis', 
                                     result: 'UnifiedQueryResult'):
        """
        重写父类的遥感数据处理方法，增加本地数据优先检查
        
        Args:
            intent: 意图分析结果
            result: 查询结果对象
        """
        # 先检查本地是否有匹配的遥感数据
        if self.vector_matcher:
            region = intent.remote_sensing_region or ''
            satellite = intent.satellite or 'sentinel-2'
            time_range = intent.time_range or ''
            
            # Build search description
            search_desc = f"Find {satellite} remote sensing imagery for {region}"
            if time_range:
                search_desc += f", time range {time_range}"
            
            print(f"   [Local First] Checking for matching local remote sensing data...")
            candidate_datasets = self.vector_matcher.search_local_data(search_desc, top_n=5)
            
            if candidate_datasets:
                # 使用大模型判断是否能满足需求
                selected_dataset = self.vector_matcher.check_if_satisfies_requirement(
                    search_desc, candidate_datasets
                )
                
                if selected_dataset:
                    # Local data can meet the requirements
                    dataset = selected_dataset['dataset']
                    file_path = dataset.get('absolute_path', '')
                    
                    print(f"   ✓ Using local remote sensing data: {Path(file_path).name}")
                    print(f"      Path: {file_path}")
                    print(f"      Reason: {selected_dataset.get('reason', '')}")
                    
                    # 🆕 检查本地数据是否已经按边界裁剪过
                    # 如果文件名不包含 _boundary 或区域名，且用户查询的是具体地标（如清华大学），则需要裁剪
                    needs_clipping = False
                    stem = Path(file_path).stem
                    if '_boundary' not in stem:
                        # 判断是否是具体地标而非大区域（如"北京"、"上海"等）
                        # 如果是地标（如清华大学、颐和园），则需要裁剪
                        landmark_keywords = ['大学', '学院', '公园', '景区', '博物馆', '寺', '宫', '园', '山', 
                                           'university', 'college', 'park', 'museum', 'temple', 'palace']
                        if any(kw in region.lower() for kw in landmark_keywords):
                            needs_clipping = True
                            print(f"   ℹ️ Landmark query detected, need to clip remote sensing image by boundary")
                    
                    # 如果需要裁剪，尝试获取边界并裁剪
                    if needs_clipping:
                        # 尝试获取地标边界
                        from pathlib import Path as PathLib
                        boundary_file = None
                        region_id = region
                        
                        # 检查是否有对应的边界文件
                        boundary_dir = PathLib(self.output_dir) / 'boundaries'
                        if boundary_dir.exists():
                            # 查找匹配的边界文件
                            possible_boundaries = list(boundary_dir.glob(f'boundary_{region}*.geojson'))
                            if possible_boundaries:
                                boundary_file = possible_boundaries[0]
                                print(f"   ✓ Found local boundary file: {boundary_file.name}")
                        
                        # 如果本地没有边界，尝试在线获取
                        if not boundary_file:
                            print(f"   ℹ️ Trying to get boundary for '{region}'...")
                            from core.geo_query_engine import GeoQueryEngine
                            # 临时创建一个engine实例来获取边界
                            temp_engine = GeoQueryEngine(
                                catalog_path=self.catalog_path,
                                output_dir=self.output_dir,
                                use_llm=False,
                                api_key=self.api_key
                            )
                            online_boundary = temp_engine.osm.get_admin_boundary(region)
                            
                            if online_boundary and online_boundary.get('geojson_file'):
                                boundary_file = PathLib(online_boundary['geojson_file'])
                                print(f"   ✓ Successfully obtained boundary online")
                        
                        # 执行裁剪
                        if boundary_file and boundary_file.exists():
                            print(f"   Clipping remote sensing image by boundary...")
                            # 调用父类的裁剪方法
                            clipped_filepath = self._clip_raster_to_boundary(
                                file_path, boundary_file, region_id
                            )
                            if clipped_filepath:
                                file_path = clipped_filepath
                                print(f"   ✓ Clipping completed: {Path(file_path).name}")
                                
                                # 更新数据目录，添加裁剪后的文件
                                self._add_downloaded_file_to_catalog(clipped_filepath)
                            else:
                                print(f"   ⚠️ Clipping failed, using original file")
                        else:
                            print(f"   ⚠️ Boundary file not found, using original remote sensing image (may contain data outside the region)")
                    
                    result.remote_sensing_data = file_path
                    result.local_results.append({
                        'id': dataset.get('dataset_id', ''),
                        'name': dataset.get('name', ''),
                        'file': file_path,
                        'score': 1.0,
                        'metadata': dataset,
                        'recommendation': selected_dataset.get('reason', '')
                    })
                    result.suggestions.append(f"Found matching remote sensing data in local: {Path(file_path).name}")
                    return
        
        # Local data cannot satisfy, execute online download
        print(f"   🌐 No matching local data, executing online remote sensing download...")
        super()._handle_remote_sensing_query(intent, result)
    
    def _handle_osm_data_query(self, intent: 'IntentAnalysis', 
                               result: 'UnifiedQueryResult'):
        """
        重写父类的OSM数据处理方法，增加本地数据优先检查
        
        Args:
            intent: 意图分析结果
            result: 查询结果对象
        """
        # 先检查本地是否有匹配的OSM数据
        if self.vector_matcher:
            region = intent.osm_region or ''
            region_lower = region.lower()
            data_types = intent.osm_data_types or ['roads', 'buildings']
            
            # Build search description
            data_types_str = ', '.join(data_types)
            search_desc = f"Find {data_types_str} data for {region}"
            
            print(f"   [Local First] Checking for matching local OSM data...")
            candidate_datasets = self.vector_matcher.search_local_data(search_desc, top_n=10)
            
            if candidate_datasets:
                # 🔧 直接使用LLM判断（prompt已优化，能正确判断地理范围覆盖问题）
                # 不再使用基于规则的文件名匹配，完全交给LLM判断
                selected_dataset = self.vector_matcher.check_if_satisfies_requirement(
                    search_desc, candidate_datasets[:5]
                )
                
                if selected_dataset:
                    dataset = selected_dataset['dataset']
                    file_path = dataset.get('absolute_path', '')
                    
                    print(f"   ✓ Using local OSM data: {Path(file_path).name}")
                    print(f"      Path: {file_path}")
                    
                    # 🔧 修复：本地使用的文件不添加到downloaded_files，只添加到local_results
                    # 这样后续的"自动处理下载的文件"就不会处理本地文件
                    result.local_results.append({
                        'id': dataset.get('dataset_id', ''),
                        'name': dataset.get('name', ''),
                        'file': file_path,
                        'score': 1.0,
                        'metadata': dataset,
                        'recommendation': selected_dataset.get('reason', '')
                    })
                    result.message = f"Using local data: {Path(file_path).name}"
                    return
        
        # Local data cannot satisfy, execute online download
        print(f"   🌐 No matching local OSM data, executing online download...")
        super()._handle_osm_data_query(intent, result)
    
    def query(self, user_query: str, top_k: int = 5) -> UnifiedQueryResult:
        """
        重写父类的query方法，在查询完成后自动处理下载的文件
        
        Args:
            user_query: 用户查询
            top_k: Top K结果数量
            
        Returns:
            查询结果
        """
        # 调用父类方法执行查询
        result = super().query(user_query, top_k)
        
        # 自动处理查询过程中下载的文件（添加到catalog和向量数据库）
        if result.downloaded_files and self.catalog_path:
            print(f"\nAuto-processing {len(result.downloaded_files)} downloaded files...")
            for file_path in result.downloaded_files:
                # 🔧 修复：先转换为字符串，然后处理路径
                file_path_str = str(file_path)
                
                # 检查文件是否存在（可能是相对路径）
                file_path_obj = Path(file_path_str)
                
                # 如果路径不是绝对路径，尝试多个可能的解析方式
                if not file_path_obj.is_absolute():
                    # 方式1: 相对于output_dir（output_dir可能是相对路径或绝对路径）
                    if Path(self.output_dir).is_absolute():
                        candidate1 = Path(self.output_dir) / file_path_str
                    else:
                        candidate1 = Path.cwd() / self.output_dir / file_path_str
                    
                    # 方式2: 相对于当前工作目录
                    candidate2 = Path.cwd() / file_path_str
                    
                    # 方式3: 直接使用原始路径（可能是相对于脚本目录）
                    candidate3 = Path(file_path_str)
                    
                    # 方式4: 尝试将反斜杠路径转换为正斜杠后再试
                    file_path_normalized = file_path_str.replace('\\', '/')
                    candidate4 = Path.cwd() / file_path_normalized
                    
                    # 尝试找到存在的文件
                    if candidate1.exists():
                        file_path_obj = candidate1
                    elif candidate2.exists():
                        file_path_obj = candidate2
                    elif candidate3.exists():
                        file_path_obj = candidate3
                    elif candidate4.exists():
                        file_path_obj = candidate4
                    else:
                        # 如果都不存在，尝试相对于output_dir的原始路径
                        if Path(self.output_dir).is_absolute():
                            candidate5 = Path(self.output_dir) / file_path_normalized
                        else:
                            candidate5 = Path.cwd() / self.output_dir / file_path_normalized
                        if candidate5.exists():
                            file_path_obj = candidate5
                        else:
                            print(f"   ⚠️ File not found, skipping: {file_path}")
                            print(f"     Tried paths:")
                            print(f"       - {candidate1}")
                            print(f"       - {candidate2}")
                            print(f"       - {candidate3}")
                            print(f"       - {candidate4}")
                            print(f"       - {candidate5}")
                            continue
                
                # 确保使用绝对路径
                file_path_obj = file_path_obj.resolve()
                
                if file_path_obj.exists():
                    print(f"   Processing file: {file_path_obj.name} (path: {file_path_obj})")
                    self._add_downloaded_file_to_catalog(str(file_path_obj))
                else:
                    print(f"   ⚠️ File not found, skipping: {file_path} (final path: {file_path_obj})")
        
        return result
    
    def download_results(self, result: UnifiedQueryResult, output_dir: str = None) -> List[str]:
        """
        重写父类的download_results方法，添加自动添加到catalog和向量数据库的功能
        
        Args:
            result: 查询结果
            output_dir: 输出目录，默认使用 self.output_dir
            
        Returns:
            保存的文件路径列表
        """
        # 调用父类方法保存文件
        saved_files = super().download_results(result, output_dir)
        
        # 自动添加新下载的数据到catalog和向量数据库
        if saved_files and self.catalog_path:
            print(f"\nAutomatically adding {len(saved_files)} newly downloaded files to data catalog and vector database...")
            for file_path in saved_files:
                self._add_downloaded_file_to_catalog(file_path)
        
        return saved_files
    
    def _add_downloaded_file_to_catalog(self, file_path: str):
        """
        将新下载的文件添加到catalog和向量数据库
        
        Args:
            file_path: 下载的文件路径
        """
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            print(f"   ⚠️ File not found: {file_path}")
            return
        
        try:
            # 🔧 修复：检查文件是否已经存在于catalog中（避免重复添加）
            absolute_path = str(file_path_obj.absolute())
            dataset_id = self.vector_matcher._generate_dataset_id(absolute_path) if self.vector_matcher else None
            
            # 检查catalog中是否已存在该文件
            if self.metadata_generator.file_exists_in_catalog(absolute_path, self.catalog_path):
                print(f"   ⚠️ File already exists in catalog, skipping: {file_path_obj.name}")
                return
            
            # 1. 生成元数据（使用metadata_generator模块）
            metadata = self.metadata_generator.generate_metadata_for_file(file_path_obj)
            if not metadata:
                print(f"   ⚠️ Unable to generate metadata: {file_path}")
                return
            
            # 🔧 修复：添加dataset_id字段到metadata，使其与向量库一致
            if dataset_id:
                metadata['dataset_id'] = dataset_id
            
            # 2. 添加到catalog
            if not self.catalog_path:
                print(f"   ⚠️ catalog_path not set, unable to add to catalog")
            else:
                self.metadata_generator.add_metadata_to_catalog(metadata, self.catalog_path)
            
            # 3. 添加到向量数据库（检查是否已存在）
            if self.vector_matcher and self.vector_matcher.vector_db:
                description = metadata.get('description', '')
                
                # 🔧 增强描述：将文件名语义信息添加到描述开头
                # 从文件名中提取关键信息（如 hotel_北京 -> 北京的酒店数据）
                filename_stem = file_path_obj.stem  # 不含扩展名
                filename_parts = filename_stem.replace('_', ' ').replace('-', ' ')
                
                # 解析常见的数据类型关键词
                # ⚠️ 使用有序列表而非字典遍历，确保高优先级关键词先匹配
                # 遥感影像关键词必须排在 'boundary' 前面，因为 Sentinel-2
                # 文件名格式为 Region_sentinel_2_YYYYMM_YYYYMM_boundary.tif，
                # 如果 'boundary' 先匹配就会被误标为"边界数据"
                type_keywords = [
                    # ── 高优先级：遥感影像（文件名常含 _boundary 后缀） ──
                    ('sentinel', '遥感卫星影像 (Sentinel)'),
                    ('landsat', '遥感卫星影像 (Landsat)'),
                    # ── 普通优先级 ──
                    ('hotel', '酒店数据 (hotel)'),
                    ('roads', '道路数据 (roads)'),
                    ('poi', 'POI兴趣点数据'),
                    ('museum', '博物馆数据 (museum)'),
                    ('building', '建筑数据 (building)'),
                    ('railway', '铁路数据 (railway)'),
                    ('restaurant', '餐厅数据 (restaurant)'),
                    ('hospital', '医院数据 (hospital)'),
                    ('school', '学校数据 (school)'),
                    ('park', '公园数据 (park)'),
                    # ── 低优先级：通用关键词（仅当上面都不匹配时才用） ──
                    ('boundary', '边界数据 (boundary)'),
                ]
                # 用于区域提取时跳过的关键词集合
                skip_keywords = {kw for kw, _ in type_keywords}
                skip_keywords.add('osm')
                skip_keywords.add('boundary')
                # 跳过纯数字（如 '2' in sentinel_2）
                
                # 构建增强描述前缀
                enhanced_prefix = ""
                filename_lower = filename_stem.lower()
                for key, value in type_keywords:
                    if key in filename_lower:
                        # 提取区域信息（假设格式：type_region 或 type_timestamp_region）
                        parts = filename_stem.split('_')
                        region = ""
                        for part in parts:
                            # 跳过数字（时间戳）、数据类型关键词、osm 前缀
                            if not part.isdigit() and part.lower() not in skip_keywords:
                                region = part
                                break
                        if region:
                            # 🔧 增强描述：明确说明这是完整的区域数据
                            enhanced_prefix = f"[{region}完整的{value}] "
                        else:
                            enhanced_prefix = f"[{value}] "
                        break
                
                # 将增强前缀添加到描述
                if enhanced_prefix:
                    description = enhanced_prefix + description
                    # 同时更新metadata中的description
                    metadata['description'] = description
                    # 更新catalog中的描述
                    if self.catalog_path:
                        self.metadata_generator.update_description_in_catalog(
                            absolute_path, description, self.catalog_path
                        )
                
                if description:
                    # 检查向量数据库是否已存在该dataset_id
                    existing_vector = self.vector_matcher.vector_db.get_vector(dataset_id)
                    if existing_vector:
                        print(f"   ⚠️ Vector already exists in vector database, skipping: {file_path_obj.name}")
                    else:
                        # 向量化description
                        vector = self.vector_matcher.embedding_client.embed_text(description)
                        if vector:
                            self.vector_matcher.vector_db.add_vector(dataset_id, description, vector)
                            print(f"   ✓ Added to vector database: {file_path_obj.name}")
                        else:
                            print(f"   ⚠️ Vectorization failed, cannot add to vector database: {file_path_obj.name}")
                else:
                    print(f"   ⚠️ No description field in metadata, cannot add to vector database: {file_path_obj.name}")
            else:
                print(f"   ⚠️ vector_matcher or vector_db not initialized, unable to add to vector database")
            
            # 4. 更新vector_matcher的本地数据集列表
            if self.vector_matcher:
                self.vector_matcher.local_datasets.append(metadata)
                # 更新ID映射
                if dataset_id:
                    self.vector_matcher.dataset_id_to_idx[dataset_id] = len(self.vector_matcher.local_datasets) - 1
            
            print(f"   ✓ Added to data catalog: {file_path_obj.name}")
            
        except Exception as e:
            import traceback
            print(f"   ⚠️ Failed to add file to catalog: {e}")
            print(f"   ⚠️ Detailed error: {traceback.format_exc()}")
    
    def _infer_region_from_context(self, entity_name: str, task_desc: str) -> str:
        """从上下文推断区域（使用 LLM）"""
        if not self.llm:
            return ""
        
        prompt = f"""Based on the following context, infer the geographic region (city/country).
Only output the region name, nothing else. If no region can be inferred, output empty string.

Entity name: "{entity_name}"
Task description: "{task_desc}"

Region:"""
        try:
            response = self.llm.chat(prompt)
            if response:
                region = response.strip().strip('"').strip("'")
                if region and region.lower() not in ['none', 'null', '', 'n/a', 'unknown']:
                    return region
        except Exception:
            pass
        return ""
    
    def _extract_params_from_description(self, description: str, task_type: str) -> Dict[str, Any]:
        """
        使用 LLM 从任务描述中提取参数（更鲁棒，支持多语言和口语化表达）
        """
        if not self.llm:
            return {}
        
        # 根据任务类型构建提取 prompt（参考父类的实现）
        if task_type == 'remote_sensing_data':
            prompt = f"""Extract parameters for remote sensing/satellite imagery download from the task description.
Support both Chinese and English.

Task description: "{description}"

Extract the following parameters and return as JSON (only JSON, no other content):
{{
    "region": "region name to download (e.g., 北京, Germany, London, 上海)",
    "satellite": "satellite type: sentinel-2 or landsat-8 or landsat-9 (default sentinel-2)",
    "time_range": "time range in format YYYY-MM or YYYY-MM-DD,YYYY-MM-DD",
    "cloud_cover_max": cloud cover percentage (0-100, 0 if user does not mention cloud cover),
    "processing": "processing type: NDVI, NDWI, RGB, or empty for raw bands"
}}

Notes:
- "卫星影像/satellite imagery/遥感数据" -> extract region and time
- "Sentinel" -> satellite="sentinel-2", "Landsat" -> satellite="landsat-8"
- If time is not specified, use current year-month
- "NDVI/植被指数" -> processing="NDVI", "NDWI/水体指数" -> processing="NDWI"
- Accept both Chinese and English region names"""
        elif task_type == 'worldkg':
            prompt = f"""Extract parameters for WorldKG/OSM semantic query from the task description.
Support both Chinese and English.

Task description: "{description}"

Extract the following parameters and return as JSON (only JSON, no other content):
{{
    "entity_type": "entity type in English (e.g., restaurant, hotel, hospital, school, park, bank)",
    "region": "geographic region (e.g., 北京, Berlin, London, Shanghai)"
}}

Notes:
- If description mentions "these hotels/restaurants/etc", infer entity_type from context
- If no explicit region but mentions a city name anywhere, extract it
- For descriptions like "query OSM semantic info of these hotels", entity_type should be "hotel"
- Accept both Chinese and English location names"""
        elif task_type == 'recommendation':
            prompt = f"""Extract parameters for recommendation query from the task description.
Support both Chinese and English.

Task description: "{description}"

Extract the following parameters and return as JSON (only JSON, no other content):
{{
    "facility_type": "facility type in English (e.g., hotel, restaurant, museum)",
    "criteria": ["criteria list, e.g., '四星级', '靠近地铁', '市中心'"],
    "location_context": "location context (e.g., '市中心', '远离高速')"
}}

Notes:
- "推荐" -> recommendation query
- "四星级/五星级" -> criteria includes stars
- "靠近地铁/远离高速" -> location_context
- Accept both Chinese and English"""
        else:
            # 对于其他任务类型，调用父类方法（如果存在）
            if hasattr(super(), '_extract_params_from_description'):
                return super()._extract_params_from_description(description, task_type)
            return {}
        
        try:
            response = self.llm.chat(prompt)
            if response:
                parsed = self.llm.parse_json_response(response)
                if parsed:
                    return parsed
        except Exception as e:
            print(f"      ⚠️ LLM parameter extraction failed: {e}")
        
        return {}

