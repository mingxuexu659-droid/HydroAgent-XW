# -*- coding: utf-8 -*-
"""
数据目录构建器模块

自动扫描指定目录，生成data_catalog.json和向量数据库。
"""

import json
import os
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import Config, get_config
from .llm_client import LLMClient


class CatalogBuilder:
    """
    数据目录构建器
    
    扫描指定目录，自动生成数据目录(data_catalog.json)和向量数据库。
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        初始化目录构建器
        
        Args:
            config: 配置对象
        """
        self.config = config or get_config()
        self.llm_client = None
        
        if self.config.data.use_llm_for_description:
            try:
                self.llm_client = LLMClient(self.config)
            except Exception as e:
                print(f"⚠️ LLM client initialization failed: {e}, will use rule-based description generation")
    
    def build_catalog(
        self,
        data_dirs: Optional[List[str]] = None,
        output_catalog_path: Optional[str] = None,
        output_vector_db_path: Optional[str] = None
    ) -> Tuple[Dict[str, Any], int]:
        """
        构建数据目录
        
        Args:
            data_dirs: 要扫描的数据目录列表，如果为None则使用配置中的目录
            output_catalog_path: 输出的catalog JSON路径
            output_vector_db_path: 输出的向量数据库路径
        
        Returns:
            (catalog_dict, file_count): 生成的目录字典和扫描到的文件数量
        """
        print(f"\n{'='*60}")
        print(f"Data Catalog Builder")
        print(f"{'='*60}")
        
        # 确定要扫描的目录
        if data_dirs is None:
            data_dirs = self.config.data.raw_data_dirs
        
        # 确定输出路径
        if output_catalog_path is None:
            output_catalog_path = self.config.data.data_catalog_path
        if output_vector_db_path is None:
            output_vector_db_path = self.config.data.vector_db_path
        
        print(f"Scanning directories: {data_dirs}")
        print(f"Output catalog: {output_catalog_path}")
        print(f"Output vector DB: {output_vector_db_path}")
        
        # 扫描文件
        all_files = self._scan_directories(data_dirs)
        print(f"\n✓ Scan completed, found {len(all_files)} GIS files")
        
        if not all_files:
            print("⚠️ No GIS files found")
            return {}, 0
        
        # 构建目录结构
        catalog = self._build_catalog_structure(all_files)
        
        # 保存目录
        self._save_catalog(catalog, output_catalog_path)
        
        # 构建向量数据库
        self._build_vector_db(catalog, output_vector_db_path)
        
        return catalog, len(all_files)
    
    def _scan_directories(self, data_dirs: List[str]) -> List[Path]:
        """
        扫描目录获取所有GIS文件
        
        Args:
            data_dirs: 数据目录列表
        
        Returns:
            文件路径列表
        """
        all_files = []
        
        # 获取支持的扩展名
        vector_exts = set(self.config.data.supported_extensions.get("vector", []))
        raster_exts = set(self.config.data.supported_extensions.get("raster", []))
        all_exts = vector_exts | raster_exts
        
        # 编译排除模式
        exclude_patterns = [re.compile(p) for p in self.config.data.exclude_patterns]
        
        for data_dir in data_dirs:
            dir_path = Path(data_dir)
            if not dir_path.exists():
                print(f"  ⚠️ Directory not found: {data_dir}")
                continue
            
            print(f"Scanning: {data_dir}")
            
            # 选择扫描方式
            if self.config.data.recursive_scan:
                file_iter = dir_path.rglob("*")
            else:
                file_iter = dir_path.glob("*")
            
            for file_path in file_iter:
                # 跳过目录
                if file_path.is_dir():
                    continue
                
                # 检查是否匹配排除模式
                should_exclude = False
                for pattern in exclude_patterns:
                    if pattern.search(str(file_path)):
                        should_exclude = True
                        break
                if should_exclude:
                    continue
                
                # 检查扩展名
                if file_path.suffix.lower() in all_exts:
                    all_files.append(file_path)
        
        return all_files
    
    def _build_catalog_structure(self, files: List[Path]) -> Dict[str, Any]:
        """
        构建目录结构
        
        Args:
            files: 文件路径列表
        
        Returns:
            目录结构字典
        """
        vector_exts = set(self.config.data.supported_extensions.get("vector", []))
        raster_exts = set(self.config.data.supported_extensions.get("raster", []))
        
        catalog = {
            "metadata": {
                "version": "1.0.0",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "total_datasets": len(files),
                "generator": "AutoGIS CatalogBuilder"
            },
            "vector_data": {
                "description": "矢量数据集合",
                "datasets": []
            },
            "raster_data": {
                "description": "栅格数据集合",
                "datasets": []
            }
        }
        
        print(f"\n Generating metadata...")
        
        for i, file_path in enumerate(files):
            suffix = file_path.suffix.lower()
            
            # 生成数据集元数据
            dataset = self._generate_dataset_metadata(file_path)
            
            # 添加到对应的类别
            if suffix in vector_exts:
                catalog["vector_data"]["datasets"].append(dataset)
            elif suffix in raster_exts:
                catalog["raster_data"]["datasets"].append(dataset)
            
            # 进度显示
            if (i + 1) % 10 == 0 or i == len(files) - 1:
                print(f"  Progress: {i+1}/{len(files)}")
        
        return catalog
    
    def _generate_dataset_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        生成单个数据集的元数据
        
        Args:
            file_path: 文件路径
        
        Returns:
            数据集元数据字典
        """
        # 生成唯一ID
        dataset_id = self._generate_id(file_path)
        
        # 基础信息
        metadata = {
            "dataset_id": dataset_id,
            "name": file_path.stem,
            "absolute_path": str(file_path.resolve()),
            "format": self._get_format_name(file_path.suffix),
            "file_size_mb": round(file_path.stat().st_size / (1024 * 1024), 2),
            "created_at": datetime.now().isoformat(),
        }
        
        # 尝试获取详细元数据
        detailed_metadata = self._extract_file_metadata(file_path)
        metadata.update(detailed_metadata)
        
        # 生成描述
        if self.llm_client and self.config.data.use_llm_for_description:
            description = self._generate_description_with_llm(metadata)
            if description:
                metadata["description"] = description
        
        if "description" not in metadata:
            metadata["description"] = self._generate_description_rule_based(metadata)
        
        return metadata
    
    def _generate_id(self, file_path: Path) -> str:
        """生成唯一ID"""
        hash_input = str(file_path.resolve())
        return hashlib.md5(hash_input.encode()).hexdigest()[:16]
    
    def _get_format_name(self, suffix: str) -> str:
        """获取格式名称"""
        format_map = {
            ".shp": "Shapefile",
            ".geojson": "GeoJSON",
            ".gpkg": "GeoPackage",
            ".gdb": "FileGDB",
            ".kml": "KML",
            ".json": "JSON",
            ".tif": "GeoTIFF",
            ".tiff": "GeoTIFF",
            ".img": "ERDAS IMG",
            ".jp2": "JPEG2000",
            ".ecw": "ECW",
            ".nc": "NetCDF",
        }
        return format_map.get(suffix.lower(), suffix.upper().replace(".", ""))
    
    def _extract_file_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        提取文件详细元数据
        
        尝试使用GDAL/OGR读取，如果失败则返回基础信息
        """
        metadata = {}
        suffix = file_path.suffix.lower()
        
        try:
            # 尝试使用GDAL读取栅格
            if suffix in [".tif", ".tiff", ".img", ".jp2", ".ecw", ".nc"]:
                metadata.update(self._extract_raster_metadata(file_path))
            # 尝试使用OGR读取矢量
            elif suffix in [".shp", ".geojson", ".gpkg", ".gdb", ".kml", ".json"]:
                metadata.update(self._extract_vector_metadata(file_path))
        except Exception as e:
            # 如果GDAL不可用，使用基础信息
            pass
        
        return metadata
    
    def _extract_raster_metadata(self, file_path: Path) -> Dict[str, Any]:
        """提取栅格元数据"""
        metadata = {}
        try:
            from osgeo import gdal
            ds = gdal.Open(str(file_path))
            if ds:
                metadata["width"] = ds.RasterXSize
                metadata["height"] = ds.RasterYSize
                metadata["band_count"] = ds.RasterCount
                
                # 获取投影
                prj = ds.GetProjection()
                if prj:
                    from osgeo import osr
                    srs = osr.SpatialReference()
                    srs.ImportFromWkt(prj)
                    auth = srs.GetAuthorityCode(None)
                    if auth:
                        metadata["crs"] = f"EPSG:{auth}"
                    else:
                        metadata["crs"] = "Unknown"
                
                # 获取范围
                gt = ds.GetGeoTransform()
                if gt:
                    minx = gt[0]
                    maxy = gt[3]
                    maxx = minx + gt[1] * ds.RasterXSize
                    miny = maxy + gt[5] * ds.RasterYSize
                    metadata["bounds"] = f"{minx:.6f}, {miny:.6f}, {maxx:.6f}, {maxy:.6f}"
                
                ds = None
        except ImportError:
            pass
        except Exception:
            pass
        
        return metadata
    
    def _extract_vector_metadata(self, file_path: Path) -> Dict[str, Any]:
        """提取矢量元数据"""
        metadata = {}
        suffix = file_path.suffix.lower()
        
        # 尝试使用geopandas
        try:
            import geopandas as gpd
            gdf = gpd.read_file(str(file_path))
            
            metadata["feature_count"] = len(gdf)
            metadata["geometry_type"] = gdf.geometry.geom_type.unique().tolist()[0] if len(gdf) > 0 else "Unknown"
            
            if gdf.crs:
                metadata["crs"] = str(gdf.crs)
            
            # 获取范围
            bounds = gdf.total_bounds
            metadata["bounds"] = f"{bounds[0]:.6f}, {bounds[1]:.6f}, {bounds[2]:.6f}, {bounds[3]:.6f}"
            
            # 获取属性字段
            non_geom_cols = [c for c in gdf.columns if c != 'geometry']
            if non_geom_cols:
                metadata["attributes"] = [{"name": c, "type": str(gdf[c].dtype)} for c in non_geom_cols[:20]]
            
        except ImportError:
            # 尝试使用OGR
            try:
                from osgeo import ogr
                ds = ogr.Open(str(file_path))
                if ds:
                    layer = ds.GetLayer(0)
                    if layer:
                        metadata["feature_count"] = layer.GetFeatureCount()
                        
                        # 获取几何类型
                        geom_type = ogr.GeometryTypeToName(layer.GetGeomType())
                        metadata["geometry_type"] = geom_type
                        
                        # 获取投影
                        srs = layer.GetSpatialRef()
                        if srs:
                            auth = srs.GetAuthorityCode(None)
                            if auth:
                                metadata["crs"] = f"EPSG:{auth}"
                        
                        # 获取范围
                        extent = layer.GetExtent()
                        if extent:
                            metadata["bounds"] = f"{extent[0]:.6f}, {extent[2]:.6f}, {extent[1]:.6f}, {extent[3]:.6f}"
                    
                    ds = None
            except ImportError:
                pass
        except Exception:
            pass
        
        # 如果是GeoJSON，尝试直接解析
        if suffix == ".geojson" and "feature_count" not in metadata:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if "features" in data:
                    metadata["feature_count"] = len(data["features"])
                    if data["features"]:
                        geom = data["features"][0].get("geometry", {})
                        metadata["geometry_type"] = geom.get("type", "Unknown")
            except Exception:
                pass
        
        return metadata
    
    def _generate_description_with_llm(self, metadata: Dict[str, Any]) -> Optional[str]:
        """使用LLM生成描述"""
        try:
            prompt = f"""Generate a concise English description (1-2 sentences) for the following GIS dataset:

File name: {metadata.get('name', 'Unknown')}
Format: {metadata.get('format', 'Unknown')}
Geometry type: {metadata.get('geometry_type', 'Unknown')}
Feature count: {metadata.get('feature_count', 'Unknown')}
Coordinate system: {metadata.get('crs', 'Unknown')}

Return the description text directly, without any other content."""
            
            response, _ = self.llm_client.chat(prompt, temperature=0.3)
            if response:
                return response.strip()
        except Exception:
            pass
        
        return None
    
    def _generate_description_rule_based(self, metadata: Dict[str, Any]) -> str:
        """基于规则生成描述"""
        name = metadata.get("name", "Unknown")
        format_name = metadata.get("format", "Unknown")
        geom_type = metadata.get("geometry_type", "")
        feature_count = metadata.get("feature_count", "")
        crs = metadata.get("crs", "")
        
        parts = [f"{name}"]
        
        if geom_type:
            parts.append(f"with {geom_type} geometry")
        
        if feature_count:
            parts.append(f"containing {feature_count} features")
        
        if crs:
            parts.append(f"in {crs}")
        
        return " ".join(parts) + f". Format: {format_name}."
    
    def _save_catalog(self, catalog: Dict[str, Any], output_path: str) -> None:
        """保存目录到JSON文件"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2)
        
        print(f"\n✓ Data catalog has been saved: {output_path}")
    
    def _build_vector_db(self, catalog: Dict[str, Any], output_path: str) -> None:
        """构建向量数据库"""
        print(f"\n🔢 Building vector database...")
        
        try:
            # 尝试导入向量数据库模块
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
            from vector_database import VectorDatabase
            from vector_embedding import VectorEmbeddingClient
            
            # 初始化（使用配置中的向量嵌入设置）
            embedding = VectorEmbeddingClient(
                api_key=self.config.vector_embedding.api_key or self.config.llm.api_key,
                api_url=self.config.vector_embedding.api_url,
                model_name=self.config.vector_embedding.model_name,
                timeout=self.config.vector_embedding.timeout
            )
            vdb = VectorDatabase(output_path)
            
            # 收集所有数据集
            all_datasets = []
            for section_name in ["vector_data", "raster_data"]:
                if section_name in catalog:
                    datasets = catalog[section_name].get("datasets", [])
                    all_datasets.extend(datasets)
            
            # 生成向量并添加到数据库
            added_count = 0
            for dataset in all_datasets:
                dataset_id = dataset.get("dataset_id", "")
                description = dataset.get("description", "")
                
                if dataset_id and description:
                    # 检查是否已存在
                    if not vdb.get_vector(dataset_id):
                        vector = embedding.embed_text(description)
                        if vector is not None:
                            vdb.add_vector(dataset_id, description, vector)
                            added_count += 1
            
            vdb._save_database()
            print(f"Vector database updated: added {added_count} vectors")
            
        except ImportError as e:
            print(f"❌ Unable to import vector database module: {e}")
        except Exception as e:
            print(f"❌ Failed to build vector database: {e}")
    
    def update_catalog(self, new_file_path: str) -> bool:
        """
        更新目录（添加单个新文件）
        
        Args:
            new_file_path: 新文件路径
        
        Returns:
            是否成功添加
        """
        file_path = Path(new_file_path)
        if not file_path.exists():
            return False
        
        # 加载现有目录
        catalog_path = Path(self.config.data.data_catalog_path)
        if catalog_path.exists():
            with open(catalog_path, 'r', encoding='utf-8') as f:
                catalog = json.load(f)
        else:
            catalog = self._build_catalog_structure([])
        
        # 生成新数据集元数据
        dataset = self._generate_dataset_metadata(file_path)
        
        # 确定类别
        vector_exts = set(self.config.data.supported_extensions.get("vector", []))
        suffix = file_path.suffix.lower()
        
        if suffix in vector_exts:
            section = "vector_data"
        else:
            section = "raster_data"
        
        # 检查是否已存在
        existing_ids = {d.get("dataset_id") for d in catalog.get(section, {}).get("datasets", [])}
        if dataset["dataset_id"] in existing_ids:
            return False
        
        # 添加到目录
        if section not in catalog:
            catalog[section] = {"description": "", "datasets": []}
        catalog[section]["datasets"].append(dataset)
        
        # 更新元数据
        catalog["metadata"]["updated_at"] = datetime.now().isoformat()
        catalog["metadata"]["total_datasets"] = sum(
            len(catalog.get(s, {}).get("datasets", [])) 
            for s in ["vector_data", "raster_data"]
        )
        
        # 保存
        self._save_catalog(catalog, str(catalog_path))
        
        # 更新向量数据库
        self._add_to_vector_db(dataset)
        
        return True
    
    def _add_to_vector_db(self, dataset: Dict[str, Any]) -> None:
        """添加单个数据集到向量数据库"""
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
            from vector_database import VectorDatabase
            from vector_embedding import VectorEmbeddingClient
            
            embedding = VectorEmbeddingClient()
            vdb = VectorDatabase(self.config.data.vector_db_path)
            
            dataset_id = dataset.get("dataset_id", "")
            description = dataset.get("description", "")
            
            if dataset_id and description:
                vector = embedding.embed_text(description)
                if vector is not None:
                    vdb.add_vector(dataset_id, description, vector)
                    vdb._save_database()
                    
        except Exception:
            pass


def build_catalog_from_config():
    """从配置文件构建目录的便捷函数"""
    config = get_config()
    builder = CatalogBuilder(config)
    return builder.build_catalog()

