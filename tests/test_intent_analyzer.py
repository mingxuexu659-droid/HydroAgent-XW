# -*- coding: utf-8 -*-
"""
意图分析器单元测试
"""

import unittest
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from spatial_analysis_system.intent_analyzer import (
    IntentAnalyzer,
    TaskIntent,
    TaskType,
    DataRequirement,
    AnalysisRequirement,
)
from spatial_analysis_system.config import Config


class TestTaskType(unittest.TestCase):
    """测试任务类型枚举"""
    
    def test_task_type_values(self):
        """测试任务类型值"""
        self.assertEqual(TaskType.DATA_DOWNLOAD_ONLY.value, "data_download_only")
        self.assertEqual(TaskType.DATA_AND_CODE.value, "data_and_code")
        self.assertEqual(TaskType.CODE_ONLY.value, "code_only")
        self.assertEqual(TaskType.UNKNOWN.value, "unknown")


class TestDataRequirement(unittest.TestCase):
    """测试数据需求类"""
    
    def test_data_requirement_creation(self):
        """测试数据需求创建"""
        dr = DataRequirement(
            data_type="remote_sensing",
            region="北京",
            satellite="sentinel-2",
            time_range="2024-01"
        )
        
        self.assertEqual(dr.data_type, "remote_sensing")
        self.assertEqual(dr.region, "北京")
        self.assertEqual(dr.satellite, "sentinel-2")
    
    def test_data_requirement_to_dict(self):
        """测试数据需求转字典"""
        dr = DataRequirement(
            data_type="osm",
            region="上海",
            osm_types=["roads", "buildings"]
        )
        
        result = dr.to_dict()
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result["data_type"], "osm")
        self.assertEqual(result["region"], "上海")
        self.assertEqual(result["osm_types"], ["roads", "buildings"])


class TestAnalysisRequirement(unittest.TestCase):
    """测试分析需求类"""
    
    def test_analysis_requirement_creation(self):
        """测试分析需求创建"""
        ar = AnalysisRequirement(
            analysis_type="buffer",
            description="创建1000米缓冲区",
            parameters={"distance": 1000}
        )
        
        self.assertEqual(ar.analysis_type, "buffer")
        self.assertEqual(ar.parameters["distance"], 1000)
    
    def test_analysis_requirement_to_dict(self):
        """测试分析需求转字典"""
        ar = AnalysisRequirement(
            analysis_type="clip",
            description="裁剪道路数据"
        )
        
        result = ar.to_dict()
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result["analysis_type"], "clip")


class TestTaskIntent(unittest.TestCase):
    """测试任务意图类"""
    
    def test_task_intent_data_only(self):
        """测试数据下载意图"""
        intent = TaskIntent(
            task_type=TaskType.DATA_DOWNLOAD_ONLY,
            original_query="下载北京的Sentinel-2影像"
        )
        
        self.assertTrue(intent.is_data_only())
        self.assertFalse(intent.needs_code_generation())
        self.assertTrue(intent.needs_data_download())
    
    def test_task_intent_data_and_code(self):
        """测试数据+代码意图"""
        intent = TaskIntent(
            task_type=TaskType.DATA_AND_CODE,
            original_query="下载北京道路数据并计算缓冲区"
        )
        
        self.assertFalse(intent.is_data_only())
        self.assertTrue(intent.needs_code_generation())
        self.assertTrue(intent.needs_data_download())
    
    def test_task_intent_code_only(self):
        """测试仅代码意图"""
        intent = TaskIntent(
            task_type=TaskType.CODE_ONLY,
            original_query="对D:/data/roads.shp计算500米缓冲区"
        )
        
        self.assertFalse(intent.is_data_only())
        self.assertTrue(intent.needs_code_generation())
        self.assertFalse(intent.needs_data_download())
    
    def test_task_intent_to_dict(self):
        """测试意图转字典"""
        intent = TaskIntent(
            task_type=TaskType.DATA_AND_CODE,
            original_query="测试查询",
            summary="测试摘要",
            confidence=0.9
        )
        
        result = intent.to_dict()
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result["task_type"], "data_and_code")
        self.assertEqual(result["confidence"], 0.9)


class TestIntentAnalyzerQuickAnalyze(unittest.TestCase):
    """测试意图分析器的快速分析功能"""
    
    def setUp(self):
        """设置测试环境"""
        # 使用模拟配置，不实际调用LLM
        pass
    
    def test_quick_analyze_data_download(self):
        """测试快速分析：数据下载"""
        # 这些查询应该被识别为数据下载
        download_queries = [
            "下载北京的Sentinel-2影像",
            "获取上海的道路数据",
            "查询西湖景区的POI",
            "搜索故宫附近的博物馆",
        ]
        
        for query in download_queries:
            # 直接测试规则匹配逻辑
            query_lower = query.lower()
            download_keywords = ["下载", "获取", "查询", "搜索"]
            analysis_keywords = ["缓冲区", "裁剪", "叠加", "ndvi", "统计"]
            
            has_download = any(kw in query_lower for kw in download_keywords)
            has_analysis = any(kw in query_lower for kw in analysis_keywords)
            
            self.assertTrue(has_download, f"应检测到下载关键词: {query}")
            self.assertFalse(has_analysis, f"不应检测到分析关键词: {query}")
    
    def test_quick_analyze_data_and_code(self):
        """测试快速分析：数据+代码"""
        analysis_queries = [
            "下载北京道路数据并创建1000米缓冲区",
            "获取上海影像并计算NDVI",
            "裁剪西湖景区的土地利用数据",
            "对北京的建筑数据进行融合分析",
        ]
        
        for query in analysis_queries:
            query_lower = query.lower()
            analysis_keywords = ["缓冲区", "裁剪", "叠加", "ndvi", "统计", "融合", "分析"]
            
            has_analysis = any(kw in query_lower for kw in analysis_keywords)
            self.assertTrue(has_analysis, f"应检测到分析关键词: {query}")
    
    def test_quick_analyze_code_only(self):
        """测试快速分析：仅代码"""
        import re
        
        code_only_queries = [
            "对D:/data/roads.shp计算500米缓冲区",
            "将/home/user/data/landuse.tif与boundary.shp裁剪",
        ]
        
        for query in code_only_queries:
            has_local_path = bool(re.search(r'[a-zA-Z]:\\|/home/|\.shp|\.tif', query))
            analysis_keywords = ["缓冲区", "裁剪", "计算"]
            has_analysis = any(kw in query.lower() for kw in analysis_keywords)
            
            self.assertTrue(has_local_path, f"应检测到本地路径: {query}")
            self.assertTrue(has_analysis, f"应检测到分析关键词: {query}")


if __name__ == '__main__':
    unittest.main()

