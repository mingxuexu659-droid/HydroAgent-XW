"""
任务持久化测试
"""
import pytest
import os
import json
from datetime import datetime

from api.services.task_manager import (
    TaskManager, TaskStatus,
    _load_tasks_from_cache, _save_tasks_to_cache,
    get_task_manager, reset_task_manager,
    TASKS_CACHE_FILE
)


class TestTaskPersistence:
    """测试任务持久化功能"""
    
    def setup_method(self):
        """测试前清理"""
        # 清理缓存文件
        if os.path.exists(TASKS_CACHE_FILE):
            os.remove(TASKS_CACHE_FILE)
        reset_task_manager()
    
    def teardown_method(self):
        """测试后清理"""
        if os.path.exists(TASKS_CACHE_FILE):
            os.remove(TASKS_CACHE_FILE)
        reset_task_manager()
    
    def test_save_and_load_tasks(self):
        """测试保存和加载任务"""
        # 创建测试任务
        tasks = {
            "task-1": {
                "task_id": "task-1",
                "status": TaskStatus.COMPLETED,
                "message": "完成",
                "created_at": datetime(2026, 1, 14, 10, 0, 0),
                "updated_at": datetime(2026, 1, 14, 10, 5, 0),
                "progress": 100,
                "current_step": "完成",
                "logs": "测试日志"
            }
        }
        
        # 保存
        _save_tasks_to_cache(tasks)
        assert os.path.exists(TASKS_CACHE_FILE)
        
        # 加载
        loaded_tasks = _load_tasks_from_cache()
        assert len(loaded_tasks) == 1
        assert "task-1" in loaded_tasks
        assert loaded_tasks["task-1"]["task_id"] == "task-1"
        assert loaded_tasks["task-1"]["status"] == TaskStatus.COMPLETED
        assert isinstance(loaded_tasks["task-1"]["created_at"], datetime)
    
    def test_task_manager_restore(self):
        """测试任务管理器从缓存恢复"""
        # 第一个管理器实例
        manager1 = get_task_manager()
        task1 = manager1.create_task("restore-test", {"query": "测试"})
        manager1.update_task("restore-test", status=TaskStatus.COMPLETED, message="完成")
        
        # 保存状态
        manager1._save_state()
        
        # 重置并创建新实例（模拟重启）
        reset_task_manager()
        manager2 = get_task_manager()
        
        # 验证任务被恢复
        restored_task = manager2.get_task("restore-test")
        assert restored_task is not None
        assert restored_task["task_id"] == "restore-test"
        assert restored_task["status"] == TaskStatus.COMPLETED
    
    def test_cache_file_format(self):
        """测试缓存文件格式"""
        manager = get_task_manager()
        manager.create_task("format-test", {"query": "测试"})
        manager.update_task("format-test", status=TaskStatus.ANALYZING, progress=15)
        manager._save_state()
        
        # 读取并验证JSON格式
        with open(TASKS_CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert isinstance(data, dict)
        assert "format-test" in data
        assert data["format-test"]["status"] == "analyzing"
        assert data["format-test"]["progress"] == 15
    
    def test_task_update_auto_save(self):
        """测试任务更新时自动保存"""
        manager = get_task_manager()
        manager.create_task("autosave-test", {"query": "测试"})
        
        # 完成任务应该触发保存
        manager.update_task("autosave-test", status=TaskStatus.COMPLETED, message="完成")
        
        # 验证文件存在
        assert os.path.exists(TASKS_CACHE_FILE)
        
        # 验证数据
        loaded_tasks = _load_tasks_from_cache()
        assert loaded_tasks["autosave-test"]["status"] == TaskStatus.COMPLETED
    
    def test_load_empty_cache(self):
        """测试加载空缓存"""
        # 确保没有缓存文件
        assert not os.path.exists(TASKS_CACHE_FILE)
        
        # 加载应该返回空字典
        tasks = _load_tasks_from_cache()
        assert tasks == {}
    
    def test_corrupted_cache_handling(self):
        """测试处理损坏的缓存文件"""
        # 创建损坏的缓存文件
        os.makedirs(os.path.dirname(TASKS_CACHE_FILE), exist_ok=True)
        with open(TASKS_CACHE_FILE, 'w') as f:
            f.write("这不是有效的JSON")
        
        # 加载应该返回空字典而不抛出异常
        tasks = _load_tasks_from_cache()
        assert tasks == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

