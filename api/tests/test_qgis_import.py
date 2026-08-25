"""
测试 QGIS 模块导入是否正常
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
BASE_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BASE_DIR))


def test_qgis_import_in_code_executor():
    """测试在 CodeExecutor 中执行包含 qgis.core 导入的代码"""
    from spatial_analysis_system.code_executor import CodeExecutor
    from spatial_analysis_system.config import Config
    
    config = Config()
    executor = CodeExecutor(config=config)
    
    # 测试代码：导入 qgis.core
    test_code = """
from qgis.core import QgsVectorLayer, QgsProject
import processing

print("✓ QGIS core modules imported successfully")
print("✓ Processing module imported successfully")

# 测试 QgsProject
project = QgsProject.instance()
print(f"✓ QgsProject instance created: {project}")

print("All QGIS imports successful!")
"""
    
    print("\n" + "=" * 60)
    print("测试 QGIS 模块导入")
    print("=" * 60)
    print("\n执行代码...")
    print("-" * 60)
    
    result = executor.execute(test_code, timeout=30)
    
    print("\n执行结果:")
    print(f"  成功: {result.success}")
    print(f"  返回码: {result.return_code}")
    print(f"  执行时间: {result.execution_time:.2f}秒")
    
    if result.output:
        print(f"\n输出:")
        print(result.output[:1000])
    
    if result.error:
        print(f"\n错误信息:")
        print(result.error[:1000])
    
    # 检查是否成功导入
    if result.success and 'QGIS imports successful' in result.output:
        print("\n✓ 测试通过 - QGIS 模块导入成功")
        return True
    else:
        print("\n✗ 测试失败 - QGIS 模块导入失败")
        if result.error:
            print(f"错误: {result.error[:500]}")
        return False


def test_api_qgis_import():
    """测试通过 API 执行包含 qgis.core 导入的代码"""
    from fastapi.testclient import TestClient
    from api.main import app
    
    client = TestClient(app)
    
    test_code = """
from qgis.core import QgsVectorLayer, QgsProject
print("QGIS modules imported successfully")
"""
    
    print("\n" + "=" * 60)
    print("测试 API 端点: QGIS 模块导入")
    print("=" * 60)
    
    response = client.post(
        "/api/analysis/execute-code",
        json={
            "code": test_code,
            "timeout": 30
        }
    )
    
    result = response.json()
    
    print(f"\n响应:")
    print(f"  success: {result.get('success')}")
    print(f"  message: {result.get('message')}")
    
    output = result.get('output', '') or ''
    error = result.get('error', '') or ''
    
    if output:
        print(f"\n输出 (前500字符):")
        print(output[:500])
    
    if error:
        print(f"\n错误 (前500字符):")
        print(error[:500])
    
    if result.get('success') and 'imported successfully' in output:
        print("\n✓ API 测试通过 - QGIS 模块导入成功")
        return True
    else:
        print("\n✗ API 测试失败")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("QGIS 模块导入测试")
    print("=" * 60)
    
    # 测试1: CodeExecutor
    print("\n[测试1] CodeExecutor 中的 QGIS 导入")
    print("-" * 60)
    try:
        success = test_qgis_import_in_code_executor()
        if not success:
            sys.exit(1)
    except Exception as e:
        print(f"\n✗ 测试1异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 测试2: API端点
    print("\n[测试2] API 端点中的 QGIS 导入")
    print("-" * 60)
    try:
        success = test_api_qgis_import()
        if not success:
            sys.exit(1)
    except Exception as e:
        print(f"\n✗ 测试2异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✓ 所有测试通过")
    print("=" * 60)

