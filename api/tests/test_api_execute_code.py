"""
测试API端点的代码执行功能
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
BASE_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BASE_DIR))


def test_api_execute_code_endpoint():
    """测试API端点的完整执行流程"""
    import json
    from fastapi.testclient import TestClient
    
    # 导入API应用
    from api.main import app
    
    client = TestClient(app)
    
    # 测试代码（简单的QGIS代码）
    test_code = """
from qgis.core import QgsApplication
print("QGIS Application initialized")
print("This is running in QGIS Python environment")
"""
    
    print("\n" + "=" * 60)
    print("测试API端点: /api/analysis/execute-code")
    print("=" * 60)
    
    # 发送POST请求
    print(f"\n发送请求...")
    print(f"代码长度: {len(test_code)} 字符")
    
    response = client.post(
        "/api/analysis/execute-code",
        json={
            "code": test_code,
            "timeout": 30
        }
    )
    
    print(f"\n响应状态码: {response.status_code}")
    
    if response.status_code != 200:
        print(f"✗ 请求失败")
        print(f"响应内容: {response.text}")
        return False
    
    # 解析响应
    result = response.json()
    
    print(f"\n响应内容:")
    print(f"  success: {result.get('success')}")
    print(f"  message: {result.get('message')}")
    print(f"  execution_time: {result.get('execution_time')}")
    
    # 检查输出
    output = result.get('output', '')
    error = result.get('error', '')
    
    print(f"\n输出内容 (前500字符):")
    if output:
        print(f"  {output[:500]}")
    else:
        print(f"  (无)")
    
    print(f"\n错误内容 (前500字符):")
    if error:
        print(f"  {error[:500]}")
    else:
        print(f"  (无)")
    
    # 检查是否使用了QGIS环境
    output_str = output or ''
    error_str = error or ''
    combined = (output_str + error_str).lower()
    
    qgis_indicators = [
        'qgis',
        'grass',
        'saga',
        'processing',
        'runqgis',
        'provider'
    ]
    
    uses_qgis = any(indicator in combined for indicator in qgis_indicators)
    
    print(f"\n" + "-" * 60)
    if uses_qgis:
        print("✓ 检测到QGIS环境标识 - 使用了QGIS环境")
    else:
        print("✗ 未检测到QGIS环境标识 - 可能使用了普通Python")
        print(f"  完整输出: {combined[:1000]}")
    
    print(f"\n执行结果:")
    if result.get('success'):
        print("  ✓ 代码执行成功")
    else:
        print("  ✗ 代码执行失败")
        print(f"  错误信息: {result.get('error', '')[:200]}")
    
    return result.get('success') and uses_qgis


def test_api_execute_code_with_qgis_processing():
    """测试执行包含QGIS processing的代码"""
    from fastapi.testclient import TestClient
    from api.main import app
    
    client = TestClient(app)
    
    # 测试代码（使用QGIS processing）
    test_code = """
from qgis.core import QgsVectorLayer, QgsProject
import processing

# 创建一个简单的测试
print("Testing QGIS Processing...")
print("QGIS Processing module loaded successfully")
"""
    
    print("\n" + "=" * 60)
    print("测试API端点: 执行QGIS Processing代码")
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
    combined = (output + error).lower()
    
    # 检查QGIS标识
    qgis_indicators = ['qgis', 'grass', 'saga', 'processing', 'runqgis']
    uses_qgis = any(indicator in combined for indicator in qgis_indicators)
    
    if uses_qgis:
        print("✓ 使用了QGIS环境")
    else:
        print("✗ 未使用QGIS环境")
        print(f"输出: {combined[:500]}")
    
    return result.get('success') and uses_qgis


if __name__ == "__main__":
    print("=" * 60)
    print("API 代码执行端点测试")
    print("=" * 60)
    
    # 测试1: 基本执行
    print("\n[测试1] 基本代码执行")
    print("-" * 60)
    try:
        success = test_api_execute_code_endpoint()
        if success:
            print("\n✓ 测试1通过 - API正确使用QGIS环境")
        else:
            print("\n✗ 测试1失败 - API未使用QGIS环境")
    except Exception as e:
        print(f"\n✗ 测试1异常: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试2: QGIS Processing代码
    print("\n[测试2] QGIS Processing代码执行")
    print("-" * 60)
    try:
        success = test_api_execute_code_with_qgis_processing()
        if success:
            print("\n✓ 测试2通过")
        else:
            print("\n✗ 测试2失败")
    except Exception as e:
        print(f"\n✗ 测试2异常: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

