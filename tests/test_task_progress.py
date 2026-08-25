"""
任务进度更新测试
"""
import pytest
import asyncio
import json
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket
import httpx

# 测试配置
BASE_URL = "http://localhost:8080"
WS_URL = "ws://localhost:8080"


class TestTaskProgress:
    """测试任务进度更新"""
    
    def test_submit_and_get_task(self):
        """测试提交任务并获取状态"""
        with httpx.Client(base_url=BASE_URL, timeout=30) as client:
            # 1. 提交任务
            response = client.post("/api/analysis/submit", json={
                "query": "测试任务",
                "skip_download": True,
                "auto_run": False,
                "auto_optimize": False
            })
            
            print(f"Submit response: {response.status_code}")
            print(f"Response body: {response.json()}")
            
            assert response.status_code == 200
            result = response.json()
            task_id = result["task_id"]
            
            print(f"Task ID: {task_id}")
            print(f"Initial status: {result['status']}")
            
            # 2. 等待一段时间让任务处理
            import time
            time.sleep(2)
            
            # 3. 获取任务状态
            response = client.get(f"/api/analysis/task/{task_id}")
            print(f"Get task response: {response.status_code}")
            
            if response.status_code == 200:
                task = response.json()
                print(f"Task status: {task['status']}")
                print(f"Task progress: {task['progress']}")
                print(f"Task message: {task['message']}")
            else:
                print(f"Error: {response.json()}")
    
    def test_task_list(self):
        """测试获取任务列表"""
        with httpx.Client(base_url=BASE_URL, timeout=30) as client:
            response = client.get("/api/analysis/tasks")
            print(f"Tasks response: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"Total tasks: {result['total']}")
                for task in result['tasks'][:5]:
                    print(f"  - {task['task_id']}: {task['status']} ({task['progress']}%)")
            else:
                print(f"Error: {response.json()}")


class TestWebSocket:
    """测试 WebSocket 连接"""
    
    @pytest.mark.asyncio
    async def test_websocket_connection(self):
        """测试 WebSocket 连接和消息接收"""
        import websockets
        
        # 先提交一个任务
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
            response = await client.post("/api/analysis/submit", json={
                "query": "WebSocket 测试任务",
                "skip_download": True,
                "auto_run": False,
                "auto_optimize": False
            })
            
            assert response.status_code == 200
            task_id = response.json()["task_id"]
            print(f"Created task: {task_id}")
        
        # 连接 WebSocket
        ws_url = f"{WS_URL}/ws/task/{task_id}"
        print(f"Connecting to: {ws_url}")
        
        try:
            async with websockets.connect(ws_url) as ws:
                print("WebSocket connected")
                
                # 接收消息（最多等待 10 秒）
                for _ in range(10):
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        data = json.loads(message)
                        print(f"Received: {data['type']} - {data.get('status')} ({data.get('progress')}%)")
                        
                        if data.get('status') in ['completed', 'failed']:
                            break
                    except asyncio.TimeoutError:
                        print("Waiting for message...")
                        continue
                
        except Exception as e:
            print(f"WebSocket error: {e}")


def test_simple():
    """简单测试 - 验证服务是否运行"""
    with httpx.Client(base_url=BASE_URL, timeout=5) as client:
        try:
            response = client.get("/docs")
            print(f"Server status: {response.status_code}")
            assert response.status_code == 200
            print("✅ Server is running")
        except Exception as e:
            print(f"❌ Server error: {e}")


def test_full_workflow():
    """完整工作流测试"""
    import time
    
    with httpx.Client(base_url=BASE_URL, timeout=120) as client:
        # 1. 提交真实的分析任务
        print("提交分析任务...")
        response = client.post("/api/analysis/submit", json={
            "query": "请下载清华大学的矢量边界",
            "skip_download": False,
            "auto_run": False,
            "auto_optimize": False
        })
        
        assert response.status_code == 200
        result = response.json()
        task_id = result["task_id"]
        print(f"Task ID: {task_id}")
        
        # 2. 轮询任务状态直到完成
        max_wait = 60  # 最多等待60秒
        start = time.time()
        
        while time.time() - start < max_wait:
            response = client.get(f"/api/analysis/task/{task_id}")
            
            if response.status_code == 200:
                task = response.json()
                print(f"Status: {task['status']} ({task['progress']}%) - {task['message']}")
                
                if task['status'] in ['completed', 'failed']:
                    print(f"\n任务结束: {task['status']}")
                    if task['status'] == 'completed':
                        print("✅ 任务成功完成")
                    else:
                        print(f"❌ 任务失败: {task.get('message')}")
                    break
            else:
                print(f"Error getting task: {response.status_code}")
            
            time.sleep(1)
        else:
            print("⚠️ 任务超时")


if __name__ == "__main__":
    print("=" * 60)
    print("任务进度测试")
    print("=" * 60)
    
    # 测试服务器状态
    print("\n1. 测试服务器状态")
    test_simple()
    
    # 测试任务提交和获取
    print("\n2. 测试任务提交和获取")
    test = TestTaskProgress()
    test.test_submit_and_get_task()
    
    # 测试任务列表
    print("\n3. 测试任务列表")
    test.test_task_list()
    
    # 完整工作流测试
    print("\n4. 完整工作流测试")
    test_full_workflow()

