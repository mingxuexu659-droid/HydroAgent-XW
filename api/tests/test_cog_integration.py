"""
COG 转换集成测试 - 测试完整的 API 流程
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def test_convert_to_cog():
    """测试 _convert_to_cog 函数"""
    from api.routers.analysis import _convert_to_cog
    
    print("\n=== 测试 _convert_to_cog 函数 ===")
    
    # 测试文件
    test_files = [
        "downloaded_data/北京_sentinel_2_202510_202601_clipped.tif",
        "output/results/北京_sentinel_ndvi.tif"
    ]
    
    for tif_path in test_files:
        if not os.path.exists(tif_path):
            print(f"⚠️  文件不存在，跳过: {tif_path}")
            continue
        
        print(f"\n处理: {Path(tif_path).name}")
        
        # 调用 _convert_to_cog
        result = _convert_to_cog(tif_path)
        
        if result.get("success"):
            cog_path = result.get("cog_path")
            bounds = result.get("bounds")
            
            print(f"✅ 转换成功")
            print(f"   COG 路径: {cog_path}")
            print(f"   范围: {bounds}")
            
            # 验证文件存在且可读
            if os.path.exists(cog_path):
                from osgeo import gdal
                ds = gdal.Open(cog_path)
                if ds:
                    print(f"   ✓ COG 文件可读")
                    print(f"   ✓ 尺寸: {ds.RasterXSize} x {ds.RasterYSize}")
                    print(f"   ✓ 波段数: {ds.RasterCount}")
                    ds = None
                else:
                    print(f"   ❌ COG 文件无法打开")
            else:
                print(f"   ❌ COG 文件不存在")
        else:
            error = result.get("error", "未知错误")
            print(f"❌ 转换失败: {error}")


def test_convert_to_web_format():
    """测试 _convert_to_web_format 函数"""
    from api.routers.analysis import _convert_to_web_format
    
    print("\n=== 测试 _convert_to_web_format 函数 ===")
    
    # 测试文件
    test_files = [
        "downloaded_data/北京_sentinel_2_202510_202601_clipped.tif",
        "output/results/北京_sentinel_ndvi.tif"
    ]
    
    for tif_path in test_files:
        if not os.path.exists(tif_path):
            print(f"⚠️  文件不存在，跳过: {tif_path}")
            continue
        
        print(f"\n处理: {Path(tif_path).name}")
        
        # 调用 _convert_to_web_format
        result = _convert_to_web_format(tif_path)
        
        if result.get("success"):
            output_path = result.get("path")
            file_type = result.get("type")
            web_compatible = result.get("web_compatible")
            bounds = result.get("bounds")
            format_type = result.get("format")
            message = result.get("message")
            
            print(f"✅ {message}")
            print(f"   输出路径: {output_path}")
            print(f"   类型: {file_type}")
            print(f"   Web 兼容: {web_compatible}")
            print(f"   格式: {format_type}")
            print(f"   范围: {bounds}")
            
            # 验证文件
            if os.path.exists(output_path):
                from osgeo import gdal
                ds = gdal.Open(output_path)
                if ds:
                    print(f"   ✓ 文件可读")
                    ds = None
                else:
                    print(f"   ❌ 文件无法打开")
            else:
                print(f"   ❌ 文件不存在")
        else:
            message = result.get("message", "未知错误")
            print(f"❌ 转换失败: {message}")


def test_get_url_for_path():
    """测试 _get_url_for_path 函数"""
    from api.routers.analysis import _get_url_for_path
    
    print("\n=== 测试 _get_url_for_path 函数 ===")
    
    # 测试路径
    test_paths = [
        "output/cog_cache/北京_sentinel_2_202510_202601_clipped_cog.tif",
        "output/cog_cache/北京_sentinel_ndvi_cog.tif",
        "downloaded_data/boundaries/boundary_北京.geojson"
    ]
    
    for path in test_paths:
        url = _get_url_for_path(path)
        print(f"\n路径: {Path(path).name}")
        print(f"URL: {url}")


if __name__ == "__main__":
    print("=" * 60)
    print("COG 转换集成测试")
    print("=" * 60)
    
    # 测试 1: _convert_to_cog
    test_convert_to_cog()
    
    # 测试 2: _convert_to_web_format
    test_convert_to_web_format()
    
    # 测试 3: _get_url_for_path
    test_get_url_for_path()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

