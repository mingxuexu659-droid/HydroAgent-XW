"""
数据管理 API 路由
"""
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, Response
from typing import Optional, List
import os
import json
import tempfile
import shutil
import zipfile
import requests
from datetime import datetime

from api.schemas.data import FileInfo, FileListResponse

router = APIRouter()

# An outbound proxy is optional and must be set explicitly by the deployer.
PROXY_URL = os.environ.get("AUTOGIS_PROXY_URL", "")

# 数据目录（相对于 AutoGIS_main）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_DIR = os.path.join(BASE_DIR, "output", "results")
DOWNLOADED_DIR = os.path.join(BASE_DIR, "downloaded_data")
SCRIPTS_DIR = os.path.join(BASE_DIR, "output", "generated_scripts")


def _get_file_type(ext: str) -> str:
    """获取文件类型"""
    vector_exts = [".geojson", ".json", ".shp", ".gpkg", ".gdb"]
    raster_exts = [".tif", ".tiff", ".img", ".jp2"]
    script_exts = [".py"]
    
    if ext in vector_exts:
        return "vector"
    elif ext in raster_exts:
        return "raster"
    elif ext in script_exts:
        return "script"
    else:
        return "other"


def _scan_directory(dir_path: str, url_prefix: str, type_filter: Optional[str] = None) -> list:
    """扫描目录获取文件列表"""
    files = []
    
    if not os.path.exists(dir_path):
        return files
    
    for root, dirs, filenames in os.walk(dir_path):
        for filename in filenames:
            filepath = os.path.join(root, filename)
            ext = os.path.splitext(filename)[1].lower()
            file_type = _get_file_type(ext)
            
            # 类型过滤
            if type_filter and type_filter != "all" and file_type != type_filter:
                continue
            
            # 获取相对路径
            rel_path = os.path.relpath(filepath, dir_path)
            
            # 获取修改时间
            try:
                mtime = os.path.getmtime(filepath)
                modified_at = datetime.fromtimestamp(mtime).isoformat()
            except Exception:
                modified_at = None
            
            files.append(FileInfo(
                name=filename,
                path=filepath,
                url=f"{url_prefix}/{rel_path.replace(os.sep, '/')}",
                type=file_type,
                size=os.path.getsize(filepath),
                modified_at=modified_at
            ))
    
    return files


@router.get("/files", response_model=FileListResponse, summary="获取数据文件列表")
async def list_files(
    type: Optional[str] = Query(None, description="文件类型过滤: vector, raster, script, all"),
    source: str = Query("results", description="数据源: results, downloaded, scripts")
):
    """
    获取数据文件列表
    
    - **type**: 文件类型过滤（vector, raster, script, all）
    - **source**: 数据源（results, downloaded, scripts）
    """
    source_map = {
        "results": (RESULTS_DIR, "/results"),
        "downloaded": (DOWNLOADED_DIR, "/downloaded"),
        "scripts": (SCRIPTS_DIR, "/scripts")
    }
    
    if source not in source_map:
        raise HTTPException(status_code=400, detail=f"无效的数据源: {source}")
    
    dir_path, url_prefix = source_map[source]
    files = _scan_directory(dir_path, url_prefix, type)
    
    return FileListResponse(
        total=len(files),
        files=files
    )


@router.get("/geojson/{filename:path}", summary="获取 GeoJSON 文件内容")
async def get_geojson(filename: str):
    """
    获取 GeoJSON 文件内容
    
    - **filename**: 文件名（可包含子路径）
    """
    # 在多个目录中查找
    search_dirs = [RESULTS_DIR, DOWNLOADED_DIR]
    
    for dir_path in search_dirs:
        filepath = os.path.join(dir_path, filename)
        # 安全检查：防止路径遍历
        if not os.path.abspath(filepath).startswith(os.path.abspath(dir_path)):
            continue
            
        if os.path.exists(filepath) and filepath.endswith(('.geojson', '.json')):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return JSONResponse(content=data)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="文件不是有效的JSON格式")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"读取文件失败: {str(e)}")
    
    raise HTTPException(status_code=404, detail="文件不存在")


@router.get("/download/{source}/{filename:path}", summary="下载文件")
async def download_file(source: str, filename: str):
    """
    下载数据文件
    
    - **source**: 数据源（results, downloaded, scripts）
    - **filename**: 文件名（可包含子路径）
    """
    source_map = {
        "results": RESULTS_DIR,
        "downloaded": DOWNLOADED_DIR,
        "scripts": SCRIPTS_DIR
    }
    
    if source not in source_map:
        raise HTTPException(status_code=400, detail=f"无效的数据源: {source}")
    
    dir_path = source_map[source]
    filepath = os.path.join(dir_path, filename)
    
    # 安全检查：防止路径遍历
    if not os.path.abspath(filepath).startswith(os.path.abspath(dir_path)):
        raise HTTPException(status_code=400, detail="无效的文件路径")
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return FileResponse(
        filepath,
        filename=os.path.basename(filename),
        media_type="application/octet-stream"
    )


@router.get("/preview/{source}/{filename:path}", summary="预览文件信息")
async def preview_file(source: str, filename: str):
    """
    预览文件信息（不下载完整内容）
    
    - **source**: 数据源（results, downloaded, scripts）
    - **filename**: 文件名（可包含子路径）
    """
    source_map = {
        "results": RESULTS_DIR,
        "downloaded": DOWNLOADED_DIR,
        "scripts": SCRIPTS_DIR
    }
    
    if source not in source_map:
        raise HTTPException(status_code=400, detail=f"无效的数据源: {source}")
    
    dir_path = source_map[source]
    filepath = os.path.join(dir_path, filename)
    
    # 安全检查
    if not os.path.abspath(filepath).startswith(os.path.abspath(dir_path)):
        raise HTTPException(status_code=400, detail="无效的文件路径")
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")
    
    ext = os.path.splitext(filename)[1].lower()
    file_type = _get_file_type(ext)
    
    result = {
        "name": os.path.basename(filename),
        "path": filepath,
        "type": file_type,
        "size": os.path.getsize(filepath),
        "extension": ext
    }
    
    # 对于 GeoJSON，提取额外信息
    if ext in ['.geojson', '.json']:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if data.get('type') == 'FeatureCollection':
                features = data.get('features', [])
                result['feature_count'] = len(features)
                
                if features:
                    # 获取几何类型
                    geom_types = set()
                    for f in features:
                        if f.get('geometry'):
                            geom_types.add(f['geometry'].get('type'))
                    result['geometry_types'] = list(geom_types)
                    
                    # 获取属性字段
                    if features[0].get('properties'):
                        result['properties'] = list(features[0]['properties'].keys())
        except Exception:
            pass
    
    return result


@router.post("/convert-shapefile-multi", summary="将多个 Shapefile 组件文件转换为 GeoJSON")
async def convert_shapefile_multi(files: List[UploadFile] = File(...)):
    """
    将上传的多个 Shapefile 组件文件转换为 GeoJSON
    
    - **files**: Shapefile 组件文件列表（.shp, .dbf, .shx, .prj 等）
    
    返回 GeoJSON FeatureCollection
    """
    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail="请上传文件")
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    
    try:
        # 保存所有上传的文件
        shp_file = None
        for file in files:
            if not file.filename:
                continue
            file_path = os.path.join(temp_dir, file.filename)
            with open(file_path, 'wb') as f:
                content = await file.read()
                f.write(content)
            
            if file.filename.lower().endswith('.shp'):
                shp_file = file_path
        
        if not shp_file:
            raise HTTPException(status_code=400, detail="未找到 .shp 文件")
        
        # 检查必需的文件
        base_name = os.path.splitext(shp_file)[0]
        required_files = ['.shp', '.dbf', '.shx']
        missing = []
        for ext in required_files:
            if not os.path.exists(base_name + ext):
                missing.append(ext)
        
        if missing:
            raise HTTPException(
                status_code=400, 
                detail=f"Shapefile 不完整，缺少: {', '.join(missing)}"
            )
        
        # 使用 geopandas 或 fiona 转换
        try:
            import geopandas as gpd
            
            gdf = gpd.read_file(shp_file)
            
            # 转换到 WGS-84 (EPSG:4326)
            if gdf.crs and gdf.crs != 'EPSG:4326':
                gdf = gdf.to_crs('EPSG:4326')
            
            geojson = json.loads(gdf.to_json())
            return JSONResponse(content=geojson)
            
        except ImportError:
            try:
                import fiona
                
                features = []
                with fiona.open(shp_file) as src:
                    for feature in src:
                        features.append(dict(feature))
                
                geojson = {
                    "type": "FeatureCollection",
                    "features": features
                }
                return JSONResponse(content=geojson)
                
            except ImportError:
                raise HTTPException(
                    status_code=500, 
                    detail="服务器缺少 geopandas 或 fiona 库"
                )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"转换失败: {str(e)}")
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


@router.post("/convert-shapefile", summary="将 Shapefile ZIP 转换为 GeoJSON")
async def convert_shapefile(file: UploadFile = File(...)):
    """
    将上传的 Shapefile ZIP 文件转换为 GeoJSON
    
    - **file**: 包含 Shapefile 的 ZIP 文件（必须包含 .shp, .dbf, .shx 文件）
    
    返回 GeoJSON FeatureCollection
    """
    if not file.filename or not file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="请上传 .zip 格式的文件")
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    
    try:
        # 保存上传的 ZIP 文件
        zip_path = os.path.join(temp_dir, file.filename)
        with open(zip_path, 'wb') as f:
            content = await file.read()
            f.write(content)
        
        # 解压 ZIP 文件
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="无效的 ZIP 文件")
        
        # 查找 .shp 文件
        shp_file = None
        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                if f.lower().endswith('.shp'):
                    shp_file = os.path.join(root, f)
                    break
            if shp_file:
                break
        
        if not shp_file:
            raise HTTPException(status_code=400, detail="ZIP 文件中未找到 .shp 文件")
        
        # 尝试使用 geopandas 转换
        try:
            import geopandas as gpd
            
            gdf = gpd.read_file(shp_file)
            
            # 转换到 WGS-84 (EPSG:4326) 如果不是的话
            if gdf.crs and gdf.crs != 'EPSG:4326':
                gdf = gdf.to_crs('EPSG:4326')
            
            # 转换为 GeoJSON
            geojson = json.loads(gdf.to_json())
            
            return JSONResponse(content=geojson)
            
        except ImportError:
            # 如果没有 geopandas，尝试使用 fiona
            try:
                import fiona
                from fiona.transform import transform_geom
                
                features = []
                with fiona.open(shp_file) as src:
                    src_crs = src.crs
                    
                    for feature in src:
                        # 如果不是 WGS-84，进行坐标转换
                        if src_crs and src_crs.get('init') != 'epsg:4326':
                            try:
                                feature['geometry'] = transform_geom(
                                    src_crs, 'EPSG:4326', feature['geometry']
                                )
                            except Exception:
                                pass  # 转换失败时保持原坐标
                        
                        features.append({
                            'type': 'Feature',
                            'geometry': dict(feature['geometry']),
                            'properties': dict(feature['properties'])
                        })
                
                geojson = {
                    'type': 'FeatureCollection',
                    'features': features
                }
                
                return JSONResponse(content=geojson)
                
            except ImportError:
                raise HTTPException(
                    status_code=500, 
                    detail="服务器缺少 geopandas 或 fiona 库，无法处理 Shapefile"
                )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"转换失败: {str(e)}")
    finally:
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


@router.post("/convert-geopackage", summary="将 GeoPackage 转换为 GeoJSON")
async def convert_geopackage(file: UploadFile = File(...)):
    """
    将上传的 GeoPackage (.gpkg) 文件转换为 GeoJSON
    
    - **file**: GeoPackage 文件 (.gpkg)
    
    返回 GeoJSON FeatureCollection
    """
    if not file.filename or not file.filename.lower().endswith('.gpkg'):
        raise HTTPException(status_code=400, detail="请上传 .gpkg 格式的文件")
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    
    try:
        # 保存上传的文件
        gpkg_path = os.path.join(temp_dir, file.filename)
        with open(gpkg_path, 'wb') as f:
            content = await file.read()
            f.write(content)
        
        # 方法1: 尝试使用 geopandas（更可靠）
        try:
            import geopandas as gpd
            gdf = gpd.read_file(gpkg_path)
            # 转换到 EPSG:4326
            if gdf.crs and gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs(epsg=4326)
            geojson = json.loads(gdf.to_json())
            return geojson
        except ImportError:
            pass  # geopandas 不可用，尝试其他方法
        except Exception as gpd_err:
            print(f"geopandas 读取失败: {gpd_err}，尝试 ogr2ogr")
        
        # 方法2: 使用 ogr2ogr 转换（忽略 DLL 加载警告）
        output_path = os.path.join(temp_dir, os.path.splitext(file.filename)[0] + '.geojson')
        
        qgis_root = os.environ.get('QGIS_ROOT', '')
        ogr2ogr = os.path.join(qgis_root, 'bin', 'ogr2ogr.exe') if qgis_root else ''
        
        if not os.path.exists(ogr2ogr):
            raise HTTPException(status_code=500, detail="ogr2ogr 工具未找到，且 geopandas 不可用")
        
        import subprocess
        cmd = [
            ogr2ogr,
            '-f', 'GeoJSON',
            '-t_srs', 'EPSG:4326',
            output_path,
            gpkg_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        # 只检查返回码和输出文件是否存在，忽略 stderr 中的 DLL 警告
        if result.returncode != 0:
            # 过滤掉 DLL 加载警告，只保留真正的错误
            stderr_lines = result.stderr.split('\n') if result.stderr else []
            real_errors = [line for line in stderr_lines if line.strip() and "Can't load requested DLL" not in line]
            if real_errors:
                raise HTTPException(status_code=500, detail=f"GeoPackage 转换失败: {' '.join(real_errors)}")
        
        if not os.path.exists(output_path):
            raise HTTPException(status_code=500, detail="GeoPackage 转换失败: 输出文件未生成")
        
        # 读取并返回 GeoJSON
        with open(output_path, 'r', encoding='utf-8') as f:
            geojson = json.load(f)
        
        return geojson
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"转换失败: {str(e)}")
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


@router.post("/convert-raster", summary="将上传的 GeoTIFF 转换为 Web 可显示格式")
async def convert_raster(file: UploadFile = File(...)):
    """
    将上传的 GeoTIFF 文件转换为 PNG 格式，用于 Web 地图显示
    
    - **file**: GeoTIFF 文件 (.tif, .tiff)
    
    返回:
    - url: PNG 文件的 URL
    - bounds: 地理范围 [west, south, east, north]
    - format: 文件格式 ("png")
    - name: 图层名称
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="请上传文件")
    
    filename_lower = file.filename.lower()
    if not (filename_lower.endswith('.tif') or filename_lower.endswith('.tiff')):
        raise HTTPException(status_code=400, detail="请上传 .tif 或 .tiff 格式的文件")
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    
    try:
        # 保存上传的文件
        tif_path = os.path.join(temp_dir, file.filename)
        with open(tif_path, 'wb') as f:
            content = await file.read()
            f.write(content)
        
        # 导入转换函数
        from api.routers.analysis import _convert_tif_to_png_reliable
        
        # 转换为 PNG
        result = _convert_tif_to_png_reliable(tif_path)
        
        if not result.get("success"):
            raise HTTPException(
                status_code=500, 
                detail=f"栅格转换失败: {result.get('error', '未知错误')}"
            )
        
        png_path = result.get("png_path")
        bounds = result.get("bounds")
        
        # 生成 URL
        from api.routers.analysis import _get_url_for_path
        url = _get_url_for_path(png_path)
        
        # 返回结果
        layer_name = os.path.splitext(file.filename)[0]
        
        return {
            "success": True,
            "url": url,
            "bounds": bounds,
            "format": "png",
            "name": layer_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"栅格转换失败: {str(e)}")
    finally:
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


@router.post("/convert-existing-raster", summary="转换已存在的 GeoTIFF 文件为 Web 格式")
async def convert_existing_raster(file_path: str = Form(...)):
    """
    将服务器上已存在的 GeoTIFF 文件转换为 PNG 格式，用于 Web 地图显示
    
    - **file_path**: 服务器上的 GeoTIFF 文件路径
    
    返回:
    - url: PNG 文件的 URL
    - bounds: 地理范围 [west, south, east, north]
    - format: 文件格式 ("png")
    - name: 图层名称
    """
    # 标准化路径
    file_path = file_path.replace('\\', '/')
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
    
    filename_lower = file_path.lower()
    if not (filename_lower.endswith('.tif') or filename_lower.endswith('.tiff')):
        raise HTTPException(status_code=400, detail="只支持 .tif 或 .tiff 格式的文件")
    
    try:
        # 导入转换函数
        from api.routers.analysis import _convert_tif_to_png_reliable, _get_url_for_path
        
        # 转换为 PNG
        result = _convert_tif_to_png_reliable(file_path)
        
        if not result.get("success"):
            raise HTTPException(
                status_code=500, 
                detail=f"栅格转换失败: {result.get('error', '未知错误')}"
            )
        
        png_path = result.get("png_path")
        bounds = result.get("bounds")
        
        # 生成 URL
        url = _get_url_for_path(png_path)
        
        # 提取图层名称
        layer_name = os.path.splitext(os.path.basename(file_path))[0]
        
        return {
            "success": True,
            "url": url,
            "bounds": bounds,
            "format": "png",
            "name": layer_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"栅格转换失败: {str(e)}")


# ============================================================================
# OSM 瓦片代理 - 通过本地代理访问 OpenStreetMap
# ============================================================================

# 瓦片缓存目录
TILE_CACHE_DIR = os.path.join(BASE_DIR, "output", "tile_cache")
os.makedirs(TILE_CACHE_DIR, exist_ok=True)


@router.get("/tiles/osm/{z}/{x}/{y}.png", summary="获取 OSM 瓦片（代理）")
async def get_osm_tile(z: int, x: int, y: int):
    """
    代理获取 OpenStreetMap 瓦片
    
    OSM 在国内需要代理访问，通过后端代理转发
    优化策略：
    - 本地缓存（永久保存）
    - 使用更快的 OSM 镜像站点
    - 异步请求
    """
    # 检查缓存（永久缓存，除非手动清理）
    cache_path = os.path.join(TILE_CACHE_DIR, "osm", str(z), str(x), f"{y}.png")
    if os.path.exists(cache_path):
        return FileResponse(
            cache_path, 
            media_type="image/png",
            headers={'Cache-Control': 'public, max-age=2592000'}  # 缓存30天
        )
    
    # 使用多个 OSM 镜像站点（提高成功率和速度）
    osm_urls = [
        f"https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        f"https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
        f"https://b.tile.openstreetmap.org/{z}/{x}/{y}.png",
        f"https://c.tile.openstreetmap.org/{z}/{x}/{y}.png",
    ]
    
    last_error = None
    
    # 尝试多个镜像
    for osm_url in osm_urls:
        try:
            # 使用更短的超时，快速失败
            request_kwargs = {
                'timeout': 8,
                'headers': {
                    'User-Agent': 'AutoGIS/1.0 (Educational Project)',
                    'Accept': 'image/png,image/*;q=0.9,*/*;q=0.8'
                }
            }
            if PROXY_URL:
                request_kwargs['proxies'] = {'http': PROXY_URL, 'https': PROXY_URL}
            response = requests.get(osm_url, **request_kwargs)
            
            if response.status_code == 200:
                # 缓存瓦片（异步写入，不阻塞响应）
                try:
                    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                    with open(cache_path, 'wb') as f:
                        f.write(response.content)
                except Exception:
                    pass  # 缓存失败不影响响应
                
                return Response(
                    content=response.content,
                    media_type="image/png",
                    headers={
                        'Cache-Control': 'public, max-age=2592000',  # 缓存30天
                        'Access-Control-Allow-Origin': '*'
                    }
                )
            
            last_error = f"HTTP {response.status_code}"
            
        except requests.exceptions.Timeout:
            last_error = "timeout"
            continue  # 超时立即尝试下一个镜像
        except requests.exceptions.ProxyError:
            last_error = "proxy_error"
            break  # 代理问题，不再尝试其他镜像
        except Exception as e:
            last_error = str(e)
            continue
    
    # 所有镜像都失败
    if "proxy_error" in str(last_error):
        raise HTTPException(status_code=502, detail="代理连接失败，请检查代理服务是否运行")
    else:
        raise HTTPException(status_code=504, detail=f"获取瓦片失败: {last_error}")


@router.get("/tiles/voyager/{z}/{x}/{y}.png", summary="Get CartoDB Voyager tiles (proxy with cache)")
async def get_voyager_tile(z: int, x: int, y: int):
    """
    Proxy for CartoDB Voyager tiles (OSM style with English labels)
    
    Features:
    - Local cache (permanent storage)
    - VPN proxy support for network access
    - Multiple CDN endpoints for reliability
    - Fast response with cache headers
    """
    # Check cache first (instant response if cached)
    cache_path = os.path.join(TILE_CACHE_DIR, "voyager", str(z), str(x), f"{y}.png")
    if os.path.exists(cache_path):
        return FileResponse(
            cache_path, 
            media_type="image/png",
            headers={'Cache-Control': 'public, max-age=2592000'}  # 30 days cache
        )
    
    # CartoDB CDN endpoints
    carto_urls = [
        f"https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
        f"https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
        f"https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
    ]
    
    last_error = None
    
    for carto_url in carto_urls:
        try:
            request_kwargs = {
                'timeout': 8,
                'headers': {
                    'User-Agent': 'AutoGIS/1.0 (Educational Project)',
                    'Accept': 'image/png,image/*;q=0.9,*/*;q=0.8'
                }
            }
            if PROXY_URL:
                request_kwargs['proxies'] = {'http': PROXY_URL, 'https': PROXY_URL}
            response = requests.get(carto_url, **request_kwargs)
            
            if response.status_code == 200:
                # Cache tile for future use
                try:
                    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                    with open(cache_path, 'wb') as f:
                        f.write(response.content)
                except Exception:
                    pass
                
                return Response(
                    content=response.content,
                    media_type="image/png",
                    headers={
                        'Cache-Control': 'public, max-age=2592000',
                        'Access-Control-Allow-Origin': '*'
                    }
                )
            
            last_error = f"HTTP {response.status_code}"
            
        except requests.exceptions.Timeout:
            last_error = "timeout"
            continue
        except requests.exceptions.ProxyError:
            last_error = "proxy_error"
            break  # Proxy issue, don't try other mirrors
        except Exception as e:
            last_error = str(e)
            continue
    
    if "proxy_error" in str(last_error):
        raise HTTPException(status_code=502, detail="Proxy connection failed, please check if VPN/proxy is running")
    else:
        raise HTTPException(status_code=504, detail=f"Failed to fetch tile: {last_error}")


# ============ 文档 API ============

DOCS_DIR = os.path.join(BASE_DIR, "docs")

@router.get("/docs/list", summary="获取文档列表")
async def list_docs():
    """获取 docs 目录下的所有 Markdown 文档"""
    docs = []
    
    if os.path.exists(DOCS_DIR):
        for filename in os.listdir(DOCS_DIR):
            if filename.endswith('.md'):
                filepath = os.path.join(DOCS_DIR, filename)
                docs.append({
                    "name": filename,
                    "title": filename.replace('.md', '').replace('_', ' '),
                    "path": filepath,
                    "size": os.path.getsize(filepath),
                    "modified_at": datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
                })
    
    return {"total": len(docs), "docs": docs}


@router.get("/docs/read/{filename}", summary="读取文档内容")
async def read_doc(filename: str):
    """读取指定的 Markdown 文档内容"""
    # 安全检查：防止路径遍历
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")
    
    if not filename.endswith('.md'):
        filename += '.md'
    
    filepath = os.path.join(DOCS_DIR, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"文档不存在: {filename}")
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return {
            "filename": filename,
            "content": content,
            "size": len(content),
            "lines": content.count('\n') + 1
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取文档失败: {str(e)}")
