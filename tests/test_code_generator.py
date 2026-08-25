# -*- coding: utf-8 -*-
"""
代码生成器单元测试
"""

import unittest
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from spatial_analysis_system.code_generator import CodeGenerator
from spatial_analysis_system.intent_analyzer import (
    TaskIntent,
    TaskType,
    DataRequirement,
    AnalysisRequirement,
)
from spatial_analysis_system.config import Config


class TestCodeGeneratorTemplates(unittest.TestCase):
    """测试代码生成器模板功能"""
    
    def test_buffer_template(self):
        """测试缓冲区分析模板"""
        config = Config()
        generator = CodeGenerator.__new__(CodeGenerator)
        generator.config = config
        
        code = generator._template_buffer(
            input_files=["D:/data/roads.shp"],
            output_dir="D:/output",
            params={"distance": 1000}
        )
        
        # 验证代码包含关键元素
        self.assertIn("processing.run", code)
        self.assertIn("native:buffer", code)
        self.assertIn("DISTANCE", code)
        self.assertIn("1000", code)
        self.assertIn("D:/data/roads.shp", code)
        self.assertIn("D:/output", code)
    
    def test_clip_template(self):
        """测试裁剪分析模板"""
        config = Config()
        generator = CodeGenerator.__new__(CodeGenerator)
        generator.config = config
        
        code = generator._template_clip(
            input_files=["D:/data/landuse.shp", "D:/data/boundary.shp"],
            output_dir="D:/output",
            params={}
        )
        
        self.assertIn("processing.run", code)
        self.assertIn("native:clip", code)
        self.assertIn("INPUT", code)
        self.assertIn("OVERLAY", code)
    
    def test_intersection_template(self):
        """测试相交分析模板"""
        config = Config()
        generator = CodeGenerator.__new__(CodeGenerator)
        generator.config = config
        
        code = generator._template_intersection(
            input_files=["D:/data/roads.shp", "D:/data/buildings.shp"],
            output_dir="D:/output",
            params={}
        )
        
        self.assertIn("processing.run", code)
        self.assertIn("native:intersection", code)
    
    def test_dissolve_template(self):
        """测试融合分析模板"""
        config = Config()
        generator = CodeGenerator.__new__(CodeGenerator)
        generator.config = config
        
        code = generator._template_dissolve(
            input_files=["D:/data/parcels.shp"],
            output_dir="D:/output",
            params={"field": "category"}
        )
        
        self.assertIn("processing.run", code)
        self.assertIn("native:dissolve", code)
        self.assertIn("FIELD", code)
    
    def test_ndvi_template(self):
        """测试NDVI计算模板"""
        config = Config()
        generator = CodeGenerator.__new__(CodeGenerator)
        generator.config = config
        
        code = generator._template_ndvi(
            input_files=["D:/data/sentinel.tif"],
            output_dir="D:/output",
            params={"red_band": 4, "nir_band": 8}
        )
        
        self.assertIn("processing.run", code)
        self.assertIn("rastercalculator", code)
        self.assertIn("NDVI", code)


class TestCodeGeneratorFormatting(unittest.TestCase):
    """测试代码生成器格式化功能"""
    
    def test_format_data_metadata(self):
        """测试数据元数据格式化"""
        config = Config()
        generator = CodeGenerator.__new__(CodeGenerator)
        generator.config = config
        
        data_files = [
            {
                "name": "roads.shp",
                "path": "D:/data/roads.shp",
                "format": "Shapefile",
                "geometry_type": "LineString",
                "crs": "EPSG:4326",
                "feature_count": 1000,
            }
        ]
        
        result = generator._format_data_metadata(data_files)
        
        self.assertIn("roads.shp", result)
        self.assertIn("LineString", result)
        self.assertIn("EPSG:4326", result)
        self.assertIn("1000", result)
    
    def test_format_data_metadata_empty(self):
        """测试空数据元数据格式化"""
        config = Config()
        generator = CodeGenerator.__new__(CodeGenerator)
        generator.config = config
        
        result = generator._format_data_metadata([])
        
        self.assertIn("No input data info", result)
    
    def test_format_analysis_tasks(self):
        """测试分析任务格式化"""
        config = Config()
        generator = CodeGenerator.__new__(CodeGenerator)
        generator.config = config
        
        intent = TaskIntent(
            task_type=TaskType.DATA_AND_CODE,
            original_query="测试查询",
            analysis_requirements=[
                AnalysisRequirement(
                    analysis_type="buffer",
                    description="创建缓冲区",
                    parameters={"distance": 1000}
                )
            ]
        )
        
        result = generator._format_analysis_tasks(intent)
        
        self.assertIn("buffer", result)
        self.assertIn("创建缓冲区", result)
        self.assertIn("1000", result)


class TestCodeGeneratorGenerate(unittest.TestCase):
    """测试代码生成器主要生成功能"""
    
    def test_generate_from_template_buffer(self):
        """测试从模板生成缓冲区代码"""
        config = Config()
        generator = CodeGenerator.__new__(CodeGenerator)
        generator.config = config
        
        code = generator.generate_from_template(
            analysis_type="buffer",
            input_files=["D:/data/roads.shp"],
            output_dir="D:/output",
            parameters={"distance": 500}
        )
        
        self.assertIsNotNone(code)
        self.assertIn("buffer", code)
    
    def test_generate_from_template_unknown(self):
        """测试从模板生成未知类型"""
        config = Config()
        generator = CodeGenerator.__new__(CodeGenerator)
        generator.config = config
        
        code = generator.generate_from_template(
            analysis_type="unknown_type",
            input_files=[],
            output_dir="D:/output",
            parameters={}
        )
        
        self.assertIsNone(code)


if __name__ == '__main__':
    unittest.main()

