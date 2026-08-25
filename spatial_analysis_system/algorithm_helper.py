# -*- coding: utf-8 -*-
"""
QGIS算法帮助模块

提供QGIS Processing算法的文档检索功能，支持从CSV文件加载算法信息。
"""

import csv
import os
import re
from typing import Any, Dict, List, Optional

from .config import Config, get_config


# 全局缓存：算法Help Text字典
_algorithm_help_cache: Dict[str, Dict[str, str]] = {}


def load_algorithm_help_cache(csv_path: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    """
    从CSV文件加载算法Help Text到内存缓存
    
    Args:
        csv_path: CSV文件路径，如果为None则从配置获取
    
    Returns:
        字典，格式：{algorithm_id: {'display_name': ..., 'help_text': ..., 'group': ..., 'provider': ...}}
    """
    global _algorithm_help_cache
    
    # 如果已经加载过，直接返回
    if _algorithm_help_cache:
        return _algorithm_help_cache
    
    if csv_path is None:
        config = get_config()
        csv_path = config.qgis.algorithm_csv_path
    
    if not os.path.exists(csv_path):
        print(f"⚠️ Algorithm CSV file not found: {csv_path}")
        return {}
    
    print(f"Loading algorithm details CSV: {csv_path}")
    cache = {}
    
    try:
        # 使用utf-8-sig编码来处理BOM
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                # 处理可能的BOM问题，尝试多个列名变体
                alg_id = (row.get('Algorithm ID', '') or 
                         row.get('\ufeffAlgorithm ID', '') or 
                         row.get('algorithm_id', '')).strip()
                
                if alg_id:
                    cache[alg_id] = {
                        'display_name': (row.get('Display Name', '') or 
                                        row.get('display_name', '')).strip(),
                        'help_text': (row.get('Help Text', '') or 
                                     row.get('help_text', '')).strip(),
                        'group': (row.get('Group', '') or 
                                 row.get('group', '')).strip(),
                        'provider': (row.get('Provider', '') or 
                                    row.get('provider', '')).strip(),
                        'provider_name': (row.get('Provider Name', '') or 
                                         row.get('provider_name', '')).strip()
                    }
                    count += 1
        print(f"   ✓ Loaded {count} algorithm info")
    except Exception as e:
        print(f"   ❌ Failed to load CSV: {e}")
        return {}
    
    _algorithm_help_cache = cache
    return cache


def get_algorithm_help_text(algorithm_id: str, cache: Optional[Dict[str, Dict[str, str]]] = None) -> Optional[Dict[str, str]]:
    """
    从缓存中检索算法的Help Text
    
    Args:
        algorithm_id: 算法ID，如 'native:buffer'
        cache: 算法缓存字典，如果为None则使用全局缓存
    
    Returns:
        算法信息字典，如果未找到则返回None
    """
    if cache is None:
        cache = load_algorithm_help_cache()
    return cache.get(algorithm_id)


def extract_algorithm_ids_from_code(code: str) -> List[str]:
    """
    从代码中提取QGIS processing算法ID（基于规则的方法）
    
    支持的格式：
    - processing.run("native:algorithm", ...)
    - processing.run('native:algorithm', ...)
    - processing.runAndLoadResults("native:algorithm", ...)
    - 多行格式
    
    Args:
        code: Python代码字符串
    
    Returns:
        算法ID列表，如 ['native:buffer', 'qgis:dissolve']
    """
    algorithm_ids = []
    
    # 模式1: processing.run("provider:algorithm", ...) 或 processing.run('provider:algorithm', ...)
    pattern1 = r'processing\.run\s*\(\s*["\']([a-zA-Z0-9_-]+:[a-zA-Z0-9_.-]+)["\']'
    matches1 = re.findall(pattern1, code, re.MULTILINE | re.DOTALL)
    algorithm_ids.extend(matches1)
    
    # 模式2: processing.runAndLoadResults("provider:algorithm", ...)
    pattern2 = r'processing\.runAndLoadResults\s*\(\s*["\']([a-zA-Z0-9_-]+:[a-zA-Z0-9_.-]+)["\']'
    matches2 = re.findall(pattern2, code, re.MULTILINE | re.DOTALL)
    algorithm_ids.extend(matches2)
    
    # 模式3: 多行格式
    pattern3 = r'processing\.run\s*\(\s*\n\s*["\']([a-zA-Z0-9_-]+:[a-zA-Z0-9_.-]+)["\']'
    matches3 = re.findall(pattern3, code, re.MULTILINE)
    algorithm_ids.extend(matches3)
    
    # 去重并保持顺序
    seen = set()
    unique_ids = []
    for alg_id in algorithm_ids:
        if alg_id not in seen:
            seen.add(alg_id)
            unique_ids.append(alg_id)
    
    return unique_ids


def fuzzy_match_algorithm(
    algorithm_id: str, 
    cache: Optional[Dict[str, Dict[str, str]]] = None, 
    max_results: int = 5
) -> List[Dict[str, str]]:
    """
    对算法ID进行模糊匹配，找到相似的算法
    
    Args:
        algorithm_id: 要匹配的算法ID（如 'sagang:kappacoefficient'）
        cache: 算法缓存字典
        max_results: 最多返回的结果数量
    
    Returns:
        相似算法列表，每个元素包含算法ID、显示名称和相似度信息
    """
    if cache is None:
        cache = load_algorithm_help_cache()
    
    if not algorithm_id or not cache:
        return []
    
    # 提取关键词：从算法ID中提取有意义的部分
    parts = algorithm_id.lower().split(':')
    if len(parts) < 2:
        return []
    
    provider = parts[0]
    alg_name = parts[1]
    
    # 提取关键词：将算法名称按常见分隔符拆分
    keywords = []
    # 按驼峰命名拆分
    words = re.findall(r'[a-z]+|[A-Z][a-z]*', alg_name)
    keywords.extend([w.lower() for w in words])
    # 按下划线、连字符、点号拆分
    words = re.split(r'[_.-]', alg_name)
    keywords.extend([w.lower() for w in words if w])
    
    # 去重
    keywords = list(set(keywords))
    
    # 计算每个算法的相似度分数
    matches = []
    for alg_id, alg_info in cache.items():
        score = 0
        alg_id_lower = alg_id.lower()
        display_name_lower = alg_info.get('display_name', '').lower()
        
        # 1. 完全匹配算法ID（忽略大小写）
        if alg_id_lower == algorithm_id.lower():
            score += 1000
        # 2. 算法ID包含关键词
        for keyword in keywords:
            if keyword in alg_id_lower:
                score += 10
            if keyword in display_name_lower:
                score += 5
        # 3. 算法名称相似
        if alg_name in alg_id_lower or alg_id_lower.split(':')[-1] in alg_name:
            score += 20
        
        # 4. 如果关键词长度>=3，检查是否在算法ID或显示名称中
        for keyword in keywords:
            if len(keyword) >= 3:
                if keyword in alg_id_lower:
                    score += 15
                if keyword in display_name_lower:
                    score += 10
        
        if score > 0:
            matches.append({
                'algorithm_id': alg_id,
                'display_name': alg_info.get('display_name', ''),
                'group': alg_info.get('group', ''),
                'provider': alg_info.get('provider', ''),
                'score': score
            })
    
    # 按分数排序，返回前max_results个
    matches.sort(key=lambda x: x['score'], reverse=True)
    return matches[:max_results]


def search_algorithms_by_keywords(keywords: List[str], max_results: int = 10) -> List[Dict[str, str]]:
    """
    根据关键词搜索相关算法
    
    Args:
        keywords: 关键词列表，如 ['buffer', 'distance']
        max_results: 最多返回的结果数量
    
    Returns:
        匹配的算法列表
    """
    cache = load_algorithm_help_cache()
    if not cache or not keywords:
        return []
    
    # 转换为小写
    keywords_lower = [k.lower() for k in keywords]
    
    matches = []
    for alg_id, alg_info in cache.items():
        score = 0
        alg_id_lower = alg_id.lower()
        display_name_lower = alg_info.get('display_name', '').lower()
        help_text_lower = alg_info.get('help_text', '').lower()[:500]  # 只检查前500字符
        
        for keyword in keywords_lower:
            if keyword in alg_id_lower:
                score += 20
            if keyword in display_name_lower:
                score += 15
            if keyword in help_text_lower:
                score += 5
        
        if score > 0:
            matches.append({
                'algorithm_id': alg_id,
                'display_name': alg_info.get('display_name', ''),
                'group': alg_info.get('group', ''),
                'provider': alg_info.get('provider', ''),
                'help_text': alg_info.get('help_text', ''),
                'score': score
            })
    
    matches.sort(key=lambda x: x['score'], reverse=True)
    return matches[:max_results]


class AlgorithmHelper:
    """
    QGIS算法帮助类
    
    提供算法文档检索、模糊匹配等功能。
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        初始化算法帮助器
        
        Args:
            config: 配置对象
        """
        self.config = config or get_config()
        self.cache = load_algorithm_help_cache(self.config.qgis.algorithm_csv_path)
    
    def get_help(self, algorithm_id: str) -> Optional[Dict[str, str]]:
        """获取算法帮助文档"""
        return get_algorithm_help_text(algorithm_id, self.cache)
    
    def extract_from_code(self, code: str) -> List[str]:
        """从代码中提取算法ID"""
        return extract_algorithm_ids_from_code(code)
    
    def fuzzy_match(self, algorithm_id: str, max_results: int = 5) -> List[Dict[str, str]]:
        """模糊匹配算法"""
        return fuzzy_match_algorithm(algorithm_id, self.cache, max_results)
    
    def search(self, keywords: List[str], max_results: int = 10) -> List[Dict[str, str]]:
        """搜索算法"""
        return search_algorithms_by_keywords(keywords, max_results)
    
    def get_algorithm_docs_for_code(self, code: str) -> tuple:
        """
        获取代码中使用的所有算法的文档
        
        Args:
            code: Python代码
        
        Returns:
            (found_algorithms, not_found_algorithms): 找到的算法列表和未找到的算法列表
        """
        algorithm_ids = self.extract_from_code(code)
        
        found_algorithms = []
        not_found_algorithms = []
        
        for alg_id in algorithm_ids:
            alg_info = self.get_help(alg_id)
            if alg_info:
                found_algorithms.append({
                    'algorithm_id': alg_id,
                    'display_name': alg_info.get('display_name', ''),
                    'group': alg_info.get('group', ''),
                    'provider': alg_info.get('provider', ''),
                    'help_text': alg_info.get('help_text', '')
                })
            else:
                # 尝试模糊匹配
                similar = self.fuzzy_match(alg_id, max_results=3)
                similar_with_help = []
                for s in similar:
                    s_info = self.get_help(s['algorithm_id'])
                    if s_info:
                        similar_with_help.append({
                            'algorithm_id': s['algorithm_id'],
                            'display_name': s_info.get('display_name', ''),
                            'help_text': s_info.get('help_text', '')
                        })
                
                not_found_algorithms.append({
                    'original_algorithm_id': alg_id,
                    'similar_algorithms': similar_with_help
                })
        
        return found_algorithms, not_found_algorithms

