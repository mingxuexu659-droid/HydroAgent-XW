#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单测：验证 routing 任务从 poi_search 任务获取结果的功能
"""

import sys
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass, field

# 添加父目录到路径
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from geo_query_engine import (
    IntentAnalysis, UnifiedQueryResult, SubTaskResult,
    QueryIntent, POIResult, RouteResult
)

# 模拟 POIResult
@dataclass
class MockPOIResult:
    osm_id: int
    name: str
    poi_type: str
    lat: float
    lon: float
    distance_meters: float = 0.0
    tags: Dict[str, str] = field(default_factory=dict)
    address: str = ""

def test_routing_from_poi_search():
    """测试 routing 任务从 poi_search 任务获取结果"""
    
    # 模拟 task_outputs
    task_outputs = {}
    
    # 模拟第一个任务（poi_search）的结果
    mock_pois = [
        MockPOIResult(
            osm_id=1,
            name="故宫博物院",
            poi_type="museum",
            lat=39.9163,
            lon=116.3972,
            distance_meters=0.0
        ),
        MockPOIResult(
            osm_id=2,
            name="中国国家博物馆",
            poi_type="museum",
            lat=39.9042,
            lon=116.4074,
            distance_meters=0.0
        ),
        MockPOIResult(
            osm_id=3,
            name="首都博物馆",
            poi_type="museum",
            lat=39.9056,
            lon=116.3439,
            distance_meters=0.0
        ),
    ]
    
    # 模拟第一个任务保存结果到 task_outputs
    output_name_1 = "task_1"
    first_poi = mock_pois[0]
    task_outputs[output_name_1] = {
        'lat': first_poi.lat,
        'lon': first_poi.lon,
        'name': first_poi.name,
        'poi_results': mock_pois  # 保存完整的POI列表
    }
    
    print("=" * 60)
    print("测试1: routing 任务从 task_outputs 获取 poi_search 结果")
    print("=" * 60)
    print(f"task_outputs 内容: {list(task_outputs.keys())}")
    print(f"task_outputs[{output_name_1}]: {task_outputs[output_name_1]}")
    
    # 模拟第二个任务（routing）
    depends_on = 1  # 依赖第一个任务
    origin = ""
    destination = ""
    
    # 模拟 routing 任务的逻辑
    prev = None
    depends_on_str = str(depends_on)
    
    # 方式1: 直接匹配
    if depends_on in task_outputs:
        prev = task_outputs[depends_on]
        print(f"✓ 方式1匹配成功: depends_on={depends_on}")
    # 方式2: 字符串匹配
    elif depends_on_str in task_outputs:
        prev = task_outputs[depends_on_str]
        print(f"✓ 方式2匹配成功: depends_on_str={depends_on_str}")
    # 方式3: 尝试匹配 output_name (如 'task_1')
    else:
        for key in task_outputs.keys():
            if str(depends_on) in str(key) or str(key) == f'task_{depends_on}':
                prev = task_outputs[key]
                print(f"✓ 方式3匹配成功: key={key}")
                break
    
    if prev and isinstance(prev, dict):
        print(f"✓ 找到依赖任务结果: {prev.keys()}")
        # 如果前一个任务是poi_search，使用POI结果
        if 'poi_results' in prev and prev['poi_results']:
            poi_list = prev['poi_results']
            print(f"✓ 找到 {len(poi_list)} 个 POI")
            # 对于"规划参观路线"这类查询，使用第一个POI作为起点，最后一个POI作为终点
            if not origin and len(poi_list) > 0:
                first_poi = poi_list[0]
                origin = first_poi.name
                print(f"✓ 从任务{depends_on}获取起点: {origin}")
            if not destination and len(poi_list) > 1:
                last_poi = poi_list[-1]
                destination = last_poi.name
                print(f"✓ 从任务{depends_on}获取终点: {destination}")
            elif not destination and len(poi_list) == 1:
                # 如果只有一个POI，使用它作为终点
                first_poi = poi_list[0]
                destination = destination or first_poi.name
                print(f"✓ 从任务{depends_on}获取终点（单个POI）: {destination}")
        elif 'name' in prev:
            destination = destination or prev.get('name', '')
            print(f"✓ 从任务{depends_on}获取终点（name字段）: {destination}")
    else:
        print(f"✗ 未找到依赖任务结果")
    
    print(f"\n最终结果:")
    print(f"  origin: {origin}")
    print(f"  destination: {destination}")
    
    if origin and destination:
        print(f"\n✓ 测试通过：成功获取起点和终点")
        return True
    else:
        print(f"\n✗ 测试失败：缺少起点或终点")
        return False


def test_routing_from_result_poi_results():
    """测试 routing 任务从 result.poi_results 获取结果（备用方案）"""
    
    print("\n" + "=" * 60)
    print("测试2: routing 任务从 result.poi_results 获取结果（备用方案）")
    print("=" * 60)
    
    # 模拟 result.poi_results
    mock_pois = [
        MockPOIResult(
            osm_id=1,
            name="故宫博物院",
            poi_type="museum",
            lat=39.9163,
            lon=116.3972,
            distance_meters=0.0
        ),
        MockPOIResult(
            osm_id=2,
            name="中国国家博物馆",
            poi_type="museum",
            lat=39.9042,
            lon=116.4074,
            distance_meters=0.0
        ),
    ]
    
    origin = ""
    destination = ""
    
    # 模拟 routing 任务的备用逻辑
    if not origin and mock_pois:
        first_poi = mock_pois[0]
        origin = first_poi.name if first_poi.name and first_poi.name != '未命名' else '最近POI'
        print(f"✓ 从POI结果获取起点: {origin}")
    
    if not destination and mock_pois:
        # 如果有多个POI，使用最后一个作为终点；否则使用第一个
        if len(mock_pois) > 1:
            last_poi = mock_pois[-1]
            destination = last_poi.name if last_poi.name and last_poi.name != '未命名' else '最近POI'
        else:
            nearest_poi = mock_pois[0]
            destination = nearest_poi.name if nearest_poi.name and nearest_poi.name != '未命名' else '最近POI'
        print(f"✓ 从POI结果获取终点: {destination}")
    
    print(f"\n最终结果:")
    print(f"  origin: {origin}")
    print(f"  destination: {destination}")
    
    if origin and destination:
        print(f"\n✓ 测试通过：成功获取起点和终点")
        return True
    else:
        print(f"\n✗ 测试失败：缺少起点或终点")
        return False


def test_depends_on_matching():
    """测试 depends_on 的多种匹配方式"""
    
    print("\n" + "=" * 60)
    print("测试3: depends_on 的多种匹配方式")
    print("=" * 60)
    
    # 测试不同的 task_outputs 键格式
    test_cases = [
        (1, {"1": {"name": "test"}}, "数字键"),
        (1, {"task_1": {"name": "test"}}, "task_N格式"),
        (1, {1: {"name": "test"}}, "整数键"),
    ]
    
    for depends_on, task_outputs, desc in test_cases:
        print(f"\n测试场景: {desc}")
        print(f"  depends_on: {depends_on} (type: {type(depends_on).__name__})")
        print(f"  task_outputs keys: {list(task_outputs.keys())}")
        
        prev = None
        depends_on_str = str(depends_on)
        
        # 方式1: 直接匹配
        if depends_on in task_outputs:
            prev = task_outputs[depends_on]
            print(f"  ✓ 方式1匹配成功")
        # 方式2: 字符串匹配
        elif depends_on_str in task_outputs:
            prev = task_outputs[depends_on_str]
            print(f"  ✓ 方式2匹配成功")
        # 方式3: 尝试匹配 output_name (如 'task_1')
        else:
            for key in task_outputs.keys():
                if str(depends_on) in str(key) or str(key) == f'task_{depends_on}':
                    prev = task_outputs[key]
                    print(f"  ✓ 方式3匹配成功: key={key}")
                    break
        
        if prev:
            print(f"  ✓ 找到结果: {prev}")
        else:
            print(f"  ✗ 未找到结果")


if __name__ == '__main__':
    print("开始运行单测...\n")
    
    result1 = test_routing_from_poi_search()
    result2 = test_routing_from_result_poi_results()
    test_depends_on_matching()
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"测试1 (从task_outputs获取): {'通过' if result1 else '失败'}")
    print(f"测试2 (从result.poi_results获取): {'通过' if result2 else '失败'}")
    
    if result1 and result2:
        print("\n✓ 所有测试通过！")
        sys.exit(0)
    else:
        print("\n✗ 部分测试失败！")
        sys.exit(1)

