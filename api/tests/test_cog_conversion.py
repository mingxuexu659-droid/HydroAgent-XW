"""
测试 GeoTIFF 到 COG 转换功能
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def test_gdal_cog_support():
    """测试 GDAL 是否支持 COG 驱动"""
    from osgeo import gdal
    
    print("\n=== 测试 GDAL COG 驱动支持 ===")
    
    # 获取 GDAL 版本
    gdal_version = gdal.__version__
    print(f"GDAL 版本: {gdal_version}")
    
    # 检查 COG 驱动是否可用
    driver = gdal.GetDriverByName('COG')
    if driver:
        print("✅ COG 驱动可用")
        metadata = driver.GetMetadata()
        print(f"   驱动元数据: {metadata}")
        return True
    else:
        print("❌ COG 驱动不可用")
        print("   建议：GDAL 3.1+ 才支持 COG 驱动")
        return False


def test_gtiff_cog_options():
    """测试使用 GTiff 驱动 + COG 选项创建 COG"""
    from osgeo import gdal
    import numpy as np
    
    print("\n=== 测试 GTiff + COG 选项 ===")
    
    # 创建测试输出目录
    output_dir = Path("output/test_cog")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建测试 TIF 文件
    test_tif = str(output_dir / "test_input.tif")
    test_cog = str(output_dir / "test_output_cog.tif")
    
    # 创建一个简单的测试栅格
    driver = gdal.GetDriverByName('GTiff')
    ds = driver.Create(test_tif, 256, 256, 1, gdal.GDT_Byte)
    
    # 设置地理变换和投影
    ds.SetGeoTransform([116.0, 0.01, 0, 40.0, 0, -0.01])  # 北京附近
    ds.SetProjection('EPSG:4326')
    
    # 写入测试数据
    band = ds.GetRasterBand(1)
    data = np.random.randint(0, 255, (256, 256), dtype=np.uint8)
    band.WriteArray(data)
    band.FlushCache()
    
    ds = None  # 关闭文件
    
    print(f"✓ 创建测试 TIF: {test_tif}")
    
    # 方法 1：尝试使用 COG 驱动
    cog_driver = gdal.GetDriverByName('COG')
    if cog_driver:
        print("\n方法 1: 使用 COG 驱动")
        try:
            src_ds = gdal.Open(test_tif)
            cog_options = [
                'COMPRESS=DEFLATE',
                'TILED=YES',
                'OVERVIEWS=AUTO'
            ]
            cog_ds = cog_driver.CreateCopy(test_cog, src_ds, options=cog_options)
            if cog_ds:
                cog_ds = None  # 关闭
                src_ds = None
                print(f"✅ COG 驱动转换成功: {test_cog}")
                
                # 验证文件
                verify_ds = gdal.Open(test_cog)
                if verify_ds:
                    print(f"   ✓ COG 文件可读")
                    print(f"   ✓ 尺寸: {verify_ds.RasterXSize} x {verify_ds.RasterYSize}")
                    print(f"   ✓ 波段数: {verify_ds.RasterCount}")
                    verify_ds = None
                    return True
                else:
                    print(f"   ❌ COG 文件无法读取")
                    return False
        except Exception as e:
            print(f"❌ COG 驱动转换失败: {e}")
    
    # 方法 2：使用 GTiff 驱动 + COG 兼容选项
    print("\n方法 2: 使用 GTiff 驱动 + COG 兼容选项")
    try:
        src_ds = gdal.Open(test_tif)
        gtiff_driver = gdal.GetDriverByName('GTiff')
        
        # COG 兼容的创建选项
        cog_options = [
            'TILED=YES',           # 必须：使用瓦片结构
            'COPY_SRC_OVERVIEWS=YES',  # 复制概览
            'COMPRESS=DEFLATE',    # 压缩
            'BLOCKXSIZE=512',      # 瓦片大小
            'BLOCKYSIZE=512'
        ]
        
        cog_ds = gtiff_driver.CreateCopy(test_cog, src_ds, options=cog_options)
        if cog_ds:
            cog_ds = None
            src_ds = None
            print(f"✅ GTiff 驱动转换成功: {test_cog}")
            
            # 验证文件
            verify_ds = gdal.Open(test_cog)
            if verify_ds:
                print(f"   ✓ COG 文件可读")
                print(f"   ✓ 尺寸: {verify_ds.RasterXSize} x {verify_ds.RasterYSize}")
                print(f"   ✓ 波段数: {verify_ds.RasterCount}")
                
                # 检查是否有瓦片结构
                metadata = verify_ds.GetMetadata('IMAGE_STRUCTURE')
                print(f"   ✓ 图像结构: {metadata}")
                
                verify_ds = None
                return True
            else:
                print(f"   ❌ COG 文件无法读取")
                return False
    except Exception as e:
        print(f"❌ GTiff 驱动转换失败: {e}")
        return False


def test_convert_sentinel_to_cog():
    """测试转换真实的 Sentinel-2 文件到 COG"""
    from osgeo import gdal
    
    print("\n=== 测试转换真实 Sentinel-2 文件 ===")
    
    # 检查是否存在 Sentinel-2 文件
    sentinel_files = [
        "downloaded_data/北京_sentinel_2_202510_202601_clipped.tif",
        "output/results/北京_sentinel_ndvi.tif"
    ]
    
    for sentinel_tif in sentinel_files:
        if not os.path.exists(sentinel_tif):
            print(f"⚠️  文件不存在，跳过: {sentinel_tif}")
            continue
        
        print(f"\n处理: {Path(sentinel_tif).name}")
        
        # 检查原始文件
        src_ds = gdal.Open(sentinel_tif)
        if not src_ds:
            print(f"   ❌ 无法打开原始文件")
            continue
        
        print(f"   ✓ 原始文件可读")
        print(f"   ✓ 尺寸: {src_ds.RasterXSize} x {src_ds.RasterYSize}")
        print(f"   ✓ 波段数: {src_ds.RasterCount}")
        
        # 获取地理范围
        gt = src_ds.GetGeoTransform()
        width = src_ds.RasterXSize
        height = src_ds.RasterYSize
        
        west = gt[0]
        north = gt[3]
        east = west + width * gt[1]
        south = north + height * gt[5]
        
        print(f"   ✓ 范围: [{west:.4f}, {south:.4f}, {east:.4f}, {north:.4f}]")
        
        src_ds = None
        
        # 转换为 COG
        output_dir = Path("output/test_cog")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        cog_path = str(output_dir / f"{Path(sentinel_tif).stem}_cog.tif")
        
        # 尝试方法 1: COG 驱动
        cog_driver = gdal.GetDriverByName('COG')
        success = False
        
        if cog_driver:
            print(f"   尝试使用 COG 驱动...")
            try:
                src_ds = gdal.Open(sentinel_tif)
                cog_options = ['COMPRESS=DEFLATE', 'TILED=YES', 'OVERVIEWS=AUTO']
                cog_ds = cog_driver.CreateCopy(cog_path, src_ds, options=cog_options)
                if cog_ds:
                    cog_ds = None
                    src_ds = None
                    
                    # 验证
                    verify_ds = gdal.Open(cog_path)
                    if verify_ds:
                        print(f"   ✅ COG 转换成功: {Path(cog_path).name}")
                        verify_ds = None
                        success = True
            except Exception as e:
                print(f"   ❌ COG 驱动失败: {e}")
        
        # 尝试方法 2: GTiff 驱动
        if not success:
            print(f"   尝试使用 GTiff 驱动...")
            try:
                src_ds = gdal.Open(sentinel_tif)
                gtiff_driver = gdal.GetDriverByName('GTiff')
                cog_options = [
                    'TILED=YES',
                    'COMPRESS=DEFLATE',
                    'BLOCKXSIZE=512',
                    'BLOCKYSIZE=512'
                ]
                cog_ds = gtiff_driver.CreateCopy(cog_path, src_ds, options=cog_options)
                if cog_ds:
                    cog_ds = None
                    src_ds = None
                    
                    # 验证
                    verify_ds = gdal.Open(cog_path)
                    if verify_ds:
                        print(f"   ✅ GTiff 转换成功: {Path(cog_path).name}")
                        verify_ds = None
                        success = True
            except Exception as e:
                print(f"   ❌ GTiff 驱动失败: {e}")
        
        if not success:
            print(f"   ❌ 所有转换方法均失败")


if __name__ == "__main__":
    print("=" * 60)
    print("GeoTIFF 到 COG 转换测试")
    print("=" * 60)
    
    # 测试 1: 检查 COG 驱动支持
    cog_supported = test_gdal_cog_support()
    
    # 测试 2: 测试 GTiff + COG 选项
    test_gtiff_cog_options()
    
    # 测试 3: 测试真实文件转换
    test_convert_sentinel_to_cog()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

