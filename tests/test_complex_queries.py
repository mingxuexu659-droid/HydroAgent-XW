#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试复杂查询用例
"""

import sys
from pathlib import Path

# 导入查询引擎
sys.path.insert(0, str(Path(__file__).parent.parent))
from AutoGIS_main.data_retrieval_and_search import VectorLocalFirstGeoQueryEngine

def test_query(query: str):
    """测试单个查询"""
    print(f"\n{'='*70}")
    print(f"📝 查询: {query}")
    print(f"{'='*70}\n")
    
    try:
        # 初始化引擎
        engine = VectorLocalFirstGeoQueryEngine(
            catalog_path='data_catalog_test.json',
            output_dir='downloaded_data'
        )
        
        # 执行查询
        result = engine.query(query)
        
        # 格式化输出
        print(engine.format_result(result))
        
        return True
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    # 测试用例
    test_cases = [
        "查询北京的博物馆，然后规划参观路线",
        "分析故宫内的设施类型，然后规划一条参观路线",
        "找出故宫附近的咖啡店，并规划步行路线",
    ]
    
    print("🧪 复杂查询测试")
    print("="*70)
    
    success_count = 0
    for query in test_cases:
        if test_query(query):
            success_count += 1
    
    print(f"\n{'='*70}")
    print(f"📊 测试汇总: {success_count}/{len(test_cases)} 通过")
    print(f"{'='*70}")

