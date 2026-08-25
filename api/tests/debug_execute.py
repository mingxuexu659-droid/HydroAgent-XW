"""
调试代码执行问题
"""
import os
import sys
import subprocess
from pathlib import Path

# 添加项目根目录到路径
BASE_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BASE_DIR))


def debug_code_executor():
    """详细调试 CodeExecutor"""
    from spatial_analysis_system.code_executor import CodeExecutor
    from spatial_analysis_system.config import Config
    
    print("=" * 60)
    print("调试 CodeExecutor")
    print("=" * 60)
    
    # 1. 检查配置
    print("\n[1] 检查配置")
    print("-" * 60)
    config = Config()
    print(f"配置文件路径: {config.config_path}")
    print(f"QGIS 根目录: {config.qgis.root_path}")
    print(f"runqgis_bat_path: {config.qgis.runqgis_bat_path}")
    print(f"qgis_run_py_path: {config.qgis.qgis_run_py_path}")
    
    # 检查路径是否存在
    if config.qgis.runqgis_bat_path:
        exists = os.path.exists(config.qgis.runqgis_bat_path)
        print(f"runqgis_bat_path 存在: {exists}")
    
    if config.qgis.qgis_run_py_path:
        exists = os.path.exists(config.qgis.qgis_run_py_path)
        print(f"qgis_run_py_path 存在: {exists}")
    
    # 2. 初始化 CodeExecutor
    print("\n[2] 初始化 CodeExecutor")
    print("-" * 60)
    try:
        executor = CodeExecutor(config=config)
        print(f"✓ CodeExecutor 初始化成功")
        print(f"使用的 runqgis 路径: {executor.runqgis_path}")
    except FileNotFoundError as e:
        print(f"✗ CodeExecutor 初始化失败: {e}")
        return
    
    # 3. 手动测试 cmd.exe /c 执行
    print("\n[3] 测试 cmd.exe /c 执行 runqgis.bat")
    print("-" * 60)
    
    # 创建一个简单的测试脚本
    import tempfile
    test_code = """
print("Hello from test script")
try:
    from qgis.core import QgsApplication
    print("SUCCESS: qgis.core imported!")
except ImportError as e:
    print(f"FAILED: {e}")
"""
    
    # 写入临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(test_code)
        temp_script = f.name
    
    print(f"临时脚本: {temp_script}")
    
    # 构建命令
    bat_path = executor.runqgis_path
    cmd = ['cmd.exe', '/c', bat_path, temp_script]
    print(f"执行命令: {' '.join(cmd)}")
    
    # 执行
    print("\n执行中...")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            encoding='utf-8',
            errors='replace'
        )
        
        print(f"\n返回码: {result.returncode}")
        print(f"\nstdout:")
        print(result.stdout[:1000] if result.stdout else "(空)")
        print(f"\nstderr:")
        print(result.stderr[:1000] if result.stderr else "(空)")
        
        if "SUCCESS: qgis.core imported" in result.stdout:
            print("\n✓ QGIS 环境正常!")
        elif "FAILED" in result.stdout:
            print("\n✗ QGIS 导入失败")
        elif "No module named 'qgis'" in (result.stdout + result.stderr):
            print("\n✗ QGIS 模块未找到 - 环境未正确设置")
    except Exception as e:
        print(f"执行异常: {e}")
    finally:
        os.unlink(temp_script)
    
    # 4. 测试 CodeExecutor.execute()
    print("\n[4] 测试 CodeExecutor.execute()")
    print("-" * 60)
    
    simple_code = """
print("Testing CodeExecutor")
from qgis.core import QgsApplication
print("QGIS imported successfully!")
"""
    
    result = executor.execute(simple_code, timeout=30)
    
    print(f"成功: {result.success}")
    print(f"返回码: {result.return_code}")
    print(f"输出: {result.output[:500] if result.output else '(空)'}")
    print(f"错误: {result.error[:500] if result.error else '(空)'}")
    
    if result.success and "QGIS imported successfully" in result.output:
        print("\n✓ CodeExecutor 正常工作!")
    else:
        print("\n✗ CodeExecutor 执行失败")


def debug_direct_bat_execution():
    """直接测试 .bat 文件执行"""
    print("\n" + "=" * 60)
    print("直接测试 runqgis.bat 执行")
    print("=" * 60)
    
    bat_path = os.environ.get("AUTOGIS_QGIS_LAUNCHER", "")
    
    if not os.path.exists(bat_path):
        print(f"✗ runqgis.bat 不存在: {bat_path}")
        return
    
    print(f"runqgis.bat 路径: {bat_path}")
    
    # 创建测试脚本
    import tempfile
    test_code = """
print("Direct test")
import sys
print(f"Python: {sys.executable}")
try:
    from qgis.core import QgsApplication
    print("QGIS OK!")
except Exception as e:
    print(f"QGIS ERROR: {e}")
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(test_code)
        temp_script = f.name
    
    print(f"测试脚本: {temp_script}")
    
    # 方式1: cmd.exe /c
    print("\n--- 方式1: cmd.exe /c ---")
    cmd1 = ['cmd.exe', '/c', bat_path, temp_script]
    print(f"命令: {cmd1}")
    
    result1 = subprocess.run(cmd1, capture_output=True, text=True, timeout=30)
    print(f"返回码: {result1.returncode}")
    print(f"stdout: {result1.stdout[:300]}")
    print(f"stderr: {result1.stderr[:300]}")
    
    # 方式2: 直接执行
    print("\n--- 方式2: 直接执行 ---")
    cmd2 = [bat_path, temp_script]
    print(f"命令: {cmd2}")
    
    try:
        result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=30, shell=True)
        print(f"返回码: {result2.returncode}")
        print(f"stdout: {result2.stdout[:300]}")
        print(f"stderr: {result2.stderr[:300]}")
    except Exception as e:
        print(f"执行失败: {e}")
    
    # 清理
    os.unlink(temp_script)


if __name__ == "__main__":
    debug_code_executor()
    debug_direct_bat_execution()

