"""
WebSocket 任务进度推送
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set
import json
import asyncio

from api.services.task_manager import get_task_manager

router = APIRouter()


class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        # task_id -> set of websocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # websocket -> task_id mapping for cleanup
        self._ws_to_task: Dict[WebSocket, str] = {}
    
    async def connect(self, websocket: WebSocket, task_id: str):
        """建立连接"""
        await websocket.accept()
        
        if task_id not in self.active_connections:
            self.active_connections[task_id] = set()
        
        self.active_connections[task_id].add(websocket)
        self._ws_to_task[websocket] = task_id
    
    def disconnect(self, websocket: WebSocket):
        """断开连接"""
        task_id = self._ws_to_task.get(websocket)
        
        if task_id and task_id in self.active_connections:
            self.active_connections[task_id].discard(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
        
        if websocket in self._ws_to_task:
            del self._ws_to_task[websocket]
    
    async def send_to_task(self, task_id: str, message: dict):
        """向任务的所有连接发送消息"""
        if task_id not in self.active_connections:
            return
        
        disconnected = set()
        for connection in self.active_connections[task_id]:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)
        
        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)
    
    def get_connection_count(self, task_id: str) -> int:
        """获取任务的连接数"""
        return len(self.active_connections.get(task_id, set()))
    
    def get_total_connections(self) -> int:
        """获取总连接数"""
        return sum(len(conns) for conns in self.active_connections.values())


# 全局连接管理器
manager = ConnectionManager()


@router.websocket("/task/{task_id}")
async def task_progress_websocket(websocket: WebSocket, task_id: str):
    """
    任务进度 WebSocket 端点
    
    连接后自动推送任务状态更新
    
    **消息格式：**
    
    接收：
    - `{"action": "ping"}` - 心跳检测
    - `{"action": "get_status"}` - 获取当前状态
    
    发送：
    - `{"type": "initial", ...}` - 初始状态
    - `{"type": "progress", ...}` - 进度更新
    - `{"type": "pong"}` - 心跳响应
    - `{"type": "status", ...}` - 状态响应
    """
    await manager.connect(websocket, task_id)
    
    task_manager = get_task_manager()
    
    # 获取当前运行的事件循环
    loop = asyncio.get_running_loop()
    
    # 使用队列来传递更新（线程安全）
    update_queue: asyncio.Queue = asyncio.Queue()
    
    # 创建进度回调
    async def send_progress(task_data):
        """发送进度更新"""
        message = {
            "type": "progress",
            "task_id": task_id,
            "status": task_data["status"].value if hasattr(task_data["status"], "value") else task_data["status"],
            "message": task_data["message"],
            "progress": task_data["progress"],
            "current_step": task_data.get("current_step"),
            "updated_at": task_data["updated_at"].isoformat() if task_data.get("updated_at") else None,
            "logs": task_data.get("logs", ""),  # logs 是字符串
            "task_type": task_data.get("task_type"),  # 任务类型
            "downloaded_files": task_data.get("downloaded_files", [])  # 下载的文件
        }
        await manager.send_to_task(task_id, message)
    
    # 同步回调包装器 - 使用队列
    def sync_callback(task_data):
        try:
            # 将更新放入队列（线程安全）
            loop.call_soon_threadsafe(update_queue.put_nowait, task_data.copy())
        except Exception:
            pass
    
    # 后台任务：处理队列中的更新
    async def process_updates():
        while True:
            try:
                task_data = await asyncio.wait_for(update_queue.get(), timeout=0.5)
                await send_progress(task_data)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                pass
    
    # 启动更新处理任务
    update_task = asyncio.create_task(process_updates())
    
    # 注册进度回调
    task_manager.register_progress_callback(task_id, sync_callback)
    
    try:
        # 发送初始状态
        current_task = task_manager.get_task(task_id)
        if current_task:
            await websocket.send_json({
                "type": "initial",
                "task_id": task_id,
                "status": current_task["status"].value if hasattr(current_task["status"], "value") else current_task["status"],
                "message": current_task["message"],
                "progress": current_task["progress"],
                "current_step": current_task.get("current_step"),
                "created_at": current_task["created_at"].isoformat() if current_task.get("created_at") else None,
                "logs": current_task.get("logs", ""),  # logs 是字符串
                "task_type": current_task.get("task_type"),  # 任务类型
                "downloaded_files": current_task.get("downloaded_files", [])  # 下载的文件
            })
        else:
            await websocket.send_json({
                "type": "error",
                "message": "任务不存在"
            })
        
        # 保持连接，处理客户端消息
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0  # 60秒超时
                )
                
                # 处理客户端命令
                try:
                    command = json.loads(data)
                    action = command.get("action")
                    
                    if action == "ping":
                        await websocket.send_json({"type": "pong"})
                    
                    elif action == "get_status":
                        task = task_manager.get_task(task_id)
                        if task:
                            await websocket.send_json({
                                "type": "status",
                                "task_id": task_id,
                                "status": task["status"].value if hasattr(task["status"], "value") else task["status"],
                                "progress": task["progress"],
                                "message": task["message"],
                                "current_step": task.get("current_step"),
                                "task_type": task.get("task_type"),
                                "downloaded_files": task.get("downloaded_files", [])
                            })
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "message": "任务不存在"
                            })
                    
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "message": "无效的JSON格式"
                    })
                    
            except asyncio.TimeoutError:
                # 发送心跳
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except Exception:
                    break
                    
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # 取消更新处理任务
        update_task.cancel()
        try:
            await update_task
        except asyncio.CancelledError:
            pass
        # 清理连接和回调
        manager.disconnect(websocket)
        task_manager.unregister_progress_callbacks(task_id)


@router.get("/connections", summary="获取 WebSocket 连接统计")
async def get_connection_stats():
    """获取当前 WebSocket 连接统计"""
    return {
        "total_connections": manager.get_total_connections(),
        "tasks_with_connections": len(manager.active_connections),
        "connections_by_task": {
            task_id: len(conns) 
            for task_id, conns in manager.active_connections.items()
        }
    }

