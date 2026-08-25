"""
测试 GeoTIFF COG 方案

这个测试验证后端能正确处理 GeoTIFF 文件并返回正确的 URL 和边界信息
"""
import pytest
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.routers.analysis import _get_tif_bounds, _convert_to_web_format, _get_url_for_path


class TestGeoTiffBounds:
    """测试获取 GeoTIFF 边界"""
    
    def test_get_tif_bounds_with_real_file(self):
        """测试从真实 TIF 文件获取边界"""
        # 使用项目中已有的 TIF 文件
        tif_path = "downloaded_data/北京_sentinel_2_202510_202601_clipped.tif"
        
        if os.path.exists(tif_path):
            bounds = _get_tif_bounds(tif_path)
            
            assert bounds is not None, "bounds 不应为 None"
            assert len(bounds) == 4, "bounds 应该是 [west, south, east, north]"
            
            west, south, east, north = bounds
            print(f"📍 TIF 边界: west={west}, south={south}, east={east}, north={north}")
            
            # 验证边界值合理性（北京的经纬度范围大约是 115-118, 39-41）
            assert 100 < west < 130, f"west 应在中国范围内: {west}"
            assert 100 < east < 130, f"east 应在中国范围内: {east}"
            assert 30 < south < 50, f"south 应在中国范围内: {south}"
            assert 30 < north < 50, f"north 应在中国范围内: {north}"
            assert west < east, "west 应小于 east"
            assert south < north, "south 应小于 north"
        else:
            pytest.skip(f"测试文件不存在: {tif_path}")
    
    def test_get_tif_bounds_nonexistent_file(self):
        """测试不存在的文件"""
        bounds = _get_tif_bounds("/nonexistent/path/file.tif")
        # 应该返回 None 而不是抛出异常
        assert bounds is None


class TestConvertToWebFormat:
    """测试文件格式转换"""
    
    def test_convert_geotiff_returns_geotiff_format(self):
        """测试 GeoTIFF 文件返回正确格式"""
        tif_path = "downloaded_data/北京_sentinel_2_202510_202601_clipped.tif"
        
        if os.path.exists(tif_path):
            result = _convert_to_web_format(tif_path)
            
            print(f"🔍 转换结果: {result}")
            
            assert result["success"] == True, "转换应该成功"
            assert result["type"] == "raster", "类型应该是 raster"
            assert result["web_compatible"] == True, "应该是 web 兼容的"
            assert result.get("format") == "geotiff", "格式应该是 geotiff"
            assert result.get("bounds") is not None, "应该有边界信息"
            
            # 验证 path 是原始路径
            assert result["path"] == tif_path, "path 应该是原始 TIF 路径"
        else:
            pytest.skip(f"测试文件不存在: {tif_path}")
    
    def test_convert_geojson_returns_vector(self):
        """测试 GeoJSON 文件返回正确格式"""
        geojson_path = "downloaded_data/boundaries/boundary_北京.geojson"
        
        if os.path.exists(geojson_path):
            result = _convert_to_web_format(geojson_path)
            
            print(f"🔍 转换结果: {result}")
            
            assert result["success"] == True, "转换应该成功"
            assert result["type"] == "vector", "类型应该是 vector"
        else:
            pytest.skip(f"测试文件不存在: {geojson_path}")


class TestUrlGeneration:
    """测试 URL 生成"""
    
    def test_url_for_downloaded_tif(self):
        """测试 downloaded_data 目录下的 TIF 文件 URL"""
        path = "downloaded_data/北京_sentinel.tif"
        url = _get_url_for_path(path)
        
        print(f"📎 URL: {url}")
        
        assert url.startswith("/downloaded/"), f"URL 应以 /downloaded/ 开头: {url}"
        assert "sentinel" in url.lower(), "URL 应包含文件名"
    
    def test_url_for_results_tif(self):
        """测试 output/results 目录下的 TIF 文件 URL"""
        path = "output/results/ndvi_result.tif"
        url = _get_url_for_path(path)
        
        print(f"📎 URL: {url}")
        
        assert url.startswith("/results/"), f"URL 应以 /results/ 开头: {url}"
        assert "ndvi" in url.lower(), "URL 应包含文件名"
    
    def test_url_encoding_chinese(self):
        """测试中文文件名的 URL 编码"""
        path = "downloaded_data/北京_sentinel_2.tif"
        url = _get_url_for_path(path)
        
        print(f"📎 URL (encoded): {url}")
        
        # URL 应该是编码过的
        assert "%" in url, "中文文件名应该被 URL 编码"
        assert url.endswith(".tif"), "URL 应以 .tif 结尾"


class TestIntegration:
    """集成测试"""
    
    def test_full_pipeline(self):
        """测试完整流程：获取边界 -> 格式转换 -> URL 生成"""
        tif_path = "downloaded_data/北京_sentinel_2_202510_202601_clipped.tif"
        
        if not os.path.exists(tif_path):
            pytest.skip(f"测试文件不存在: {tif_path}")
        
        # 1. 获取边界
        bounds = _get_tif_bounds(tif_path)
        assert bounds is not None, "应该能获取边界"
        print(f"1️⃣ 边界: {bounds}")
        
        # 2. 格式转换
        convert_result = _convert_to_web_format(tif_path)
        assert convert_result["success"], "转换应该成功"
        assert convert_result["format"] == "geotiff", "格式应该是 geotiff"
        print(f"2️⃣ 转换结果: {convert_result}")
        
        # 3. 生成 URL
        url = _get_url_for_path(tif_path)
        assert url, "应该能生成 URL"
        print(f"3️⃣ URL: {url}")
        
        # 验证最终结果
        print(f"\n✅ 完整流程测试通过")
        print(f"   - 边界: {bounds}")
        print(f"   - 格式: {convert_result['format']}")
        print(f"   - URL: {url}")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])

