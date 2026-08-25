"""
API 单元测试
"""
import pytest
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from api.main import app
from api.services.task_manager import TaskManager, TaskStatus, reset_task_manager


# 创建测试客户端
client = TestClient(app)


class TestRootEndpoints:
    """根路径测试"""
    
    def test_root(self):
        """测试根路径"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "AutoGIS API"
        assert data["status"] == "running"
    
    def test_health_check(self):
        """测试健康检查"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestAnalysisAPI:
    """分析任务 API 测试"""
    
    def setup_method(self):
        """每个测试前重置任务管理器"""
        reset_task_manager()
    
    def test_submit_task(self):
        """测试提交任务"""
        response = client.post(
            "/api/analysis/submit",
            json={
                "query": "测试分析任务",
                "skip_download": True,
                "auto_run": False,
                "auto_optimize": False,
                "max_optimization_rounds": 1
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        assert "任务已创建" in data["message"]
    
    def test_submit_task_validation(self):
        """测试任务提交验证"""
        # 空查询
        response = client.post(
            "/api/analysis/submit",
            json={
                "query": "",
                "skip_download": True
            }
        )
        assert response.status_code == 422  # 验证错误
    
    def test_get_task_not_found(self):
        """测试获取不存在的任务"""
        response = client.get("/api/analysis/task/non-existent-id")
        assert response.status_code == 404
    
    def test_get_task(self):
        """测试获取任务状态"""
        # 先创建任务
        submit_response = client.post(
            "/api/analysis/submit",
            json={"query": "测试任务", "auto_run": False}
        )
        task_id = submit_response.json()["task_id"]
        
        # 获取任务状态
        response = client.get(f"/api/analysis/task/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
    
    def test_list_tasks(self):
        """测试获取任务列表"""
        # 创建几个任务
        for i in range(3):
            client.post(
                "/api/analysis/submit",
                json={"query": f"任务 {i}", "auto_run": False}
            )
        
        response = client.get("/api/analysis/tasks?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
        assert len(data["tasks"]) >= 3
    
    def test_cancel_task(self):
        """测试取消任务"""
        from api.services.task_manager import get_task_manager, TaskStatus
        
        # 直接通过任务管理器创建任务（避免后台任务执行）
        task_manager = get_task_manager()
        task_id = "cancel-test-task"
        task_manager.create_task(task_id, {"query": "待取消任务"})
        
        # 确认任务处于 pending 状态
        task = task_manager.get_task(task_id)
        assert task["status"] == TaskStatus.PENDING
        
        # 取消任务
        response = client.delete(f"/api/analysis/task/{task_id}")
        assert response.status_code == 200
        assert response.json()["message"] == "任务已取消"
    
    def test_get_task_code(self):
        """测试获取生成的代码"""
        # 创建任务
        submit_response = client.post(
            "/api/analysis/submit",
            json={"query": "代码测试", "auto_run": False}
        )
        task_id = submit_response.json()["task_id"]
        
        response = client.get(f"/api/analysis/task/{task_id}/code")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["language"] == "python"


class TestDataAPI:
    """数据管理 API 测试"""
    
    def test_list_files(self):
        """测试获取文件列表"""
        response = client.get("/api/data/files?source=results")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "files" in data
    
    def test_list_files_with_type_filter(self):
        """测试带类型过滤的文件列表"""
        response = client.get("/api/data/files?source=results&type=vector")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
    
    def test_list_files_invalid_source(self):
        """测试无效数据源"""
        response = client.get("/api/data/files?source=invalid")
        assert response.status_code == 400
    
    def test_get_geojson_not_found(self):
        """测试获取不存在的 GeoJSON"""
        response = client.get("/api/data/geojson/non-existent.geojson")
        assert response.status_code == 404


class TestCatalogAPI:
    """数据目录 API 测试"""
    
    def test_get_catalog(self):
        """测试获取数据目录"""
        response = client.get("/api/catalog")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "entries" in data
    
    def test_get_catalog_with_pagination(self):
        """测试分页获取数据目录"""
        response = client.get("/api/catalog?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["entries"]) <= 5
    
    def test_search_catalog(self):
        """测试搜索数据目录"""
        response = client.post(
            "/api/catalog/search",
            json={
                "query": "boundary",
                "limit": 10
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "entries" in data
    
    def test_get_catalog_stats(self):
        """测试获取数据目录统计"""
        response = client.get("/api/catalog/stats/summary")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "by_type" in data


class TestTaskManager:
    """任务管理器单元测试"""
    
    def setup_method(self):
        """每个测试前重置"""
        reset_task_manager()
    
    def test_create_task(self):
        """测试创建任务"""
        manager = TaskManager()
        task = manager.create_task("test-001", {"query": "测试"})
        
        assert task["task_id"] == "test-001"
        assert task["status"] == TaskStatus.PENDING
        assert task["progress"] == 0
    
    def test_get_task(self):
        """测试获取任务"""
        manager = TaskManager()
        manager.create_task("test-002", {"query": "测试"})
        
        task = manager.get_task("test-002")
        assert task is not None
        assert task["task_id"] == "test-002"
        
        # 不存在的任务
        assert manager.get_task("non-existent") is None
    
    def test_update_task(self):
        """测试更新任务"""
        manager = TaskManager()
        manager.create_task("test-003", {"query": "测试"})
        
        manager.update_task(
            "test-003",
            status=TaskStatus.ANALYZING,
            message="分析中",
            progress=50
        )
        
        task = manager.get_task("test-003")
        assert task["status"] == TaskStatus.ANALYZING
        assert task["message"] == "分析中"
        assert task["progress"] == 50
    
    def test_list_tasks(self):
        """测试列出任务"""
        manager = TaskManager()
        for i in range(5):
            manager.create_task(f"test-{i}", {"query": f"任务{i}"})
        
        tasks = manager.list_tasks(limit=3)
        assert len(tasks) == 3
        
        all_tasks = manager.list_tasks(limit=10)
        assert len(all_tasks) == 5
    
    def test_cancel_task(self):
        """测试取消任务"""
        manager = TaskManager()
        manager.create_task("test-cancel", {"query": "待取消"})
        
        success = manager.cancel_task("test-cancel")
        assert success
        
        task = manager.get_task("test-cancel")
        assert task["status"] == TaskStatus.FAILED
        assert "取消" in task["message"]
    
    def test_delete_task(self):
        """测试删除任务"""
        manager = TaskManager()
        manager.create_task("test-delete", {"query": "待删除"})
        
        success = manager.delete_task("test-delete")
        assert success
        assert manager.get_task("test-delete") is None
    
    def test_progress_callback(self):
        """测试进度回调"""
        manager = TaskManager()
        manager.create_task("test-callback", {"query": "回调测试"})
        
        callback_data = []
        def callback(task):
            callback_data.append(task["progress"])
        
        manager.register_progress_callback("test-callback", callback)
        
        manager.update_task("test-callback", progress=50)
        manager.update_task("test-callback", progress=100)
        
        assert 50 in callback_data
        assert 100 in callback_data


class TestAsyncTaskExecution:
    """异步任务执行测试"""
    
    def setup_method(self):
        reset_task_manager()
    
    @pytest.mark.asyncio
    async def test_execute_task(self):
        """测试异步执行任务"""
        manager = TaskManager()
        manager.create_task("async-test", {"query": "异步测试"})
        
        await manager.execute_task(
            "async-test",
            "测试查询",
            skip_download=True,
            auto_run=False
        )
        
        task = manager.get_task("async-test")
        # 任务应该完成（即使是模拟执行）
        assert task["status"] in [TaskStatus.COMPLETED, TaskStatus.FAILED]
        assert task["progress"] in [0, 100]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

