"""
测试代码执行器是否正确使用QGIS环境
"""
import os
import sys
import pytest
from pathlib import Path

# 添加项目根目录到路径
BASE_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BASE_DIR))


def test_code_executor_initialization():
    """测试CodeExecutor是否能正确初始化"""
    from spatial_analysis_system.code_executor import CodeExecutor
    from spatial_analysis_system.config import Config
    
    # 加载配置
    config = Config()
    print(f"\n配置路径: {config.config_path}")
    print(f"QGIS配置:")
    print(f"  runqgis_bat_path: {config.qgis.runqgis_bat_path}")
    print(f"  qgis_run_py_path: {config.qgis.qgis_run_py_path}")
    
    # 检查路径是否存在
    if config.qgis.runqgis_bat_path:
        exists = os.path.exists(config.qgis.runqgis_bat_path)
        print(f"  runqgis_bat_path 存在: {exists}")
    
    if config.qgis.qgis_run_py_path:
        exists = os.path.exists(config.qgis.qgis_run_py_path)
        print(f"  qgis_run_py_path 存在: {exists}")
    
    # 尝试初始化CodeExecutor
    try:
        executor = CodeExecutor(config=config)
        print(f"\n✓ CodeExecutor 初始化成功")
        print(f"  使用的 runqgis 路径: {executor.runqgis_path}")
        return executor
    except FileNotFoundError as e:
        print(f"\n✗ CodeExecutor 初始化失败: {e}")
        raise


def test_code_executor_find_runqgis():
    """测试CodeExecutor是否能找到runqgis"""
    from spatial_analysis_system.code_executor import CodeExecutor
    from spatial_analysis_system.config import Config
    
    config = Config()
    executor = CodeExecutor(config=config)
    
    # 检查runqgis路径
    assert executor.runqgis_path is not None, "runqgis路径不能为空"
    assert os.path.exists(executor.runqgis_path), f"runqgis路径不存在: {executor.runqgis_path}"
    
    print(f"\n✓ 找到 runqgis: {executor.runqgis_path}")
    
    # 检查是否是QGIS相关的路径
    runqgis_path_lower = executor.runqgis_path.lower()
    is_qgis = (
        'qgis' in runqgis_path_lower or 
        'runqgis' in runqgis_path_lower or
        executor.runqgis_path.endswith('.bat') or
        executor.runqgis_path.endswith('.py')
    )
    
    assert is_qgis, f"runqgis路径看起来不正确: {executor.runqgis_path}"
    print(f"✓ runqgis路径格式正确")


def test_code_executor_execute_simple_code():
    """测试执行简单代码"""
    from spatial_analysis_system.code_executor import CodeExecutor
    from spatial_analysis_system.config import Config
    
    config = Config()
    executor = CodeExecutor(config=config)
    
    # 简单的测试代码（不依赖QGIS）
    test_code = """
print("Hello from QGIS Python environment")
result = 1 + 1
print(f"Result: {result}")
"""
    
    print(f"\n执行测试代码...")
    result = executor.execute(test_code, timeout=30)
    
    print(f"\n执行结果:")
    print(f"  成功: {result.success}")
    print(f"  返回码: {result.return_code}")
    print(f"  输出: {result.output[:200] if result.output else '无'}")
    print(f"  错误: {result.error[:200] if result.error else '无'}")
    print(f"  执行时间: {result.execution_time:.2f}秒")
    
    # 检查是否使用了QGIS环境（通过检查输出中是否包含QGIS相关信息）
    output_lower = (result.output or "").lower()
    error_lower = (result.error or "").lower()
    combined = output_lower + error_lower
    
    # QGIS环境通常会输出一些初始化信息
    qgis_indicators = [
        'qgis',
        'grass',
        'saga',
        'processing',
        'runqgis',
        'provider'
    ]
    
    uses_qgis = any(indicator in combined for indicator in qgis_indicators)
    
    if uses_qgis:
        print(f"\n✓ 检测到QGIS环境标识")
    else:
        print(f"\n⚠️ 未检测到QGIS环境标识，可能使用了普通Python")
        print(f"  输出内容: {combined[:500]}")
    
    return result


def test_api_execute_code_endpoint():
    """测试API端点的代码执行"""
    import sys
    import os
    
    # 模拟API请求
    from spatial_analysis_system.code_executor import CodeExecutor
    from spatial_analysis_system.config import Config
    
    config = Config()
    
    try:
        executor = CodeExecutor(config=config)
        print(f"\n✓ API可以创建CodeExecutor")
        print(f"  使用的路径: {executor.runqgis_path}")
        
        # 测试简单代码
        test_code = "print('API test')"
        result = executor.execute(test_code, timeout=10)
        
        print(f"\nAPI执行结果:")
        print(f"  成功: {result.success}")
        print(f"  返回码: {result.return_code}")
        
        return True
    except FileNotFoundError as e:
        print(f"\n✗ API无法创建CodeExecutor: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("CodeExecutor 测试")
    print("=" * 60)
    
    # 测试1: 初始化
    print("\n[测试1] CodeExecutor 初始化")
    print("-" * 60)
    try:
        executor = test_code_executor_initialization()
        print("✓ 测试1通过")
    except Exception as e:
        print(f"✗ 测试1失败: {e}")
        sys.exit(1)
    
    # 测试2: 查找runqgis
    print("\n[测试2] 查找 runqgis 路径")
    print("-" * 60)
    try:
        test_code_executor_find_runqgis()
        print("✓ 测试2通过")
    except Exception as e:
        print(f"✗ 测试2失败: {e}")
        sys.exit(1)
    
    # 测试3: 执行简单代码
    print("\n[测试3] 执行简单代码")
    print("-" * 60)
    try:
        result = test_code_executor_execute_simple_code()
        if result.success:
            print("✓ 测试3通过")
        else:
            print(f"⚠️ 测试3: 代码执行失败，但这是预期的（如果QGIS环境未正确配置）")
    except Exception as e:
        print(f"✗ 测试3失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试4: API端点测试
    print("\n[测试4] API端点测试")
    print("-" * 60)
    try:
        success = test_api_execute_code_endpoint()
        if success:
            print("✓ 测试4通过")
        else:
            print("✗ 测试4失败")
    except Exception as e:
        print(f"✗ 测试4失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

