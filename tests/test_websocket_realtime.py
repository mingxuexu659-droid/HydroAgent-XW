"""
WebSocket 实时日志推送测试
"""
import pytest
import asyncio
import threading
import time
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

# 测试 TaskManager 的日志回调机制
class TestTaskManagerCallback:
    """测试 TaskManager 回调机制"""
    
    def test_callback_called_on_log(self):
        """测试添加日志时回调被调用"""
        from api.services.task_manager import TaskManager, TaskStatus
        import uuid
        
        manager = TaskManager()
        task_id = str(uuid.uuid4())
        manager.create_task(task_id, {"query": "test query"})
        
        # 记录回调调用
        callback_calls = []
        def callback(task_data):
            callback_calls.append(task_data.copy())
        
        manager.register_progress_callback(task_id, callback)
        
        # 添加日志
        manager._add_log(task_id, "info", "测试日志1")
        manager._notify_progress(task_id)
        
        manager._add_log(task_id, "info", "测试日志2")
        manager._notify_progress(task_id)
        
        # 验证回调被调用
        assert len(callback_calls) >= 2
        assert "测试日志1" in callback_calls[0]["logs"]
        assert "测试日志2" in callback_calls[-1]["logs"]
    
    def test_callback_from_thread(self):
        """测试从后台线程调用回调"""
        from api.services.task_manager import TaskManager, TaskStatus
        import uuid
        
        manager = TaskManager()
        task_id = str(uuid.uuid4())
        manager.create_task(task_id, {"query": "test query"})
        
        # 记录回调调用
        callback_calls = []
        callback_lock = threading.Lock()
        
        def callback(task_data):
            with callback_lock:
                callback_calls.append({
                    "logs": task_data.get("logs", ""),
                    "thread": threading.current_thread().name
                })
        
        manager.register_progress_callback(task_id, callback)
        
        # 从后台线程添加日志
        def add_logs():
            for i in range(5):
                manager._add_log(task_id, "info", f"线程日志 {i}")
                manager._notify_progress(task_id)
                time.sleep(0.1)
        
        thread = threading.Thread(target=add_logs)
        thread.start()
        thread.join()
        
        # 验证回调被调用
        assert len(callback_calls) >= 5
        for call in callback_calls:
            assert "线程日志" in call["logs"]


class TestWebSocketQueue:
    """测试 WebSocket 队列机制"""
    
    @pytest.mark.asyncio
    async def test_queue_receives_updates(self):
        """测试队列能收到更新"""
        loop = asyncio.get_running_loop()
        update_queue = asyncio.Queue()
        
        received = []
        
        # 消费者协程
        async def consumer():
            while len(received) < 5:
                try:
                    data = await asyncio.wait_for(update_queue.get(), timeout=1.0)
                    received.append(data)
                except asyncio.TimeoutError:
                    break
        
        # 生产者线程
        def producer():
            for i in range(5):
                loop.call_soon_threadsafe(update_queue.put_nowait, f"消息 {i}")
                time.sleep(0.05)
        
        # 启动消费者和生产者
        consumer_task = asyncio.create_task(consumer())
        thread = threading.Thread(target=producer)
        thread.start()
        
        await consumer_task
        thread.join()
        
        # 验证所有消息都被接收
        assert len(received) == 5
        for i in range(5):
            assert f"消息 {i}" in received
    
    @pytest.mark.asyncio
    async def test_concurrent_queue_and_receive(self):
        """测试队列处理与 WebSocket 接收并发"""
        loop = asyncio.get_running_loop()
        update_queue = asyncio.Queue()
        
        received_updates = []
        received_messages = []
        
        # 模拟 WebSocket 消息接收
        async def mock_receive():
            await asyncio.sleep(0.3)
            return "ping"
        
        # 更新处理协程
        async def process_updates():
            while True:
                try:
                    data = await asyncio.wait_for(update_queue.get(), timeout=0.1)
                    received_updates.append(data)
                except asyncio.TimeoutError:
                    if len(received_updates) >= 5:
                        break
                except asyncio.CancelledError:
                    break
        
        # WebSocket 主循环协程
        async def ws_loop():
            for _ in range(3):
                msg = await mock_receive()
                received_messages.append(msg)
        
        # 生产者线程
        def producer():
            for i in range(5):
                loop.call_soon_threadsafe(update_queue.put_nowait, f"更新 {i}")
                time.sleep(0.1)
        
        # 并发运行
        thread = threading.Thread(target=producer)
        thread.start()
        
        update_task = asyncio.create_task(process_updates())
        ws_task = asyncio.create_task(ws_loop())
        
        await asyncio.gather(update_task, ws_task, return_exceptions=True)
        thread.join()
        
        # 验证两个任务都正常工作
        assert len(received_updates) >= 5
        assert len(received_messages) == 3


class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_flow(self):
        """测试完整流程：TaskManager -> Queue -> WebSocket"""
        from api.services.task_manager import TaskManager
        import uuid
        
        loop = asyncio.get_running_loop()
        manager = TaskManager()
        task_id = str(uuid.uuid4())
        manager.create_task(task_id, {"query": "集成测试"})
        
        # 模拟 WebSocket 端的队列和处理
        update_queue = asyncio.Queue()
        received_logs = []
        
        def sync_callback(task_data):
            try:
                loop.call_soon_threadsafe(
                    update_queue.put_nowait, 
                    task_data.get("logs", "")
                )
            except Exception:
                pass
        
        manager.register_progress_callback(task_id, sync_callback)
        
        # 处理更新的协程
        async def process():
            while True:
                try:
                    logs = await asyncio.wait_for(update_queue.get(), timeout=0.5)
                    received_logs.append(logs)
                    if "完成" in logs:
                        break
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
        
        # 模拟工作流执行的线程
        def workflow():
            for i in range(3):
                manager._add_log(task_id, "info", f"步骤 {i+1}")
                manager._notify_progress(task_id)
                time.sleep(0.1)
            manager._add_log(task_id, "info", "完成")
            manager._notify_progress(task_id)
        
        # 启动处理和工作流
        process_task = asyncio.create_task(process())
        thread = threading.Thread(target=workflow)
        thread.start()
        
        # 等待完成
        try:
            await asyncio.wait_for(process_task, timeout=5.0)
        except asyncio.TimeoutError:
            process_task.cancel()
        
        thread.join()
        
        # 验证日志被接收
        assert len(received_logs) >= 4
        final_logs = received_logs[-1]
        assert "步骤 1" in final_logs
        assert "步骤 2" in final_logs
        assert "步骤 3" in final_logs
        assert "完成" in final_logs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

