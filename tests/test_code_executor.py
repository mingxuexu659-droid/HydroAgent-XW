# -*- coding: utf-8 -*-
"""
代码执行器单元测试
"""

import unittest
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from spatial_analysis_system.code_executor import (
    CodeExecutor,
    ExecutionResult,
)
from spatial_analysis_system.config import Config


class TestExecutionResult(unittest.TestCase):
    """测试执行结果类"""
    
    def test_execution_result_creation(self):
        """测试执行结果创建"""
        result = ExecutionResult(
            success=True,
            output="执行成功",
            error="",
            return_code=0,
            execution_time=1.5,
            script_path="D:/test.py"
        )
        
        self.assertTrue(result.success)
        self.assertEqual(result.return_code, 0)
        self.assertEqual(result.execution_time, 1.5)
    
    def test_execution_result_to_dict(self):
        """测试执行结果转字典"""
        result = ExecutionResult(
            success=False,
            output="",
            error="执行失败",
            return_code=1,
            execution_time=2.0,
            script_path="D:/test.py"
        )
        
        result_dict = result.to_dict()
        
        self.assertIsInstance(result_dict, dict)
        self.assertFalse(result_dict["success"])
        self.assertEqual(result_dict["return_code"], 1)
        self.assertEqual(result_dict["error"], "执行失败")


class TestCodeExecutorValidation(unittest.TestCase):
    """测试代码执行器验证功能"""
    
    def test_validate_code_valid(self):
        """测试有效代码验证"""
        config = Config()
        executor = CodeExecutor.__new__(CodeExecutor)
        executor.config = config
        
        valid_code = """
import os
print("Hello World")
"""
        
        is_valid, message = executor.validate_code(valid_code)
        
        self.assertTrue(is_valid)
        self.assertIn("正确", message)
    
    def test_validate_code_syntax_error(self):
        """测试语法错误代码验证"""
        config = Config()
        executor = CodeExecutor.__new__(CodeExecutor)
        executor.config = config
        
        invalid_code = """
import os
print("Hello World"
"""  # 缺少右括号
        
        is_valid, message = executor.validate_code(invalid_code)
        
        self.assertFalse(is_valid)
        self.assertIn("语法错误", message)


class TestCodeExecutorTimeout(unittest.TestCase):
    """测试代码执行器超时计算"""
    
    def test_calculate_timeout_single_tool(self):
        """测试单工具超时计算"""
        config = Config()
        config.qgis.timeout_per_tool = 20
        
        executor = CodeExecutor.__new__(CodeExecutor)
        executor.config = config
        
        code = """
import processing
result = processing.run("native:buffer", {...})
"""
        
        timeout = executor.calculate_timeout(code, base_timeout=100)
        
        # 100 + 1*20 = 120
        self.assertEqual(timeout, 120)
    
    def test_calculate_timeout_multiple_tools(self):
        """测试多工具超时计算"""
        config = Config()
        config.qgis.timeout_per_tool = 20
        config.qgis.script_timeout = 300
        
        executor = CodeExecutor.__new__(CodeExecutor)
        executor.config = config
        
        code = """
import processing
result1 = processing.run("native:buffer", {...})
result2 = processing.run("native:clip", {...})
result3 = processing.run("native:dissolve", {...})
"""
        
        timeout = executor.calculate_timeout(code, base_timeout=100)
        
        # 100 + 3*20 = 160
        self.assertEqual(timeout, 160)
    
    def test_calculate_timeout_max_limit(self):
        """测试超时上限"""
        config = Config()
        config.qgis.timeout_per_tool = 100
        config.qgis.script_timeout = 200
        
        executor = CodeExecutor.__new__(CodeExecutor)
        executor.config = config
        
        # 很多工具调用
        code = "\n".join([f'processing.run("native:tool{i}", {{}})' for i in range(10)])
        
        timeout = executor.calculate_timeout(code, base_timeout=100)
        
        # 应该被限制在 script_timeout (200)
        self.assertEqual(timeout, 200)


if __name__ == '__main__':
    unittest.main()

