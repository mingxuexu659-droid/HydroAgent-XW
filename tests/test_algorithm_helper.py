# -*- coding: utf-8 -*-
"""
算法帮助模块单元测试
"""

import unittest
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from spatial_analysis_system.algorithm_helper import (
    extract_algorithm_ids_from_code,
    fuzzy_match_algorithm,
)


class TestExtractAlgorithmIds(unittest.TestCase):
    """测试从代码中提取算法ID"""
    
    def test_extract_single_algorithm(self):
        """测试提取单个算法"""
        code = '''
import processing
result = processing.run("native:buffer", {
    'INPUT': 'input.shp',
    'DISTANCE': 100,
    'OUTPUT': 'output.shp'
})
'''
        
        ids = extract_algorithm_ids_from_code(code)
        
        self.assertEqual(len(ids), 1)
        self.assertIn("native:buffer", ids)
    
    def test_extract_multiple_algorithms(self):
        """测试提取多个算法"""
        code = '''
import processing
result1 = processing.run("native:buffer", {...})
result2 = processing.run("native:clip", {...})
result3 = processing.run("qgis:dissolve", {...})
'''
        
        ids = extract_algorithm_ids_from_code(code)
        
        self.assertEqual(len(ids), 3)
        self.assertIn("native:buffer", ids)
        self.assertIn("native:clip", ids)
        self.assertIn("qgis:dissolve", ids)
    
    def test_extract_with_single_quotes(self):
        """测试单引号格式"""
        code = "processing.run('native:buffer', {...})"
        
        ids = extract_algorithm_ids_from_code(code)
        
        self.assertEqual(len(ids), 1)
        self.assertIn("native:buffer", ids)
    
    def test_extract_runAndLoadResults(self):
        """测试runAndLoadResults格式"""
        code = 'processing.runAndLoadResults("native:buffer", {...})'
        
        ids = extract_algorithm_ids_from_code(code)
        
        self.assertEqual(len(ids), 1)
        self.assertIn("native:buffer", ids)
    
    def test_extract_multiline_format(self):
        """测试多行格式"""
        code = '''
processing.run(
    "native:buffer",
    {
        'INPUT': 'input.shp',
        'DISTANCE': 100
    }
)
'''
        
        ids = extract_algorithm_ids_from_code(code)
        
        self.assertEqual(len(ids), 1)
        self.assertIn("native:buffer", ids)
    
    def test_extract_various_providers(self):
        """测试不同提供者的算法"""
        code = '''
processing.run("native:buffer", {...})
processing.run("qgis:dissolve", {...})
processing.run("grass:v.buffer", {...})
processing.run("sagang:kappacoefficient", {...})
processing.run("gdal:rastercalculator", {...})
'''
        
        ids = extract_algorithm_ids_from_code(code)
        
        self.assertIn("native:buffer", ids)
        self.assertIn("qgis:dissolve", ids)
        self.assertIn("grass:v.buffer", ids)
        self.assertIn("sagang:kappacoefficient", ids)
        self.assertIn("gdal:rastercalculator", ids)
    
    def test_extract_no_duplicates(self):
        """测试去重"""
        code = '''
processing.run("native:buffer", {...})
processing.run("native:buffer", {...})
processing.run("native:buffer", {...})
'''
        
        ids = extract_algorithm_ids_from_code(code)
        
        self.assertEqual(len(ids), 1)
    
    def test_extract_empty_code(self):
        """测试空代码"""
        ids = extract_algorithm_ids_from_code("")
        
        self.assertEqual(len(ids), 0)
    
    def test_extract_no_algorithms(self):
        """测试没有算法的代码"""
        code = '''
import os
print("Hello World")
'''
        
        ids = extract_algorithm_ids_from_code(code)
        
        self.assertEqual(len(ids), 0)


class TestFuzzyMatchAlgorithm(unittest.TestCase):
    """测试算法模糊匹配"""
    
    def test_fuzzy_match_with_cache(self):
        """测试使用缓存进行模糊匹配"""
        cache = {
            "native:buffer": {
                "display_name": "Buffer",
                "group": "Vector geometry"
            },
            "native:bufferbyexpressions": {
                "display_name": "Variable distance buffer",
                "group": "Vector geometry"
            },
            "qgis:dissolve": {
                "display_name": "Dissolve",
                "group": "Vector geometry"
            },
        }
        
        matches = fuzzy_match_algorithm("native:buffer", cache, max_results=3)
        
        # 应该找到精确匹配
        self.assertTrue(len(matches) > 0)
        self.assertEqual(matches[0]["algorithm_id"], "native:buffer")
    
    def test_fuzzy_match_similar_name(self):
        """测试相似名称匹配"""
        cache = {
            "native:buffer": {
                "display_name": "Buffer",
                "group": "Vector geometry"
            },
            "native:variablebuffer": {
                "display_name": "Variable distance buffer",
                "group": "Vector geometry"
            },
        }
        
        # 搜索一个不存在但相似的算法
        matches = fuzzy_match_algorithm("native:bufferdistance", cache, max_results=3)
        
        # 应该找到相似的算法
        self.assertTrue(len(matches) > 0)
        algorithm_ids = [m["algorithm_id"] for m in matches]
        self.assertTrue("native:buffer" in algorithm_ids or "native:variablebuffer" in algorithm_ids)
    
    def test_fuzzy_match_empty_cache(self):
        """测试空缓存"""
        matches = fuzzy_match_algorithm("native:buffer", {}, max_results=3)
        
        self.assertEqual(len(matches), 0)
    
    def test_fuzzy_match_empty_id(self):
        """测试空算法ID"""
        cache = {
            "native:buffer": {"display_name": "Buffer"}
        }
        
        matches = fuzzy_match_algorithm("", cache, max_results=3)
        
        self.assertEqual(len(matches), 0)
    
    def test_fuzzy_match_invalid_format(self):
        """测试无效格式的算法ID"""
        cache = {
            "native:buffer": {"display_name": "Buffer"}
        }
        
        # 没有冒号的ID
        matches = fuzzy_match_algorithm("buffer", cache, max_results=3)
        
        self.assertEqual(len(matches), 0)


if __name__ == '__main__':
    unittest.main()

