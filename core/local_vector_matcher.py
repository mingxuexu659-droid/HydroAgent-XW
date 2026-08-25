#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local Vector Matcher Module

Provides LocalDataVectorMatcher class for:
1. Loading local data catalog
2. Building and maintaining vector index
3. Searching local data based on vector similarity
4. Using LLM to judge if data satisfies requirements
"""

import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional

from .vector_embedding import VectorEmbeddingClient, cosine_similarity
from .vector_database import VectorDatabase

# 尝试从同目录导入LLMClient
try:
    from .data_search_llm import LLMClient
except ImportError:
        # 使用内置的简单LLM客户端
        from openai import OpenAI
        import os
        
        class LLMClient:
            def __init__(self, api_key: str = None):
                self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
                )
            
            def chat(self, prompt: str, system_prompt: str = None):
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                
                try:
                    response = self.client.chat.completions.create(
                        model="qwen-max",
                        messages=messages,
                        temperature=0.3
                    )
                    return response.choices[0].message.content
                except Exception as e:
                    print(f"LLM call failed: {e}")
                    return None
            
            def parse_json_response(self, response: str):
                """解析LLM响应中的JSON"""
                import json
                import re
                
                if not response:
                    return None
                
                try:
                    return json.loads(response)
                except json.JSONDecodeError:
                    pass
                
                # 尝试从markdown代码块中提取JSON
                for pattern in [r'```json\s*([\s\S]*?)\s*```', r'```\s*([\s\S]*?)\s*```', r'\{[\s\S]*\}']:
                    match = re.search(pattern, response)
                    if match:
                        try:
                            json_str = match.group(1) if '```' in pattern else match.group(0)
                            return json.loads(json_str)
                        except json.JSONDecodeError:
                            continue
                return None

# 测试配置：是否只使用部分数据
# 设置为 False 以使用所有数据（包括新下载的数据）
USE_TEST_MODE = False  # 改为False以启用所有数据
TEST_DATA_COUNT = 10   # 仅当 USE_TEST_MODE=True 时生效


class LocalDataVectorMatcher:
    """本地数据向量匹配器（使用向量数据库）"""
    
    def __init__(self, catalog_path: str, vector_db_path: str = None, api_key: str = None,
                 embedding_api_url: str = None, embedding_model_name: str = None, embedding_timeout: float = None):
        """
        初始化向量匹配器
        
        Args:
            catalog_path: data_catalog.json 文件路径
            vector_db_path: 向量数据库文件路径（默认：catalog_path同目录下的vector_db.json）
            api_key: 百炼API密钥
            embedding_api_url: 向量检索API地址（可选）
            embedding_model_name: 向量检索模型名称（可选）
            embedding_timeout: 向量检索请求超时时间（秒，可选）
        """
        self.catalog_path = Path(catalog_path)
        self.catalog_data = self._load_catalog()
        self.embedding_client = VectorEmbeddingClient(
            api_key=api_key,
            api_url=embedding_api_url,
            model_name=embedding_model_name,
            timeout=embedding_timeout
        )
        self.llm_client = LLMClient(api_key)
        
        # 初始化向量数据库
        if vector_db_path is None:
            vector_db_path = self.catalog_path.parent / "vector_db.json"
        self.vector_db = VectorDatabase(str(vector_db_path))
        
        # 加载本地数据集列表
        self.local_datasets = self._load_local_datasets()
        
        # 构建数据集ID到索引的映射
        self.dataset_id_to_idx = {}
        for idx, dataset in enumerate(self.local_datasets):
            file_path = dataset.get('absolute_path', '')
            if file_path:
                dataset_id = self._generate_dataset_id(file_path)
                self.dataset_id_to_idx[dataset_id] = idx
    
    def _load_catalog(self) -> Dict[str, Any]:
        """加载数据目录"""
        try:
            with open(self.catalog_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Failed to load data catalog: {e}")
            return {}
    
    def _load_local_datasets(self) -> List[Dict[str, Any]]:
        """加载本地数据集列表"""
        datasets = []
        
        # 展平数据目录结构
        data_sections = [
            'vector_data', 'shapefile_data', 'geopackage_data',
            'raster_data', 'mesh_data', 'gps_data', 'table_data'
        ]
        
        for section in data_sections:
            if section not in self.catalog_data:
                continue
            
            section_data = self.catalog_data[section]
            
            if isinstance(section_data, dict):
                for category, items in section_data.items():
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                item['_source_section'] = section
                                item['_source_category'] = category
                                datasets.append(item)
            elif isinstance(section_data, list):
                for item in section_data:
                    if isinstance(item, dict):
                        item['_source_section'] = section
                        datasets.append(item)
        
        # 测试模式：只使用前N条数据
        if USE_TEST_MODE:
            datasets = datasets[:TEST_DATA_COUNT]
            print(f"Test mode: only using first {TEST_DATA_COUNT} items")
        
        return datasets
    
    def _generate_dataset_id(self, file_path: str) -> str:
        """生成数据集ID（基于文件路径的哈希值）"""
        return hashlib.md5(file_path.encode('utf-8')).hexdigest()
    
    def _build_vector_index_from_catalog(self):
        """
        从catalog构建向量索引：检查向量数据库，缺失的进行向量化并添加
        """
        # 检查哪些数据集需要向量化
        need_vectorize = []
        for idx, dataset in enumerate(self.local_datasets):
            file_path = dataset.get('absolute_path', '')
            if not file_path:
                continue
            
            dataset_id = self._generate_dataset_id(file_path)
            
            # 检查向量数据库是否已有该向量
            existing_vector = self.vector_db.get_vector(dataset_id)
            if not existing_vector:
                # 需要向量化
                description = dataset.get('description', '')
                if not description:
                    # 如果没有description，使用name和其他元数据组合
                    name = dataset.get('name', '')
                    category = dataset.get('category', '')
                    geometry_type = dataset.get('geometry_type', '')
                    description = f"{name} {category} {geometry_type}".strip()
                
                need_vectorize.append((dataset_id, description, idx))
        
        # 批量向量化缺失的数据集
        if need_vectorize:
            print(f"\nBuilding vector index ({len(self.local_datasets)} datasets total)...")
            print(f"   Found {len(need_vectorize)} datasets need vectorization...")
            descriptions = [item[1] for item in need_vectorize]
            vectors = self.embedding_client.embed_batch(descriptions)
            
            # 添加到向量数据库
            success_count = 0
            for (dataset_id, description, idx), vector in zip(need_vectorize, vectors):
                if vector:
                    self.vector_db.add_vector(dataset_id, description, vector)
                    success_count += 1
            
            print(f"   ✓ Successfully vectorized and added {success_count}/{len(need_vectorize)} datasets")
        # 如果所有数据集都已存在，不打印任何消息（避免浪费token）
    
    def search_local_data(self, task_description: str, top_n: int = 5) -> List[Dict[str, Any]]:
        """
        使用向量数据库搜索本地数据（延迟构建向量索引）
        
        Args:
            task_description: 任务描述（节点的下载需求）
            top_n: 返回Top N个最相似的数据集
            
        Returns:
            匹配的数据集列表，每个包含：dataset, similarity_score, metadata
        """
        # 延迟构建向量索引：只在第一次调用时构建
        if not hasattr(self, '_vector_index_built') or not self._vector_index_built:
            print(f"\n🔨 [Lazy Build] First use, building index from vector database...")
            self._build_vector_index_from_catalog()
            self._vector_index_built = True
        
        # 从向量数据库获取所有向量
        if not self.vector_db:
            print("   ⚠️ Vector database unavailable, cannot perform matching")
            return []
        
        all_vectors = self.vector_db.get_all_vectors()
        if not all_vectors:
            print("   ⚠️ Vector database is empty, cannot perform matching")
            return []
        
        # 将任务描述向量化
        print(f"\nVectorizing task requirement: {task_description[:50]}...")
        query_vector = self.embedding_client.embed_text(task_description)
        
        if not query_vector:
            print("   ⚠️ Task requirement vectorization failed")
            return []
        
        # 计算相似度（只计算catalog中存在的数据集）
        similarities = []
        for vec_item in all_vectors:
            dataset_id = vec_item["dataset_id"]
            
            # 检查该数据集是否在catalog中
            if dataset_id not in self.dataset_id_to_idx:
                continue
            
            dataset_idx = self.dataset_id_to_idx[dataset_id]
            dataset_vector = vec_item["vector"]
            
            similarity = cosine_similarity(query_vector, dataset_vector)
            similarities.append({
                'dataset_idx': dataset_idx,
                'similarity': similarity,
                'dataset': self.local_datasets[dataset_idx]
            })
        
        # 按相似度排序，取Top N
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        top_matches = similarities[:top_n]
        
        print(f"   ✓ Found {len(top_matches)} candidate datasets:")
        for i, match in enumerate(top_matches, 1):
            dataset = match['dataset']
            print(f"      [{i}] {dataset.get('name', 'Unknown')} (similarity: {match['similarity']:.3f})")
        
        return top_matches
    
    def check_if_satisfies_requirement(self, task_description: str, 
                                       candidate_datasets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        使用大模型判断候选数据集是否能满足任务需求
        
        Args:
            task_description: 任务描述
            candidate_datasets: 候选数据集列表（来自向量匹配）
            
        Returns:
            如果满足需求，返回选中的数据集信息；否则返回None
        """
        if not candidate_datasets:
            return None
        
        # 构建prompt
        datasets_info = []
        for i, match in enumerate(candidate_datasets, 1):
            dataset = match['dataset']
            info = {
                "index": i,
                "name": dataset.get('name', 'Unknown'),
                "description": dataset.get('description', ''),
                "absolute_path": dataset.get('absolute_path', ''),
                "geometry_type": dataset.get('geometry_type', ''),
                "category": dataset.get('category', ''),
                "similarity_score": match['similarity']
            }
            datasets_info.append(info)
        
        prompt = f"""You are a geographic data expert. Please strictly judge whether the following local datasets can **fully satisfy** the user's task requirements.

## Task Requirement
{task_description}

## Candidate Datasets (sorted by similarity)
{json.dumps(datasets_info, ensure_ascii=False, indent=2)}

## Judgment Rules (must strictly follow):

### Rule 1: Geographic coverage must be complete (most important)

Analyze the target region in user's requirement, then judge the dataset's coverage:

**Example Analysis:**
- User requirement "Shanghai road data" → Target region is "Shanghai city" (entire city)
- Dataset name "Shanghai Lujiazui roads" → Only covers Lujiazui (a small area of Shanghai)
- Judgment: Does not satisfy (Lujiazui ⊂ Shanghai, partial cannot represent whole)

**Judgment Principles:**
- If dataset name contains target region + other place names, it's only a sub-region
- Sub-region data cannot satisfy the whole region's requirement
- Only data covering the entire target region can be considered satisfying

### Rule 2: Data type must match
- roads ≠ buildings ≠ boundaries
- Different data types cannot substitute each other
- **IMPORTANT naming convention**: For Sentinel-2/Landsat files, "Boundary" in the name means the imagery was **clipped to the administrative boundary** of the region — it is NOT a boundary/border vector dataset. Files like "Beijing Sentinel 2 202511 202602 Boundary" are full **raster remote sensing imagery** covering the entire Beijing region. If the category says "remote_sensing_imagery" or the description mentions "遥感卫星影像" or "Sentinel", treat it as satellite imagery, not boundary data.

### Rule 3: Better to lack than to have incorrect data
- If no perfectly matching data, return can_satisfy: false
- Let system download complete data online rather than using incomplete local data

Return in JSON format:
{{
    "can_satisfy": true or false,
    "selected_dataset_index": selected dataset index (1-N) or null,
    "reason": "judgment reason",
    "coverage_analysis": "geographic coverage analysis: user needs [X region], dataset covers [Y region], whether fully covered"
}}
"""
        
        try:
            response = self.llm_client.chat(prompt)
            if response:
                result = self.llm_client.parse_json_response(response)
                if result and result.get('can_satisfy', False):
                    selected_idx = result.get('selected_dataset_index')
                    if selected_idx and 1 <= selected_idx <= len(candidate_datasets):
                        selected_match = candidate_datasets[selected_idx - 1]
                        print(f"   ✓ LLM judgment: can use local data")
                        print(f"      Selected: {selected_match['dataset'].get('name', 'Unknown')}")
                        print(f"      Reason: {result.get('reason', '')}")
                        return {
                            'dataset': selected_match['dataset'],
                            'reason': result.get('reason', ''),
                            'limitations': result.get('limitations', [])
                        }
                    else:
                        print(f"   ⚠️ LLM judgment: cannot use local data")
                        print(f"      Reason: {result.get('reason', '')}")
                else:
                    print(f"   ⚠️ LLM judgment: cannot use local data")
                    if result:
                        print(f"      Reason: {result.get('reason', '')}")
        except Exception as e:
            print(f"   ⚠️ LLM judgment exception: {e}")
        
        return None

