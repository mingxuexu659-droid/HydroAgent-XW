# -*- coding: utf-8 -*-
"""
Code Generator Module

Generates QGIS spatial analysis code based on user requirements and data information.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config, get_config
from .llm_client import LLMClient
from .algorithm_helper import AlgorithmHelper, search_algorithms_by_keywords
from .intent_analyzer import TaskIntent, DataRequirement, AnalysisRequirement


class CodeGenerator:
    """
    QGIS Code Generator
    
    Generates executable PyQGIS code based on user requirements, data metadata and analysis requirements.
    """
    
#     SYSTEM_PROMPT = """你是一个专业的QGIS Processing框架专家和PyQGIS代码开发专家。你的任务是根据用户需求生成可以在QGIS中直接运行的Python空间分析代码。

# 你擅长：
# 1. 使用QGIS Processing框架进行空间分析
# 2. 使用PyQGIS API操作矢量和栅格数据
# 3. 编写高质量、可维护的地理空间处理代码
# 4. 正确处理坐标系统、几何类型等地理数据特性

# 代码要求：
# 1. 所有路径使用绝对路径，统一使用正斜杠（/）作为路径分隔符
# 2. 代码可以直接在QGIS Python控制台中运行
# 3. 所有processing.run()调用中的参数都有有效值
# 4. 代码包含必要的注释和错误处理
# 5. 使用正确的算法ID和参数，参考提供的算法文档

# ⚠️ 坐标系单位注意事项（非常重要）：
# - 如果输入数据是 EPSG:4326（WGS84经纬度），距离单位是**度**，不是米！
# - 对于以米为单位的缓冲区分析，必须先将数据重投影到投影坐标系（如 EPSG:3857 或当地 UTM）
# - 推荐流程：使用 `native:reprojectlayer` 重投影 → 执行缓冲区分析 → 可选重投影回 EPSG:4326
# """

#     CODE_GENERATION_PROMPT_TEMPLATE = """请根据以下信息生成QGIS空间分析Python代码：

# ## 用户需求
# {user_requirement}

# ## 输入数据信息
# {data_metadata}

# ## 分析任务
# {analysis_tasks}

# ## 参考算法文档
# {algorithm_docs}

# ## 输出要求
# 1. 生成可以直接在QGIS Python控制台中运行的代码
# 2. 所有路径都是绝对路径，使用正斜杠（/）
# 3. 输出文件保存到指定目录：{output_dir}
# 4. 将输出图层加载到QGIS GUI中 - `QgsProject.instance().addMapLayer()`
# 5. 代码结构清晰，包含必要的注释
# 6. 处理可能的错误情况
# 7. **必要的模块导入**
#    - from qgis.core import QgsVectorLayer, QgsRasterLayer, QgsProject, QgsCoordinateReferenceSystem
#    - import processing
#    - 其他所需库（如 os、geopandas、numpy、rasterio、scipy 等）

# ## ⚠️ 坐标系处理（必须遵守）
# 如果输入数据是 EPSG:4326 且需要使用米为单位的距离参数（如缓冲区），必须：
# 1. 先重投影到投影坐标系：`processing.run("native:reprojectlayer", {{'INPUT': layer, 'TARGET_CRS': 'EPSG:3857', 'OUTPUT': 'memory:'}})`
# 2. 在投影坐标系下执行空间分析（距离单位为米）
# 3. 可选：将结果重投影回 EPSG:4326

# **重要：只输出Python代码，不要包含markdown代码块标记。直接以代码开始。**

# 现在请生成代码："""


    SYSTEM_PROMPT = """You are an excellent QGIS expert. Please generate Python code that can be executed directly in the QGIS Python Console or within a QGIS plugin environment.

You must strictly follow the rules below:

## Forbidden elements
- **Do NOT include QgsApplication initialization code under any circumstances**
  - Do not include:
    - `qgs = QgsApplication([], True/False)`
    - `qgs.initQgis()`
- Do not use relative paths
- **Do NOT use `gdal:polygonize`** on any large raster (imagery OR classification result) — millions of polygons, will crash. For area statistics, use numpy pixel counting instead.
- **Do NOT use `sagang:supportvectormachineclassificationvigra`** — this algorithm does not exist and will cause a crash. Use `sagang:supportvectormachineclassification` instead.
- **Do NOT use `sagang:*` for raster statistics** — SAGA algorithms frequently crash (0xC0000005). Use `native:rasterlayerstatistics` or numpy instead.

## Required elements
1. **Necessary module imports**
   - from qgis.core import QgsVectorLayer, QgsRasterLayer, QgsProject
   - import processing
   - Other required libraries (such as os, geopandas, numpy, rasterio, scipy, etc.)
2. **All paths are absolute paths, using forward slashes (/).**
3. **Create output directories before saving files**
   - Use `os.makedirs(output_dir, exist_ok=True)` before saving any files
4. **Select the appropriate layer class based on input file type**
   - Vector data (.shp / .geojson / ...) → `QgsVectorLayer`
   - Raster data (.tif / ...) → `QgsRasterLayer`
5. **Generate output paths (must be absolute paths)**
   - **Use GeoJSON format (.geojson) for vector output files** to enable web visualization
6. **You must complete both of the following tasks:**
   a) Save the final processing result to disk (via the `OUTPUT` parameter)  
   b) Load the output layer into the QGIS GUI  
      - **IMPORTANT**: When `OUTPUT` is a file path (not `'memory:'`), `processing.run()` returns a **file path string**, NOT a layer object.
      - You MUST load the output file first: `result_layer = QgsVectorLayer(output_path, "Layer Name", "ogr")`
      - Then add to project: `QgsProject.instance().addMapLayer(result_layer)`
7. The code must include appropriate comments and have a clear structure.
8. For buffer/distance operations, EPSG:4326 uses **degrees** (not meters). You MUST reproject to EPSG:3857 first using `native:reprojectlayer`, then perform distance operations in meters.
9. **Prefer `native:*` algorithms** (e.g., `native:buffer`, `native:clip`, `native:intersection`, `native:dissolve`) for common operations.
10. **Use `'OUTPUT': 'memory:'` for intermediate results**; only save final output to file.
11. For random points inside polygons, use `native:randompointsinpolygons`.
12. **Sentinel-2 12-band: B4=Red, B8=NIR, B11=SWIR1, B3=Green**. `_boundary.tif` = RAW imagery, NOT indices.
   In `native:rastercalc` use actual layer name (NOT literal `{layer}`): `f'("{name}@8" - "{name}@4") / ("{name}@8" + "{name}@4" + 0.0001)'` where `name=layer.name()`. NDBI: @11,@8; NDWI: @3,@8. For multi-temporal diff, compute index from EACH image first, then diff single-band outputs.
15. **Area statistics**: use `numpy` to count pixels per class from the classification array, then convert to km² with rule 16. Do NOT polygonize.
16. **Area for EPSG:4326**: `import math; lat_rad=math.radians(abs(gt[3])); area_km2 = count * (abs(gt[1])*111320*math.cos(lat_rad)) * (abs(gt[5])*110540) / 1e6`. The cos(lat) corrects longitude shrinkage at high latitudes. NEVER omit it or use pixel_w*pixel_h directly.
17. **Land-use classification from NDVI/NDBI/NDWI**: `c=np.full(4); c[(ndvi>0.15)&(ndvi<=0.4)]=5; c[ndvi>0.5]=2; c[((ndbi-ndvi)>-0.2)&(ndvi<0.5)]=3; c[ndwi>0]=1; c[(band4==0)&(band8==0)]=0`. Later overwrites earlier, NO `~mask` exclusion.

Please output the Python code directly (do NOT include markers such as ```python```, output only the code itself).
"""

# 13. Set color rendering: continuous rasters → `QgsSingleBandPseudoColorRenderer`; classification rasters → `QgsPalettedRasterRenderer`; vectors → `QgsGraduatedSymbolRenderer`.
# 14. Land-use class numbering: 1=Water(blue), 2=Vegetation(green), 3=Built-up(red), 4=Bare Soil(brown), 5=Cropland(yellow).


    CODE_GENERATION_PROMPT_TEMPLATE = """Based on the following task description, please generate complete Python code.

## User Requirement
{user_requirement}

## Input Data Information
{data_metadata}

## Analysis Tasks
{analysis_tasks}

## Output Directory (MUST USE THIS PATH)
All output files must be saved to: `{output_dir}`
- Create the directory first: `os.makedirs("{output_dir}", exist_ok=True)`
- Save output files to this directory
- **IMPORTANT: Use GeoJSON format (.geojson) for vector output files** (e.g., "buffer_result.geojson", NOT "buffer_result.gpkg")
  - GeoJSON is required for web visualization

## Reference Algorithm Documentation
{algorithm_docs}

**Important: Output Python code only. Do NOT include markdown code block markers (such as ```python). Start directly with the code.**

Now please generate the code:"""

    def __init__(self, config: Optional[Config] = None, llm_client: Optional[LLMClient] = None):
        """
        Initialize code generator
        
        Args:
            config: Configuration object
            llm_client: LLM client
        """
        self.config = config or get_config()
        
        # Use code generator specific LLM config
        if llm_client:
            self.llm_client = llm_client
        else:
            # Get code generator specific config
            code_gen_llm_config = self.config.get_code_generator_llm_config()
            self.llm_client = LLMClient(self.config, llm_config_override=code_gen_llm_config)
        
        self.algorithm_helper = AlgorithmHelper(self.config)
    
    def generate(
        self,
        intent: TaskIntent,
        data_files: List[Dict[str, Any]],
        output_dir: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate spatial analysis code
        
        Args:
            intent: Task intent
            data_files: List of data file info, each element contains file path and metadata
            output_dir: Output directory
        
        Returns:
            Generated Python code string, None if generation fails
        """
        print(f"\n{'='*60}")
        print(f"Code Generation")
        print(f"{'='*60}")
        print(f"Using model: {self.llm_client.model}")
        
        if output_dir is None:
            output_dir = self.config.output.result_output_dir
        
        # Ensure output directory exists
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # Prepare data metadata
        data_metadata = self._format_data_metadata(data_files)
        
        # Prepare analysis task description
        analysis_tasks = self._format_analysis_tasks(intent)
        
        # Search relevant algorithm docs
        algorithm_docs = self._search_relevant_algorithms(intent)
        
        # Generate code
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_req_short = intent.original_query[:50] + "..." if len(intent.original_query) > 50 else intent.original_query
        
        prompt = self.CODE_GENERATION_PROMPT_TEMPLATE.format(
            user_requirement=intent.original_query,
            data_metadata=data_metadata,
            analysis_tasks=analysis_tasks,
            algorithm_docs=algorithm_docs,
            output_dir=output_dir.replace('\\', '/'),
            timestamp=timestamp,
            user_requirement_short=user_req_short,
        )
        
        print(f"Generating code...")
        
        response_text, token_stats = self.llm_client.chat(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.2  # Use lower temperature for more deterministic code
        )
        
        if response_text is None:
            print("❌ Code generation failed")
            return None
        
        # Extract code
        code = self.llm_client.extract_code_from_response(response_text)
        if code is None:
            # If cannot extract, try to use response directly
            code = response_text.strip()
        
        print(f"✓ Code generation successful")
        print(f"  Token usage: input={token_stats['input_tokens']}, output={token_stats['output_tokens']}")
        print(f"  Code lines: {len(code.splitlines())}")
        
        return code
    
    def generate_from_template(
        self,
        analysis_type: str,
        input_files: List[str],
        output_dir: str,
        parameters: Dict[str, Any] = None
    ) -> Optional[str]:
        """
        Generate code for common analysis based on templates
        
        Args:
            analysis_type: Analysis type (buffer, clip, intersection, etc.)
            input_files: List of input file paths
            output_dir: Output directory
            parameters: Analysis parameters
        
        Returns:
            Generated code
        """
        templates = {
            'buffer': self._template_buffer,
            'clip': self._template_clip,
            'intersection': self._template_intersection,
            'dissolve': self._template_dissolve,
            'ndvi': self._template_ndvi,
        }
        
        if analysis_type in templates:
            return templates[analysis_type](input_files, output_dir, parameters or {})
        
        return None
    
    def save_code(self, code: str, filename: Optional[str] = None) -> str:
        """
        Save generated code to file
        
        Args:
            code: Python code
            filename: Filename, auto-generated if None
        
        Returns:
            Saved file path
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"analysis_{timestamp}.py"
        
        output_path = Path(self.config.output.script_output_dir) / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(code)
        
        print(f"Code saved: {output_path}")
        return str(output_path)
    
    def _format_data_metadata(self, data_files: List[Dict[str, Any]]) -> str:
        """Format data metadata"""
        if not data_files:
            return "No input data info"
        
        lines = []
        for i, data in enumerate(data_files, 1):
            lines.append(f"\n### Data {i}: {data.get('name', 'Unknown')}")
            lines.append(f"- File path: {data.get('path', data.get('absolute_path', 'N/A'))}")
            lines.append(f"- Data format: {data.get('format', 'N/A')}")
            
            if 'geometry_type' in data:
                lines.append(f"- Geometry type: {data['geometry_type']}")
            if 'crs' in data:
                lines.append(f"- CRS: {data['crs']}")
            if 'feature_count' in data:
                lines.append(f"- Feature count: {data['feature_count']}")
            if 'attributes' in data:
                attrs = data['attributes']
                if isinstance(attrs, list):
                    attr_names = [a.get('name', str(a)) if isinstance(a, dict) else str(a) for a in attrs[:10]]
                    lines.append(f"- Attributes: {', '.join(attr_names)}")
            if 'bounds' in data:
                lines.append(f"- Bounds: {data['bounds']}")
            if 'description' in data:
                lines.append(f"- Description: {data['description']}")
        
        return '\n'.join(lines)
    
    def _format_analysis_tasks(self, intent: TaskIntent) -> str:
        """Format analysis tasks"""
        if not intent.analysis_requirements:
            return f"Analyze based on user requirement: {intent.original_query}"
        
        lines = []
        for i, ar in enumerate(intent.analysis_requirements, 1):
            lines.append(f"\n### Task {i}: {ar.analysis_type}")
            lines.append(f"- Description: {ar.description}")
            if ar.parameters:
                lines.append(f"- Parameters: {json.dumps(ar.parameters, ensure_ascii=False)}")
            if ar.expected_output:
                lines.append(f"- Expected output: {ar.expected_output}")
        
        return '\n'.join(lines)
    
    def _search_relevant_algorithms(self, intent: TaskIntent) -> str:
        """Search relevant QGIS algorithm docs"""
        # Extract keywords from analysis requirements
        keywords = []
        
        for ar in intent.analysis_requirements:
            keywords.append(ar.analysis_type)
            # Extract keywords from description
            desc_words = ar.description.split()
            keywords.extend([w for w in desc_words if len(w) > 2])
        
        # Extract keywords from original query
        analysis_keywords = [
            'buffer', 'clip', 'intersection', 'dissolve', 'merge',
            'raster', 'vector', 'ndvi', 'slope', 'aspect',
        ]
        for kw in analysis_keywords:
            if kw in intent.original_query.lower():
                keywords.append(kw)
        
        # Deduplicate
        keywords = list(set(keywords))
        
        if not keywords:
            return "No relevant algorithm docs"
        
        # Search algorithms
        algorithms = search_algorithms_by_keywords(keywords, max_results=5)
        
        if not algorithms:
            return "No relevant algorithm docs found"
        
        lines = []
        for alg in algorithms:
            lines.append(f"\n### {alg['algorithm_id']} ({alg['display_name']})")
            help_text = alg.get('help_text', '')
            if help_text:
                # Truncate to first 800 chars
                if len(help_text) > 800:
                    help_text = help_text[:800] + "..."
                lines.append(f"Documentation:\n{help_text}")
        
        return '\n'.join(lines)
    
    def _template_buffer(self, input_files: List[str], output_dir: str, params: Dict) -> str:
        """Buffer analysis template"""
        distance = params.get('distance', 1000)
        input_file = input_files[0] if input_files else "INPUT_FILE_PATH"
        
        return f'''# -*- coding: utf-8 -*-
"""Buffer Analysis Script"""
import os
import processing
from qgis.core import QgsVectorLayer

# Input data
input_layer = "{input_file.replace(chr(92), '/')}"

# Output directory
output_dir = "{output_dir.replace(chr(92), '/')}"
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, "buffer_result.geojson").replace("\\\\", "/")

# Execute buffer analysis
result = processing.run("native:buffer", {{
    'INPUT': input_layer,
    'DISTANCE': {distance},
    'SEGMENTS': 5,
    'END_CAP_STYLE': 0,
    'JOIN_STYLE': 0,
    'MITER_LIMIT': 2,
    'DISSOLVE': False,
    'OUTPUT': output_file
}})

print(f"Buffer analysis complete, output file: {{output_file}}")
'''
    
    def _template_clip(self, input_files: List[str], output_dir: str, params: Dict) -> str:
        """Clip analysis template"""
        input_file = input_files[0] if input_files else "INPUT_FILE_PATH"
        clip_layer = input_files[1] if len(input_files) > 1 else "CLIP_LAYER_PATH"
        
        return f'''# -*- coding: utf-8 -*-
"""Clip Analysis Script"""
import os
import processing
from qgis.core import QgsVectorLayer

# Input data
input_layer = "{input_file.replace(chr(92), '/')}"
clip_layer = "{clip_layer.replace(chr(92), '/')}"

# Output directory
output_dir = "{output_dir.replace(chr(92), '/')}"
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, "clip_result.geojson").replace("\\\\", "/")

# Execute clip analysis
result = processing.run("native:clip", {{
    'INPUT': input_layer,
    'OVERLAY': clip_layer,
    'OUTPUT': output_file
}})

print(f"Clip analysis complete, output file: {{output_file}}")
'''
    
    def _template_intersection(self, input_files: List[str], output_dir: str, params: Dict) -> str:
        """Intersection analysis template"""
        input_file = input_files[0] if input_files else "INPUT_FILE_PATH"
        overlay_layer = input_files[1] if len(input_files) > 1 else "OVERLAY_LAYER_PATH"
        
        return f'''# -*- coding: utf-8 -*-
"""Intersection Analysis Script"""
import os
import processing
from qgis.core import QgsVectorLayer

# Input data
input_layer = "{input_file.replace(chr(92), '/')}"
overlay_layer = "{overlay_layer.replace(chr(92), '/')}"

# Output directory
output_dir = "{output_dir.replace(chr(92), '/')}"
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, "intersection_result.geojson").replace("\\\\", "/")

# Execute intersection analysis
result = processing.run("native:intersection", {{
    'INPUT': input_layer,
    'OVERLAY': overlay_layer,
    'INPUT_FIELDS': [],
    'OVERLAY_FIELDS': [],
    'OVERLAY_FIELDS_PREFIX': '',
    'OUTPUT': output_file
}})

print(f"Intersection analysis complete, output file: {{output_file}}")
'''
    
    def _template_dissolve(self, input_files: List[str], output_dir: str, params: Dict) -> str:
        """Dissolve analysis template"""
        input_file = input_files[0] if input_files else "INPUT_FILE_PATH"
        field = params.get('field', '')
        
        return f'''# -*- coding: utf-8 -*-
"""Dissolve Analysis Script"""
import os
import processing
from qgis.core import QgsVectorLayer

# Input data
input_layer = "{input_file.replace(chr(92), '/')}"

# Output directory
output_dir = "{output_dir.replace(chr(92), '/')}"
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, "dissolve_result.geojson").replace("\\\\", "/")

# Execute dissolve analysis
result = processing.run("native:dissolve", {{
    'INPUT': input_layer,
    'FIELD': ['{field}'] if '{field}' else [],
    'OUTPUT': output_file
}})

print(f"Dissolve analysis complete, output file: {{output_file}}")
'''
    
    def _template_ndvi(self, input_files: List[str], output_dir: str, params: Dict) -> str:
        """NDVI calculation template"""
        input_file = input_files[0] if input_files else "INPUT_RASTER_PATH"
        red_band = params.get('red_band', 4)
        nir_band = params.get('nir_band', 8)
        
        return f'''# -*- coding: utf-8 -*-
"""NDVI Calculation Script"""
import os
import processing
from qgis.core import QgsRasterLayer

# Input data
input_raster = "{input_file.replace(chr(92), '/')}"

# Output directory
output_dir = "{output_dir.replace(chr(92), '/')}"
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, "ndvi_result.tif").replace("\\\\", "/")

# Load raster layer
layer = QgsRasterLayer(input_raster, "input_raster")
if not layer.isValid():
    raise Exception(f"Cannot load raster data: {{input_raster}}")

# NDVI formula: (NIR - RED) / (NIR + RED)
# Assuming red band is band {red_band}, NIR band is band {nir_band}
expression = f'({{layer.name()}}@{nir_band} - {{layer.name()}}@{red_band}) / ({{layer.name()}}@{nir_band} + {{layer.name()}}@{red_band})'

result = processing.run("qgis:rastercalculator", {{
    'EXPRESSION': expression,
    'LAYERS': [input_raster],
    'CELLSIZE': 0,
    'EXTENT': None,
    'CRS': None,
    'OUTPUT': output_file
}})

print(f"NDVI calculation complete, output file: {{output_file}}")
'''

