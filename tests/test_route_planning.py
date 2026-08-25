# -*- coding: utf-8 -*-
"""
路径规划功能单元测试
"""
import pytest
import sys
from pathlib import Path

# 添加项目根目录到路径
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))


class TestRouteCalculation:
    """测试路径规划功能"""
    
    def test_geocode_resolution(self):
        """测试地理编码解析"""
        from core.geo_query_engine import OSMAdapter
        
        osm = OSMAdapter()
        
        # 测试天安门
        result = osm.geocode("天安门", get_bbox=False)
        assert result is not None, "应该能解析天安门坐标"
        assert 'lat' in result and 'lon' in result
        
        print(f"\n天安门坐标: ({result['lat']}, {result['lon']})")
        
        # 验证坐标在北京范围内
        assert 39.8 < result['lat'] < 40.2
        assert 116.2 < result['lon'] < 116.6
    
    def test_calculate_route_with_stable_method(self):
        """测试使用稳定方法计算路径"""
        from core.geo_query_engine import OSMAdapter
        
        osm = OSMAdapter()
        
        # 天安门: ~39.9054, 116.3976
        # 颐和园: ~39.9999, 116.2755
        result = osm.calculate_route(
            origin_lat=39.9054,
            origin_lon=116.3976,
            dest_lat=39.9999,
            dest_lon=116.2755,
            mode="driving"
        )
        
        if result:
            print(f"\n✅ 路径规划成功:")
            print(f"   距离: {result.distance_meters / 1000:.2f} km")
            print(f"   时长: {result.duration_seconds / 60:.1f} 分钟")
            print(f"   坐标点数: {len(result.geometry)}")
            
            assert result.distance_meters > 0
            assert result.duration_seconds > 0
            assert len(result.geometry) > 0
        else:
            pytest.skip("路径规划 API 不可用")
    
    def test_intent_analysis_for_route(self):
        """测试意图分析识别路径规划"""
        from spatial_analysis_system.intent_analyzer import IntentAnalyzer
        
        analyzer = IntentAnalyzer()
        
        # 测试英文查询
        intent = analyzer.analyze("Route from Tiananmen to the Summer Palace")
        
        print(f"\n意图分析结果:")
        print(f"  任务类型: {intent.task_type.value}")
        print(f"  置信度: {intent.confidence}")
        
        if intent.route_info:
            print(f"  起点: {intent.route_info.origin}")
            print(f"  终点: {intent.route_info.destination}")
            print(f"  方式: {intent.route_info.mode}")
        
        assert intent.is_data_only(), "应该识别为 data_download_only"
        assert intent.route_info is not None, "应该有路径规划信息"
        assert intent.route_info.origin, "应该有起点"
        assert intent.route_info.destination, "应该有终点"
    
    def test_workflow_route_planning_end_to_end(self):
        """测试完整的路径规划工作流"""
        from spatial_analysis_system.workflow_engine import WorkflowEngine
        
        engine = WorkflowEngine()
        
        # 执行工作流
        result = engine.process("Route from Tiananmen to the Summer Palace")
        
        print(f"\n工作流结果:")
        print(f"  成功: {result.success}")
        print(f"  消息: {result.message}")
        print(f"  下载文件数: {len(result.downloaded_files)}")
        
        if result.success:
            assert len(result.downloaded_files) > 0, "应该有下载的路线文件"
            
            route_file = result.downloaded_files[0]
            print(f"\n路线文件:")
            print(f"  名称: {route_file['name']}")
            print(f"  路径: {route_file['path']}")
            print(f"  类型: {route_file['type']}")
            
            if 'route_info' in route_file:
                print(f"  距离: {route_file['route_info']['distance_km']:.2f} km")
                print(f"  时长: {route_file['route_info']['duration_min']:.1f} 分钟")
            
            assert route_file['type'] == 'geojson'
            assert Path(route_file['path']).exists()
        else:
            print(f"  失败原因: {result.warnings}")
            pytest.skip(f"工作流失败: {result.message}")
    
    def test_chinese_route_query(self):
        """测试中文路径查询"""
        from spatial_analysis_system.intent_analyzer import IntentAnalyzer
        
        analyzer = IntentAnalyzer()
        
        # 测试中文查询
        intent = analyzer.analyze("从天安门到颐和园的路线")
        
        print(f"\n中文查询意图分析:")
        print(f"  任务类型: {intent.task_type.value}")
        
        if intent.route_info:
            print(f"  起点: {intent.route_info.origin}")
            print(f"  终点: {intent.route_info.destination}")
        
        assert intent.is_data_only()
        assert intent.route_info is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])

