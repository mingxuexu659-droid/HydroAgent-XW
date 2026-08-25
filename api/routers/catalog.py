"""
数据目录 API 路由
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import os
import json

from api.schemas.data import CatalogEntry, CatalogResponse, CatalogSearchRequest

router = APIRouter()

# 数据目录文件路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CATALOG_PATH = os.path.join(BASE_DIR, "data", "data_catalog.json")


def _load_catalog() -> list:
    """加载数据目录"""
    if not os.path.exists(CATALOG_PATH):
        return []
    
    try:
        with open(CATALOG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        all_datasets = []
        
        # 处理不同格式的目录文件
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # 新格式：包含 vector_data 和 raster_data
            if 'vector_data' in data and isinstance(data['vector_data'], dict):
                vector_data = data['vector_data']
                # datasets 数组
                datasets = vector_data.get('datasets', [])
                for ds in datasets:
                    ds['data_category'] = 'vector'
                all_datasets.extend(datasets)
                
                # points 数组（也是矢量数据）
                points = vector_data.get('points', [])
                for ds in points:
                    ds['data_category'] = 'vector'
                all_datasets.extend(points)
                
                # lines 数组（也是矢量数据）
                lines = vector_data.get('lines', [])
                for ds in lines:
                    ds['data_category'] = 'vector'
                all_datasets.extend(lines)
                
                # polygons 数组（也是矢量数据）
                polygons = vector_data.get('polygons', [])
                for ds in polygons:
                    ds['data_category'] = 'vector'
                all_datasets.extend(polygons)
            
            if 'raster_data' in data and isinstance(data['raster_data'], dict):
                raster_data = data['raster_data']
                # datasets 数组
                datasets = raster_data.get('datasets', [])
                for ds in datasets:
                    ds['data_category'] = 'raster'
                all_datasets.extend(datasets)
                
                # imagery 数组（也是栅格数据）
                imagery = raster_data.get('imagery', [])
                for ds in imagery:
                    ds['data_category'] = 'raster'
                all_datasets.extend(imagery)
            
            # 旧格式：直接有 datasets 字段
            if 'datasets' in data and isinstance(data['datasets'], list):
                all_datasets.extend(data['datasets'])
            
            return all_datasets
        else:
            return []
    except Exception as e:
        print(f"加载数据目录失败: {e}")
        return []


def _entry_to_model(entry: dict, idx: int) -> CatalogEntry:
    """将目录条目转换为模型"""
    # 解析 bounds - 可能是字符串或数组 (bbox)
    bounds = entry.get('bounds') or entry.get('bbox')
    if isinstance(bounds, str):
        try:
            bounds = [float(x.strip()) for x in bounds.split(',')]
        except:
            bounds = None
    elif isinstance(bounds, list) and len(bounds) == 4:
        try:
            bounds = [float(x) for x in bounds]
        except:
            bounds = None
    
    # 提取属性名称
    attributes = entry.get('attributes', [])
    attr_names = []
    for attr in attributes:
        if isinstance(attr, dict):
            attr_names.append(attr.get('name', ''))
        elif isinstance(attr, str):
            attr_names.append(attr)
    
    # 获取名称 - 优先使用 name，然后是 file_name，最后是 file
    name = entry.get('name') or entry.get('file_name') or entry.get('file', 'Unknown')
    
    # 获取文件路径 - 优先使用 absolute_path，然后是 file
    file_path = entry.get('absolute_path') or entry.get('file', '')
    
    # 处理几何类型 - 标准化显示
    geometry_type = entry.get('geometry_type')
    if geometry_type:
        # 标准化几何类型名称
        geom_normalize_map = {
            'Unknown (any)': 'Geometry',
            'Unknown': 'Geometry', 
            'None': 'Geometry',
            'Mixed': 'Geometry',
            '3D Point': 'Point',
            '3D Line String': 'LineString',
            '3D Polygon': 'Polygon',
            '3D Multi Point': 'MultiPoint',
            '3D Multi Line String': 'MultiLineString',
            '3D Multi Polygon': 'MultiPolygon',
            'Multi Point': 'MultiPoint',
            'Multi Line String': 'MultiLineString',
            'Multi Polygon': 'MultiPolygon',
            'Line String': 'LineString',
        }
        geometry_type = geom_normalize_map.get(geometry_type, geometry_type)
    
    # 栅格数据没有几何类型
    if entry.get('data_category') == 'raster' or entry.get('format', '').lower() in ['geotiff', 'tif', 'tiff']:
        geometry_type = 'Raster'
    
    return CatalogEntry(
        id=entry.get('dataset_id', entry.get('id', f"dataset_{idx}")),
        name=name,
        file_path=file_path,
        file_type=entry.get('format', 'unknown'),
        geometry_type=geometry_type,
        crs=entry.get('crs'),
        feature_count=entry.get('feature_count'),
        description=entry.get('description', entry.get('ai_description', '')),
        attributes=attr_names,
        bounds=bounds,
        file_size_mb=entry.get('file_size_mb'),
        created_at=entry.get('created_at'),
        data_category=entry.get('data_category', 'vector')
    )


@router.get("", response_model=CatalogResponse, summary="获取数据目录")
async def get_catalog(
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    type: Optional[str] = Query(None, description="数据类型过滤: vector, raster")
):
    """
    获取数据目录
    
    - **limit**: 返回数量限制
    - **offset**: 偏移量
    - **type**: 数据类型过滤
    """
    catalog = _load_catalog()
    
    # 类型过滤
    if type:
        type_lower = type.lower()
        if type_lower == 'vector':
            catalog = [e for e in catalog if e.get('format', '').lower() in ['geojson', 'shp', 'gpkg', 'gdb', 'shapefile', 'geopackage']]
        elif type_lower == 'raster':
            catalog = [e for e in catalog if e.get('format', '').lower() in ['tif', 'tiff', 'img', 'jp2', 'geotiff', 'cog']]
    
    total = len(catalog)
    catalog = catalog[offset:offset + limit]
    
    entries = [_entry_to_model(e, i) for i, e in enumerate(catalog)]
    
    return CatalogResponse(
        total=total,
        entries=entries
    )


@router.get("/{entry_id}", response_model=CatalogEntry, summary="获取数据目录条目")
async def get_catalog_entry(entry_id: str):
    """
    获取指定的数据目录条目
    
    - **entry_id**: 数据ID
    """
    catalog = _load_catalog()
    
    for i, entry in enumerate(catalog):
        if entry.get('id') == entry_id or entry.get('file') == entry_id:
            return _entry_to_model(entry, i)
    
    raise HTTPException(status_code=404, detail="数据条目不存在")


@router.post("/search", response_model=CatalogResponse, summary="搜索数据目录")
async def search_catalog(request: CatalogSearchRequest):
    """
    搜索数据目录
    
    - **query**: 搜索关键词
    - **type**: 数据类型过滤
    - **limit**: 返回数量限制
    """
    catalog = _load_catalog()
    query_lower = request.query.lower()
    
    # 搜索匹配
    matched = []
    for entry in catalog:
        # 在名称、描述、文件路径中搜索
        searchable = ' '.join([
            entry.get('name', ''),
            entry.get('description', ''),
            entry.get('ai_description', ''),
            entry.get('file', ''),
            entry.get('geometry_type', '')
        ]).lower()
        
        if query_lower in searchable:
            matched.append(entry)
    
    # 类型过滤
    if request.type:
        type_lower = request.type.lower()
        if type_lower == 'vector':
            matched = [e for e in matched if e.get('format', '').lower() in ['geojson', 'shp', 'gpkg', 'gdb', 'shapefile', 'geopackage']]
        elif type_lower == 'raster':
            matched = [e for e in matched if e.get('format', '').lower() in ['tif', 'tiff', 'img', 'jp2', 'geotiff', 'cog']]
    
    # 限制数量
    total = len(matched)
    matched = matched[:request.limit]
    
    entries = [_entry_to_model(e, i) for i, e in enumerate(matched)]
    
    return CatalogResponse(
        total=total,
        entries=entries
    )


@router.get("/stats/summary", summary="获取数据目录统计")
async def get_catalog_stats():
    """
    获取数据目录统计信息
    """
    catalog = _load_catalog()
    
    # 统计各类型数量
    vector_formats = ['geojson', 'shp', 'gpkg', 'gdb', 'shapefile', 'geopackage']
    raster_formats = ['tif', 'tiff', 'img', 'jp2', 'geotiff', 'cog']
    
    vector_count = sum(1 for e in catalog if e.get('format', '').lower() in vector_formats)
    raster_count = sum(1 for e in catalog if e.get('format', '').lower() in raster_formats)
    other_count = len(catalog) - vector_count - raster_count
    
    # 统计几何类型（标准化后）
    geometry_types = {}
    geom_normalize_map = {
        'Unknown (any)': 'Geometry',
        'Unknown': 'Geometry', 
        'None': 'Geometry',
        'Mixed': 'Geometry',
        '3D Point': 'Point',
        '3D Line String': 'LineString',
        '3D Polygon': 'Polygon',
        '3D Multi Point': 'MultiPoint',
        '3D Multi Line String': 'MultiLineString',
        '3D Multi Polygon': 'MultiPolygon',
        'Multi Point': 'MultiPoint',
        'Multi Line String': 'MultiLineString',
        'Multi Polygon': 'MultiPolygon',
        'Line String': 'LineString',
    }
    for entry in catalog:
        geom_type = entry.get('geometry_type', 'Geometry')
        # 标准化
        geom_type = geom_normalize_map.get(geom_type, geom_type)
        # 栅格数据标记为 Raster
        if entry.get('data_category') == 'raster' or entry.get('format', '').lower() in ['geotiff', 'tif', 'tiff']:
            geom_type = 'Raster'
        geometry_types[geom_type] = geometry_types.get(geom_type, 0) + 1
    
    return {
        "total": len(catalog),
        "by_type": {
            "vector": vector_count,
            "raster": raster_count,
            "other": other_count
        },
        "by_geometry": geometry_types
    }

