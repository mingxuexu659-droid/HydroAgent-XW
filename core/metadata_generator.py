#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
元数据生成器模块

提供元数据生成功能，严格参考 generate_data_catalog_enhanced.py 的方法：
1. 为不同类型的文件生成元数据
2. 使用LLM生成英文描述
3. 构建data_summary用于prompt
"""

from pathlib import Path
from typing import Dict, Any, Optional, List

# 字段类型推断规则（从generate_data_catalog_enhanced.py复制）
FIELD_TYPE_MAPPING = {
    "Integer": "integer",
    "Integer64": "integer",
    "Real": "float",
    "String": "string",
    "Date": "date",
    "DateTime": "datetime",
    "Time": "time",
    "Binary": "binary",
    "IntegerList": "integer_list",
    "RealList": "float_list",
    "StringList": "string_list"
}

FIELD_ROLE_PATTERNS = {
    "id": ["id", "fid", "gid", "objectid", "feature_id", "uid", "uuid", "code"],
    "label": ["name", "label", "title", "description", "desc", "caption"],
    "measure": ["count", "total", "sum", "avg", "mean", "min", "max", "value", "amount", "rate", "ratio", "percent", "area", "length", "perimeter", "population", "gdp", "elevation", "height", "depth", "weight", "size", "score", "index"],
    "category": ["type", "class", "category", "group", "status", "level", "grade", "rank", "kind"],
    "time": ["date", "time", "datetime", "timestamp", "year", "month", "day", "created", "updated", "modified"],
    "geometry": ["x", "y", "z", "lat", "lon", "latitude", "longitude", "easting", "northing", "coord"]
}


class MetadataGenerator:
    """元数据生成器"""
    
    def __init__(self, llm_client=None):
        """
        初始化元数据生成器
        
        Args:
            llm_client: LLM客户端，用于生成描述
        """
        self.llm_client = llm_client
    
    def generate_metadata_for_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        为文件生成元数据（使用generate_data_catalog_enhanced.py的方法）
        
        Args:
            file_path: 文件路径
            
        Returns:
            元数据字典
        """
        try:
            # 根据文件类型调用相应的元数据生成方法
            suffix = file_path.suffix.lower()
            
            if suffix == '.geojson':
                # GeoJSON文件 - 使用vector_data的方法
                return self._generate_vector_metadata(file_path)
            elif suffix == '.tif' or suffix == '.tiff':
                # 栅格文件
                return self._generate_raster_metadata(file_path)
            elif suffix == '.shp':
                # Shapefile
                return self._generate_shapefile_metadata(file_path)
            elif suffix == '.gpkg':
                # GeoPackage
                return self._generate_geopackage_metadata(file_path)
            else:
                # 其他格式，使用简单方法
                return self._generate_simple_metadata(file_path)
                
        except Exception as e:
            print(f"   ⚠️ Exception generating metadata: {e}")
            return self._generate_simple_metadata(file_path)
    
    def _generate_vector_metadata(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """生成矢量数据元数据"""
        try:
            # 尝试导入GDAL
            try:
                from osgeo import ogr
                ds = ogr.Open(str(file_path))
                if ds:
                    layer = ds.GetLayer(0)
                    if layer:
                        raw_geom_type = layer.GetGeomType()
                        geom_type = ogr.GeometryTypeToName(raw_geom_type)
                        feature_count = layer.GetFeatureCount()
                        
                        # 🔧 修复：更精确的几何类型名称映射
                        geom_type_map = {
                            'Unknown (any)': 'Geometry',
                            'Unknown': 'Geometry',
                            'None': 'Geometry',
                            '3D Point': 'Point',
                            '3D Line String': 'LineString',
                            '3D Polygon': 'Polygon',
                            '3D Multi Point': 'MultiPoint',
                            '3D Multi Line String': 'MultiLineString',
                            '3D Multi Polygon': 'MultiPolygon',
                            'Measured Point': 'Point',
                            'Measured Line String': 'LineString',
                            'Measured Polygon': 'Polygon',
                        }
                        geom_type = geom_type_map.get(geom_type, geom_type)
                        
                        # 如果仍然是 Unknown，尝试从第一个要素推断
                        if geom_type in ['Geometry', 'Unknown', 'None', '']:
                            layer.ResetReading()
                            feat = layer.GetNextFeature()
                            if feat:
                                geom = feat.GetGeometryRef()
                                if geom:
                                    actual_type = geom.GetGeometryName()
                                    if actual_type:
                                        geom_type = actual_type.replace('MULTI', 'Multi ').replace('LINESTRING', 'LineString').replace('POLYGON', 'Polygon').replace('POINT', 'Point').strip()
                                        # 标准化名称
                                        geom_type = geom_type.replace('Multi ', 'Multi')
                            layer.ResetReading()
                        
                        # 根据几何类型确定category
                        category_map = {
                            'Point': 'points',
                            'MultiPoint': 'points',
                            'LineString': 'lines',
                            'MultiLineString': 'lines',
                            'Polygon': 'polygons',
                            'MultiPolygon': 'polygons',
                        }
                        category = category_map.get(geom_type, 'polygons')
                        
                        # 获取CRS
                        srs = layer.GetSpatialRef()
                        crs = "EPSG:4326"
                        if srs:
                            epsg_code = srs.GetAuthorityCode(None)
                            if epsg_code:
                                crs = f"EPSG:{epsg_code}"
                        
                        # 获取extent（使用与generate_data_catalog_enhanced.py相同的分类方法）
                        extent = layer.GetExtent()
                        bbox = None
                        extent_type = "unknown"
                        if extent:
                            min_x, max_x, min_y, max_y = extent
                            bbox = [min_x, min_y, max_x, max_y]
                            # 使用与generate_data_catalog_enhanced.py相同的分类逻辑
                            if (max_x - min_x) > 100:
                                extent_type = "global"
                            elif 5 <= min_x <= 18 and 44 <= min_y <= 52:
                                extent_type = "europe_central"
                            elif 5 <= min_x <= 30 and 35 <= min_y <= 70:
                                extent_type = "europe"
                            else:
                                extent_type = "local"
                        
                        # 构建属性元数据（使用字段类型映射和角色推断规则）
                        attributes = []
                        layer_defn = layer.GetLayerDefn()
                        
                        def _infer_field_type(ogr_type_name: str) -> str:
                            """从 OGR 类型推断通用类型"""
                            return FIELD_TYPE_MAPPING.get(ogr_type_name, "string")
                        
                        def _infer_field_roles(field_name: str) -> List[str]:
                            """根据字段名推断角色"""
                            roles = []
                            name_lower = field_name.lower()
                            for role, patterns in FIELD_ROLE_PATTERNS.items():
                                for pattern in patterns:
                                    if pattern in name_lower:
                                        roles.append(role)
                                        break
                            return roles if roles else ["unknown"]
                        
                        for i in range(layer_defn.GetFieldCount()):
                            field_defn = layer_defn.GetFieldDefn(i)
                            field_name = field_defn.GetName()
                            ogr_type = field_defn.GetTypeName()
                            
                            attributes.append({
                                "name": field_name,
                                "type": _infer_field_type(ogr_type),
                                "role": _infer_field_roles(field_name)
                            })
                        
                        ds = None
                        
                        metadata = {
                            "name": file_path.stem.replace('_', ' ').title(),
                            "absolute_path": str(file_path.absolute()),
                            "file_name": file_path.name,
                            "format": "GeoJSON",
                            "category": category,
                            "geometry_type": geom_type,
                            "crs": crs,
                            "feature_count": feature_count,
                            "extent": extent_type,
                            "bbox": bbox,
                            "attributes": attributes,
                            "relations": []
                        }
                        
                        # 生成description（使用LLM）
                        if self.llm_client:
                            description = self._generate_description_with_llm(metadata)
                            if description:
                                metadata["description"] = description
                        
                        return metadata
            except ImportError:
                pass
            
            # 如果没有GDAL，使用简单方法
            return self._generate_simple_metadata(file_path)
            
        except Exception as e:
            print(f"   ⚠️ Exception generating vector metadata: {e}")
            return self._generate_simple_metadata(file_path)
    
    def _generate_raster_metadata(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """生成栅格数据元数据"""
        try:
            try:
                from osgeo import gdal, osr
                ds = gdal.Open(str(file_path))
                if ds:
                    # 根据文件名推断category
                    filename_lower = file_path.name.lower()
                    if 'dem' in filename_lower or 'elevation' in filename_lower:
                        category = 'dem'
                    elif 'slope' in filename_lower or 'aspect' in filename_lower or 'hillshade' in filename_lower:
                        category = 'terrain'
                    elif 'sentinel' in filename_lower or 'landsat' in filename_lower or 'imagery' in filename_lower or 'rgb' in filename_lower:
                        category = 'imagery'
                    elif 'temp' in filename_lower or 'precip' in filename_lower or 'climate' in filename_lower:
                        category = 'climate'
                    elif 'timeseries' in filename_lower or 'time_series' in filename_lower:
                        category = 'timeseries'
                    else:
                        category = 'imagery'  # 默认分类为imagery
                    
                    metadata = {
                        "name": file_path.stem.replace('_', ' ').title(),
                        "absolute_path": str(file_path.absolute()),
                        "file_name": file_path.name,
                        "format": "GeoTIFF",
                        "category": category,
                        "crs": "EPSG:4326",
                        "extent": "unknown",
                        "bbox": None,
                        "width": ds.RasterXSize,
                        "height": ds.RasterYSize,
                        "bands": ds.RasterCount,
                        "pixel_size": None
                    }
                    
                    # 获取CRS
                    srs = ds.GetProjectionRef()
                    if srs:
                        spatial_ref = osr.SpatialReference(srs)
                        epsg_code = spatial_ref.GetAuthorityCode(None)
                        if epsg_code:
                            metadata["crs"] = f"EPSG:{epsg_code}"
                    
                    # 获取地理变换和边界框
                    geotransform = ds.GetGeoTransform()
                    if geotransform:
                        metadata["pixel_size"] = [abs(geotransform[1]), abs(geotransform[5])]
                        min_x = geotransform[0]
                        max_y = geotransform[3]
                        max_x = min_x + geotransform[1] * ds.RasterXSize
                        min_y = max_y + geotransform[5] * ds.RasterYSize
                        metadata["bbox"] = [min_x, min_y, max_x, max_y]
                        # 使用与generate_data_catalog_enhanced.py相同的extent分类
                        if (max_x - min_x) > 100:
                            metadata["extent"] = "global"
                        elif 5 <= min_x <= 18 and 44 <= min_y <= 52:
                            metadata["extent"] = "europe_central"
                        elif 5 <= min_x <= 30 and 35 <= min_y <= 70:
                            metadata["extent"] = "europe"
                        else:
                            metadata["extent"] = "local"
                    
                    ds = None
                    
                    # 生成description
                    if self.llm_client:
                        description = self._generate_description_with_llm(metadata)
                        if description:
                            metadata["description"] = description
                    
                    return metadata
            except ImportError:
                pass
            
            return self._generate_simple_metadata(file_path)
            
        except Exception as e:
            print(f"   ⚠️ Exception generating raster metadata: {e}")
            return self._generate_simple_metadata(file_path)
    
    def _generate_shapefile_metadata(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """生成Shapefile元数据"""
        # 简化处理，使用简单方法
        return self._generate_simple_metadata(file_path)
    
    def _generate_geopackage_metadata(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """生成GeoPackage元数据"""
        # 简化处理，使用简单方法
        return self._generate_simple_metadata(file_path)
    
    def _generate_simple_metadata(self, file_path: Path) -> Dict[str, Any]:
        """生成简单的元数据（当无法使用GDAL时）"""
        suffix = file_path.suffix.lower()
        format_map = {
            '.geojson': 'GeoJSON',
            '.tif': 'GeoTIFF',
            '.tiff': 'GeoTIFF',
            '.shp': 'Shapefile',
            '.gpkg': 'GeoPackage'
        }
        
        metadata = {
            "name": file_path.stem.replace('_', ' ').title(),
            "absolute_path": str(file_path.absolute()),
            "file_name": file_path.name,
            "format": format_map.get(suffix, suffix[1:].upper() if suffix else 'Unknown'),
            "category": "unknown",
            "description": f"This is a geographic data file: {file_path.name}"
        }
        
        # 尝试生成更好的description
        if self.llm_client:
            description = self._generate_description_with_llm(metadata)
            if description:
                metadata["description"] = description
        
        return metadata
    
    def _build_data_summary(self, metadata: Dict[str, Any]) -> str:
        """
        构建data_summary，严格参考generate_data_catalog_enhanced.py的_build_prompt方法
        
        Args:
            metadata: 元数据字典
            
        Returns:
            data_summary字符串
        """
        parts = []
        
        # 文件名和路径
        file_name = metadata.get("name", "")
        file_name_value = metadata.get("file_name", "")
        if file_name:
            parts.append(f"File name: {file_name}")
        if file_name_value:
            parts.append(f"File name (actual): {file_name_value}")
        
        # 格式和类别
        file_format = metadata.get("format", "")
        category = metadata.get("category", "")
        if file_format:
            parts.append(f"Data format: {file_format}")
        if category:
            parts.append(f"Data category: {category}")
        
        # 几何类型（如果是矢量）
        geometry_type = metadata.get("geometry_type", "")
        if geometry_type and geometry_type != "Unknown":
            parts.append(f"Geometry type: {geometry_type}")
        
        # 要素数量
        feature_count = metadata.get("feature_count", 0)
        if feature_count > 0:
            parts.append(f"Feature count: {feature_count}")
        
        # 坐标系
        crs = metadata.get("crs", "")
        if crs:
            parts.append(f"Coordinate system: {crs}")
        
        # 空间范围
        extent = metadata.get("extent", "")
        bbox = metadata.get("bbox")
        if extent and extent != "unknown":
            parts.append(f"Spatial extent: {extent}")
        if bbox:
            parts.append(f"Bounding box: {bbox}")
        
        # 栅格特有字段
        width = metadata.get("width", 0)
        height = metadata.get("height", 0)
        bands = metadata.get("bands", 0)
        if width > 0 and height > 0:
            parts.append(f"Raster size: {width} x {height} pixels")
        if bands > 0:
            parts.append(f"Number of bands: {bands}")
        
        # 属性字段（只列出字段名和类型，不猜测含义）
        attributes = metadata.get("attributes", [])
        if attributes:
            attr_list = []
            for attr in attributes[:10]:  # 限制字段数量
                attr_name = attr.get("name", "")
                attr_type = attr.get("type", "")
                if attr_name:
                    attr_list.append(f"{attr_name}({attr_type})")
            if attr_list:
                parts.append(f"Attribute fields: {', '.join(attr_list)}")
        
        # 表格特有字段
        row_count = metadata.get("row_count", 0)
        columns = metadata.get("columns", [])
        if row_count > 0:
            parts.append(f"Row count: {row_count}")
        if columns:
            parts.append(f"Columns: {', '.join(columns[:10])}")
        
        # 构建完整的data_summary
        return "\n".join(parts)
    
    def _generate_description_with_llm(self, metadata: Dict[str, Any]) -> Optional[str]:
        """
        使用LLM生成description（英文），严格参考generate_data_catalog_enhanced.py的方法
        
        Args:
            metadata: 元数据字典
            
        Returns:
            生成的英文描述
        """
        if not self.llm_client:
            return None
        
        try:
            # 构建data_summary
            data_summary = self._build_data_summary(metadata)
            
            # 使用与generate_data_catalog_enhanced.py完全相同的prompt格式
            prompt = f"""Please generate a concise and accurate English description (50-200 words) based on the following data file metadata.

Requirements:
1. Only use the provided information, do not add content that does not exist
2. The description should include: data type, purpose, and main characteristics
3. Do not guess the specific content or source of the data
4. If information is insufficient, only describe the known parts

Data file information:
{data_summary}

Please generate the description:"""
            
            response = self.llm_client.chat(prompt)
            if response:
                return response.strip()
        except Exception as e:
            print(f"   ⚠️ LLM failed to generate description: {e}")
        
        return None
    
    def add_metadata_to_catalog(self, metadata: Dict[str, Any], catalog_path):
        """
        将元数据添加到catalog JSON文件
        
        Args:
            metadata: 元数据字典
            catalog_path: catalog文件路径（可以是Path对象或字符串）
        """
        try:
            import json
            from datetime import datetime as dt
            
            # 🔧 修复：确保catalog_path是Path对象
            if isinstance(catalog_path, str):
                catalog_path = Path(catalog_path)
            elif not isinstance(catalog_path, Path):
                print(f"   ⚠️ catalog_path type error: {type(catalog_path)}")
                return
            
            # 检查文件是否存在
            if not catalog_path.exists():
                print(f"   ⚠️ catalog file does not exist: {catalog_path}")
                return
            
            # 加载现有catalog
            with open(catalog_path, 'r', encoding='utf-8') as f:
                catalog = json.load(f)
            
            # 确定应该添加到哪个section
            format_type = metadata.get('format', '').lower()
            category = metadata.get('category', '')
            
            # 根据格式和类别确定section
            if format_type == 'geojson':
                section = 'vector_data'
                if category in ['points', 'lines', 'polygons']:
                    if category not in catalog.get(section, {}):
                        catalog[section] = catalog.get(section, {})
                        catalog[section][category] = []
                    catalog[section][category].append(metadata)
                else:
                    # 默认添加到points
                    if 'points' not in catalog.get(section, {}):
                        catalog[section] = catalog.get(section, {})
                        catalog[section]['points'] = []
                    catalog[section]['points'].append(metadata)
            elif format_type in ['geotiff', 'tif', 'tiff']:
                section = 'raster_data'
                # 🔧 修复：确保raster_data有标准结构
                if section not in catalog:
                    catalog[section] = {
                        "description": "栅格数据集合",
                        "datasets": [],
                        "dem": [],
                        "terrain": [],
                        "imagery": [],
                        "climate": [],
                        "timeseries": [],
                        "unknown": []
                    }
                
                # 确定更精确的category
                # 根据文件名推断更准确的category
                filename_lower = metadata.get('file_name', '').lower()
                if 'dem' in filename_lower or 'elevation' in filename_lower:
                    category = 'dem'
                elif 'slope' in filename_lower or 'aspect' in filename_lower or 'hillshade' in filename_lower:
                    category = 'terrain'
                elif 'sentinel' in filename_lower or 'landsat' in filename_lower or 'imagery' in filename_lower or 'rgb' in filename_lower:
                    category = 'imagery'
                elif 'temp' in filename_lower or 'precip' in filename_lower or 'climate' in filename_lower:
                    category = 'climate'
                elif 'timeseries' in filename_lower or 'time_series' in filename_lower:
                    category = 'timeseries'
                elif category not in ['dem', 'terrain', 'imagery', 'climate', 'timeseries']:
                    category = 'unknown'  # 不确定类型的放到unknown
                
                # 确保该category存在
                if category not in catalog[section]:
                    catalog[section][category] = []
                
                # 添加metadata
                catalog[section][category].append(metadata)
            elif format_type == 'shapefile':
                section = 'shapefile_data'
                if section not in catalog:
                    catalog[section] = []
                catalog[section].append(metadata)
            elif format_type == 'geopackage':
                section = 'geopackage_data'
                if section not in catalog:
                    catalog[section] = []
                catalog[section].append(metadata)
            else:
                # 默认添加到vector_data.points
                section = 'vector_data'
                if 'points' not in catalog.get(section, {}):
                    catalog[section] = catalog.get(section, {})
                    catalog[section]['points'] = []
                catalog[section]['points'].append(metadata)
            
            # 更新统计信息
            if 'metadata' in catalog:
                catalog['metadata']['total_files'] = catalog['metadata'].get('total_files', 0) + 1
                catalog['metadata']['generated_at'] = dt.now().isoformat()
            
            # 保存catalog
            with open(catalog_path, 'w', encoding='utf-8') as f:
                json.dump(catalog, f, ensure_ascii=False, indent=2)
            
            print(f"   ✓ Saved to catalog: {catalog_path.name}")
            
        except Exception as e:
            import traceback
            print(f"   ⚠️ Failed to add to catalog: {e}")
            print(f"   ⚠️ Detailed error: {traceback.format_exc()}")
    
    def file_exists_in_catalog(self, absolute_path: str, catalog_path) -> bool:
        """
        检查文件是否已存在于catalog中
        
        Args:
            absolute_path: 文件的绝对路径
            catalog_path: catalog文件路径（可以是Path对象或字符串）
            
        Returns:
            如果存在返回True，否则返回False
        """
        try:
            import json
            
            # 🔧 修复：确保catalog_path是Path对象
            if isinstance(catalog_path, str):
                catalog_path = Path(catalog_path)
            elif not isinstance(catalog_path, Path):
                print(f"   ⚠️ catalog_path type error: {type(catalog_path)}")
                return False
            
            if not catalog_path.exists():
                return False
            
            with open(catalog_path, 'r', encoding='utf-8') as f:
                catalog = json.load(f)
            
            # 遍历所有section查找该文件
            sections_to_check = [
                catalog.get('vector_data', {}).get('points', []),
                catalog.get('vector_data', {}).get('lines', []),
                catalog.get('vector_data', {}).get('polygons', []),
                catalog.get('raster_data', {}).get('dem', []),
                catalog.get('raster_data', {}).get('imagery', []),
                catalog.get('raster_data', {}).get('climate', []),
                catalog.get('raster_data', {}).get('timeseries', []),
                catalog.get('shapefile_data', []),
                catalog.get('geopackage_data', []),
                catalog.get('gps_data', []),
                catalog.get('table_data', [])
            ]
            
            for section_list in sections_to_check:
                for item in section_list:
                    if item.get('absolute_path', '') == absolute_path:
                        return True
            
            return False
        except Exception as e:
            print(f"   ⚠️ Error checking if file exists: {e}")
            return False

    def update_description_in_catalog(self, absolute_path: str, new_description: str, catalog_path) -> bool:
        """
        更新catalog中指定文件的description字段
        
        Args:
            absolute_path: 文件的绝对路径
            new_description: 新的描述
            catalog_path: catalog文件路径
            
        Returns:
            如果更新成功返回True，否则返回False
        """
        try:
            import json
            
            if isinstance(catalog_path, str):
                catalog_path = Path(catalog_path)
            
            if not catalog_path.exists():
                return False
            
            with open(catalog_path, 'r', encoding='utf-8') as f:
                catalog = json.load(f)
            
            # 遍历所有section查找并更新该文件
            sections_to_check = [
                ('vector_data', 'points'),
                ('vector_data', 'lines'),
                ('vector_data', 'polygons'),
                ('raster_data', 'dem'),
                ('raster_data', 'imagery'),
                ('raster_data', 'climate'),
                ('raster_data', 'timeseries'),
            ]
            
            updated = False
            for main_key, sub_key in sections_to_check:
                if main_key in catalog and sub_key in catalog[main_key]:
                    for item in catalog[main_key][sub_key]:
                        if item.get('absolute_path', '') == absolute_path:
                            item['description'] = new_description
                            updated = True
                            break
                if updated:
                    break
            
            # 检查其他顶级列表
            for key in ['shapefile_data', 'geopackage_data', 'gps_data', 'table_data']:
                if key in catalog:
                    for item in catalog[key]:
                        if item.get('absolute_path', '') == absolute_path:
                            item['description'] = new_description
                            updated = True
                            break
                if updated:
                    break
            
            if updated:
                with open(catalog_path, 'w', encoding='utf-8') as f:
                    json.dump(catalog, f, ensure_ascii=False, indent=2)
            
            return updated
        except Exception as e:
            print(f"   ⚠️ Error updating description: {e}")
            return False

