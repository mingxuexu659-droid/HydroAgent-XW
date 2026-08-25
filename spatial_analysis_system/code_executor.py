# -*- coding: utf-8 -*-
"""
Code Executor Module

Responsible for executing generated QGIS spatial analysis code, supports timeout control and error capture.
"""

import os
import subprocess
import tempfile
import platform
import signal
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

from .config import Config, get_config


# 全局变量，用于信号处理
_active_processes = []
_lock = threading.Lock()


@dataclass
class ExecutionResult:
    """Code execution result"""
    success: bool
    output: str = ""
    error: str = ""
    return_code: int = -1
    execution_time: float = 0.0
    script_path: str = ""
    
    def to_dict(self):
        return {
            'success': self.success,
            'output': self.output,
            'error': self.error,
            'return_code': self.return_code,
            'execution_time': self.execution_time,
            'script_path': self.script_path,
        }


def kill_process_tree(pid: int) -> None:
    """Force terminate process and all its child processes"""
    try:
        if platform.system() == 'Windows':
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5
            )
        else:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            import time
            time.sleep(1)
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except:
                pass
    except Exception:
        pass


class CodeExecutor:
    """
    QGIS Code Executor
    
    Executes generated spatial analysis code using QGIS Python environment.
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize code executor
        
        Args:
            config: Configuration object
        """
        self.config = config or get_config()
        self.runqgis_path = self._find_runqgis_path()
    
    def _find_runqgis_path(self) -> str:
        """Find runqgis path"""
        # 首先检查配置中的路径
        paths_to_check = [
            self.config.qgis.runqgis_bat_path,
            self.config.qgis.qgis_run_py_path,
        ]
        
        for path in paths_to_check:
            if path and os.path.exists(path):
                return path
        
        raise FileNotFoundError("Cannot find runqgis, please check path settings in config")
    
    def execute(self, code: str, timeout: Optional[int] = None) -> ExecutionResult:
        """
        Execute Python code
        
        Args:
            code: Python code string
            timeout: Timeout in seconds, uses config default if None
        
        Returns:
            ExecutionResult: Execution result
        """
        if timeout is None:
            timeout = self.config.qgis.script_timeout
        
        print(f"\n{'='*60}")
        print(f"Code Execution")
        print(f"{'='*60}")
        
        start_time = datetime.now()
        temp_script = None
        
        try:
            # Create temporary script file
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.py',
                delete=False,
                encoding='utf-8'
            ) as f:
                temp_script = f.name
                f.write(code)
            
            # Fix: ensure temp file path is absolute (important for packaged exe)
            temp_script = os.path.abspath(temp_script)
            
            # Fix: ensure runqgis path is absolute
            runqgis_path = os.path.abspath(self.runqgis_path)
            
            print(f"Temp script: {temp_script}")
            print(f"Timeout: {timeout}s")
            print(f"runqgis path: {runqgis_path}")
            print(f"Starting execution...")
            
            # Build command
            # Windows requires special handling for .bat files
            if runqgis_path.endswith('.bat'):
                # Fix: on Windows with shell=True, command should be string format
                # If path contains spaces, wrap with quotes
                if ' ' in runqgis_path:
                    runqgis_path_quoted = f'"{runqgis_path}"'
                else:
                    runqgis_path_quoted = runqgis_path
                if ' ' in temp_script:
                    temp_script_quoted = f'"{temp_script}"'
                else:
                    temp_script_quoted = temp_script
                cmd = f'{runqgis_path_quoted} {temp_script_quoted}'
                use_shell = True
            elif runqgis_path.endswith('.py'):
                # For .py files, need to use QGIS Python interpreter
                # Try to get python-qgis.bat path from config
                qgis_root = self.config.qgis.root_path
                python_qgis_bat = os.path.join(qgis_root, 'bin', 'python-qgis.bat')
                if os.path.exists(python_qgis_bat):
                    python_qgis_bat = os.path.abspath(python_qgis_bat)
                    # Fix: on Windows with shell=True, command should be string format
                    if ' ' in python_qgis_bat:
                        python_qgis_bat_quoted = f'"{python_qgis_bat}"'
                    else:
                        python_qgis_bat_quoted = python_qgis_bat
                    if ' ' in runqgis_path:
                        runqgis_path_quoted = f'"{runqgis_path}"'
                    else:
                        runqgis_path_quoted = runqgis_path
                    if ' ' in temp_script:
                        temp_script_quoted = f'"{temp_script}"'
                    else:
                        temp_script_quoted = temp_script
                    cmd = f'{python_qgis_bat_quoted} {runqgis_path_quoted} {temp_script_quoted}'
                    use_shell = True
                else:
                    # Fallback to regular python (not recommended, will fail)
                    cmd = ['python', runqgis_path, temp_script]
                    use_shell = False
            else:
                cmd = [runqgis_path, temp_script]
                use_shell = False
            
            print(f"Command: {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
            print(f"shell={use_shell}")
            
            # Execute command
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                shell=use_shell
            )
            
            # 注册进程
            with _lock:
                _active_processes.append(process)
            
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                return_code = process.returncode
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                # 合并 stdout 和 stderr（qgis_run.py 的调试信息在 stderr 中，用户输出在 stdout 中）
                # 将 stderr 中的 [runqgis] 信息和分隔线过滤掉，只保留真正的错误
                stderr_lines = stderr.split('\n') if stderr else []
                user_stderr = []
                runqgis_info = []
                
                for line in stderr_lines:
                    stripped = line.strip()
                    # 过滤 runqgis 信息、空行、分隔线
                    if '[runqgis]' in line:
                        runqgis_info.append(line)
                    elif stripped and not stripped.startswith('-' * 10):
                        # 只保留有实际内容的行（非空行、非分隔线）
                        user_stderr.append(line)
                
                # 过滤 stdout 中的 QGIS 算法参数调试输出
                # 这些是 QGIS 初始化时打印的，形如 ['PARAM_NAME', 'Description', None, 'True/False']
                stdout_lines = stdout.split('\n') if stdout else []
                filtered_stdout_lines = []
                for line in stdout_lines:
                    stripped = line.strip()
                    # 过滤掉 QGIS 算法参数输出（形如 ['XXX', 'YYY', None, 'True/False']）
                    if stripped.startswith('[\'') and stripped.endswith('\']'):
                        # 检查是否是算法参数格式：['NAME', 'Description', None, 'True/False']
                        if ', None, \'' in stripped or ', None, "' in stripped:
                            continue  # 跳过这种调试输出
                    filtered_stdout_lines.append(line)
                
                # 合并输出：用户输出（已过滤）
                combined_output = '\n'.join(filtered_stdout_lines)
                
                # 判断是否成功 - 主要依据返回码
                success = return_code == 0
                
                # 检查是否有真正的 Python 错误（只检查有实际内容的错误信息）
                actual_errors = [line for line in user_stderr if line.strip()]
                if actual_errors:
                    error_text = '\n'.join(actual_errors)
                    
                    # 检查是否包含 Python 异常（明确的错误指示）
                    python_error_indicators = [
                        'Traceback (most recent call last)',
                        'ModuleNotFoundError:',
                        'ImportError:',
                        'SyntaxError:',
                        'NameError:',
                        'TypeError:',
                        'ValueError:',
                        'AttributeError:',
                        'KeyError:',
                        'IndexError:',
                        'FileNotFoundError:',
                        'OSError:',
                        'RuntimeError:',
                    ]
                    for indicator in python_error_indicators:
                        if indicator in error_text:
                            success = False
                            break
                    
                    # 注意：GDAL/OGR 的 "ERROR 1:" 警告（如 Permission denied）不应该导致失败
                    # 这些通常是警告而非致命错误
                
                # 也检查 stdout 中的错误信息
                if success and combined_output:
                    # Python 异常
                    python_errors = ['Traceback (most recent call last)', 'ModuleNotFoundError:', 'ImportError:']
                    for indicator in python_errors:
                        if indicator in combined_output:
                            success = False
                            break
                    
                    # 用户自定义的错误输出（常见的错误打印模式）
                    if success:
                        user_error_indicators = [
                            'Error during processing:',
                            'Error: Failed to',
                            'Error: Unable to',
                            'Error: Could not',
                            '❌',  # Error marker
                        ]
                        for indicator in user_error_indicators:
                            if indicator in combined_output:
                                success = False
                                break
                
                if success:
                    print(f"✓ Execution successful (elapsed: {execution_time:.2f}s)")
                else:
                    print(f"✗ Execution failed (return code: {return_code})")
                    if user_stderr:
                        error_preview = '\n'.join(user_stderr[:5])
                        print(f"  Error info: {error_preview[:200]}...")
                
                return ExecutionResult(
                    success=success,
                    output=combined_output,  # Use merged output
                    error='\n'.join(user_stderr) if user_stderr else '',  # Only return actual errors
                    return_code=return_code,
                    execution_time=execution_time,
                    script_path=temp_script
                )
                
            except subprocess.TimeoutExpired:
                print(f"⚠️  Execution timeout (>{timeout}s)")
                process.terminate()
                try:
                    process.wait(timeout=2)
                except:
                    kill_process_tree(process.pid)
                    try:
                        process.kill()
                    except:
                        pass
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"Execution timeout (>{timeout}s)",
                    return_code=-1,
                    execution_time=execution_time,
                    script_path=temp_script
                )
            
            finally:
                # Remove from active processes list
                with _lock:
                    if process in _active_processes:
                        _active_processes.remove(process)
        
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            print(f"❌ Execution exception: {e}")
            
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                return_code=-1,
                execution_time=execution_time,
                script_path=temp_script or ""
            )
        
        finally:
            # Clean up temp file (optional, keep for debugging)
            # if temp_script and os.path.exists(temp_script):
            #     os.remove(temp_script)
            pass
    
    def execute_file(self, script_path: str, timeout: Optional[int] = None) -> ExecutionResult:
        """
        Execute script file
        
        Args:
            script_path: Script file path
            timeout: Timeout in seconds
        
        Returns:
            ExecutionResult: Execution result
        """
        if not os.path.exists(script_path):
            return ExecutionResult(
                success=False,
                error=f"Script file not found: {script_path}",
                script_path=script_path
            )
        
        with open(script_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        result = self.execute(code, timeout)
        result.script_path = script_path
        return result
    
    def calculate_timeout(self, code: str, base_timeout: int = 150) -> int:
        """
        Calculate timeout based on code complexity
        
        Args:
            code: Python code
            base_timeout: Base timeout
        
        Returns:
            Calculated timeout
        """
        import re
        
        # Count processing.run calls
        processing_calls = len(re.findall(r'processing\.run\s*\(', code))
        
        # Add extra time per processing call
        timeout = base_timeout + processing_calls * self.config.qgis.timeout_per_tool
        
        # Cap at max configured timeout
        return min(timeout, self.config.qgis.script_timeout)
    
    def validate_code(self, code: str) -> Tuple[bool, str]:
        """
        Validate code syntax
        
        Args:
            code: Python code
        
        Returns:
            (valid, message): Whether valid and error message
        """
        try:
            compile(code, '<string>', 'exec')
            return True, "Code syntax correct"
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

