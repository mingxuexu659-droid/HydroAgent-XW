"""
集成测试：验证 script_path 在整个工作流中的传递
"""
import pytest
import requests
import time
import os

BASE_URL = "http://localhost:8000"


def test_script_path_full_workflow():
    """测试 script_path 在提交任务->完成->获取代码的完整流程中正确传递"""
    
    # 1. 提交任务
    submit_response = requests.post(
        f"{BASE_URL}/api/analysis/submit",
        json={
            "query": "请使用清华大学和北京大学的边界，设置600米缓冲区",
            "skip_download": True,
            "auto_run": True,
            "auto_optimize": False
        }
    )
    
    assert submit_response.status_code == 200
    task_id = submit_response.json()["task_id"]
    
    # 2. 等待任务完成
    max_wait = 120
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        status_response = requests.get(f"{BASE_URL}/api/analysis/task/{task_id}")
        assert status_response.status_code == 200
        
        status_data = status_response.json()
        if status_data["status"] == "completed":
            break
        elif status_data["status"] == "failed":
            pytest.fail(f"任务失败: {status_data['message']}")
        
        time.sleep(2)
    else:
        pytest.fail("等待任务完成超时")
    
    # 3. 验证 /task 端点返回 script_path
    task_response = requests.get(f"{BASE_URL}/api/analysis/task/{task_id}")
    assert task_response.status_code == 200
    task_data = task_response.json()
    
    assert task_data["script_path"] is not None, "GET /task 端点未返回 script_path"
    assert task_data["script_path"].endswith(".py"), "script_path 不是 Python 文件"
    assert os.path.exists(task_data["script_path"]), "script_path 指向的文件不存在"
    assert task_data["code"] is not None, "GET /task 端点未返回 code"
    assert len(task_data["code"]) > 0, "返回的 code 为空"
    
    # 4. 验证 /code 端点返回 script_path
    code_response = requests.get(f"{BASE_URL}/api/analysis/task/{task_id}/code")
    assert code_response.status_code == 200
    code_data = code_response.json()
    
    assert code_data["script_path"] is not None, "GET /code 端点未返回 script_path"
    assert code_data["script_path"] == task_data["script_path"], "/code 和 /task 返回的 script_path 不一致"
    assert code_data["code"] is not None, "GET /code 端点未返回 code"
    assert code_data["code"] == task_data["code"], "/code 和 /task 返回的 code 不一致"
    
    print(f"\n✅ 测试通过！")
    print(f"   任务ID: {task_id}")
    print(f"   脚本路径: {task_data['script_path']}")
    print(f"   代码长度: {len(task_data['code'])} 字符")


def test_script_path_with_optimization():
    """测试在代码优化场景下，script_path 正确更新为优化后的脚本"""
    
    # 提交一个会触发优化的任务（使用不存在的数据路径）
    submit_response = requests.post(
        f"{BASE_URL}/api/analysis/submit",
        json={
            "query": "分析 /nonexistent/path.geojson 的缓冲区",
            "skip_download": True,
            "auto_run": True,
            "auto_optimize": True,
            "max_optimization_rounds": 1
        }
    )
    
    assert submit_response.status_code == 200
    task_id = submit_response.json()["task_id"]
    
    # 等待任务完成（可能失败或优化）
    max_wait = 120
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        status_response = requests.get(f"{BASE_URL}/api/analysis/task/{task_id}")
        assert status_response.status_code == 200
        
        status_data = status_response.json()
        if status_data["status"] in ["completed", "failed"]:
            break
        
        time.sleep(2)
    
    # 如果任务完成（优化成功）或失败，都应该有 script_path
    task_data = status_response.json()
    
    if task_data["status"] == "completed":
        # 优化成功，应该有优化后的脚本
        assert task_data["script_path"] is not None, "优化后未返回 script_path"
        assert "opt" in task_data["script_path"].lower(), "script_path 应该包含 'opt' 标识"
    else:
        # 优化失败，应该有原始或最后一次尝试的脚本
        assert task_data["script_path"] is not None, "失败后也应该返回 script_path"
    
    print(f"\n✅ 优化测试通过！")
    print(f"   任务ID: {task_id}")
    print(f"   最终状态: {task_data['status']}")
    print(f"   脚本路径: {task_data['script_path']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

