"""数据管理相关的数据模型"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class FileInfo(BaseModel):
    """文件信息模型"""
    name: str = Field(..., description="文件名")
    path: str = Field(..., description="文件路径")
    url: str = Field(..., description="访问URL")
    type: str = Field(..., description="文件类型: vector, raster, other")
    size: int = Field(..., description="文件大小(字节)")
    modified_at: Optional[str] = Field(None, description="修改时间")


class FileListResponse(BaseModel):
    """文件列表响应模型"""
    total: int = Field(..., description="文件总数")
    files: List[FileInfo] = Field(..., description="文件列表")


class CatalogEntry(BaseModel):
    """数据目录条目模型"""
    id: str = Field(..., description="数据ID")
    name: str = Field(..., description="数据名称")
    file_path: str = Field(..., description="文件路径")
    file_type: str = Field(..., description="文件类型")
    geometry_type: Optional[str] = Field(None, description="几何类型")
    crs: Optional[str] = Field(None, description="坐标系")
    feature_count: Optional[int] = Field(None, description="要素数量")
    description: Optional[str] = Field(None, description="描述")
    attributes: Optional[List[str]] = Field(None, description="属性字段列表")
    bounds: Optional[List[float]] = Field(None, description="边界范围 [minx, miny, maxx, maxy]")
    file_size_mb: Optional[float] = Field(None, description="文件大小(MB)")
    created_at: Optional[str] = Field(None, description="创建时间")
    data_category: Optional[str] = Field(None, description="数据类别: vector, raster")


class CatalogResponse(BaseModel):
    """数据目录响应模型"""
    total: int = Field(..., description="数据集总数")
    entries: List[CatalogEntry] = Field(..., description="数据目录条目列表")


class CatalogSearchRequest(BaseModel):
    """数据目录搜索请求模型"""
    query: str = Field(..., description="搜索关键词", min_length=1)
    type: Optional[str] = Field(None, description="数据类型过滤: vector, raster")
    limit: int = Field(10, ge=1, le=100, description="返回数量限制")


class GeoJSONResponse(BaseModel):
    """GeoJSON 响应模型"""
    type: str = Field("FeatureCollection", description="GeoJSON类型")
    features: List[Dict[str, Any]] = Field(..., description="要素列表")
    crs: Optional[Dict[str, Any]] = Field(None, description="坐标系信息")

