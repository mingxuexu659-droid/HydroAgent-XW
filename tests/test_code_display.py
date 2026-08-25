"""
测试代码显示和执行功能
"""
import pytest
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCodeRetrieval:
    """测试代码获取功能"""
    
    def test_task_has_code_after_completion(self):
        """测试任务完成后是否有代码"""
        from api.services.task_manager import TaskManager, TaskStatus
        import uuid
        
        manager = TaskManager()
        task_id = str(uuid.uuid4())
        manager.create_task(task_id, {"query": "测试查询"})
        
        # 模拟设置代码
        test_code = "print('hello world')"
        manager.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            code=test_code,
            message="完成"
        )
        
        # 获取任务
        task = manager.get_task(task_id)
        
        # 验证代码存在
        assert task is not None
        assert "code" in task
        assert task["code"] == test_code
    
    def test_api_returns_code(self):
        """测试 API 返回代码"""
        from fastapi.testclient import TestClient
        from api.main import app
        from api.services.task_manager import get_task_manager, TaskStatus
        import uuid
        
        client = TestClient(app)
        
        # 创建任务并设置代码
        task_manager = get_task_manager()
        task_id = str(uuid.uuid4())
        test_code = "# 测试代码\nprint('test')"
        
        task_manager.create_task(task_id, {"query": "测试"})
        task_manager.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            code=test_code,
            message="完成"
        )
        
        # 调用 API 获取代码
        response = client.get(f"/api/analysis/task/{task_id}/code")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "code" in data
        assert data["code"] == test_code
        assert data["language"] == "python"
    
    def test_extract_code_from_script_path(self):
        """测试从脚本路径提取代码"""
        from api.services.task_manager import TaskManager
        import tempfile
        import os
        
        manager = TaskManager()
        
        # 创建临时脚本文件
        test_code = "# Test script\nprint('hello')\nx = 1 + 2"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(test_code)
            script_path = f.name
        
        try:
            # 测试 _extract_code 方法
            result = {"script_path": script_path}
            extracted = manager._extract_code(result)
            
            print(f"Script path: {script_path}")
            print(f"Extracted code: {extracted}")
            
            assert extracted is not None
            assert extracted == test_code
        finally:
            os.unlink(script_path)
    
    def test_code_available_after_real_task(self):
        """测试真实任务完成后代码是否可用"""
        from api.services.task_manager import TaskManager
        import glob
        import os
        
        # 查找最新的生成脚本
        scripts_dir = "output/generated_scripts"
        if not os.path.exists(scripts_dir):
            pytest.skip("脚本目录不存在")
        
        scripts = glob.glob(os.path.join(scripts_dir, "analysis_*.py"))
        if not scripts:
            pytest.skip("没有找到生成的脚本")
        
        # 获取最新的脚本
        latest_script = max(scripts, key=os.path.getmtime)
        print(f"Latest script: {latest_script}")
        
        with open(latest_script, 'r', encoding='utf-8') as f:
            code = f.read()
        
        print(f"Script length: {len(code)} chars")
        print(f"First 200 chars: {code[:200]}")
        
        assert len(code) > 0


class TestCodeExecution:
    """测试代码执行功能"""
    
    def test_execute_simple_code(self):
        """测试执行简单代码"""
        from fastapi.testclient import TestClient
        from api.main import app
        
        client = TestClient(app)
        
        # 简单的打印代码
        code = "print('Hello, World!')"
        
        response = client.post(
            "/api/analysis/execute-code",
            json={"code": code}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        print(f"Response: {data}")
        
        assert "success" in data
        assert "message" in data
        # 使用 CodeExecutor 或回退到普通 Python，都应该成功
        assert data["success"] == True
    
    def test_execute_code_with_syntax_error(self):
        """测试执行有语法错误的代码"""
        from fastapi.testclient import TestClient
        from api.main import app
        
        client = TestClient(app)
        
        # 有语法错误的代码
        code = "print('unclosed string"
        
        response = client.post(
            "/api/analysis/execute-code",
            json={"code": code}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        print(f"Syntax Error Response: {data}")
        
        assert data["success"] == False
        assert "error" in data
        assert data["error"] is not None
        # 应该检测到语法错误
        assert "语法" in data["message"] or "SyntaxError" in str(data.get("error", ""))
    
    def test_execute_code_with_runtime_error(self):
        """测试执行有运行时错误的代码"""
        from fastapi.testclient import TestClient
        from api.main import app
        
        client = TestClient(app)
        
        # 有运行时错误的代码
        code = """
x = 1 / 0  # ZeroDivisionError
print("This won't be printed")
"""
        
        response = client.post(
            "/api/analysis/execute-code",
            json={"code": code}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        print(f"Runtime Error Response: {data}")
        
        assert data["success"] == False
        assert "error" in data
        # 应该包含 ZeroDivisionError
        assert "ZeroDivision" in str(data.get("error", "")) or "division" in str(data.get("error", "")).lower()
    
    def test_execute_real_script(self):
        """测试执行真实的脚本文件（使用 QGIS 环境）"""
        script_path = "output/generated_scripts/analysis_opt3_20260114_112707.py"
        
        if not os.path.exists(script_path):
            pytest.skip(f"脚本文件不存在: {script_path}")
        
        from fastapi.testclient import TestClient
        from api.main import app
        
        client = TestClient(app)
        
        # 读取脚本内容
        with open(script_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        print(f"Executing script: {script_path}")
        print(f"Code length: {len(code)} chars")
        
        response = client.post(
            "/api/analysis/execute-code",
            json={"code": code, "timeout": 120}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        print(f"\nExecution Result:")
        print(f"  Success: {data.get('success')}")
        print(f"  Message: {data.get('message')}")
        if data.get('execution_time'):
            print(f"  Execution Time: {data.get('execution_time'):.2f}s")
        if data.get('output_files'):
            print(f"  Output Files: {data.get('output_files')}")
        if data.get('output'):
            print(f"  Output (first 500 chars): {data.get('output', '')[:500]}")
        
        # 如果执行失败，打印详细错误
        if not data["success"]:
            print(f"\n=== 详细错误信息 ===")
            print(data.get("error", "无错误信息")[:1000])
    
    def test_code_executor_directly(self):
        """直接测试 CodeExecutor"""
        try:
            from spatial_analysis_system.code_executor import CodeExecutor
            
            executor = CodeExecutor()
            
            # 测试简单代码
            code = "print('Direct executor test')\nx = 1 + 2\nprint(f'Result: {x}')"
            
            # 验证代码
            is_valid, msg = executor.validate_code(code)
            print(f"Code validation: {is_valid}, {msg}")
            assert is_valid
            
            # 计算超时
            timeout = executor.calculate_timeout(code)
            print(f"Calculated timeout: {timeout}s")
            
            # 执行代码
            result = executor.execute(code, timeout=30)
            
            print(f"\nCodeExecutor Result:")
            print(f"  Success: {result.success}")
            print(f"  Output: {result.output}")
            print(f"  Error: {result.error}")
            print(f"  Execution Time: {result.execution_time:.2f}s")
            
        except FileNotFoundError as e:
            print(f"CodeExecutor not available: {e}")
            pytest.skip("runqgis 未配置")


class TestExecuteCodeAPI:
    """测试执行代码 API 响应格式"""
    
    def test_response_format(self):
        """测试响应格式正确"""
        from fastapi.testclient import TestClient
        from api.main import app
        
        client = TestClient(app)
        
        code = "x = 1 + 1\nprint(f'Result: {x}')"
        
        response = client.post(
            "/api/analysis/execute-code",
            json={"code": code}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # 检查响应字段
        assert "success" in data, "Response should have 'success' field"
        assert "message" in data, "Response should have 'message' field"
        assert "output_files" in data, "Response should have 'output_files' field"
        
        # success 应该是布尔值
        assert isinstance(data["success"], bool)
        # message 应该是字符串
        assert isinstance(data["message"], str)
        # output_files 应该是列表
        assert isinstance(data["output_files"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

