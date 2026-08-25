"""
Task Management Service - Integrated with AutoGIS Workflow Engine
"""
import asyncio
import os
import sys
import json
import traceback
import re
import io
import threading
from typing import Dict, Optional, List, Any, Callable
from datetime import datetime
from enum import Enum
from contextlib import redirect_stdout, redirect_stderr

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TaskStatus(str, Enum):
    """Task status enumeration"""
    PENDING = "pending"
    ANALYZING = "analyzing"
    DOWNLOADING = "downloading"
    GENERATING = "generating"
    EXECUTING = "executing"
    OPTIMIZING = "optimizing"
    COMPLETED = "completed"
    FAILED = "failed"


class LogCapture(io.StringIO):
    """
    Log Capture - Captures print output with real-time callback
    """
    def __init__(self, callback: Callable[[str], None], original_stdout=None):
        super().__init__()
        self.callback = callback
        self.original_stdout = original_stdout or sys.stdout
        self._buffer = ""
    
    def write(self, text: str):
        # Write to original stdout (keep terminal output)
        if self.original_stdout:
            self.original_stdout.write(text)
            self.original_stdout.flush()
        
        # Accumulate text until newline
        self._buffer += text
        
        # Split by line and process complete lines
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():  # Ignore empty lines
                self.callback(line)
        
        return len(text)
    
    def flush(self):
        if self.original_stdout:
            self.original_stdout.flush()
        # Process remaining content in buffer
        if self._buffer.strip():
            self.callback(self._buffer)
            self._buffer = ""


class TaskManager:
    """Task Manager"""
    
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self._progress_callbacks: Dict[str, List[Callable]] = {}
        self._config = None
    
    def _get_config(self):
        """Lazy load configuration"""
        if self._config is None:
            try:
                from spatial_analysis_system.config import Config
                self._config = Config()
            except ImportError:
                self._config = None
        return self._config
    
    def create_task(self, task_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create task"""
        now = datetime.now()
        task = {
            "task_id": task_id,
            "status": TaskStatus.PENDING,
            "message": "Task created, waiting to process",
            "created_at": now,
            "updated_at": now,
            "progress": 0,
            "current_step": "Waiting",
            "params": params,
            "result": None,
            "code": None,
            "script_path": None,
                    "output_files": [],
            "task_type": None,  # Task type: data_download_only, data_and_code, code_only
            "downloaded_files": [],  # Downloaded data file list
            "logs": ""  # Raw output text
        }
        self.tasks[task_id] = task
        return task
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task"""
        return self.tasks.get(task_id)
    
    def list_tasks(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """Get task list"""
        tasks = list(self.tasks.values())
        tasks.sort(key=lambda x: x["created_at"], reverse=True)
        return tasks[offset:offset + limit]
    
    def count_tasks(self) -> int:
        """Get total task count"""
        return len(self.tasks)
    
    def update_task(self, task_id: str, **kwargs):
        """Update task status"""
        if task_id in self.tasks:
            self.tasks[task_id].update(kwargs)
            self.tasks[task_id]["updated_at"] = datetime.now()
            
            # Log message
            if "message" in kwargs:
                self._add_log(task_id, "info", kwargs["message"])
            
            # Trigger progress callback
            self._notify_progress(task_id)
            
            # Save state when task ends
            status = kwargs.get("status")
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                self._save_state()
    
    def _save_state(self):
        """Save current state to cache"""
        _save_tasks_to_cache(self.tasks)
    
    def _add_log(self, task_id: str, level: str, message: str):
        """Add log (append to raw output text)"""
        if task_id in self.tasks:
            # Append raw text directly, preserve newlines
            self.tasks[task_id]["logs"] += message + "\n"
    
    def _notify_progress(self, task_id: str):
        """Notify progress update (thread-safe) - call callbacks directly, callbacks handle async"""
        if task_id not in self._progress_callbacks:
            return
            
        if task_id not in self.tasks:
            return
        
        # Copy task data to avoid thread issues
        task = self.tasks[task_id].copy()
        task["logs"] = self.tasks[task_id].get("logs", "")
        
        # Call all callbacks directly - callbacks handle thread safety
        for callback in list(self._progress_callbacks[task_id]):
            try:
                callback(task)
            except Exception:
                # Silently ignore callback errors
                pass
    
    def register_progress_callback(self, task_id: str, callback: Callable):
        """Register progress callback"""
        if task_id not in self._progress_callbacks:
            self._progress_callbacks[task_id] = []
        self._progress_callbacks[task_id].append(callback)
    
    def unregister_progress_callbacks(self, task_id: str):
        """Unregister all progress callbacks"""
        if task_id in self._progress_callbacks:
            del self._progress_callbacks[task_id]
    
    def _parse_log_line(self, line: str) -> tuple:
        """
        Parse log line, extract status info
        Returns: (level, message, status_update)
        """
        line = line.strip()
        if not line:
            return None, None, None
        
        # Remove ANSI escape codes
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        line = ansi_escape.sub('', line)
        
        # Determine log level
        level = "info"
        if "❌" in line or "✗" in line or "error" in line.lower() or "fail" in line.lower():
            level = "error"
        elif "⚠️" in line or "warning" in line.lower():
            level = "warning"
        elif "✓" in line or "✅" in line or "success" in line.lower():
            level = "info"
        
        # Parse status update (only key statuses trigger updates)
        status_update = None
        if "Intent Analysis" in line or "Intent analysis" in line:
            status_update = {"status": TaskStatus.ANALYZING, "current_step": "Intent Analysis", "progress": 15}
        elif "Data Download" in line or "Downloading" in line or "Step 1" in line:
            status_update = {"status": TaskStatus.DOWNLOADING, "current_step": "Data Retrieval", "progress": 30}
        elif "Code Generation" in line or "Step 2" in line or "Code generation" in line:
            status_update = {"status": TaskStatus.GENERATING, "current_step": "Code Generation", "progress": 50}
        elif "Code Execution" in line or "Step 3" in line or "Code execution" in line:
            status_update = {"status": TaskStatus.EXECUTING, "current_step": "Code Execution", "progress": 70}
        elif "Optimization Round" in line or "optimization round" in line:
            # Parse optimization round
            match = re.search(r'(\d+)/(\d+)', line)
            if match:
                current, total = int(match.group(1)), int(match.group(2))
                progress = 70 + int(25 * current / total)
                status_update = {"status": TaskStatus.OPTIMIZING, "current_step": f"Optimizing {current}/{total}", "progress": progress}
        
        return level, line, status_update
    
    
    async def execute_task(
        self,
        task_id: str,
        query: str,
        skip_download: bool = False,
        auto_run: bool = True,
        auto_optimize: bool = True,
        max_optimization_rounds: int = 3
    ):
        """Execute analysis task"""
        
        # Log callback function - push every log
        def on_log_line(line: str):
            level, message, status_update = self._parse_log_line(line)
            if message:
                self._add_log(task_id, level or "info", message)
                
                # If status update, update task status
                if status_update:
                    self.update_task(task_id, **status_update)
                else:
                    # Push every log to maintain real-time updates
                    self._notify_progress(task_id)
        
        try:
            # Initial status
            self.update_task(
                task_id,
                status=TaskStatus.ANALYZING,
                message="Analyzing your requirements...",
                progress=10,
                current_step="Intent Analysis"
            )
            await asyncio.sleep(0.1)
            
            # Try to import workflow engine
            try:
                from spatial_analysis_system.workflow_engine import WorkflowEngine
                config = self._get_config()
                engine = WorkflowEngine(config)
                has_engine = True
            except ImportError as e:
                has_engine = False
                self._add_log(task_id, "warning", f"Workflow engine not loaded: {e}")
            
            result = None
            if has_engine:
                # Execute workflow with log capture
                def run_workflow():
                    original_stdout = sys.stdout
                    original_stderr = sys.stderr
                    
                    # Create log capture
                    log_capture = LogCapture(on_log_line, original_stdout)
                    
                    try:
                        sys.stdout = log_capture
                        sys.stderr = log_capture
                        
                        # Execute workflow
                        return engine.process(query)
                    finally:
                        # Restore original output
                        sys.stdout = original_stdout
                        sys.stderr = original_stderr
                        log_capture.flush()
                
                try:
                    workflow_result = await asyncio.to_thread(run_workflow)
                    
                    # Convert WorkflowResult to dict
                    result = {
                        "success": workflow_result.success if hasattr(workflow_result, 'success') else True,
                        "message": workflow_result.message if hasattr(workflow_result, 'message') else "Execution complete",
                        "script_path": workflow_result.script_path if hasattr(workflow_result, 'script_path') else None,
                        "output_files": workflow_result.output_files if hasattr(workflow_result, 'output_files') else [],
                        "task_type": workflow_result.task_type.value if hasattr(workflow_result, 'task_type') else None,
                        "downloaded_files": workflow_result.downloaded_files if hasattr(workflow_result, 'downloaded_files') else [],
                        "query": query,
                        # Add execution output (print results from code)
                        "execution_output": workflow_result.execution_result.output if (
                            hasattr(workflow_result, 'execution_result') and 
                            workflow_result.execution_result and 
                            hasattr(workflow_result.execution_result, 'output')
                        ) else ""
                    }
                except Exception as engine_error:
                    self._add_log(task_id, "error", f"Workflow engine execution failed: {engine_error}")
                    result = {
                        "success": False,
                        "message": str(engine_error),
                        "query": query
                    }
            else:
                # Simulate execution (for testing)
                self._add_log(task_id, "info", "Retrieving data...")
                self.update_task(task_id, status=TaskStatus.DOWNLOADING, progress=30, current_step="Data Retrieval")
                await asyncio.sleep(0.3)
                
                self._add_log(task_id, "info", "Generating analysis code...")
                self.update_task(task_id, status=TaskStatus.GENERATING, progress=50, current_step="Code Generation")
                await asyncio.sleep(0.3)
                
                self._add_log(task_id, "info", "Executing analysis script...")
                self.update_task(task_id, status=TaskStatus.EXECUTING, progress=70, current_step="Code Execution")
                await asyncio.sleep(0.3)
                
                result = {
                    "success": True,
                    "message": "Simulation complete (workflow engine not loaded)",
                    "query": query
                }
            
            # Process results
            output_files = self._collect_output_files(result)
            code = self._extract_code(result)
            script_path = result.get("script_path") if result else None
            execution_output = result.get("execution_output", "") if result else ""
            
            # Set final status based on execution result
            if result and result.get("success", False):
                self._add_log(task_id, "info", "Analysis complete!")
                
                # Add execution output to logs (if any)
                if execution_output:
                    self._add_log(task_id, "info", "====== Code Execution Output ======")
                    for line in execution_output.split('\n'):
                        if line.strip():
                            self._add_log(task_id, "info", line)
                    self._add_log(task_id, "info", "===================================")
                
                self.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    message="Analysis complete!",
                    progress=100,
                    current_step="Completed",
                    result=result,
                    code=code,
                    script_path=script_path,
                    output_files=output_files,
                    execution_output=execution_output,
                    task_type=result.get("task_type") if result else None,
                    downloaded_files=result.get("downloaded_files", []) if result else []
                )
            else:
                error_msg = result.get("message", "Execution failed") if result else "Execution failed"
                self._add_log(task_id, "error", error_msg)
                self.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message=error_msg,
                    progress=100,
                    current_step="Failed",
                    result=result,
                    code=code,
                    script_path=script_path,
                    output_files=output_files,
                    task_type=result.get("task_type") if result else None,
                    downloaded_files=result.get("downloaded_files", []) if result else []
                )
            
        except Exception as e:
            error_msg = str(e)
            traceback_str = traceback.format_exc()
            
            self._add_log(task_id, "error", f"Task execution failed: {error_msg}")
            self._add_log(task_id, "error", traceback_str)
            
            self.update_task(
                task_id,
                status=TaskStatus.FAILED,
                message=f"Task failed: {error_msg}",
                progress=0,
                current_step="Error"
            )
    
    def _collect_output_files(self, result: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Collect output files and convert GPKG to GeoJSON for web display"""
        files = []
        
        # Get output directory from config
        config = self._get_config()
        if config and hasattr(config, 'output') and hasattr(config.output, 'result_output_dir'):
            output_dir = config.output.result_output_dir
        else:
            output_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "output", "results"
            )
        
        if os.path.exists(output_dir):
            for filename in os.listdir(output_dir):
                filepath = os.path.join(output_dir, filename)
                if os.path.isfile(filepath):
                    ext = os.path.splitext(filename)[1].lower()
                    file_type = self._get_file_type(filename)
                    
                    # Convert GPKG to GeoJSON for web display
                    if ext == '.gpkg':
                        geojson_path = filepath.replace('.gpkg', '.geojson')
                        geojson_filename = filename.replace('.gpkg', '.geojson')
                        
                        # Convert if GeoJSON doesn't exist or GPKG is newer
                        if not os.path.exists(geojson_path) or os.path.getmtime(filepath) > os.path.getmtime(geojson_path):
                            try:
                                import geopandas as gpd
                                gdf = gpd.read_file(filepath)
                                # Reproject to WGS84 if needed
                                if gdf.crs and gdf.crs.to_epsg() != 4326:
                                    gdf = gdf.to_crs(epsg=4326)
                                gdf.to_file(geojson_path, driver='GeoJSON')
                                print(f"[TaskManager] Converted {filename} to GeoJSON")
                            except Exception as e:
                                print(f"[TaskManager] Failed to convert {filename}: {e}")
                        
                        # Use GeoJSON if it exists
                        if os.path.exists(geojson_path):
                            file_info = {
                                "name": geojson_filename.replace('.geojson', '').replace('_', ' ').title(),
                                "path": geojson_path,
                                "url": f"/results/{geojson_filename}",
                                "type": "vector",
                                "size": os.path.getsize(geojson_path)
                            }
                            files.append(file_info)
                            continue
                    
                    file_info = {
                        "name": filename,
                        "path": filepath,
                        "url": f"/results/{filename}",
                        "type": file_type,
                        "size": os.path.getsize(filepath)
                    }
                    files.append(file_info)
        
        return files
    
    def _get_file_type(self, filename: str) -> str:
        """Get file type"""
        ext = os.path.splitext(filename)[1].lower()
        type_map = {
            ".geojson": "vector",
            ".json": "json",
            ".tif": "raster",
            ".tiff": "raster",
            ".shp": "vector",
            ".gpkg": "vector",
            ".png": "image",
            ".jpg": "image",
            ".py": "script"
        }
        return type_map.get(ext, "other")
    
    def _extract_code(self, result: Optional[Dict[str, Any]]) -> Optional[str]:
        """Extract generated code"""
        if result and "script_path" in result:
            script_path = result["script_path"]
            if script_path and os.path.exists(script_path):
                try:
                    with open(script_path, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception:
                    pass
        return None
    
    def get_task_code(self, task_id: str) -> Optional[str]:
        """Get task code"""
        task = self.tasks.get(task_id)
        if task:
            return task.get("code")
        return None
    
    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task result"""
        task = self.tasks.get(task_id)
        if task:
            return {
                "task_id": task_id,
                "status": task["status"],
                "output_files": task.get("output_files", []),
                "result": task.get("result")
            }
        return None
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel task"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if task["status"] in [TaskStatus.PENDING, TaskStatus.ANALYZING]:
                self.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message="Task cancelled",
                    current_step="Cancelled"
                )
                return True
        return False
    
    def delete_task(self, task_id: str) -> bool:
        """Delete task"""
        if task_id in self.tasks:
            # Clean up callbacks
            self.unregister_progress_callbacks(task_id)
            del self.tasks[task_id]
            return True
        return False


# Global task manager instance
_task_manager: Optional[TaskManager] = None

# Task persistence file path
TASKS_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "output", ".tasks_cache.json"
)


def _load_tasks_from_cache() -> Dict[str, Dict[str, Any]]:
    """Load tasks from cache file"""
    if not os.path.exists(TASKS_CACHE_FILE):
        return {}
    
    try:
        with open(TASKS_CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Restore task status enums
        for task_id, task in data.items():
            if isinstance(task.get("status"), str):
                try:
                    task["status"] = TaskStatus(task["status"])
                except ValueError:
                    task["status"] = TaskStatus.FAILED
            
            # Restore datetime
            for key in ["created_at", "updated_at"]:
                if isinstance(task.get(key), str):
                    try:
                        task[key] = datetime.fromisoformat(task[key])
                    except:
                        task[key] = datetime.now()
        
        return data
    except Exception as e:
        print(f"[TaskManager] Failed to load task cache: {e}")
        return {}


def _save_tasks_to_cache(tasks: Dict[str, Dict[str, Any]]):
    """Save tasks to cache file"""
    try:
        os.makedirs(os.path.dirname(TASKS_CACHE_FILE), exist_ok=True)
        
        # Serialize task data
        data = {}
        for task_id, task in tasks.items():
            task_copy = task.copy()
            
            # Convert enum to string
            if hasattr(task_copy.get("status"), "value"):
                task_copy["status"] = task_copy["status"].value
            
            # Convert datetime to string
            for key in ["created_at", "updated_at"]:
                if isinstance(task_copy.get(key), datetime):
                    task_copy[key] = task_copy[key].isoformat()
            
            data[task_id] = task_copy
        
        with open(TASKS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[TaskManager] Failed to save task cache: {e}")


def get_task_manager() -> TaskManager:
    """Get task manager singleton"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
        # Restore tasks from cache
        cached_tasks = _load_tasks_from_cache()
        if cached_tasks:
            _task_manager.tasks = cached_tasks
            print(f"[TaskManager] Restored {len(cached_tasks)} tasks from cache")
    return _task_manager


def save_task_manager_state():
    """Save task manager state to cache"""
    global _task_manager
    if _task_manager:
        _save_tasks_to_cache(_task_manager.tasks)


def reset_task_manager():
    """Reset task manager (for testing)"""
    global _task_manager
    _task_manager = None

