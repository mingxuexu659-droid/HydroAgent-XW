"""
分析任务 API 路由
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from typing import Optional, List
from pydantic import BaseModel, Field
import uuid
from pathlib import Path

from api.schemas.analysis import (
    AnalysisRequest, TaskResponse, TaskListResponse,
    CodeResponse, TaskResultResponse, TaskStatusEnum
)
from api.services.task_manager import get_task_manager

router = APIRouter()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PNG_CACHE_DIR = PROJECT_ROOT / "output" / "png_cache"
COG_CACHE_DIR = PROJECT_ROOT / "output" / "cog_cache"


def _task_to_response(task: dict) -> TaskResponse:
    """将内部任务转换为响应模型"""
    # 🔧 兼容历史缓存：downloaded_files 可能是 str 列表或 dict 列表
    downloaded_files_raw = task.get("downloaded_files", []) or []
    downloaded_files: list = []
    if isinstance(downloaded_files_raw, list):
        for item in downloaded_files_raw:
            if isinstance(item, dict):
                downloaded_files.append(item)
            elif isinstance(item, str):
                downloaded_files.append({"path": item})
            else:
                downloaded_files.append({"value": item})
    elif isinstance(downloaded_files_raw, dict):
        downloaded_files = [downloaded_files_raw]
    else:
        downloaded_files = [{"value": downloaded_files_raw}]

    return TaskResponse(
        task_id=task["task_id"],
        status=TaskStatusEnum(task["status"].value if hasattr(task["status"], "value") else task["status"]),
        message=task["message"],
        created_at=task["created_at"],
        updated_at=task.get("updated_at"),
        progress=task["progress"],
        current_step=task.get("current_step"),
        output_files=task.get("output_files", []),
        logs=task.get("logs", []),
        script_path=task.get("script_path"),
        code=task.get("code"),
        task_type=task.get("task_type"),
        downloaded_files=downloaded_files
    )


@router.post("/submit", response_model=TaskResponse, summary="提交分析任务")
async def submit_analysis(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks
):
    """
    提交一个新的空间分析任务
    
    - **query**: 用户的分析需求描述
    - **skip_download**: 是否跳过数据下载步骤
    - **auto_run**: 是否自动运行生成的脚本
    - **auto_optimize**: 失败时是否自动优化代码
    - **max_optimization_rounds**: 最大优化轮数
    
    返回任务ID，可通过 WebSocket 或轮询获取进度
    """
    task_manager = get_task_manager()
    task_id = str(uuid.uuid4())
    
    # 创建任务
    task = task_manager.create_task(task_id, request.model_dump())
    
    # 后台执行任务
    background_tasks.add_task(
        task_manager.execute_task,
        task_id,
        request.query,
        request.skip_download,
        request.auto_run,
        request.auto_optimize,
        request.max_optimization_rounds
    )
    
    return _task_to_response(task)


@router.get("/task/{task_id}", response_model=TaskResponse, summary="获取任务状态")
async def get_task_status(task_id: str):
    """
    获取指定任务的当前状态
    
    - **task_id**: 任务ID
    """
    task_manager = get_task_manager()
    task = task_manager.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return _task_to_response(task)


@router.get("/tasks", response_model=TaskListResponse, summary="获取任务列表")
async def list_tasks(
    limit: int = Query(20, ge=1, le=100, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量")
):
    """
    获取任务列表
    
    - **limit**: 返回数量限制(1-100)
    - **offset**: 偏移量
    """
    task_manager = get_task_manager()
    tasks = task_manager.list_tasks(limit, offset)
    total = task_manager.count_tasks()
    
    return TaskListResponse(
        total=total,
        tasks=[_task_to_response(t) for t in tasks]
    )


@router.delete("/task/{task_id}", summary="取消任务")
async def cancel_task(task_id: str):
    """
    取消指定任务
    
    - **task_id**: 任务ID
    
    注意：只有处于 pending 或 analyzing 状态的任务可以取消
    """
    task_manager = get_task_manager()
    task = task_manager.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    success = task_manager.cancel_task(task_id)
    if not success:
        raise HTTPException(
            status_code=400, 
            detail="任务无法取消，可能已经完成或正在执行"
        )
    
    return {"message": "任务已取消", "task_id": task_id}


@router.get("/task/{task_id}/code", response_model=CodeResponse, summary="获取生成的代码")
async def get_generated_code(task_id: str):
    """
    获取任务生成的代码
    
    - **task_id**: 任务ID
    """
    task_manager = get_task_manager()
    task = task_manager.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return CodeResponse(
        task_id=task_id,
        code=task.get("code"),
        language="python",
        script_path=task.get("script_path")
    )


@router.get("/task/{task_id}/result", response_model=TaskResultResponse, summary="获取任务结果")
async def get_task_result(task_id: str):
    """
    获取任务结果（输出文件列表等）
    
    - **task_id**: 任务ID
    """
    task_manager = get_task_manager()
    task = task_manager.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return TaskResultResponse(
        task_id=task_id,
        status=TaskStatusEnum(task["status"].value if hasattr(task["status"], "value") else task["status"]),
        output_files=task.get("output_files", []),
        geojson_data=None  # 如果有GeoJSON结果可以在这里返回
    )


from pydantic import BaseModel
import json
import re

class ExecuteCodeRequest(BaseModel):
    """执行代码请求"""
    code: str
    timeout: Optional[int] = None  # 可选超时时间


class ExecuteCodeResponse(BaseModel):
    """执行代码响应"""
    success: bool
    message: str
    output_files: list = []  # 从代码中提取的图层信息
    error: Optional[str] = None
    output: Optional[str] = None  # 标准输出
    execution_time: Optional[float] = None  # 执行时间


def _extract_layers_with_llm(code: str) -> list:
    """
    使用 LLM 从代码中提取 addMapLayer 的图层信息
    
    返回格式: [{"name": "图层名称", "path": "文件绝对路径", "type": "vector|raster"}, ...]
    """
    try:
        from spatial_analysis_system.config import Config
        from spatial_analysis_system.llm_client import LLMClient
        
        config = Config()
        llm_client = LLMClient(config)  # LLMClient 接受 Config 对象
        
        prompt = f"""分析以下 QGIS Python 代码，提取所有通过 addMapLayer 添加到地图的图层信息。

代码：
```python
{code}
```

请提取每个 addMapLayer 调用中的：
1. **图层名称**：QgsVectorLayer 或 QgsRasterLayer 构造函数的第二个参数（图层名称）
2. **文件路径**：图层对应的数据文件的绝对路径（从代码中推断）
3. **图层类型**：vector（矢量）或 raster（栅格）

注意：
- 只提取实际会被添加到地图的图层（即有 addMapLayer 调用的）
- 文件路径要解析为完整的绝对路径（如果代码中使用了变量，请推断出实际路径）
- 如果图层创建时使用了 processing.run 的结果，追踪到实际的输出文件路径

请以 JSON 数组格式返回，每个元素包含 name、path、type 字段：
```json
[
  {{"name": "Layer name", "path": "C:/data/layer.geojson", "type": "vector"}},
  {{"name": "Heat map", "path": "C:/data/heatmap.tif", "type": "raster"}}
]
```

如果没有找到任何 addMapLayer 调用，返回空数组 []。
只返回 JSON，不要其他解释。"""

        response, _ = llm_client.chat(prompt)  # chat 返回 (text, stats) 元组
        
        if not response:
            return _extract_layers_with_regex(code)
        
        # 从响应中提取 JSON
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            layers = json.loads(json_match.group())
            # 验证和规范化结果
            valid_layers = []
            for layer in layers:
                if isinstance(layer, dict) and 'name' in layer and 'path' in layer:
                    valid_layers.append({
                        "name": layer.get("name", "未命名图层"),
                        "path": layer.get("path", "").replace('\\', '/'),
                        "type": layer.get("type", "vector")
                    })
            return valid_layers
        
        return []
        
    except Exception as e:
        print(f"[Warning] LLM failed to extract layer info: {e}")
        # 降级到正则表达式提取
        return _extract_layers_with_regex(code)


def _extract_layers_with_regex(code: str) -> list:
    """
    使用正则表达式从代码中提取 addMapLayer 的图层信息（备用方案）
    """
    layers = []
    layer_vars = {}
    
    # 更宽松的匹配模式
    # 匹配 var = QgsVectorLayer(path_expr, "name", "provider")
    vector_patterns = [
        # 匹配直接字符串路径
        r'(\w+)\s*=\s*QgsVectorLayer\s*\(\s*r?["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']',
        # 匹配变量路径
        r'(\w+)\s*=\s*QgsVectorLayer\s*\(\s*(\w+(?:\[["\']?\w+["\']?\])?)\s*,\s*["\']([^"\']+)["\']',
    ]
    
    for pattern in vector_patterns:
        for match in re.finditer(pattern, code):
            var_name, path_expr, layer_name = match.groups()
            resolved_path = _resolve_path_variable(code, path_expr)
            layer_vars[var_name] = {
                "name": layer_name,
                "path": resolved_path,
                "type": "vector"
            }
    
    # 匹配 var = QgsRasterLayer(path_expr, "name")
    raster_patterns = [
        # 匹配直接字符串路径
        r'(\w+)\s*=\s*QgsRasterLayer\s*\(\s*r?["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']',
        # 匹配变量路径
        r'(\w+)\s*=\s*QgsRasterLayer\s*\(\s*(\w+(?:\[["\']?\w+["\']?\])?)\s*,\s*["\']([^"\']+)["\']',
    ]
    
    for pattern in raster_patterns:
        for match in re.finditer(pattern, code):
            var_name, path_expr, layer_name = match.groups()
            resolved_path = _resolve_path_variable(code, path_expr)
            layer_vars[var_name] = {
                "name": layer_name,
                "path": resolved_path,
                "type": "raster"
            }
    
    # 查找 addMapLayer 调用，确定哪些图层实际被添加
    add_pattern = r'addMapLayer\s*\(\s*(\w+)'
    for match in re.finditer(add_pattern, code):
        var_name = match.group(1)
        if var_name in layer_vars:
            # 避免重复添加
            if layer_vars[var_name] not in layers:
                layers.append(layer_vars[var_name])
    
    return layers


def _resolve_path_variable(code: str, path_expr: str) -> str:
    """尝试解析代码中的路径变量"""
    import os as os_module
    path_expr = path_expr.strip()
    
    # 如果已经是绝对路径，直接返回
    if re.match(r'^[A-Za-z]:[/\\]', path_expr) or path_expr.startswith('/'):
        return path_expr.replace('\\', '/')
    
    # 尝试查找变量定义: var_name = "path" 或 var_name = r"path"
    var_pattern = rf'{re.escape(path_expr)}\s*=\s*r?["\']([^"\']+)["\']'
    match = re.search(var_pattern, code)
    if match:
        return match.group(1).replace('\\', '/')
    
    # 尝试解析 os.path.join 形式: var_name = os.path.join(dir_var, "filename")
    join_pattern = rf'{re.escape(path_expr)}\s*=\s*os\.path\.join\s*\(\s*(\w+)\s*,\s*["\']([^"\']+)["\']\s*\)'
    join_match = re.search(join_pattern, code)
    if join_match:
        dir_var, filename = join_match.groups()
        # 递归解析目录变量
        resolved_dir = _resolve_path_variable(code, dir_var)
        if resolved_dir and resolved_dir != dir_var:
            return os_module.path.join(resolved_dir, filename).replace('\\', '/')
    
    # 尝试匹配 result["OUTPUT"] 或 result['output'] 形式
    if '[' in path_expr:
        result_var = path_expr.split('[')[0]
        key_match = re.search(r'\[["\']?(\w+)["\']?\]', path_expr)
        key = key_match.group(1) if key_match else 'OUTPUT'
        
        # 查找 processing.run 的输出路径
        # 模式1: result = processing.run(..., {"OUTPUT": "path"})
        output_pattern = rf'{re.escape(result_var)}\s*=\s*processing\.run\s*\([^{{]*\{{\s*[^}}]*["\']OUTPUT["\']\s*:\s*["\']([^"\']+)["\']'
        match = re.search(output_pattern, code, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).replace('\\', '/')
        
        # 模式2: 查找变量赋值 output_path = "xxx"，然后在 processing.run 中使用
        output_var_pattern = rf'{re.escape(result_var)}\s*=\s*processing\.run\s*\([^{{]*\{{\s*[^}}]*["\']OUTPUT["\']\s*:\s*(\w+)'
        match = re.search(output_var_pattern, code, re.IGNORECASE | re.DOTALL)
        if match:
            output_var = match.group(1)
            # 递归解析这个变量
            return _resolve_path_variable(code, output_var)
    
    return path_expr.replace('\\', '/')


def _get_gdal_env() -> tuple:
    """
    获取 GDAL 工具路径和环境变量
    
    Returns:
        (qgis_root, env) 或 (None, None) 如果找不到
    """
    import os
    
    configured_qgis_root = os.environ.get("QGIS_ROOT")
    qgis_paths = [path for path in [
        configured_qgis_root,
        r"C:\Program Files\QGIS 3.44.0",
        r"C:\Program Files\QGIS 3.34.0",
        r"C:\OSGeo4W",
    ] if path]
    
    for qgis_path in qgis_paths:
        ogr2ogr_exe = os.path.join(qgis_path, "bin", "ogr2ogr.exe")
        if os.path.exists(ogr2ogr_exe):
            env = os.environ.copy()
            env['GDAL_DATA'] = os.path.join(qgis_path, 'share', 'gdal')
            env['PROJ_DATA'] = os.path.join(qgis_path, 'share', 'proj')
            env['PROJ_LIB'] = os.path.join(qgis_path, 'share', 'proj')
            return qgis_path, env
    
    return None, None


def _check_geojson_has_geometry(geojson_path: str) -> bool:
    """
    检查 GeoJSON 文件是否包含几何数据
    
    Returns:
        True 如果至少有一个要素有几何数据，False 如果全是纯属性数据
    """
    import json
    
    try:
        with open(geojson_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            features = data.get('features', [])
            if not features:
                return False  # 空文件视为无几何
            
            # 检查是否有任何要素有几何数据
            for feature in features:
                geom = feature.get('geometry')
                if geom is not None and geom.get('coordinates'):
                    return True
            
            return False  # 所有要素都没有几何数据
    except Exception as e:
        print(f"   ⚠️ Failed to check geometry data: {e}")
        return True  # 出错时默认有几何


def _validate_wgs84_coords(geojson_path: str) -> bool:
    """
    验证 GeoJSON 坐标是否在 WGS-84 范围内
    
    Returns:
        True 如果坐标有效，False 如果异常
    """
    import json
    
    try:
        with open(geojson_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            features = data.get('features', [])
            if not features:
                return True  # 空文件视为有效
            
            # 🔧 修复：确保 geometry 不为 None
            geom = features[0].get('geometry')
            if geom is None:
                return True  # 无几何信息视为有效
            
            coords = geom.get('coordinates', [])
            geom_type = geom.get('type', '')
            
            # 获取第一个坐标点
            first_coord = None
            if geom_type == 'Polygon' and coords and coords[0]:
                first_coord = coords[0][0]
            elif geom_type == 'MultiPolygon' and coords and coords[0] and coords[0][0]:
                first_coord = coords[0][0][0]
            elif geom_type == 'Point':
                first_coord = coords
            elif geom_type == 'LineString' and coords:
                first_coord = coords[0]
            
            if first_coord and len(first_coord) >= 2:
                lng, lat = first_coord[0], first_coord[1]
                if -180 <= lng <= 180 and -90 <= lat <= 90:
                    return True
                else:
                    print(f"   ⚠️ Abnormal coordinates ({lng:.2f}, {lat:.2f})")
                    print(f"      Reason: Data lacks correct georeferencing info (common in heatmap and raster conversion results)")
                    print(f"      Solution: Use GDAL to manually set GeoTransform in QGIS code")
                    return False
    except Exception as e:
        print(f"   ⚠️ Coordinate validation failed: {e}")
    
    return True  # 出错时默认有效


def _reproject_to_wgs84(input_path: str, output_path: str = None) -> str:
    """
    将地理空间文件重投影到 WGS-84 (EPSG:4326)
    
    支持格式: GeoJSON, Shapefile (.shp), GeoTIFF (.tif/.tiff), GeoPackage (.gpkg)
    
    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径（可选，默认在同目录生成 _wgs84 后缀文件）
        
    Returns:
        输出文件路径，失败返回 None
    """
    import os
    import subprocess
    
    if not os.path.exists(input_path):
        print(f"   ⚠️ Input file does not exist: {input_path}")
        return None
    
    qgis_root, env = _get_gdal_env()
    if not qgis_root:
        print(f"   ⚠️ GDAL tools not found")
        return None
    
    ext = os.path.splitext(input_path)[1].lower()
    base_name = os.path.splitext(input_path)[0]
    
    # 确定输出路径和工具
    if ext in ['.shp', '.geojson', '.json', '.gpkg']:
        # 矢量文件使用 ogr2ogr
        tool = os.path.join(qgis_root, 'bin', 'ogr2ogr.exe')
        if not output_path:
            output_path = base_name + '_wgs84.geojson'
        
        # 删除已存在的输出文件
        if os.path.exists(output_path):
            os.remove(output_path)
        
        # 构建命令
        cmd = [tool, '-f', 'GeoJSON', '-t_srs', 'EPSG:4326', output_path, input_path]
        
    elif ext in ['.tif', '.tiff']:
        # 栅格文件使用 gdalwarp
        tool = os.path.join(qgis_root, 'bin', 'gdalwarp.exe')
        if not output_path:
            output_path = base_name + '_wgs84.tif'
        
        # 删除已存在的输出文件
        if os.path.exists(output_path):
            os.remove(output_path)
        
        # 构建命令：重投影栅格到 WGS-84
        cmd = [tool, '-t_srs', 'EPSG:4326', '-r', 'bilinear', '-of', 'GTiff', input_path, output_path]
        
    else:
        print(f"   ⚠️ Unsupported file format: {ext}")
        return None
    
    if not os.path.exists(tool):
        print(f"   ⚠️ Tool not found: {tool}")
        return None
    
    print(f"   🔄 Reprojecting to WGS-84: {os.path.basename(input_path)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
        
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"   ✓ Reprojection successful: {os.path.basename(output_path)}")
            return output_path
        else:
            error_msg = result.stderr or result.stdout
            print(f"   ⚠️ Reprojection failed: {error_msg[:200]}")
            return None
            
    except subprocess.TimeoutExpired:
        print(f"   ⚠️ Reprojection timeout")
        return None
    except Exception as e:
        print(f"   ⚠️ Reprojection exception: {e}")
        return None


def _convert_to_web_format(file_path: str) -> dict:
    """
    将地理空间文件转换为 Web 可显示的格式
    
    - 矢量文件 -> GeoJSON (WGS-84)
    - 栅格文件 -> 保留原格式，返回路径信息
    
    Args:
        file_path: 输入文件路径
        
    Returns:
        {
            "success": bool,
            "path": str,  # 输出文件路径
            "type": str,  # "vector" 或 "raster"
            "web_compatible": bool,  # 是否可在 Web 地图显示
            "message": str  # 提示信息
        }
    """
    import os
    
    if not os.path.exists(file_path):
        return {"success": False, "message": f"文件不存在: {file_path}"}
    
    ext = os.path.splitext(file_path)[1].lower()
    base_name = os.path.splitext(file_path)[0]
    
    # 矢量文件处理
    if ext in ['.shp', '.gpkg']:
        output_path = base_name + '.geojson'
        
        # 如果 GeoJSON 已存在且更新，直接使用
        if os.path.exists(output_path):
            if os.path.getmtime(output_path) >= os.path.getmtime(file_path):
                if _validate_wgs84_coords(output_path):
                    return {
                        "success": True,
                        "path": output_path,
                        "type": "vector",
                        "web_compatible": True,
                        "message": "使用已有 GeoJSON"
                    }
        
        # 转换为 GeoJSON
        result_path = _reproject_to_wgs84(file_path, output_path)
        if result_path and os.path.exists(result_path):
            if _validate_wgs84_coords(result_path):
                return {
                    "success": True,
                    "path": result_path,
                    "type": "vector",
                    "web_compatible": True,
                    "message": "转换成功"
                }
            else:
                # 坐标异常，返回原文件信息
                try:
                    os.remove(result_path)
                except:
                    pass
                return {
                    "success": True,
                    "path": file_path,
                    "type": "vector",
                    "web_compatible": False,
                    "message": "坐标系异常，请在 QGIS 中查看"
                }
        else:
            return {
                "success": True,
                "path": file_path,
                "type": "vector",
                "web_compatible": False,
                "message": "转换失败，请在 QGIS 中查看"
            }
    
    elif ext in ['.geojson', '.json']:
        # 已经是 GeoJSON，先检查是否有几何数据
        has_geometry = _check_geojson_has_geometry(file_path)
        if not has_geometry:
            return {
                "success": True,
                "path": file_path,
                "type": "vector",
                "web_compatible": False,
                "message": "纯属性文件（无几何数据），请在 QGIS 中查看"
            }
        
        # 检查坐标系
        if _validate_wgs84_coords(file_path):
            return {
                "success": True,
                "path": file_path,
                "type": "vector",
                "web_compatible": True,
                "message": "GeoJSON 坐标有效"
            }
        else:
            # 尝试重投影
            output_path = base_name + '_wgs84.geojson'
            result_path = _reproject_to_wgs84(file_path, output_path)
            if result_path and _validate_wgs84_coords(result_path):
                return {
                    "success": True,
                    "path": result_path,
                    "type": "vector",
                    "web_compatible": True,
                    "message": "重投影成功"
                }
            else:
                return {
                    "success": True,
                    "path": file_path,
                    "type": "vector",
                    "web_compatible": False,
                    "message": "坐标系异常，请在 QGIS 中查看"
                }
    
    elif ext in ['.tif', '.tiff']:
        # 🔧 将 GeoTIFF 转换为 PNG 格式，使用 MapLibre 原生 image source 加载
        png_result = _convert_tif_to_png_reliable(file_path)
        if png_result.get("success"):
            return {
                "success": True,
                "path": png_result["png_path"],
                "original_path": file_path,
                "type": "raster",
                "web_compatible": True,
                "bounds": png_result.get("bounds"),
                "format": "png",
                "message": "GeoTIFF 已转换为 PNG 格式"
            }
        else:
            # PNG 转换失败，返回原文件信息
            bounds = _get_tif_bounds(file_path)
            return {
                "success": True,
                "path": file_path,
                "type": "raster",
                "web_compatible": False,
                "bounds": bounds,
                "format": "geotiff",
                "message": f"PNG 转换失败: {png_result.get('error', '未知错误')}"
            }
    
    else:
        return {
            "success": False,
            "path": file_path,
            "type": "unknown",
            "web_compatible": False,
            "message": f"不支持的格式: {ext}"
        }


def _get_tif_bounds(tif_path: str) -> list:
    """
    获取 GeoTIFF 的地理范围
    
    Args:
        tif_path: GeoTIFF 文件路径
        
    Returns:
        [west, south, east, north] 或 None
    """
    import os
    import time
    
    try:
        from osgeo import gdal
        
        # 规范化路径（处理 Windows 路径和中文）
        normalized_path = os.path.normpath(tif_path)
        
        # 检查文件是否存在
        if not os.path.exists(normalized_path):
            print(f"   ⚠️ GeoTIFF file does not exist: {normalized_path}")
            return None
        
        # 等待文件系统同步（对于刚写入的文件）
        time.sleep(0.1)
        
        # 尝试打开文件
        ds = gdal.Open(normalized_path, gdal.GA_ReadOnly)
        if ds is None:
            # 获取 GDAL 错误信息
            err = gdal.GetLastErrorMsg()
            print(f"   ⚠️ Cannot open GeoTIFF: {normalized_path}")
            if err:
                print(f"   ⚠️ GDAL error: {err}")
            return None
        
        gt = ds.GetGeoTransform()
        width = ds.RasterXSize
        height = ds.RasterYSize
        
        west = gt[0]
        east = gt[0] + width * gt[1]
        north = gt[3]
        south = gt[3] + height * gt[5]
        
        ds = None
        
        bounds = [west, south, east, north]
        print(f"   📍 GeoTIFF bounds: {bounds}")
        return bounds
        
    except Exception as e:
        import traceback
        print(f"   ⚠️ Failed to get GeoTIFF bounds: {e}")
        traceback.print_exc()
        return None


# ============================================================================
# 单波段栅格智能着色 — 分类/归一化指数/一般连续值 三种模式
# ============================================================================

# 分类栅格默认色板（按像素值索引取色，共 21 色循环）
_CLASSIFICATION_PALETTE = [
    (0,   0,   0),        # 0: 通常是 nodata
    (0,   100, 255),      # 1: 蓝 (Water)
    (34,  139, 34),       # 2: 森林绿 (Vegetation)
    (255, 50,  50),       # 3: 红 (Built-up)
    (210, 180, 140),      # 4: 棕 (Bare soil)
    (255, 230, 0),        # 5: 黄 (Cropland)
    (160, 32,  240),      # 6: 紫
    (255, 165, 0),        # 7: 橙
    (0,   200, 200),      # 8: 青
    (255, 105, 180),      # 9: 粉
    (128, 128, 0),        # 10: 橄榄
    (0,   255, 127),      # 11: 春绿
    (70,  130, 180),      # 12: 钢蓝
    (220, 20,  60),       # 13: 绯红
    (255, 215, 0),        # 14: 金
    (75,  0,   130),      # 15: 靛
    (0,   128, 128),      # 16: 暗青
    (245, 222, 179),      # 17: 麦色
    (139, 69,  19),       # 18: 鞍棕
    (0,   191, 255),      # 19: 深天蓝
    (144, 238, 144),      # 20: 浅绿
]


def _colorize_singleband_to_rgba(data, nodata_val) -> 'np.ndarray':
    """
    将单波段栅格数据智能转换为 RGBA 数组。
    
    自动检测三种模式：
    1. 分类栅格 —— 整数值、唯一值数 ≤ 20 → 鲜明分类色板
    2. 归一化指数 —— 值域 ⊂ [-1.1, 1.1] → 红-黄-绿渐变色带
    3. 一般连续值 —— 百分位灰度拉伸
    """
    import numpy as np

    # 构建 nodata 掩码
    is_nodata = np.zeros_like(data, dtype=bool)
    if nodata_val is not None:
        is_nodata |= (data == nodata_val)
    is_nodata |= ~np.isfinite(data)

    alpha = np.where(is_nodata, 0, 255).astype(np.uint8)
    valid = data[~is_nodata]

    if len(valid) == 0:
        return np.zeros((*data.shape, 4), dtype=np.uint8)

    unique_vals = np.unique(valid)

    # ---- 模式 1: 分类栅格 ----
    is_classification = (
        2 <= len(unique_vals) <= 20
        and np.all(unique_vals == np.floor(unique_vals))
        and unique_vals.min() >= 0
    )

    if is_classification:
        print(f"   🎨 检测到分类栅格 ({len(unique_vals)} 类), 使用分类色板")
        r = np.zeros_like(data, dtype=np.uint8)
        g = np.zeros_like(data, dtype=np.uint8)
        b = np.zeros_like(data, dtype=np.uint8)
        for val in unique_vals:
            idx = int(val) % len(_CLASSIFICATION_PALETTE)
            color = _CLASSIFICATION_PALETTE[idx]
            mask = (data == val) & ~is_nodata
            r[mask], g[mask], b[mask] = color[0], color[1], color[2]
        return np.stack([r, g, b, alpha], axis=-1)

    # ---- 模式 2: 归一化指数 (NDVI / NDBI / NDWI 等) ----
    vmin, vmax = float(valid.min()), float(valid.max())
    if -1.1 <= vmin and vmax <= 1.1 and vmin < 0:
        # 使用百分位拉伸，让实际数据分布占满整条色带，最大化对比度
        p2, p98 = np.percentile(valid, [2, 98])
        if p98 - p2 < 0.01:
            p98 = p2 + 0.01
        print(f"   🎨 检测到归一化指数 (范围 [{vmin:.2f}, {vmax:.2f}], "
              f"拉伸 [{p2:.3f}, {p98:.3f}]), 使用土黄-翠绿色带")
        # 将 p2→p98 映射到 [0, 1]
        norm = np.clip((data - p2) / (p98 - p2), 0, 1)

        # 遥感标准 NDVI 色带：深棕 → 土黄 → 黄绿 → 翠绿 → 深绿
        # 5 个控制点的 RGB 值
        stops_r = np.array([140, 200, 210, 60,  15], dtype=np.float64)   # 棕→黄→绿
        stops_g = np.array([ 80, 170, 210, 175, 110], dtype=np.float64)
        stops_b = np.array([ 30,  60,  70, 30,  25], dtype=np.float64)
        t = np.array([0.0, 0.25, 0.5, 0.75, 1.0])

        r_ch = np.interp(norm, t, stops_r).astype(np.uint8)
        g_ch = np.interp(norm, t, stops_g).astype(np.uint8)
        b_ch = np.interp(norm, t, stops_b).astype(np.uint8)
        return np.stack([r_ch, g_ch, b_ch, alpha], axis=-1)

    # ---- 模式 3: 一般连续值 → 百分位灰度拉伸 ----
    print(f"   🎨 一般连续值 (范围 [{vmin:.2f}, {vmax:.2f}]), 使用灰度拉伸")
    p2, p98 = np.percentile(valid, [2, 98])
    if p98 <= p2:
        p98 = p2 + 1
    gray = np.clip((data - p2) / (p98 - p2) * 255, 0, 255).astype(np.uint8)
    return np.stack([gray, gray, gray, alpha], axis=-1)


def _convert_tif_to_png_reliable(tif_path: str) -> dict:
    """
    将 GeoTIFF 可靠地转换为 PNG 格式，用于 Web 地图显示
    
    使用 GDAL Python API + numpy 进行转换，支持：
    - 多波段影像（选择 RGB 波段）
    - 单波段影像（分类彩色 / 指数色带 / 灰度拉伸）
    - nodata 透明处理
    - 自动拉伸增强可视化
    
    Args:
        tif_path: 输入 GeoTIFF 文件路径
        
    Returns:
        {
            "success": bool,
            "png_path": str,
            "bounds": [west, south, east, north],
            "error": str
        }
    """
    import os
    from pathlib import Path
    
    try:
        # 🔧 方法1: 尝试使用 rasterio（更可靠，不受 GDAL 驱动问题影响）
        try:
            import rasterio
            import numpy as np
            from PIL import Image
            
            # Create PNG cache directory
            png_cache_dir = PNG_CACHE_DIR
            png_cache_dir.mkdir(parents=True, exist_ok=True)
            
            # 缓存版本标记 — 渲染逻辑更新时递增此值，旧缓存自动失效
            _PNG_CACHE_VERSION = "v4_ndvi_ramp"
            version_file = png_cache_dir / ".cache_version"
            if version_file.exists():
                current_version = version_file.read_text().strip()
            else:
                current_version = ""
            if current_version != _PNG_CACHE_VERSION:
                # 版本不匹配，清空所有旧缓存
                for old_png in png_cache_dir.glob("*.png"):
                    try:
                        old_png.unlink()
                    except Exception:
                        pass
                version_file.write_text(_PNG_CACHE_VERSION)
                print(f"   🗑️ PNG 缓存已清空 (版本升级: {current_version} → {_PNG_CACHE_VERSION})")
            
            # Generate PNG filename
            input_name = Path(tif_path).stem
            png_filename = f"{input_name}.png"
            png_path = str(png_cache_dir / png_filename)
            
            # Check if cached version exists
            if os.path.exists(png_path):
                if os.path.getmtime(png_path) > os.path.getmtime(tif_path):
                    print(f"   ✓ Using cached PNG file: {png_filename}")
                    with rasterio.open(tif_path) as src:
                        bounds = list(src.bounds)
                    return {
                        "success": True,
                        "png_path": png_path,
                        "bounds": [bounds[0], bounds[1], bounds[2], bounds[3]]  # west, south, east, north
                    }
                else:
                    os.remove(png_path)
            
            print(f"   🔄 [rasterio] Converting GeoTIFF -> PNG: {Path(tif_path).name}")
            
            with rasterio.open(tif_path) as src:
                bounds = list(src.bounds)
                band_count = src.count
                print(f"   📊 Band count: {band_count}, Size: {src.width}x{src.height}")
                
                if band_count >= 3:
                    # 多波段：使用前 3 个波段作为 RGB
                    r_band = src.read(1).astype(np.float32)
                    g_band = src.read(2).astype(np.float32)
                    b_band = src.read(3).astype(np.float32)
                    
                    nodata = src.nodata
                    print(f"   📋 nodata value: {nodata}")
                    
                    # 创建透明度掩码
                    is_nodata = np.zeros_like(r_band, dtype=bool)
                    if nodata is not None:
                        is_nodata |= (r_band == nodata) | (g_band == nodata) | (b_band == nodata)
                    all_zero = (r_band == 0) & (g_band == 0) & (b_band == 0)
                    if np.sum(all_zero) > 0.01 * r_band.size:
                        is_nodata |= all_zero
                    
                    # 2%-98% 百分位拉伸
                    def stretch_band(band, mask):
                        valid = band[~mask]
                        if len(valid) == 0:
                            return np.zeros_like(band, dtype=np.uint8)
                        p2, p98 = np.percentile(valid, [2, 98])
                        if p98 <= p2:
                            p98 = p2 + 1
                        stretched = np.clip((band - p2) / (p98 - p2) * 255, 0, 255).astype(np.uint8)
                        return stretched
                    
                    r = stretch_band(r_band, is_nodata)
                    g = stretch_band(g_band, is_nodata)
                    b = stretch_band(b_band, is_nodata)
                    alpha = np.where(is_nodata, 0, 255).astype(np.uint8)
                    
                    rgba = np.stack([r, g, b, alpha], axis=-1)
                    
                else:
                    # 单波段 — 使用智能着色（分类/指数/灰度）
                    band_data = src.read(1).astype(np.float32)
                    nodata = src.nodata
                    rgba = _colorize_singleband_to_rgba(band_data, nodata)
                
                img = Image.fromarray(rgba, mode='RGBA')
                img.save(png_path)
                
                print(f"   ✅ PNG conversion successful: {png_filename}")
                return {
                    "success": True,
                    "png_path": png_path,
                    "bounds": [bounds[0], bounds[1], bounds[2], bounds[3]]
                }
                
        except ImportError:
            print("   ⚠️ rasterio not available, trying GDAL")
        except Exception as rio_err:
            print(f"   ⚠️ rasterio conversion failed: {rio_err}, trying GDAL")
        
        # 🔧 方法2: 使用 GDAL（设置正确的环境变量）
        from osgeo import gdal
        import numpy as np
        from PIL import Image
        
        # 设置 GDAL 环境变量，确保驱动可用
        gdal.AllRegister()
        
        # Create PNG cache directory
        png_cache_dir = PNG_CACHE_DIR
        png_cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate PNG filename
        input_name = Path(tif_path).stem
        png_filename = f"{input_name}.png"
        png_path = str(png_cache_dir / png_filename)
        
        # Check if cached version exists
        if os.path.exists(png_path):
            if os.path.getmtime(png_path) > os.path.getmtime(tif_path):
                print(f"   ✓ Using cached PNG file: {png_filename}")
                bounds = _get_tif_bounds(tif_path)
                return {
                    "success": True,
                    "png_path": png_path,
                    "bounds": bounds
                }
            else:
                os.remove(png_path)
        
        print(f"   🔄 Converting GeoTIFF -> PNG: {Path(tif_path).name}")
        
        # 打开 GeoTIFF
        ds = gdal.Open(tif_path, gdal.GA_ReadOnly)
        if ds is None:
            return {"success": False, "error": f"无法打开 GeoTIFF: {tif_path}"}
        
        # 获取地理范围
        gt = ds.GetGeoTransform()
        width = ds.RasterXSize
        height = ds.RasterYSize
        band_count = ds.RasterCount
        
        west = gt[0]
        east = gt[0] + width * gt[1]
        north = gt[3]
        south = gt[3] + height * gt[5]
        bounds = [west, south, east, north]
        
        print(f"   📊 Band count: {band_count}, Size: {width}x{height}")
        
        # 读取数据并创建 RGBA 图像
        if band_count >= 3:
            # 多波段：使用前 3 个波段作为 RGB
            r_band = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
            g_band = ds.GetRasterBand(2).ReadAsArray().astype(np.float32)
            b_band = ds.GetRasterBand(3).ReadAsArray().astype(np.float32)
            
            # 获取 nodata 值
            nodata = ds.GetRasterBand(1).GetNoDataValue()
            print(f"   📋 nodata 值: {nodata}")
            
            # 创建透明度掩码（nodata 区域和全零区域都设为透明）
            # 1. nodata 值的像素设为透明
            # 2. 所有波段都为 0 的像素也设为透明（通常是裁剪后的边界外区域）
            is_nodata = np.zeros_like(r_band, dtype=bool)
            
            if nodata is not None:
                is_nodata = is_nodata | (r_band == nodata) | (g_band == nodata) | (b_band == nodata)
            
            # 对于 Sentinel-2 等裁剪后的影像，边界外通常是全零
            # 检查所有波段是否都为 0（包括前 3 个和可能的其他波段）
            all_zero = (r_band == 0) & (g_band == 0) & (b_band == 0)
            
            # 如果有更多波段，也检查它们
            if band_count > 3:
                for i in range(4, min(band_count + 1, 13)):  # 最多检查 12 个波段
                    extra_band = ds.GetRasterBand(i).ReadAsArray().astype(np.float32)
                    all_zero = all_zero & (extra_band == 0)
            
            is_nodata = is_nodata | all_zero
            
            alpha = np.where(is_nodata, 0, 255).astype(np.uint8)
            
            valid_pixel_count = np.sum(alpha > 0)
            total_pixel_count = alpha.size
            print(f"   📊 Valid pixels: {valid_pixel_count}/{total_pixel_count} ({100*valid_pixel_count/total_pixel_count:.1f}%)")
            
            # 拉伸到 0-255（使用 2-98 百分位拉伸）
            def stretch_band(band, alpha_mask):
                valid = band[alpha_mask > 0]
                if len(valid) == 0:
                    return np.zeros_like(band, dtype=np.uint8)
                p2, p98 = np.percentile(valid, [2, 98])
                if p98 - p2 < 1:
                    p2, p98 = valid.min(), valid.max()
                if p98 - p2 < 1:
                    return np.zeros_like(band, dtype=np.uint8)
                stretched = np.clip((band - p2) / (p98 - p2) * 255, 0, 255)
                return stretched.astype(np.uint8)
            
            r = stretch_band(r_band, alpha)
            g = stretch_band(g_band, alpha)
            b = stretch_band(b_band, alpha)
            
            # 创建 RGBA 图像
            rgba = np.stack([r, g, b, alpha], axis=-1)
            
        else:
            # 单波段 — 使用智能着色（分类/指数/灰度）
            band_data = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
            nodata = ds.GetRasterBand(1).GetNoDataValue()
            rgba = _colorize_singleband_to_rgba(band_data, nodata)
        
        ds = None
        
        # 保存为 PNG
        img = Image.fromarray(rgba, 'RGBA')
        img.save(png_path, 'PNG', optimize=True)
        
        print(f"   ✅ PNG conversion successful: {png_filename}")
        return {
            "success": True,
            "png_path": png_path,
            "bounds": bounds
        }
        
    except Exception as e:
        import traceback
        print(f"   ❌ PNG conversion failed: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def _convert_to_cog(tif_path: str) -> dict:
    """
    将 GeoTIFF 转换为 Cloud Optimized GeoTIFF (COG) 格式
    
    使用 GDAL Python API 进行转换，避免 subprocess 的编码问题
    
    Args:
        tif_path: 输入 GeoTIFF 文件路径
        
    Returns:
        {
            "success": bool,
            "cog_path": str,  # COG 文件路径
            "bounds": [west, south, east, north],
            "error": str  # 错误信息（如果失败）
        }
    """
    import os
    from pathlib import Path
    from osgeo import gdal
    
    try:
        # Create COG cache directory
        cog_cache_dir = COG_CACHE_DIR
        cog_cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate COG filename
        input_name = Path(tif_path).stem
        cog_filename = f"{input_name}_cog.tif"
        cog_path = str(cog_cache_dir / cog_filename)
        
        # Check if cached COG file exists
        if os.path.exists(cog_path):
            # Check if cache is newer than source file
            if os.path.getmtime(cog_path) > os.path.getmtime(tif_path):
                print(f"   ✓ Using cached COG file: {cog_filename}")
                # 验证缓存文件是否可读
                test_ds = gdal.Open(cog_path)
                if test_ds:
                    test_ds = None  # 关闭
                    bounds = _get_tif_bounds(cog_path)
                    if bounds is None:
                        # 从原始文件获取 bounds
                        bounds = _get_tif_bounds(tif_path)
                    return {
                        "success": True,
                        "cog_path": cog_path,
                        "bounds": bounds
                    }
                else:
                    # 缓存文件损坏，删除
                    print(f"   ⚠️  Cache file corrupted, re-converting")
                    os.remove(cog_path)
            else:
                # 删除过期缓存
                os.remove(cog_path)
        
        print(f"   🔄 Converting GeoTIFF -> COG: {Path(tif_path).name}")
        
        # 打开源文件
        src_ds = gdal.Open(tif_path)
        if not src_ds:
            error_msg = f"无法打开源文件: {tif_path}"
            print(f"   ❌ {error_msg}")
            return {"success": False, "error": error_msg}
        
        # 获取 COG 驱动
        cog_driver = gdal.GetDriverByName('COG')
        if not cog_driver:
            # COG 驱动不可用，尝试使用 GTiff 驱动 + COG 选项
            print(f"   ⚠️  COG driver not available, using GTiff driver")
            gtiff_driver = gdal.GetDriverByName('GTiff')
            if not gtiff_driver:
                src_ds = None
                return {"success": False, "error": "GTiff 驱动不可用"}
            
            # COG 兼容的创建选项
            cog_options = [
                'TILED=YES',
                'COMPRESS=DEFLATE',
                'BLOCKXSIZE=512',
                'BLOCKYSIZE=512'
            ]
            
            cog_ds = gtiff_driver.CreateCopy(cog_path, src_ds, options=cog_options)
        else:
            # 使用 COG 驱动
            # COG 驱动的创建选项：
            # - COMPRESS: 压缩方法（DEFLATE, LZW, ZSTD等）
            # - BLOCKSIZE: 瓦片大小（默认512）
            # - OVERVIEWS: 自动生成概览
            cog_options = [
                'COMPRESS=DEFLATE',
                'BLOCKSIZE=512',
                'OVERVIEWS=AUTO'
            ]
            
            cog_ds = cog_driver.CreateCopy(cog_path, src_ds, options=cog_options)
        
        # 关闭数据集
        src_ds = None
        
        if not cog_ds:
            return {"success": False, "error": "COG 创建失败"}
        
        cog_ds = None  # 关闭输出文件
        
        # 验证生成的 COG 文件
        if not os.path.exists(cog_path):
            return {"success": False, "error": "COG 文件未生成"}
        
        verify_ds = gdal.Open(cog_path)
        if not verify_ds:
            return {"success": False, "error": "COG 文件无法读取"}
        
        verify_ds = None
        
        # 获取 COG 文件的地理范围
        bounds = _get_tif_bounds(cog_path)
        if bounds is None:
            print(f"   ⚠️ 从 COG 获取范围失败，尝试从原始文件获取")
            bounds = _get_tif_bounds(tif_path)
        
        print(f"   ✅ COG 转换成功: {cog_filename}")
        return {
            "success": True,
            "cog_path": cog_path,
            "bounds": bounds
        }
        
    except Exception as e:
        print(f"   ❌ COG 转换异常: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


# ============================================================
# 以下是旧的 PNG 转换代码，已废弃，保留作参考
# ============================================================



def _get_band_count(gdalinfo_output: str) -> int:
    """
    从gdalinfo输出中提取波段数量
    
    Returns:
        波段数量（默认为1）
    """
    import re
    
    try:
        # 查找 "Band 1" 到 "Band N" 的最大数字
        band_matches = re.findall(r'Band (\d+)', gdalinfo_output)
        if band_matches:
            band_numbers = [int(b) for b in band_matches]
            return max(band_numbers)
        
        # 备选方案：查找 "Size is X, Y" 下一行的 "Band count: N"
        # 或直接数 "Band X Block=" 的数量
        return 1
    except Exception as e:
        print(f"⚠️ 解析波段数失败: {e}")
        return 1


def _get_data_range(gdalinfo_output: str, tif_path: str) -> tuple:
    """
    获取栅格数据的值域范围
    
    优先从 gdalinfo 的统计信息中获取，如果没有则使用 GDAL 计算
    
    Returns:
        (min_value, max_value) 或 (None, None)
    """
    import re
    import subprocess
    
    try:
        # 方法1：从 gdalinfo 输出中查找统计信息
        # 查找 STATISTICS_MINIMUM 和 STATISTICS_MAXIMUM
        min_match = re.search(r'STATISTICS_MINIMUM=([0-9.e+-]+)', gdalinfo_output)
        max_match = re.search(r'STATISTICS_MAXIMUM=([0-9.e+-]+)', gdalinfo_output)
        
        if min_match and max_match:
            data_min = float(min_match.group(1))
            data_max = float(max_match.group(1))
            print(f"   📈 从统计信息获取值域: {data_min} - {data_max}")
            return (data_min, data_max)
        
        # 方法2：使用 gdalinfo -stats 强制计算统计信息
        try:
            stats_output = subprocess.check_output(
                ['gdalinfo', '-stats', tif_path],
                stderr=subprocess.STDOUT,
                text=True,
                timeout=60
            )
            
            min_match = re.search(r'STATISTICS_MINIMUM=([0-9.e+-]+)', stats_output)
            max_match = re.search(r'STATISTICS_MAXIMUM=([0-9.e+-]+)', stats_output)
            
            if min_match and max_match:
                data_min = float(min_match.group(1))
                data_max = float(max_match.group(1))
                print(f"   📈 计算得到值域: {data_min} - {data_max}")
                return (data_min, data_max)
        except Exception as e:
            print(f"   ⚠️ 计算统计信息失败: {e}")
        
        # 方法3：从 Computed Min/Max 中获取
        computed_match = re.search(r'Computed Min/Max=([0-9.e+-]+),([0-9.e+-]+)', gdalinfo_output)
        if computed_match:
            data_min = float(computed_match.group(1))
            data_max = float(computed_match.group(2))
            print(f"   📈 从计算结果获取值域: {data_min} - {data_max}")
            return (data_min, data_max)
        
        return (None, None)
        
    except Exception as e:
        print(f"   ⚠️ 获取值域失败: {e}")
        return (None, None)


def _extract_bounds_from_gdalinfo(gdalinfo_output: str) -> list:
    """
    从gdalinfo输出中提取地理范围（WGS84）
    
    Returns:
        [west, south, east, north] 或 None
    """
    import re
    
    try:
        # 查找Corner Coordinates
        # Upper Left  (  116.0000000,   40.5000000)
        # Lower Right (  117.0000000,   39.5000000)
        
        upper_left_match = re.search(r'Upper Left\s+\(\s*([-\d.]+),\s*([-\d.]+)\)', gdalinfo_output)
        lower_right_match = re.search(r'Lower Right\s+\(\s*([-\d.]+),\s*([-\d.]+)\)', gdalinfo_output)
        
        if upper_left_match and lower_right_match:
            west = float(upper_left_match.group(1))
            north = float(upper_left_match.group(2))
            east = float(lower_right_match.group(1))
            south = float(lower_right_match.group(2))
            
            # 验证坐标是否在合理范围内（WGS84: -180~180, -90~90）
            if (-180 <= west <= 180 and -180 <= east <= 180 and 
                -90 <= south <= 90 and -90 <= north <= 90):
                return [west, south, east, north]
        
        return None
    except Exception as e:
        print(f"⚠️ 解析bounds失败: {e}")
        return None


def _convert_shp_to_geojson(shp_path: str) -> str:
    """
    将 Shapefile 转换为 GeoJSON，以便在 Web 地图中显示
    (保留此函数以兼容现有代码)
    
    Args:
        shp_path: Shapefile 文件路径
        
    Returns:
        转换后的 GeoJSON 文件路径，失败则返回 None
    """
    result = _convert_to_web_format(shp_path)
    if result.get("success") and result.get("web_compatible"):
        return result.get("path")
    return None


def _get_url_for_path(file_path: str) -> str:
    """Generate URL based on file path"""
    import os
    from urllib.parse import quote
    from pathlib import Path
    
    path_normalized = file_path.replace('\\', '/').lower()
    file_name = os.path.basename(file_path)
    
    # URL encode filename (handle Chinese and special characters)
    # safe='./' preserves dots in extensions and path separators
    encoded_file_name = quote(file_name, safe='./')
    
    # Try to get relative path from mount point
    if 'png_cache' in path_normalized:
        # PNG cache directory
        return f'/png/{encoded_file_name}'
    elif 'cog_cache' in path_normalized:
        # COG cache directory
        return f'/cog/{encoded_file_name}'
    elif 'raster_web_cache' in path_normalized or 'raster-cache' in path_normalized:
        # Raster cache directory (PNG preview files)
        return f'/raster-cache/{encoded_file_name}'
    elif 'output/results' in path_normalized:
        # Support both autogis_main and autogis_main_en paths
        # Relative path from output/results
        rel_path = file_path[file_path.lower().find('output/results') + len('output/results') + 1:]
        rel_path = rel_path.replace('\\', '/')
        encoded_path = quote(rel_path, safe='./')
        return f'/results/{encoded_path}'
    elif 'downloaded_data' in path_normalized:
        # Support both autogis_main and autogis_main_en paths
        # Relative path from downloaded_data (includes subdirs like boundaries/)
        rel_path = file_path[file_path.lower().find('downloaded_data') + len('downloaded_data') + 1:]
        rel_path = rel_path.replace('\\', '/')
        encoded_path = quote(rel_path, safe='./')
        return f'/downloaded/{encoded_path}'
    elif '/output/' in path_normalized and ('autogis_main' in path_normalized or 'autogis_main_en' in path_normalized):
        # Support both autogis_main and autogis_main_en paths
        # Relative path from output
        rel_path = file_path[file_path.lower().find('output/') + len('output/'):]
        rel_path = rel_path.replace('\\', '/')
        encoded_path = quote(rel_path, safe='./')
        return f'/output/{encoded_path}'
    else:
        # Default: use ext-output (external output)
        return f'/ext-output/{encoded_file_name}'


class ExtractLayersRequest(BaseModel):
    """提取图层请求"""
    code: str = Field(..., description="要分析的 Python 代码")


class LayerInfo(BaseModel):
    """图层信息"""
    name: str
    path: str
    url: Optional[str] = None
    type: str = "vector"
    size: Optional[int] = None
    web_compatible: bool = True
    message: Optional[str] = None
    bounds: Optional[List[float]] = None  # 栅格图层的地理范围 [west, south, east, north]
    format: Optional[str] = None  # 栅格格式：'cog', 'geotiff', 'png' 等


class ExtractLayersResponse(BaseModel):
    """提取图层响应"""
    success: bool
    message: str
    layers: List[LayerInfo] = []


@router.post("/extract-layers", response_model=ExtractLayersResponse, summary="从代码提取图层信息")
async def extract_layers(request: ExtractLayersRequest):
    """
    从 Python 代码中提取 addMapLayer 图层信息，并转换为 Web 可显示的格式
    
    - **code**: 要分析的 Python 代码
    
    不执行代码，只分析代码结构提取图层信息。
    对于已存在的文件，会自动转换为 GeoJSON 并返回可访问的 URL。
    """
    import os
    
    try:
        # 使用 LLM 提取图层信息
        print("📝 正在分析代码中的图层信息...")
        extracted_layers = _extract_layers_with_llm(request.code)
        print(f"   找到 {len(extracted_layers)} 个图层")
        
        if not extracted_layers:
            return ExtractLayersResponse(
                success=True,
                message="代码中未找到 addMapLayer 调用",
                layers=[]
            )
        
        # 处理每个图层，转换为 Web 可显示格式
        result_layers = []
        for layer in extracted_layers:
            file_path = layer.get("path", "")
            layer_name = layer.get("name", "未命名图层")
            layer_type = layer.get("type", "vector")
            
            if not file_path:
                continue
            
            # 解析变量引用（如果路径是变量名）
            resolved_path = _resolve_path_variable(request.code, file_path)
            
            if resolved_path and os.path.exists(resolved_path):
                # 转换为 Web 可显示格式
                convert_result = _convert_to_web_format(resolved_path)
                
                if convert_result.get("success"):
                    output_path = convert_result.get("path", resolved_path)
                    file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
                    
                    # 生成 URL
                    url = _get_url_for_path(output_path) if convert_result.get("web_compatible") else None
                    print(f"   📍 图层URL: {layer_name} -> {url}")
                    print(f"   📁 文件路径: {output_path}")
                    print(f"   🌐 Web兼容: {convert_result.get('web_compatible')}")
                    print(f"   📦 类型: {convert_result.get('type', layer_type)}")
                    if convert_result.get("bounds"):
                        print(f"   🗺️  范围: {convert_result.get('bounds')}")
                    
                    result_layers.append(LayerInfo(
                        name=layer_name,
                        path=output_path,
                        url=url,
                        type=convert_result.get("type", layer_type),
                        size=file_size,
                        web_compatible=convert_result.get("web_compatible", True),
                        message=convert_result.get("message"),
                        bounds=convert_result.get("bounds"),  # 栅格图层的地理范围
                        format=convert_result.get("format")  # 栅格格式
                    ))
                else:
                    result_layers.append(LayerInfo(
                        name=layer_name,
                        path=resolved_path,
                        url=None,
                        type=layer_type,
                        web_compatible=False,
                        message=f"文件处理失败: {convert_result.get('message')}"
                    ))
            else:
                result_layers.append(LayerInfo(
                    name=layer_name,
                    path=file_path,
                    url=None,
                    type=layer_type,
                    web_compatible=False,
                    message=f"文件不存在: {resolved_path or file_path}"
                ))
        
        web_layers = [l for l in result_layers if l.web_compatible]
        return ExtractLayersResponse(
            success=True,
            message=f"找到 {len(result_layers)} 个图层，{len(web_layers)} 个可在 Web 显示",
            layers=result_layers
        )
        
    except Exception as e:
        print(f"❌ 提取图层失败: {e}")
        import traceback
        traceback.print_exc()
        return ExtractLayersResponse(
            success=False,
            message=f"提取图层失败: {str(e)}",
            layers=[]
        )


@router.post("/execute-code", response_model=ExecuteCodeResponse, summary="执行Python代码")
async def execute_code(request: ExecuteCodeRequest):
    """
    使用 QGIS 环境执行用户提供的 Python 代码
    
    - **code**: 要执行的 Python 代码
    - **timeout**: 可选的超时时间（秒），默认使用配置值
    
    执行成功后，会使用 LLM 分析代码中的 addMapLayer 调用，
    提取图层信息（文件路径、图层名称、类型）返回给前端。
    """
    import os
    
    try:
        # 导入代码执行器和配置
        from spatial_analysis_system.code_executor import CodeExecutor
        from spatial_analysis_system.config import Config
        
        # 加载配置
        config = Config()
        
        # 使用配置初始化代码执行器
        executor = CodeExecutor(config=config)
        
        # 先验证代码语法
        is_valid, validation_msg = executor.validate_code(request.code)
        if not is_valid:
            return ExecuteCodeResponse(
                success=False,
                message="代码语法错误",
                error=validation_msg
            )
        
        # 使用 LLM 预先提取代码中的 addMapLayer 图层信息
        print("📝 正在分析代码中的图层信息...")
        extracted_layers = _extract_layers_with_llm(request.code)
        print(f"   找到 {len(extracted_layers)} 个图层")
        
        # 计算超时时间
        timeout = request.timeout or executor.calculate_timeout(request.code)
        
        # 执行代码
        result = executor.execute(request.code, timeout=timeout)
        
        if result.success:
            # 检查输出中是否包含QGIS标识
            output_text = (result.output or "").lower()
            error_text = (result.error or "").lower()
            combined_text = output_text + error_text
            
            qgis_indicators = ['qgis', 'grass', 'saga', 'processing', 'runqgis', 'provider']
            uses_qgis = any(indicator in combined_text for indicator in qgis_indicators)
            
            # 验证提取的图层文件是否存在，并转换为 Web 可显示格式
            output_files = []
            for layer in extracted_layers:
                file_path = layer.get("path", "")
                if file_path and os.path.exists(file_path):
                    layer_name = layer.get("name", os.path.basename(file_path))
                    
                    # 使用统一的格式转换函数处理所有文件类型
                    convert_result = _convert_to_web_format(file_path)
                    
                    if convert_result.get("success"):
                        output_path = convert_result.get("path", file_path)
                        file_stat = os.stat(output_path) if os.path.exists(output_path) else os.stat(file_path)
                        
                        # 生成 URL
                        file_url = _get_url_for_path(output_path)
                        layer_type = convert_result.get("type", "vector")
                        bounds = convert_result.get("bounds")
                        
                        # 调试输出
                        print(f"   📍 图层: {layer_name}")
                        print(f"      文件: {output_path}")
                        print(f"      URL: {file_url}")
                        print(f"      类型: {layer_type}")
                        print(f"      Web兼容: {convert_result.get('web_compatible')}")
                        if bounds:
                            print(f"      范围: {bounds}")
                        
                        if convert_result.get("web_compatible"):
                            # Web 可显示
                            layer_info = {
                                "name": layer_name,
                                "path": output_path,
                                "url": file_url,
                                "type": layer_type,
                                "size": file_stat.st_size,
                                "original_path": file_path if output_path != file_path else None,
                                "web_compatible": True,
                            }
                            # 栅格图层需要包含 bounds 和 format
                            if bounds:
                                layer_info["bounds"] = bounds
                            if convert_result.get("format"):
                                layer_info["format"] = convert_result.get("format")
                            output_files.append(layer_info)
                        else:
                            # 无法在 Web 显示（坐标系问题或栅格文件）
                            output_files.append({
                                "name": layer_name,
                                "path": file_path,
                                "url": None,
                                "type": layer_type,
                                "size": file_stat.st_size,
                                "qgis_only": True,
                                "web_compatible": False,
                                "message": convert_result.get("message", "请在 QGIS 中查看")
                            })
                    else:
                        print(f"   ⚠️ 文件转换失败: {convert_result.get('message')}")
                else:
                    # 文件不存在，可能路径解析有问题，记录但不返回
                    print(f"   ⚠️ 图层文件不存在: {file_path}")
            
            message = "代码执行成功！"
            if uses_qgis:
                message += " (使用QGIS环境)"
            if output_files:
                message += f" 检测到 {len(output_files)} 个图层"
            message += f" (耗时: {result.execution_time:.2f}秒)"
            
            return ExecuteCodeResponse(
                success=True,
                message=message,
                output_files=output_files,
                output=result.output,
                execution_time=result.execution_time
            )
        else:
            error_msg = result.error or result.output or "未知错误"
            return ExecuteCodeResponse(
                success=False,
                message=f"代码执行失败 (返回码: {result.return_code})",
                error=error_msg,
                output=result.output,
                execution_time=result.execution_time
            )
        
    except FileNotFoundError as e:
        # runqgis 未找到，返回明确的错误信息
        error_msg = (
            f"无法找到 QGIS 运行环境 (runqgis)。\n"
            f"错误详情: {str(e)}\n\n"
            f"请检查配置文件 (spatial_analysis_system/config.yaml) 中的 QGIS 路径设置：\n"
            f"  - qgis.runqgis_bat_path\n"
            f"  - qgis.qgis_run_py_path\n\n"
            f"请为当前环境提供有效的 QGIS 启动器路径。"
        )
        return ExecuteCodeResponse(
            success=False,
            message="QGIS 环境未配置",
            error=error_msg
        )
    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        return ExecuteCodeResponse(
            success=False,
            message="执行出错",
            error=error_detail
        )


class LoadLayersRequest(BaseModel):
    """加载图层请求"""
    script_path: str = Field(..., description="脚本文件的绝对路径")


@router.post("/load-layers", response_model=ExecuteCodeResponse, summary="从脚本路径加载图层")
async def load_layers_from_script(request: LoadLayersRequest):
    """
    从已生成的脚本文件中提取图层信息并加载
    
    - **script_path**: 脚本文件的绝对路径
    
    此端点会读取脚本内容，使用 LLM 分析 addMapLayer 调用，
    提取图层信息（文件路径、图层名称、类型）并返回。
    """
    import os
    
    script_path = request.script_path
    
    # 验证脚本路径
    if not os.path.exists(script_path):
        raise HTTPException(
            status_code=404,
            detail=f"脚本文件不存在: {script_path}"
        )
    
    if not script_path.endswith('.py'):
        raise HTTPException(
            status_code=400,
            detail="只支持 .py 脚本文件"
        )
    
    try:
        # 读取脚本内容
        with open(script_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        # 使用 LLM 提取图层信息
        print(f"📝 正在从脚本中分析图层信息: {script_path}")
        extracted_layers = _extract_layers_with_llm(code)
        print(f"   找到 {len(extracted_layers)} 个图层")
        
        # 验证提取的图层文件是否存在，并转换为 Web 可显示格式
        output_files = []
        for layer in extracted_layers:
            file_path = layer.get("path", "")
            if file_path and os.path.exists(file_path):
                layer_name = layer.get("name", os.path.basename(file_path))
                
                # 使用统一的格式转换函数处理所有文件类型
                convert_result = _convert_to_web_format(file_path)
                
                if convert_result.get("success"):
                    output_path = convert_result.get("path", file_path)
                    file_stat = os.stat(output_path) if os.path.exists(output_path) else os.stat(file_path)
                    
                    if convert_result.get("web_compatible"):
                        # Web 可显示
                        layer_info = {
                            "name": layer_name,
                            "path": output_path,
                            "url": _get_url_for_path(output_path),
                            "type": convert_result.get("type", "vector"),
                            "size": file_stat.st_size,
                            "original_path": file_path if output_path != file_path else None,
                            "web_compatible": True,
                        }
                        # 栅格图层需要包含 bounds 和 format
                        if convert_result.get("bounds"):
                            layer_info["bounds"] = convert_result.get("bounds")
                        if convert_result.get("format"):
                            layer_info["format"] = convert_result.get("format")
                        output_files.append(layer_info)
                    else:
                        # 仅 QGIS 可查看
                        output_files.append({
                            "name": layer_name,
                            "path": file_path,
                            "url": "",
                            "type": convert_result.get("type", "vector"),
                            "size": file_stat.st_size,
                            "qgis_only": True,
                            "web_compatible": False,
                            "message": convert_result.get("message")
                        })
        
        # 生成图层信息（供前端使用）
        layers = []
        for file in output_files:
            if not file.get("qgis_only"):
                layers.append({
                    "name": file["name"],
                    "file_url": file["url"],
                    "type": file["type"]
                })
        
        return ExecuteCodeResponse(
            success=True,
            message=f"成功从脚本加载 {len(layers)} 个可显示图层（共找到 {len(extracted_layers)} 个图层）",
            output_files=output_files,
            layers=layers
        )
    
    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        return ExecuteCodeResponse(
            success=False,
            message="加载图层失败",
            error=error_detail
        )
