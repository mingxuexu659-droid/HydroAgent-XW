#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ============================================================================
# 🔧 关键修复：必须在任何导入之前设置 PROJ 环境变量
# 这解决了 pyproj "no database context specified" 错误
# ============================================================================
import os as _os
import sys as _sys

# 设置 PROJ 数据库路径（在导入 pyproj/sentinelhub 之前必须设置）
_proj_paths = [
    _os.path.join(_sys.prefix, 'Library', 'share', 'proj'),  # Windows conda
    _os.path.join(_sys.prefix, 'share', 'proj'),              # Linux/Mac conda
    _os.path.join(_os.environ.get('CONDA_PREFIX', ''), 'Library', 'share', 'proj'),
]
for _proj_path in _proj_paths:
    if _proj_path and _os.path.exists(_os.path.join(_proj_path, 'proj.db')):
        _os.environ['PROJ_LIB'] = _proj_path
        _os.environ['PROJ_DATA'] = _proj_path
        break
# ============================================================================

"""
统一地理查询引擎 (geo_query_engine.py)

这是 data_search_with_clip_online.py 的副本，已移动到 AutoGIS_main 文件夹。
提供统一的地理数据查询接口，支持多种数据源：
- 本地数据: 本地数据目录查询和裁剪
- 在线数据: OpenStreetMap (POI/路由) + Wikidata (知识图谱) + WorldKG (OSM语义) + 遥感数据

使用方法:
    # Linux/Mac:
    python3 geo_query_engine.py "你的查询"
    python3 geo_query_engine.py "你的查询" --download  # 下载结果为 GeoJSON
    
    # Windows:
    python geo_query_engine.py "你的查询"
    python geo_query_engine.py "你的查询" --download  # 下载结果为 GeoJSON

示例查询:
    # 本地数据查询
    python geo_query_engine.py "欧洲中部的河流数据"
    
    # 在线 POI 查询 + 下载
    python geo_query_engine.py "故宫附近500米的咖啡店" -d
    → downloaded_data/cafe_故宫_{timestamp}.geojson
    
    # 路由规划 + 下载
    python geo_query_engine.py "从天安门到故宫的步行路线" -d
    → downloaded_data/route_天安门_to_故宫_walking_{timestamp}.geojson
    
    # Wikidata 知识查询 + 下载
    python geo_query_engine.py "北京有哪些博物馆" -d
    → downloaded_data/museum_北京_{timestamp}.geojson

Windows 使用说明:
    - 代理配置: 自动检测 Windows 系统，使用端口 7897（Clash 混合端口）
    - 系统代理: 已自动禁用，只有当前脚本使用代理，不影响其他程序
    - 如果端口不同，运行 python detect_clash_ports.py 自动检测
    - 确保 Clash Verge 的"系统代理"保持关闭状态

集成四大数据源：
    1. 本地数据目录 (data_search_with_clip.py) - 静态测试数据 + 裁剪
    2. OpenStreetMap (Overpass API + OSM Routing) - 在线 POI 和路由
    3. Wikidata (SPARQL) - 语义知识图谱，用于复杂推荐和属性查询
    4. WorldKG (SPARQL) - OSM 语义知识图谱，OSM 实体的语义关系

通过 LLM 意图识别自动选择合适的数据源：
    - 本地数据查询: "欧洲中部的河流数据"
    - 空间邻近查询: "北京西单500米内的咖啡店" (OSM)
    - 路由导航查询: "从天安门到故宫的步行路线" (OSM)
    - 推荐查询: "推荐上海市中心的四星级酒店" (Wikidata + OSM)
    - 知识查询: "北京有哪些博物馆" (Wikidata)
    - 复杂查询: 自动拆解为多个子任务执行

输入：自然语言查询
输出：统一格式的查询结果 (本地文件路径 / POI 列表 / 路由信息 / 知识图谱结果)
       可选下载为 GeoJSON 文件，方便在 QGIS 中进行空间分析
"""

import json
import re
import os
import math
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta

# 尝试加载本地配置 (如 AMAP_API_KEY 等敏感信息)，该文件应加入 .gitignore 不提交到仓库
try:
    from config import local_settings  # type: ignore
except ImportError:
    try:
        import local_settings  # type: ignore
    except ImportError:
        local_settings = None

# 尝试加载系统配置 (包含云量阈值等遥感参数)
try:
    from spatial_analysis_system.config import get_config as get_system_config
    _system_config = get_system_config()
    DEFAULT_CLOUD_COVER_MAX = _system_config.remote_sensing.cloud_cover_max
except ImportError:
    DEFAULT_CLOUD_COVER_MAX = 70.0  # 默认值

# ============================================================================
# 代理/VPN 配置说明 (重要！修改代码前请阅读)
# ============================================================================
#
# 【各服务代理需求一览表】
# ┌─────────────────────┬──────────┬─────────────────────────────────────────┐
# │ 服务                 │ 需要代理 │ 说明                                    │
# ├─────────────────────┼──────────┼─────────────────────────────────────────┤
# │ Wikidata SPARQL     │ ✅ 必需  │ 在中国大陆无法直连，必须使用代理        │
# │ Nominatim           │ 🔶 推荐  │ 可直连但不稳定，建议用代理提高成功率    │
# │ Overpass API        │ 🔶 推荐  │ 同上，大范围查询时用代理更稳定          │
# │ OSRM (路由)         │ ❌ 不需要│ 可直连，用代理反而更慢，代码中已直连    │
# │ LinkedGeoData       │ 🔶 推荐  │ HTTP 服务，通常可直连，不稳定时用代理   │
# │ 阿里云 DashScope    │ ❌ 不需要│ 国内服务，直连即可                      │
# └─────────────────────┴──────────┴─────────────────────────────────────────┘
#
# 【代码实现细节】
# - WikidataAdapter: 使用 WIKIDATA_PROXY_URL 代理
# - OSMAdapter: 
#   - geocode/Overpass: 使用 OSM_PROXY_URL 代理
#   - calculate_route (OSRM): 直连，不使用代理 (proxies={'http': None, 'https': None})
# - WorldKGAdapter: 使用 WORLDKG_PROXY_URL 代理
# - LLMClient: 直连阿里云，无需代理
#
# 【修改提醒】
# 如果以后修改路由相关代码，请记住 OSRM 不需要代理！
# 如果添加新的外网服务，请先测试直连是否可行。
#
# ============================================================================

# ============================================================================
# 代理配置说明
# ============================================================================
# 设置为 None 表示不使用代理，设置为代理地址字符串则启用代理
# 
# 💡 代理会在启动时自动检测和切换到可用节点
# 💡 如果代理不可用，会自动尝试其他节点
# ============================================================================

# ============================================================================
# Windows/Linux 跨平台代理配置
# ============================================================================
# Windows 默认端口: 7897 (混合端口，HTTP 和 SOCKS5 共用)
# Linux 默认端口: 7890 (HTTP), 7891 (SOCKS5)
# 如果端口不同，请运行 python detect_clash_ports.py 自动检测
# ============================================================================
import platform
GLOBAL_PROXY_URL = os.environ.get("AUTOGIS_PROXY_URL", "")
CLASH_API_URL = os.environ.get("AUTOGIS_CLASH_API_URL", "")

# 各服务代理配置 (可根据需要单独调整)
WIKIDATA_PROXY_URL = GLOBAL_PROXY_URL  # Wikidata SPARQL - 必须用代理
OSM_PROXY_URL = GLOBAL_PROXY_URL       # Nominatim/Overpass - 推荐用代理 (OSRM 在代码中已设为直连)
WORLDKG_PROXY_URL = GLOBAL_PROXY_URL   # LinkedGeoData - 推荐用代理
USGS_PROXY_URL = None                  # 🆕 USGS API - 直连更稳定 (代理反而可能失败)

# 禁用系统代理，只让当前脚本使用代理（Windows 兼容）
os.environ.setdefault('NO_PROXY', '*')
os.environ.setdefault('no_proxy', '*')


# ============================================================================
# 代理自动检测和切换管理器
# ============================================================================
class ProxyManager:
    """代理管理器 - 自动检测和切换到可用节点"""
    
    def __init__(self, proxy_url: str = GLOBAL_PROXY_URL, api_url: str = CLASH_API_URL):
        self.proxy_url = proxy_url
        self.api_url = api_url
        self.current_node = None
    
    def check_and_switch(self, timeout: int = 5) -> bool:
        """
        检测代理是否可用，如果不可用则自动切换节点（快速版）
        
        Returns:
            True 如果找到可用节点，False 如果所有节点都不可用
        """
        # 使用快速测试 URL
        test_url = "https://httpbin.org/ip"
        
        # 1. 先测试当前节点
        if self._test_proxy_quick(test_url, timeout):
            return True
        
        # 2. 获取节点并找第一个可用的（不排序，直接找）
        try:
            nodes = self._get_proxy_nodes()
        except:
            return False
        
        # 3. 直接测试几个常见可用节点，找到立即切换
        priority_keywords = ['HK', 'JP', 'TW', 'US', 'SG']
        candidates = []
        for node in nodes[:15]:
            if node in ['DIRECT', 'REJECT', 'PASS'] or '剩余' in node or '自动' in node:
                continue
            for kw in priority_keywords:
                if kw in node:
                    candidates.append(node)
                    break
        
        # 4. 快速切换测试（只测 3 个）
        for node in candidates[:3]:
            if self._switch_node(node):
                import time
                time.sleep(0.2)
                if self._test_proxy_quick(test_url, timeout):
                    print(f"   Switched to: {node}")
                    self.current_node = node
                    return True
        
        return False
    
    def _test_proxy_quick(self, url: str, timeout: int) -> bool:
        """快速测试代理是否可用"""
        try:
            response = requests.get(
                url,
                proxies={'http': self.proxy_url, 'https': self.proxy_url},
                timeout=timeout,
                headers={'User-Agent': 'GeoQueryEngine/1.0'}
            )
            return response.status_code == 200
        except:
            return False
    
    def _get_proxy_nodes(self) -> list:
        """获取所有代理节点"""
        try:
            response = requests.get(f"{self.api_url}/proxies/GLOBAL", timeout=5)
            data = response.json()
            return data.get('all', [])
        except:
            return []
    
    def _test_node_delay(self, node: str) -> int:
        """测试节点延迟"""
        import urllib.parse
        try:
            encoded = urllib.parse.quote(node)
            response = requests.get(
                f"{self.api_url}/proxies/{encoded}/delay?timeout=3000&url=http://www.gstatic.com/generate_204",
                timeout=5
            )
            data = response.json()
            return data.get('delay', 99999)
        except:
            return 99999
    
    def _switch_node(self, node: str) -> bool:
        """切换到指定节点"""
        try:
            response = requests.put(
                f"{self.api_url}/proxies/GLOBAL",
                json={"name": node},
                timeout=5
            )
            return response.status_code == 204
        except:
            return False
    
    def get_current_node(self) -> str:
        """获取当前节点"""
        try:
            response = requests.get(f"{self.api_url}/proxies/GLOBAL", timeout=5)
            data = response.json()
            return data.get('now', 'UNKNOWN')
        except:
            return 'UNKNOWN'


# 全局代理管理器实例
_proxy_manager = None
_proxy_switch_attempted = False  # 标记是否已尝试切换

def get_proxy_manager() -> ProxyManager:
    """获取代理管理器单例"""
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager()
    return _proxy_manager


def proxy_request(method: str, url: str, proxy_url: str = None, 
                  timeout: int = 30, max_retries: int = 1,
                  auto_switch: bool = True, **kwargs) -> requests.Response:
    """
    通用代理请求函数 - 支持自动切换代理节点
    
    Args:
        method: HTTP 方法 ('get' 或 'post')
        url: 请求 URL
        proxy_url: 代理地址（None 表示直连）
        timeout: 超时时间（秒）
        max_retries: 最大重试次数
        auto_switch: 是否自动切换代理节点
        **kwargs: 传递给 requests 的其他参数
        
    Returns:
        requests.Response 对象
        
    Raises:
        requests.exceptions.RequestException: 所有尝试都失败时抛出
    """
    global _proxy_switch_attempted
    
    # 设置默认 headers
    if 'headers' not in kwargs:
        kwargs['headers'] = {}
    if 'User-Agent' not in kwargs['headers']:
        kwargs['headers']['User-Agent'] = 'GeoQueryEngine/1.0 (Educational Project)'
    
    # 设置代理
    proxies = {'http': proxy_url, 'https': proxy_url} if proxy_url else None
    
    last_error = None
    request_func = requests.get if method.lower() == 'get' else requests.post
    
    for retry in range(max_retries + 1):
        try:
            response = request_func(url, proxies=proxies, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except (requests.exceptions.ProxyError, 
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_error = e
            
            # 尝试自动切换代理（只切换一次）
            if auto_switch and proxy_url and not _proxy_switch_attempted:
                _proxy_switch_attempted = True
                proxy_mgr = get_proxy_manager()
                if proxy_mgr.check_and_switch():
                    # 切换成功，立即重试
                    try:
                        response = request_func(url, proxies=proxies, timeout=timeout, **kwargs)
                        response.raise_for_status()
                        return response
                    except Exception as retry_e:
                        last_error = retry_e
            
            # 最后一次重试前稍等
            if retry < max_retries:
                import time
                time.sleep(0.5)
                
        except requests.exceptions.HTTPError as e:
            # HTTP 错误（如 403, 404）不重试
            raise e
    
    # 所有尝试都失败
    raise last_error or requests.exceptions.RequestException("Request failed")


def reset_proxy_switch_flag():
    """重置代理切换标记（每次新查询时调用）"""
    global _proxy_switch_attempted
    _proxy_switch_attempted = False
    ProxySession.reset_switch_flag()


class ProxySession(requests.Session):
    """
    代理感知的 Session - 在请求失败时自动切换代理节点
    
    继承自 requests.Session，添加自动代理切换功能
    """
    
    # 类级别标记，所有 ProxySession 实例共享
    _global_switch_attempted = False
    
    def __init__(self, proxy_url: str = None, auto_switch: bool = True):
        super().__init__()
        self.proxy_url = proxy_url
        self.auto_switch = auto_switch
        
        if proxy_url:
            self.proxies = {'http': proxy_url, 'https': proxy_url}
        
        self.headers.update({
            'User-Agent': 'GeoQueryEngine/1.0 (Educational Project)'
        })
    
    @classmethod
    def reset_switch_flag(cls):
        """重置代理切换标记"""
        cls._global_switch_attempted = False
    
    def request(self, method, url, **kwargs):
        """重写 request 方法，添加自动代理切换"""
        # 设置默认超时
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 30
        
        try:
            return super().request(method, url, **kwargs)
        except (requests.exceptions.ProxyError, 
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            # 尝试自动切换代理（只在所有 session 中切换一次）
            if self.auto_switch and self.proxy_url and not ProxySession._global_switch_attempted:
                ProxySession._global_switch_attempted = True
                proxy_mgr = get_proxy_manager()
                if proxy_mgr.check_and_switch():
                    # 切换成功，重试请求
                    try:
                        return super().request(method, url, **kwargs)
                    except Exception:
                        pass
            raise e


# 导入本地搜索器（从同目录导入）
try:
    from .data_search_with_clip import (
        SmartDataSearcherWithClip, StructuredQueryWithClip,
        SearchResult, ClipResult
    )
except ImportError:
    # 如果data_search_with_clip不存在，定义占位符类（向量数据库检索模式下不需要此功能）
    @dataclass
    class SearchResult:
        file_path: str = ""
        metadata: Dict[str, Any] = field(default_factory=dict)
    
    @dataclass
    class ClipResult:
        original_file: str = ""
        clipped_file: str = ""
        metadata: Dict[str, Any] = field(default_factory=dict)
    
    class SmartDataSearcherWithClip:
        """占位符类：本地数据搜索功能已由向量数据库检索替代"""
        def __init__(self, *args, **kwargs):
            # 允许实例化但不执行任何操作
            pass
        
        def search_and_clip(self, *args, **kwargs):
            """占位方法：返回空结果"""
            return {
                'results': [],
                'clip_results': [],
                'availability': {'is_available': False, 'warnings': ['本地搜索功能未启用（使用向量数据库检索）']}
            }
    
    class StructuredQueryWithClip:
        pass

# 导入LLM客户端配置
try:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config.local_settings import DASHSCOPE_API_KEY, QWEN_API_KEY
    DASHSCOPE_API_KEY = DASHSCOPE_API_KEY or QWEN_API_KEY
except ImportError:
    DASHSCOPE_API_KEY = None

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-max"

# 定义LLM客户端
class LLMClient:
    """LLM客户端"""
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        self.api_key = api_key or DASHSCOPE_API_KEY
        self.base_url = base_url or DASHSCOPE_BASE_URL
        self.model = model or DEFAULT_MODEL
        
        try:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        except ImportError:
            print("⚠️ openai library not installed, LLM features unavailable")
            self.client = None
    
    def chat(self, prompt: str, system_prompt: str = None, temperature: float = 0.3):
        """调用LLM进行对话"""
        if self.client is None:
            return None
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"❌ LLM call failed: {e}")
            return None
    
    def parse_json_response(self, response: str) -> Optional[Dict]:
        """解析LLM响应中的JSON"""
        import json
        import re
        
        if not response:
            return None
        
        try:
            # 尝试直接解析
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # 尝试从markdown代码块中提取JSON
        json_patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
            r'\{[\s\S]*\}'
        ]
        
        for pattern in json_patterns:
            match = re.search(pattern, response)
            if match:
                try:
                    json_str = match.group(1) if '```' in pattern else match.group(0)
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    continue
        
        return None


# ============================================================================
# 查询意图类型
# ============================================================================

class QueryIntent(Enum):
    """查询意图类型"""
    SPATIAL_PROXIMITY = "spatial_proximity"  # 空间邻近查询 (POI)
    POI_SEARCH = "poi_search"           # 区域 POI 搜索 (品牌门店/设施统计)
    ROUTING = "routing"                 # 路由导航查询
    RECOMMENDATION = "recommendation"   # 推荐查询 (多条件筛选，使用 Wikidata)
    KNOWLEDGE = "knowledge"             # 知识查询 (Wikidata 语义查询)
    WORLDKG = "worldkg"                 # WorldKG 语义查询 (OSM 语义关系) - 已弃用，改用 semantic_analysis
    SEMANTIC_ANALYSIS = "semantic_analysis"  # 🆕 语义分析 (WorldKG 本体类型统计)
    OSM_DATA = "osm_data"               # OSM 区域数据下载 (道路、建筑、底图等)
    REMOTE_SENSING_DATA = "remote_sensing_data"  # 🆕 遥感数据下载 (Sentinel-2, Landsat等)
    HYBRID = "hybrid"                   # 混合查询
    COMPLEX = "complex"                 # 复杂查询 (需要任务拆解)
    UNKNOWN = "unknown"                 # 未知意图


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class IntentAnalysis:
    """意图分析结果"""
    intent: QueryIntent
    confidence: float
    summary: str
    
    # 本地数据查询参数
    data_type: str = ""
    geographic_extent: List[str] = field(default_factory=list)
    target_region: str = ""
    needs_clip: bool = False
    
    # 空间邻近查询参数
    poi_type: str = ""              # POI 类型 (pharmacy, restaurant, etc.)
    reference_location: str = ""     # 参考位置 (酒店名、地址等) - 应保留原文，如 "Grand Hotel"
    radius_meters: int = 500         # 搜索半径
    
    # 🆕 国际位置上下文（用于国外地名识别）
    country: str = ""               # 国家名称 (Sweden, Germany, etc.) - 英文或原文
    city: str = ""                  # 城市名称 (Lund, Berlin, etc.) - 英文或原文
    
    # 区域 POI 搜索参数 (poi_search)
    search_region: str = ""          # 搜索区域 (北京、上海、Berlin)
    brand_name: str = ""             # 品牌名称 (星巴克|Starbucks)
    
    # 路由查询参数
    origin: str = ""                 # 起点
    destination: str = ""            # 终点
    transport_mode: str = "driving"  # 交通方式 (driving, walking, cycling)
    
    # 推荐查询参数
    facility_type: str = ""          # 设施类型
    criteria: List[str] = field(default_factory=list)  # 筛选条件
    location_context: str = ""       # 位置上下文 (市中心、远离高速等)
    
    # 知识查询参数 (Wikidata)
    entity_type: str = ""            # 实体类型 (hotel, museum, university, etc.)
    property_filters: Dict[str, Any] = field(default_factory=dict)  # 属性过滤 (stars: 5, etc.)
    location_filter: str = ""        # 位置过滤 (北京, 上海, etc.)
    entity_name: str = ""            # 🆕 直接查询的实体名称 (故宫, Eiffel Tower, etc.)
    
    # OSM 区域数据下载参数
    osm_region: str = ""             # 下载区域 (北京, Shanghai, etc.)
    osm_data_types: List[str] = field(default_factory=list)  # 数据类型 (roads, buildings, waterways, etc.)
    
    # 🆕 遥感数据下载参数
    satellite: str = ""              # 卫星类型 (sentinel-2, landsat-8, landsat-9, modis)
    time_range: str = ""             # 时间范围 (格式: "2024-01-01,2024-01-31" 或 "2024-01")
    cloud_cover_max: float = 0       # 最大云量百分比 (0-100)，0表示未指定，使用config.yaml配置
    bands: List[str] = field(default_factory=list)  # 波段选择 (如 ["B04", "B08"] 或 ["RGB"])
    processing: str = ""             # 处理类型 (NDVI, NDWI, RGB, false_color, 空=原始波段)
    remote_sensing_region: str = ""  # 下载区域 (北京, Germany, etc.)
    
    # 复杂查询参数 (任务拆解)
    sub_tasks: List[Dict[str, Any]] = field(default_factory=list)  # 子任务列表
    
    reasoning: str = ""              # 推理说明


@dataclass
class POIResult:
    """POI 查询结果"""
    osm_id: int
    name: str
    poi_type: str
    lat: float
    lon: float
    distance_meters: float = 0.0
    tags: Dict[str, str] = field(default_factory=dict)
    address: str = ""


@dataclass
class RouteResult:
    """路由查询结果"""
    origin: str
    destination: str
    distance_meters: float
    duration_seconds: float
    geometry: List[List[float]]  # [[lon, lat], ...]
    steps: List[Dict[str, Any]] = field(default_factory=list)
    transport_mode: str = "driving"


@dataclass
class WikidataEntity:
    """Wikidata 实体结果"""
    wikidata_id: str               # Q123456
    name: str                      # 实体名称
    name_en: str = ""              # 英文名称
    entity_type: str = ""          # 实体类型
    description: str = ""          # 描述
    lat: Optional[float] = None    # 纬度
    lon: Optional[float] = None    # 经度
    properties: Dict[str, Any] = field(default_factory=dict)  # 属性 (星级、评分等)
    wikipedia_url: str = ""        # 维基百科链接
    image_url: str = ""            # 图片链接


@dataclass
class SubTaskResult:
    """子任务执行结果"""
    task_id: int
    task_type: str                 # 任务类型 (poi, route, knowledge, etc.)
    description: str               # 任务描述
    success: bool = True
    result: Any = None             # 任务结果
    error: str = ""                # 错误信息


@dataclass
class UnifiedQueryResult:
    """统一查询结果"""
    query: str
    intent: IntentAnalysis
    source: str  # "local", "osm", "wikidata", "hybrid"
    
    # 本地数据结果
    local_results: List[SearchResult] = field(default_factory=list)
    clip_results: List[ClipResult] = field(default_factory=list)
    
    # OSM 结果
    poi_results: List[POIResult] = field(default_factory=list)
    route_result: Optional[RouteResult] = None
    
    # Wikidata 结果
    knowledge_results: List[WikidataEntity] = field(default_factory=list)
    
    # 🆕 遥感数据结果
    remote_sensing_data: Optional[str] = None  # 下载的遥感影像文件路径
    
    # 复杂查询的子任务结果
    sub_task_results: List[SubTaskResult] = field(default_factory=list)
    
    # 下载的文件
    downloaded_files: List[str] = field(default_factory=list)
    
    # 元数据
    timestamp: str = ""
    processing_time_ms: int = 0
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    message: str = ""  # 额外的消息/说明
    properties: Dict[str, Any] = field(default_factory=dict)  # 🆕 附加属性 (语义分析结果等)


# ============================================================================
# Intent Analysis Prompt
# ============================================================================

INTENT_ANALYSIS_PROMPT = """You are a geospatial query intent analysis expert. Please analyze the user's query intent.

## Supported Query Types

### 1. spatial_proximity (Spatial Proximity Query)
Query real-time POIs (Points of Interest) around a specific location. Requires a **clear reference point**.

**⚠️ Important: Rules for extracting international locations**
- If the user mentions foreign place names (e.g., Sweden, Germany, France), you must fill both country and city fields
- reference_location should be kept in original text (e.g., "Grand Hotel"), do not translate
- Combined for Nominatim query: "Grand Hotel, Lund, Sweden"

Examples:
- "Cafes within 500m of Xidan, Beijing" → reference_location="Xidan", city="Beijing", country=""
- "Pharmacies near Grand Hotel in Lund, Sweden" → reference_location="Grand Hotel", city="Lund", country="Sweden"
- "I need pharmacies within 1000m of the Grand Hotel in Lund, Sweden" → reference_location="Grand Hotel", city="Lund", country="Sweden", radius_meters=1000
- "Restaurants within 1km of the Bund, Shanghai" → reference_location="Bund", city="Shanghai", country=""
- "cafes near Eiffel Tower in Paris" → reference_location="Eiffel Tower", city="Paris", country="France"

### 2. poi_search (Regional POI Search) - Using Overpass API
Search for specific types or brands of POIs within a specified region. **Suitable for commercial brand stores and public facilities**.
**Important**: 
- Commercial chain brands (Starbucks, McDonald's, etc.) must use this type
- Public facilities (museums, libraries, parks, schools, etc.) are also recommended to use this type, as Overpass API is usually directly accessible without proxy
- **Supports property filtering**: Can filter by stars, opening hours, facilities, etc. through property_filters
Examples:
- "How many Starbucks in Beijing" -> poi_search (brand_name="Starbucks")
- "Luckin Coffee shops in Shanghai" -> poi_search (brand_name="Luckin")
- "McDonald's distribution in Chengdu" -> poi_search (brand_name="McDonald")
- "What museums are in Beijing" -> poi_search (poi_type="museum")
- "Libraries in Shanghai" -> poi_search (poi_type="library")
- "Parks in Hangzhou" -> poi_search (poi_type="park")
- "Gas stations in Nanjing" -> poi_search (poi_type="fuel")
- "Hospitals in Guangzhou" -> poi_search (poi_type="hospital")
- "5-star hotels in Guangzhou" -> poi_search (poi_type="hotel", property_filters with stars=5)
- "24-hour pharmacies in Shanghai" -> poi_search (poi_type="pharmacy", property_filters with opening_hours_24_7=true)
- "Cafes with WiFi in Beijing" -> poi_search (poi_type="cafe", property_filters with wifi=true)
- "Restaurants with parking in Nanjing" -> poi_search (poi_type="restaurant", property_filters with parking=true)

### 3. routing (Route Navigation Query)
Calculate the shortest/optimal path between two points.
Examples:
- "Walking route from Tiananmen to Forbidden City"
- "Driving route from Pudong Airport to the Bund"
- "Shortest path from Lund Cathedral to the monument"

### 4. recommendation (Recommendation Query) - Using Wikidata Knowledge Graph
Multi-criteria facility recommendation, requiring semantic property filtering (such as star rating, score, facility features, etc.).
Examples:
- "Recommend 4-star hotels in downtown Shanghai"
- "Recommend restaurants away from highway, near subway"
- "Recommend 5-star hotels near attractions in Beijing"

### 5. knowledge (Knowledge Query) - Using Wikidata Knowledge Graph
Query semantic properties and structured knowledge of entities. Supports two modes:

**Mode 1: Direct Entity Query** - Query information about a specific place/entity
- Trigger conditions: "history/introduction/info/background of XX"
- Use entity_name field
- Examples:
  - "Query history information of Forbidden City" → entity_name="Forbidden City"
  - "When was the Forbidden City built" → entity_name="Forbidden City"
  - "Introduction of Eiffel Tower" → entity_name="Eiffel Tower"
  - "History of Tsinghua University" → entity_name="Tsinghua University"

**Mode 2: Type + Location Query** - Query entity list of certain type at a location
- Trigger conditions: "What XX are in YY", "YY's XX" (XX is a type word like museum, hotel)
- Use entity_type + location_filter fields
- Examples:
  - "What museums are in Beijing" → entity_type="museum", location_filter="Beijing"
  - "What 5-star hotels are in Shanghai" → entity_type="hotel", location_filter="Shanghai"

**Note**: Commercial chain brand stores (Starbucks, McDonald's, etc.) are not in Wikidata, please use poi_search!

### 6. osm_data (OSM Region Data Download) - Get Real Geographic Data
Download real geographic data from OpenStreetMap (boundaries, roads, buildings, waterways, etc.).

**Must use osm_data when:**
1. Getting **real landmark/building boundaries** (Summer Palace, Forbidden City, Tsinghua University, etc.)
2. Downloading **real basemap data** for specified region
3. Explicitly mentions OSM/OpenStreetMap
4. Needs **precise, real** geographic data (not test data)

**⚠️ osm_region parameter extraction rules (very important):**
- Query "Get the boundary of **Summer Palace**" → osm_region="Summer Palace", osm_data_types=["boundaries"]
- Query "**Forbidden City** extent" → osm_region="Forbidden City", osm_data_types=["boundaries"]
- Query "**Tsinghua University** boundary" → osm_region="Tsinghua University", osm_data_types=["boundaries"]
- **Do not simplify "Beijing Summer Palace" to "Beijing"!** osm_region should be "Summer Palace" or "Beijing Summer Palace"

Examples (note osm_region values):
- "Get Summer Palace boundary" -> osm_region="Summer Palace", osm_data_types=["boundaries"]
- "Get Beijing Summer Palace boundary" -> osm_region="Summer Palace", osm_data_types=["boundaries"]
- "Download Forbidden City outline" -> osm_region="Forbidden City", osm_data_types=["boundaries"]
- "Tsinghua University extent" -> osm_region="Tsinghua University", osm_data_types=["boundaries"]
- "Please access OpenStreetMap and provide me Beijing basemap" -> osm_region="Beijing"
- "Download road data of Shanghai from OSM" -> osm_region="Shanghai", osm_data_types=["roads"]
- "Get building data of New York" -> osm_region="New York", osm_data_types=["buildings"]

### 7. semantic_analysis (Semantic Analysis) - WorldKG Semantic Enhancement and Type Statistics
Use WorldKG/LinkedGeoData to perform **semantic analysis** on regions, counting the distribution and proportion of various facilities.
**This is WorldKG's core advantage: mapping OSM tags to semantic ontology types, providing regional functional profiles.**

**Trigger conditions (any of the following):**
1. Explicitly mentions "semantic analysis", "functional analysis", "type statistics", "facility distribution"
2. Query "**analyze** facility **structure/composition/types** of a region"
3. Explicitly mentions "WorldKG", "LinkedGeoData"

Examples (note: both osm_region and location_filter should be filled with **specific place names**, not simplified to city names):
- "Analyze facility type distribution in Tsinghua University" → osm_region="Tsinghua University", location_filter="Tsinghua University"
- "What types of facilities are in Beijing Forbidden City" → osm_region="Beijing Forbidden City", location_filter="Beijing Forbidden City" (not "Beijing"!)
- "Compare facility functional structure of Summer Palace and Old Summer Palace" → osm_region="Summer Palace", location_filter="Summer Palace"
- "What is the main function of Shanghai Lujiazui area?" → osm_region="Shanghai Lujiazui", location_filter="Shanghai Lujiazui"
- "Statistics of facility types in Shanghai Lujiazui" → osm_region="Shanghai Lujiazui", location_filter="Shanghai Lujiazui"

**Important: Location parameters must be the specific places mentioned by user (e.g., "Beijing Forbidden City", "Tsinghua University"), not simplified city names (e.g., "Beijing", "Shanghai")**
**Note: Due to using real boundary filtering, returns facilities "inside" the region, not "around" or "nearby"**

**Note: If user just wants to "find restaurants/find cafes", should use poi_search not semantic_analysis.
semantic_analysis output focuses on "type statistics and distribution analysis", not specific POI lists.**

### 8. remote_sensing_data (Remote Sensing Data Download) - Sentinel-2 / Landsat
Download satellite remote sensing imagery data (Sentinel-2, Landsat-8/9, MODIS, etc.).

**Supported satellite types:**
- Sentinel-2: 10m resolution, 5-day revisit cycle
- Landsat-8/9: 30m resolution, 16-day revisit cycle
- MODIS: 250-1000m resolution, daily update

**Must use remote_sensing_data when:**
1. Explicitly mentions "remote sensing", "satellite imagery", "Sentinel", "Landsat"
2. Query "download XX imagery", "get XX satellite data"
3. Needs NDVI, NDWI and other vegetation/water indices
4. Needs time series imagery data

**Parameter extraction rules:**
- satellite: satellite type (sentinel-2, landsat-8, landsat-9)
- time_range: time range ("2024-01-01,2024-01-31" or "2024-01")
- cloud_cover_max: maximum cloud cover (0 if not mentioned by user, system will use configured default)
- processing: processing type (NDVI, NDWI, RGB, false_color, empty=raw bands)
- remote_sensing_region: download region (Beijing, Germany, etc.)

Examples:
- "Download Beijing Sentinel-2 imagery for January 2024" → remote_sensing_data (satellite="sentinel-2", time_range="2024-01", remote_sensing_region="Beijing")
- "Get Germany Landsat data for summer 2023, cloud cover less than 10%" → remote_sensing_data (satellite="landsat-8", time_range="2023-06-01,2023-08-31", cloud_cover_max=10, remote_sensing_region="Germany")
- "Download Shanghai NDVI data" → remote_sensing_data (satellite="sentinel-2", processing="NDVI", remote_sensing_region="Shanghai")
- "Get Summer Palace Sentinel-2 imagery for 2024" → remote_sensing_data (satellite="sentinel-2", time_range="2024", remote_sensing_region="Summer Palace")
- "Download Chengdu Landsat-9 data, cloud cover less than 5%" → remote_sensing_data (satellite="landsat-9", cloud_cover_max=5, remote_sensing_region="Chengdu")

### 9. hybrid (Hybrid Query)
Requires combining local data and online data.
Examples:
- "Find all schools in my research area" (requires local boundary + online POI)

### 10. complex (Complex Query) - Requires Task Decomposition
Complex queries requiring multi-step execution, combining multiple data sources.
Examples:
- "Find pharmacies within 500m of Grand Hotel in Lund, and plan walking route"
- "Subway stations near 5-star hotels in Beijing"
- "First find museums in Shanghai, then plan visiting route"

## User Query
{user_query}

## Please output JSON format intent analysis result (output JSON only, no other content):
{{
    "intent": "spatial_proximity/poi_search/routing/recommendation/knowledge/osm_data/semantic_analysis/remote_sensing_data/complex/hybrid/unknown",
    "confidence": confidence between 0.0 and 1.0,
    "summary": "One sentence summarizing user requirement",
    
    "poi_type": "If spatial_proximity or poi_search, fill POI type (keep user's original expression, e.g., ktv, museum, pharmacy, Starbucks), otherwise empty",
    "reference_location": "If spatial_proximity, fill reference location name (keep original, e.g., Grand Hotel, Eiffel Tower), otherwise empty",
    "city": "If spatial_proximity with foreign place names, fill city name (English or original, e.g., Lund, Berlin, Paris), otherwise empty",
    "country": "If spatial_proximity with foreign place names, fill country name (English or original, e.g., Sweden, Germany, France), otherwise empty",
    "radius_meters": If spatial_proximity, fill search radius (meters), default 500,
    
    "search_region": "If poi_search, fill search region name (e.g., Beijing, Shanghai, Berlin), otherwise empty",
    "brand_name": "If poi_search with specific brand, fill brand name (supports Chinese/English, e.g., 'Starbucks'), otherwise empty",
    
    "origin": "If routing, fill origin name/address, otherwise empty",
    "destination": "If routing, fill destination name/address, otherwise empty",
    "transport_mode": "If routing, fill transport mode (driving/walking/cycling), otherwise empty",
    
    "facility_type": "If recommendation, fill facility type, otherwise empty",
    "criteria": ["If recommendation, list filter criteria, e.g., '4-star', 'near subway'"],
    "location_context": "If recommendation, fill location context (e.g., 'downtown', 'away from highway')",
    
    "entity_name": "If knowledge and querying a specific entity's info (e.g., 'history of Forbidden City', 'Tsinghua University introduction'), fill entity name (Forbidden City, Tsinghua University), otherwise empty",
    "entity_type": "If knowledge (type+location mode), worldkg or poi_search, fill entity type (English, e.g., hotel, museum, university, restaurant)",
    "property_filters": "Property filter conditions (JSON object), supports: stars(1-5 hotel star rating), opening_hours_24_7(true), wifi(true), parking(true), wheelchair(true), takeaway(true), vegetarian(true), halal(true). Example: 5-star hotel fill stars:5",
    "location_filter": "If knowledge (type+location mode) or semantic_analysis, fill specific location (e.g., Beijing, Shanghai), otherwise empty",
    
    "osm_region": "If osm_data or semantic_analysis, fill specific region name (e.g., Beijing Forbidden City, Tsinghua University, Shanghai Lujiazui), **keep user's original complete place name**, otherwise empty",
    "osm_data_types": ["If osm_data, fill required data type list, e.g., roads/buildings/waterways/landuse/railways, otherwise empty array"],
    
    "satellite": "If remote_sensing_data, fill satellite type (sentinel-2, landsat-8, landsat-9), otherwise empty",
    "time_range": "If remote_sensing_data, fill time range (format: '2024-01-01,2024-01-31' or '2024-01'), otherwise empty",
    "cloud_cover_max": If remote_sensing_data and user explicitly mentions cloud cover limit, fill the percentage (0-100); otherwise 0,
    "bands": ["If remote_sensing_data, fill band list (e.g., ['B04', 'B08'] or ['RGB']), otherwise empty array"],
    "processing": "If remote_sensing_data, fill processing type (NDVI, NDWI, RGB, false_color, empty=raw bands), otherwise empty",
    "remote_sensing_region": "If remote_sensing_data, fill download region name (e.g., Beijing, Germany), otherwise empty",
    
    "sub_tasks": [
        {{
            "order": 1,
            "type": "spatial_proximity/routing/knowledge",
            "description": "Sub-task description",
            "depends_on": null or previous task order
        }}
    ],
    
    "reasoning": "Explain your intent judgment reasoning"
}}"""


# ============================================================================
# OSM 适配器 (Overpass API + OSRM + Nominatim)
# ============================================================================

class OSMAdapter:
    """OpenStreetMap 适配器"""
    
    # Overpass API 端点 (多个备用)
    OVERPASS_URL = "https://overpass-api.de/api/interpreter"
    OVERPASS_URLS = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter"
    ]
    # OSM 官方路由服务 (比 router.project-osrm.org 更稳定)
    # routed-foot (步行) 和 routed-bike (骑行) 通常更快
    # routed-car (驾车) 可能较慢，提供备用端点
    OSM_ROUTING_BASE = "https://routing.openstreetmap.de"
    # OSRM 备用端点 (当 OSM 官方端点不可用时)
    OSRM_FALLBACK_URL = "http://router.project-osrm.org"
    # Nominatim 地理编码 (多个备用端点)
    NOMINATIM_URLS = [
        "https://nominatim.openstreetmap.org",
        "https://nominatim.geocoding.ai",  # 备用镜像
    ]
    NOMINATIM_URL = "https://nominatim.openstreetmap.org"  # 默认
    
    # 🆕 高德地图 API (国内稳定，Nominatim/Overpass 备选)
    # 申请 Key: https://console.amap.com/dev/key/app
    AMAP_API_URL = "https://restapi.amap.com/v3/config/district"
    AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
    AMAP_POI_URL = "https://restapi.amap.com/v3/place/text"  # POI 关键字搜索
    AMAP_DIRECTION_URL = "https://restapi.amap.com/v3/direction/driving"  # 驾车路径规划
    AMAP_WALKING_URL = "https://restapi.amap.com/v3/direction/walking"  # 步行路径规划
    
    # OSRM 公共服务 (国际路径规划备选)
    OSRM_URL = "https://router.project-osrm.org/route/v1"
    
    # 🔧 GCJ-02 转 WGS-84 坐标转换参数
    # 高德/百度/腾讯使用 GCJ-02 (火星坐标)，与 WGS-84 有约 500-700m 偏移
    _GCJ02_A = 6378245.0
    _GCJ02_EE = 0.00669342162296594323
    
    # 常用地点坐标缓存 (备用方案，当 Nominatim 不可用时)
    LOCATION_CACHE = {
        # 北京
        "清华大学": {"lat": 40.0084, "lon": 116.3268},
        "北京大学": {"lat": 39.9869, "lon": 116.3059},
        "天安门": {"lat": 39.9054, "lon": 116.3976},
        "故宫": {"lat": 39.9163, "lon": 116.3972},
        "颐和园": {"lat": 39.9999, "lon": 116.2755},
        "北京南站": {"lat": 39.8652, "lon": 116.3785},
        "北京西站": {"lat": 39.8960, "lon": 116.3222},
        "首都机场": {"lat": 40.0799, "lon": 116.6031},
        # 上海
        "外滩": {"lat": 31.2304, "lon": 121.4903},
        "东方明珠": {"lat": 31.2397, "lon": 121.4998},
        "上海虹桥站": {"lat": 31.1944, "lon": 121.3328},
        # 南京
        "南京博物馆": {"lat": 32.0447, "lon": 118.8195},
        "南京航空航天大学": {"lat": 31.9395, "lon": 118.8586},
        "南京航空航天大学将军路校区": {"lat": 31.9395, "lon": 118.8586},
        "南京站": {"lat": 32.0906, "lon": 118.8068},
        "南京南站": {"lat": 31.9714, "lon": 118.8047},
        # 其他城市
        "广州塔": {"lat": 23.1063, "lon": 113.3245},
        "西湖": {"lat": 30.2421, "lon": 120.1386},
        "成都天府广场": {"lat": 30.6570, "lon": 104.0659},
    }
    
    # 🆕 国外国家/地区名称列表（中文名称）
    # 这些地名即使包含中文字符，也不应使用高德地图（高德主要面向中国）
    # 应优先使用 Nominatim 或 Photon API
    FOREIGN_COUNTRIES = {
        # 欧洲
        "德国", "法国", "英国", "意大利", "西班牙", "荷兰", "比利时", "瑞士", "奥地利", 
        "瑞典", "挪威", "丹麦", "芬兰", "波兰", "捷克", "匈牙利", "希腊", "葡萄牙",
        "爱尔兰", "冰岛", "卢森堡", "俄罗斯", "乌克兰", "白俄罗斯", "罗马尼亚", "保加利亚",
        # 亚洲（除中国）
        "日本", "韩国", "朝鲜", "印度", "巴基斯坦", "孟加拉", "泰国", "越南", "缅甸",
        "柬埔寨", "老挝", "马来西亚", "新加坡", "印度尼西亚", "菲律宾", "文莱",
        "蒙古", "哈萨克斯坦", "乌兹别克斯坦", "吉尔吉斯斯坦", "塔吉克斯坦", "土库曼斯坦",
        "阿富汗", "伊朗", "伊拉克", "沙特阿拉伯", "阿联酋", "卡塔尔", "科威特", "巴林",
        "阿曼", "也门", "约旦", "黎巴嫩", "叙利亚", "以色列", "巴勒斯坦", "土耳其",
        # 美洲
        "美国", "加拿大", "墨西哥", "巴西", "阿根廷", "智利", "秘鲁", "哥伦比亚", "委内瑞拉",
        "厄瓜多尔", "玻利维亚", "巴拉圭", "乌拉圭", "古巴", "牙买加", "巴哈马",
        # 大洋洲
        "澳大利亚", "新西兰", "斐济", "巴布亚新几内亚",
        # 非洲
        "埃及", "南非", "肯尼亚", "尼日利亚", "埃塞俄比亚", "摩洛哥", "阿尔及利亚",
        "突尼斯", "利比亚", "苏丹", "坦桑尼亚", "乌干达", "加纳", "安哥拉",
    }
    
    # POI 类型映射 (用户友好名称 -> OSM 标签)
    # 这是一个基础映射表，当找不到时会使用 LLM 动态推断
    POI_TYPE_MAPPING = {
        # ==================== 餐饮 ====================
        "restaurant": "amenity=restaurant", "餐厅": "amenity=restaurant", "饭店": "amenity=restaurant",
        "cafe": "amenity=cafe", "咖啡店": "amenity=cafe", "咖啡厅": "amenity=cafe", "咖啡馆": "amenity=cafe",
        "fast_food": "amenity=fast_food", "快餐": "amenity=fast_food", "快餐店": "amenity=fast_food",
        "bar": "amenity=bar", "酒吧": "amenity=bar",
        "pub": "amenity=pub", "酒馆": "amenity=pub",
        "food_court": "amenity=food_court", "美食广场": "amenity=food_court",
        "ice_cream": "amenity=ice_cream", "冰淇淋店": "amenity=ice_cream",
        "bakery": "shop=bakery", "面包店": "shop=bakery", "烘焙店": "shop=bakery",
        
        # ==================== 医疗 ====================
        "pharmacy": "amenity=pharmacy", "药店": "amenity=pharmacy", "药房": "amenity=pharmacy",
        "hospital": "amenity=hospital", "医院": "amenity=hospital",
        "clinic": "amenity=clinic", "诊所": "amenity=clinic", "卫生所": "amenity=clinic",
        "dentist": "amenity=dentist", "牙科": "amenity=dentist", "牙医": "amenity=dentist",
        "doctors": "amenity=doctors", "诊室": "amenity=doctors",
        "veterinary": "amenity=veterinary", "宠物医院": "amenity=veterinary", "兽医": "amenity=veterinary",
        
        # ==================== 住宿 ====================
        "hotel": "tourism=hotel", "酒店": "tourism=hotel", "宾馆": "tourism=hotel", "饭店住宿": "tourism=hotel",
        "hostel": "tourism=hostel", "青旅": "tourism=hostel", "青年旅社": "tourism=hostel",
        "motel": "tourism=motel", "汽车旅馆": "tourism=motel",
        "guest_house": "tourism=guest_house", "民宿": "tourism=guest_house", "客栈": "tourism=guest_house",
        "apartment": "tourism=apartment", "公寓": "tourism=apartment",
        
        # ==================== 购物 ====================
        "supermarket": "shop=supermarket", "超市": "shop=supermarket",
        "mall": "shop=mall", "商场": "shop=mall", "购物中心": "shop=mall", "shopping_mall": "shop=mall",
        "convenience": "shop=convenience", "便利店": "shop=convenience",
        "department_store": "shop=department_store", "百货": "shop=department_store", "百货商店": "shop=department_store",
        "clothes": "shop=clothes", "服装店": "shop=clothes", "衣服店": "shop=clothes",
        "electronics": "shop=electronics", "电器店": "shop=electronics", "数码店": "shop=electronics",
        "mobile_phone": "shop=mobile_phone", "手机店": "shop=mobile_phone",
        "books": "shop=books", "书店": "shop=books",
        "florist": "shop=florist", "花店": "shop=florist",
        "jewelry": "shop=jewelry", "珠宝店": "shop=jewelry", "首饰店": "shop=jewelry",
        "optician": "shop=optician", "眼镜店": "shop=optician",
        "sports": "shop=sports", "运动用品店": "shop=sports", "体育用品店": "shop=sports",
        
        # ==================== 交通 ====================
        "bus_station": "amenity=bus_station", "汽车站": "amenity=bus_station", "客运站": "amenity=bus_station",
        "bus_stop": "highway=bus_stop", "公交站": "highway=bus_stop", "公交车站": "highway=bus_stop",
        "subway": "station=subway", "地铁站": "station=subway", "地铁": "station=subway",
        "railway": "railway=station", "火车站": "railway=station", "高铁站": "railway=station",
        "airport": "aeroway=aerodrome", "机场": "aeroway=aerodrome", "飞机场": "aeroway=aerodrome",
        "parking": "amenity=parking", "停车场": "amenity=parking",
        "fuel": "amenity=fuel", "加油站": "amenity=fuel", "gas_station": "amenity=fuel",
        "charging_station": "amenity=charging_station", "充电站": "amenity=charging_station", "充电桩": "amenity=charging_station",
        "taxi": "amenity=taxi", "出租车站": "amenity=taxi",
        "bicycle_rental": "amenity=bicycle_rental", "共享单车": "amenity=bicycle_rental",
        "ferry_terminal": "amenity=ferry_terminal", "渡口": "amenity=ferry_terminal", "码头": "amenity=ferry_terminal",
        
        # ==================== 教育 ====================
        "school": "amenity=school", "学校": "amenity=school", "小学": "amenity=school", "中学": "amenity=school",
        "university": "amenity=university", "大学": "amenity=university", "高校": "amenity=university",
        "college": "amenity=college", "学院": "amenity=college",
        "kindergarten": "amenity=kindergarten", "幼儿园": "amenity=kindergarten",
        "driving_school": "amenity=driving_school", "驾校": "amenity=driving_school",
        "language_school": "amenity=language_school", "语言学校": "amenity=language_school",
        "music_school": "amenity=music_school", "音乐学校": "amenity=music_school",
        
        # ==================== 文化/旅游 ====================
        "museum": "tourism=museum", "博物馆": "tourism=museum",
        "gallery": "tourism=gallery", "美术馆": "tourism=gallery", "画廊": "tourism=gallery",
        "theatre": "amenity=theatre", "theater": "amenity=theatre", "剧院": "amenity=theatre", "剧场": "amenity=theatre",
        "cinema": "amenity=cinema", "电影院": "amenity=cinema", "影院": "amenity=cinema",
        "library": "amenity=library", "图书馆": "amenity=library",
        "zoo": "tourism=zoo", "动物园": "tourism=zoo",
        "aquarium": "tourism=aquarium", "水族馆": "tourism=aquarium", "海洋馆": "tourism=aquarium",
        "theme_park": "tourism=theme_park", "主题公园": "tourism=theme_park", "游乐园": "tourism=theme_park",
        "park": "leisure=park", "公园": "leisure=park",
        "garden": "leisure=garden", "花园": "leisure=garden", "植物园": "leisure=garden",
        "attraction": "tourism=attraction", "景点": "tourism=attraction", "旅游景点": "tourism=attraction",
        "viewpoint": "tourism=viewpoint", "观景台": "tourism=viewpoint", "观景点": "tourism=viewpoint",
        "monument": "historic=monument", "纪念碑": "historic=monument", "纪念馆": "historic=monument",
        "castle": "historic=castle", "城堡": "historic=castle",
        "ruins": "historic=ruins", "遗址": "historic=ruins", "古迹": "historic=ruins",
        "temple": "amenity=place_of_worship", "寺庙": "amenity=place_of_worship", "寺院": "amenity=place_of_worship",
        "church": "amenity=place_of_worship", "教堂": "amenity=place_of_worship",
        "mosque": "amenity=place_of_worship", "清真寺": "amenity=place_of_worship",
        
        # ==================== 体育/休闲 ====================
        "sports_centre": "leisure=sports_centre", "体育中心": "leisure=sports_centre", "体育馆": "leisure=sports_centre",
        "stadium": "leisure=stadium", "体育场": "leisure=stadium", "球场": "leisure=stadium",
        "swimming_pool": "leisure=swimming_pool", "游泳池": "leisure=swimming_pool", "游泳馆": "leisure=swimming_pool",
        "fitness_centre": "leisure=fitness_centre", "健身房": "leisure=fitness_centre", "健身中心": "leisure=fitness_centre",
        "golf_course": "leisure=golf_course", "高尔夫球场": "leisure=golf_course",
        "playground": "leisure=playground", "游乐场": "leisure=playground", "儿童乐园": "leisure=playground",
        
        # ==================== 金融/商务 ====================
        "bank": "amenity=bank", "银行": "amenity=bank",
        "atm": "amenity=atm", "ATM": "amenity=atm", "取款机": "amenity=atm",
        "bureau_de_change": "amenity=bureau_de_change", "货币兑换": "amenity=bureau_de_change",
        "post_office": "amenity=post_office", "邮局": "amenity=post_office", "邮政": "amenity=post_office",
        "office": "office=yes", "办公楼": "office=yes", "写字楼": "office=yes",
        
        # ==================== 公共服务 ====================
        "police": "amenity=police", "警察局": "amenity=police", "派出所": "amenity=police", "公安局": "amenity=police",
        "fire_station": "amenity=fire_station", "消防站": "amenity=fire_station", "消防局": "amenity=fire_station",
        "courthouse": "amenity=courthouse", "法院": "amenity=courthouse",
        "townhall": "amenity=townhall", "市政厅": "amenity=townhall", "政府": "amenity=townhall",
        "embassy": "amenity=embassy", "大使馆": "amenity=embassy", "领事馆": "amenity=embassy",
        "community_centre": "amenity=community_centre", "社区中心": "amenity=community_centre", "居委会": "amenity=community_centre",
        "toilet": "amenity=toilets", "厕所": "amenity=toilets", "公厕": "amenity=toilets", "卫生间": "amenity=toilets",
        
        # ==================== 电力/能源基础设施 ====================
        # 参考: https://jishuzhan.net/article/1994731667102171138
        "power_tower": "power=tower", "输电塔": "power=tower", "电塔": "power=tower", "高压塔": "power=tower",
        "power_pole": "power=pole", "电线杆": "power=pole", "电杆": "power=pole",
        "substation": "power=substation", "变电站": "power=substation", "变电所": "power=substation",
        "power_plant": "power=plant", "发电厂": "power=plant", "电厂": "power=plant", "发电站": "power=plant",
        "transformer": "power=transformer", "变压器": "power=transformer",
        "power_line": "power=line", "电力线": "power=line", "输电线": "power=line", "高压线": "power=line",
        "power_minor_line": "power=minor_line", "配电线": "power=minor_line", "低压线": "power=minor_line",
        "power_grid": "power=line", "电网": "power=line", "电网数据": "power=line",  # 电网整体用线路代表
        "power": "power=*",  # 所有电力设施
        "wind_turbine": "power=generator", "风力发电": "power=generator", "风电": "power=generator",
        "solar_panel": "power=generator", "太阳能": "power=generator", "光伏": "power=generator",
        
        # ==================== 娱乐/夜生活 ====================
        "karaoke": "amenity=karaoke_box", "ktv": "amenity=karaoke_box", "KTV": "amenity=karaoke_box", "卡拉OK": "amenity=karaoke_box",
        "nightclub": "amenity=nightclub", "夜店": "amenity=nightclub", "夜总会": "amenity=nightclub", "迪厅": "amenity=nightclub",
        "internet_cafe": "amenity=internet_cafe", "网吧": "amenity=internet_cafe", "网咖": "amenity=internet_cafe",
        "casino": "amenity=casino", "赌场": "amenity=casino",
        "escape_game": "leisure=escape_game", "密室逃脱": "leisure=escape_game", "密室": "leisure=escape_game",
        "bowling": "leisure=bowling_alley", "保龄球馆": "leisure=bowling_alley",
        "billiard": "leisure=billiard", "台球厅": "leisure=billiard", "台球馆": "leisure=billiard",
        "massage": "shop=massage", "按摩店": "shop=massage", "足疗": "shop=massage",
        "spa": "leisure=spa", "水疗": "leisure=spa", "温泉": "leisure=spa",
        "sauna": "leisure=sauna", "桑拿": "leisure=sauna",
        
        # ==================== 其他 ====================
        "toilet": "amenity=toilets", "厕所": "amenity=toilets", "公厕": "amenity=toilets", "卫生间": "amenity=toilets",
        "waste_disposal": "amenity=waste_disposal", "垃圾站": "amenity=waste_disposal",
        "recycling": "amenity=recycling", "回收站": "amenity=recycling",
        "vending_machine": "amenity=vending_machine", "自动售货机": "amenity=vending_machine",
        "photo_booth": "amenity=photo_booth", "照相亭": "amenity=photo_booth", "证件照": "amenity=photo_booth",
        "car_wash": "amenity=car_wash", "洗车店": "amenity=car_wash", "洗车": "amenity=car_wash",
        "laundry": "shop=laundry", "洗衣店": "shop=laundry", "干洗店": "shop=laundry",
        "hairdresser": "shop=hairdresser", "理发店": "shop=hairdresser", "美发": "shop=hairdresser", "发廊": "shop=hairdresser",
        "beauty": "shop=beauty", "美容院": "shop=beauty", "美容店": "shop=beauty",
        "pet_shop": "shop=pet", "宠物店": "shop=pet",
    }
    
    def __init__(self, timeout: int = 120, llm: 'LLMClient' = None, proxy_url: str = None, 
                 amap_key: str = None, output_dir: str = None):
        """
        初始化 OSM 适配器
        
        Args:
            timeout: 请求超时时间（秒）。区域 POI 查询（如"北京的星巴克"）
                     需要较长时间，建议至少 120 秒。
            llm: LLM 客户端，用于多语言地名解析
            proxy_url: 代理服务器地址（如果网络需要代理）
            amap_key: 🆕 高德地图 API Key (Nominatim 备选，国内稳定)
                      申请地址: https://console.amap.com/dev/key/app
            output_dir: 输出目录，用于保存边界文件等
        """
        self.timeout = timeout
        self.llm = llm  # 用于跨语言地名转换
        self.proxy_url = proxy_url
        self.output_dir = output_dir or "downloaded_data"
        self._region_name_cache = {}  # 缓存地名变体
        # 🆕 使用 ProxySession 支持自动代理切换
        self.session = ProxySession(proxy_url=proxy_url, auto_switch=True)
        # 🆕 端点健康状态缓存（避免重复尝试已知失败的端点）
        self._endpoint_health = {}  # {endpoint_url: {'available': bool, 'last_check': timestamp}}
        self._available_overpass_endpoints = None  # 缓存可用的 Overpass 端点
        self._no_available_endpoints = False  # 标记是否没有可用端点
        self._endpoint_check_interval = 300  # 5分钟重新检测一次
        
        # 🆕 高德地图 API Key 优先从 local_settings 读取，其次环境变量，最后使用构造参数
        if amap_key:
            self.amap_key = amap_key
        elif local_settings is not None and hasattr(local_settings, 'AMAP_API_KEY'):
            self.amap_key = getattr(local_settings, 'AMAP_API_KEY')
        else:
            self.amap_key = os.environ.get('AMAP_API_KEY')
    
    def _check_endpoint_health(self, endpoint_url: str, timeout: int = 2) -> bool:
        """
        🆕 快速检测端点是否可用（短超时）
        
        Args:
            endpoint_url: 端点 URL
            timeout: 检测超时时间（秒），默认2秒
            
        Returns:
            端点是否可用
        """
        import time
        current_time = time.time()
        
        # 检查缓存（避免频繁检测）
        if endpoint_url in self._endpoint_health:
            cached = self._endpoint_health[endpoint_url]
            if current_time - cached['last_check'] < self._endpoint_check_interval:
                return cached['available']
        
        # 发送简单的测试请求
        try:
            # 使用一个非常简单的 Overpass 查询来测试
            test_query = "[out:json][timeout:2];node(1);out;"
            response = requests.post(
                endpoint_url,
                data={'data': test_query},
                timeout=timeout,
                proxies={'http': None, 'https': None}  # 直连测试
            )
            available = response.status_code == 200
        except Exception:
            available = False
        
        # 更新缓存
        self._endpoint_health[endpoint_url] = {
            'available': available,
            'last_check': current_time
        }
        
        return available
    
    def _get_available_overpass_endpoints(self, force_refresh: bool = False) -> List[str]:
        """
        🆕 获取可用的 Overpass 端点列表（智能排序）
        
        策略：
        1. 首次使用时并行检测所有端点
        2. 缓存检测结果，避免重复检测
        3. 可用端点排在前面，不可用端点排在后面
        
        Args:
            force_refresh: 是否强制刷新（忽略缓存）
            
        Returns:
            排序后的端点列表（可用的在前）
        """
        import time
        import concurrent.futures
        
        # 使用缓存
        if not force_refresh and self._available_overpass_endpoints is not None:
            return self._available_overpass_endpoints
        
        print("   🔍 Detecting Overpass API endpoint availability...")
        
        available = []
        unavailable = []
        
        # 并行检测所有端点（提高速度，2秒超时）
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.OVERPASS_URLS)) as executor:
            future_to_url = {
                executor.submit(self._check_endpoint_health, url, 2): url 
                for url in self.OVERPASS_URLS
            }
            
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    if future.result():
                        available.append(url)
                        print(f"      ✓ {url[:50]}... available")
                    else:
                        unavailable.append(url)
                        print(f"      ✗ {url[:50]}... unavailable")
                except Exception:
                    unavailable.append(url)
                    print(f"      ✗ {url[:50]}... detection failed")
        
        # 🆕 只返回可用端点，不可用端点不再尝试（避免长时间等待）
        if available:
            self._available_overpass_endpoints = available
            self._no_available_endpoints = False
            print(f"   ✓ Found {len(available)} available endpoints")
        else:
            # 没有可用端点时，只保留一个用于快速失败（5秒超时）
            self._available_overpass_endpoints = [self.OVERPASS_URLS[0]]
            self._no_available_endpoints = True
            print("   ⚠️ All Overpass endpoints currently unavailable, will fail fast")
        
        return self._available_overpass_endpoints
    
    def _infer_city_with_llm(self, location: str) -> Optional[str]:
        """
        使用LLM推断地名所在的城市（用于提高高德地理编码的准确性）
        
        Args:
            location: 地名（如"清华大学"、"西湖"）
            
        Returns:
            城市名称（如"北京"、"杭州"），或None
        """
        if not self.llm:
            return None
        
        prompt = f"""请推断以下地名所在的城市名称。

地名：{location}

要求：
1. 只返回城市名称，如"北京"、"上海"、"杭州"等
2. 如果地名本身就是城市，返回该城市名
3. 如果无法确定，返回"unknown"
4. 只返回一个词，不要其他内容

示例：
- "清华大学" -> "北京"
- "西湖" -> "杭州"
- "外滩" -> "上海"
- "黄山" -> "黄山"
"""
        try:
            response = self.llm.chat(prompt, temperature=0.1)
            if response:
                city = response.strip().strip('"').strip("'")
                if city and city != "unknown" and len(city) <= 10:
                    return city
        except Exception:
            pass
        return None
    
    def _get_landmark_english_name(self, landmark_name: str) -> Optional[str]:
        """
        使用LLM获取地标的英文名称（用于Nominatim搜索）
        
        Args:
            landmark_name: 中文地标名称
            
        Returns:
            英文名称，或None
        """
        if not self.llm:
            return None
        
        prompt = f"""请将以下中文地名翻译成其在OpenStreetMap中使用的标准英文名称。

地名：{landmark_name}

要求：
1. 返回该地名在国际上通用的英文名称
2. 对于大学，使用官方英文名（如"清华大学"="Tsinghua University"）
3. 对于景点，使用常用英文名（如"故宫"="Forbidden City"）
4. 只返回英文名称，不要其他内容

示例：
- "清华大学" -> "Tsinghua University"
- "故宫" -> "Forbidden City"
- "西湖" -> "West Lake"
"""
        try:
            response = self.llm.chat(prompt, temperature=0.1)
            if response:
                english_name = response.strip().strip('"').strip("'")
                if english_name and len(english_name) > 2:
                    return english_name
        except Exception:
            pass
        return None
    
    def _get_region_name_variants(self, region_name: str) -> List[str]:
        """
        使用 LLM 生成多语言地名变体，保证跨语言泛化性
        
        例如:
        - "伦敦" -> ["London", "伦敦", "Greater London"]
        - "北京" -> ["北京市", "北京", "Beijing"]
        - "巴黎" -> ["Paris", "巴黎", "Île-de-France"]
        
        Args:
            region_name: 用户输入的地名
            
        Returns:
            地名变体列表（按优先级排序）
        """
        # Check cache
        if region_name in self._region_name_cache:
            return self._region_name_cache[region_name]
        
        # Default variants (rule-based)
        default_variants = [region_name]
        if not region_name.endswith(('市', '省', '区', '县', '州', 'City', 'Province')):
            default_variants.insert(0, f"{region_name}市")
        
        # If no LLM, use default rules
        if not self.llm:
            return default_variants
        
        # Use LLM to generate multilingual variants
        prompt = f"""Generate name variants for the place "{region_name}" that might be used in OpenStreetMap database.

Requirements:
1. Include the FULL ADMINISTRATIVE NAME with proper suffix (e.g., "Pudong" -> "浦东新区", "Haidian" -> "海淀区")
2. Include the English administrative name (e.g., "Pudong District", "Haidian District")
3. Include the local language name
4. For Chinese districts/areas, ALWAYS include the Chinese name with 区/新区/市/县 suffix
5. Sort by likelihood of appearing in OSM as an administrative boundary, most likely first

IMPORTANT: For district-level queries, prioritize names that will match administrative boundaries, NOT landmarks like airports or buildings.

Return ONLY a JSON array, no other content:
["most likely admin name", "second likely name", ...]

Examples:
- Input "Shanghai Pudong" -> ["浦东新区", "Pudong New Area", "Pudong District", "Shanghai Pudong"]
- Input "Beijing Haidian" -> ["海淀区", "Haidian District", "Beijing Haidian"]
- Input "北京" -> ["北京市", "Beijing", "北京"]
- Input "New York" -> ["New York City", "New York", "NYC"]
- Input "London" -> ["Greater London", "London", "City of London"]
"""
        
        try:
            response = self.llm.chat(prompt)
            if response:
                # Try to parse JSON array
                import json
                import re
                # Clean response (remove markdown code block markers)
                response = response.strip()
                if response.startswith('```'):
                    response = response.split('\n', 1)[1]
                if response.endswith('```'):
                    response = response.rsplit('\n', 1)[0]
                response = response.strip()
                
                # Handle multi-line responses - extract first valid JSON array
                # Try to find JSON array pattern
                json_match = re.search(r'\[.*?\]', response, re.DOTALL)
                if json_match:
                    response = json_match.group(0)
                
                variants = json.loads(response)
                if isinstance(variants, list) and len(variants) > 0:
                    # Ensure original name is also in the list
                    if region_name not in variants:
                        variants.append(region_name)
                    # Cache result
                    self._region_name_cache[region_name] = variants
                    print(f"   LLM place name resolution: {region_name} -> {variants[:3]}...")
                    return variants
        except Exception as e:
            print(f"   ⚠️ LLM place name resolution failed: {e}")
        
        # Fallback to default variants
        return default_variants
    
    def _get_osm_tag_for_poi(self, poi_type: str) -> str:
        """
        获取 POI 类型对应的 OSM 标签
        
        策略：
        1. 先查映射表（快速，无 API 调用）
        2. 找不到时使用 LLM 动态推断（保证泛化性）
        3. 缓存 LLM 推断结果
        
        Args:
            poi_type: 用户输入的 POI 类型（任意语言）
            
        Returns:
            OSM 标签，格式为 "key=value"，如 "amenity=restaurant"
        """
        poi_type_lower = poi_type.lower().strip()
        
        # 1. 先查映射表
        if poi_type_lower in self.POI_TYPE_MAPPING:
            return self.POI_TYPE_MAPPING[poi_type_lower]
        
        # 2. 检查缓存（之前 LLM 推断的结果）
        if not hasattr(self, '_poi_tag_cache'):
            self._poi_tag_cache = {}
        if poi_type_lower in self._poi_tag_cache:
            return self._poi_tag_cache[poi_type_lower]
        
        # 3. 使用 LLM 动态推断
        if self.llm:
            osm_tag = self._infer_osm_tag_with_llm(poi_type)
            if osm_tag:
                # 缓存结果
                self._poi_tag_cache[poi_type_lower] = osm_tag
                print(f"   LLM inferred OSM tag: {poi_type} -> {osm_tag}")
                return osm_tag
        
        # 4. 回退：假设是 amenity 类型
        default_tag = f"amenity={poi_type_lower}"
        print(f"   ⚠️ Unknown POI type, using default: {default_tag}")
        return default_tag
    
    def _infer_osm_tag_with_llm(self, poi_type: str) -> Optional[str]:
        """
        使用 LLM 推断 POI 类型对应的 OSM 标签
        
        Args:
            poi_type: 用户输入的 POI 类型
            
        Returns:
            OSM 标签，如 "tourism=museum"，或 None
        """
        if not self.llm:
            return None
        
        prompt = f"""你是 OpenStreetMap (OSM) 标签专家。请为以下 POI 类型推断正确的 OSM 标签。

POI 类型: "{poi_type}"

OSM 常用的标签前缀包括：
- amenity: 公共设施（餐厅、医院、学校、银行、警察局等）
- tourism: 旅游相关（酒店、博物馆、景点、动物园等）
- shop: 商店（超市、便利店、服装店等）
- leisure: 休闲设施（公园、体育馆、游泳池等）
- historic: 历史遗迹（古迹、城堡、纪念碑等）
- office: 办公场所
- healthcare: 医疗机构
- education: 教育机构

请直接返回一个 OSM 标签，格式为 "key=value"，不要其他内容。

示例：
- "书店" -> "shop=books"
- "游乐场" -> "leisure=playground"
- "消防站" -> "amenity=fire_station"
- "古庙" -> "amenity=place_of_worship"
- "滑雪场" -> "leisure=ski"
"""
        
        try:
            response = self.llm.chat(prompt)
            if response:
                # 清理响应
                tag = response.strip().strip('"').strip("'")
                # 验证格式
                if '=' in tag and len(tag.split('=')) == 2:
                    return tag
        except Exception as e:
            print(f"   ⚠️ LLM OSM tag inference failed: {e}")
        
        return None
    
    # -------------------------------------------------------------------------
    # 地理编码 (Nominatim)
    # -------------------------------------------------------------------------
    
    def geocode(self, location: str, get_bbox: bool = False, force_nominatim: bool = False) -> Optional[Dict[str, Any]]:
        """
        将地名/地址转换为坐标
        
        策略：
        1. 先查本地缓存（快速、可靠）
        2. 如果不是国际地名，尝试高德地图（国内更准确）
        3. 再尝试 Nominatim API（多端点）
        4. 最后使用 LLM 推断（保底）
        
        Args:
            location: 地名或地址
            get_bbox: 是否获取边界框 (用于区域查询)
            force_nominatim: 🆕 是否强制使用 Nominatim（国际地名时设为 True）
            
        Returns:
            {'lat': float, 'lon': float, 'bbox': [south, north, west, east]} 或 None
        """
        # 1. 先查本地缓存（只有不强制 Nominatim 时才检查）
        if not force_nominatim:
            location_clean = location.strip()
            if location_clean in self.LOCATION_CACHE:
                cached = self.LOCATION_CACHE[location_clean]
                return {
                    'lat': cached['lat'],
                    'lon': cached['lon'],
                    'display_name': location_clean
                }
            
            # 尝试部分匹配（如 "南京航空航天大学将军路校区" 匹配 "南京航空航天大学"）
            # 🔧 修复: 只在查询长度与缓存 key 长度相近时才使用部分匹配
            # 避免 "清华大学蒙民伟科技大楼南楼" 被错误匹配到 "清华大学"
            for key, cached in self.LOCATION_CACHE.items():
                # 只有当查询包含缓存 key 且长度差距不大时才匹配
                if key in location_clean:
                    # 如果查询比 key 长度多出太多字符(>50%)，说明是更具体的地点，不应使用缓存
                    if len(location_clean) <= len(key) * 1.5:
                        return {
                            'lat': cached['lat'],
                            'lon': cached['lon'],
                            'display_name': key
                        }
                # 完全包含的情况（查询是 key 的子串）
                elif location_clean in key:
                    return {
                        'lat': cached['lat'],
                        'lon': cached['lon'],
                        'display_name': key
                    }
        
        # 🆕 2. 如果强制使用 Nominatim（国际地名），直接跳过高德
        if force_nominatim:
            print(f"   🌐 Using Nominatim to query international place name: {location}")
            return self._geocode_with_nominatim(location, get_bbox)
        
        # 3. 对于中文地名，优先使用高德（更准确、更稳定、无需代理）
        # 但排除国外国家名称（高德地图主要面向中国，对国外地名识别不准确）
        is_foreign_country = location.strip() in self.FOREIGN_COUNTRIES or \
                            any(country in location for country in self.FOREIGN_COUNTRIES if len(country) <= len(location))
        
        if self.amap_key and self._is_chinese_text(location) and not is_foreign_country:
            amap_result = self._geocode_with_amap(location, get_bbox)
            if amap_result:
                return amap_result
        
        # 4. 尝试 Nominatim API（国外地名或高德失败时）
        nominatim_result = self._geocode_with_nominatim(location, get_bbox)
        if nominatim_result:
            return nominatim_result
        
        # 5. 最后尝试 LLM 推断坐标
        if self.llm:
            llm_result = self._geocode_with_llm(location)
            if llm_result:
                return llm_result
        
        print(f"   ⚠️ Cannot parse address: {location}")
        return None
    
    def _geocode_with_nominatim(self, location: str, get_bbox: bool = False, prefer_proxy: bool = True) -> Optional[Dict[str, Any]]:
        """
        🆕 使用 Nominatim API 进行地理编码（支持全球地名）
        
        Args:
            location: 地名或地址（如 "Grand Hotel, Lund, Sweden"）
            get_bbox: 是否获取边界框
            prefer_proxy: 是否优先使用代理（国际地名建议设为 True）
            
        Returns:
            {'lat': float, 'lon': float, 'display_name': str, 'bbox': [s,n,w,e]} 或 None
        """
        params = {
            'q': location,
            'format': 'json',
            'limit': 1
        }
        if get_bbox:
            params['polygon_geojson'] = 0
            params['extratags'] = 1
        
        # 尝试多个端点
        for nominatim_url in self.NOMINATIM_URLS:
            url = f"{nominatim_url}/search"
            
            # 根据 prefer_proxy 决定尝试顺序
            # 对于国际地名，优先使用代理（直连可能被校园网阻塞）
            proxy_order = [True, False] if prefer_proxy else [False, True]
            
            for use_proxy in proxy_order:
                try:
                    import requests as req_direct
                    if use_proxy:
                        response = self.session.get(url, params=params, timeout=15)
                    else:
                        response = req_direct.get(
                            url, params=params, timeout=8,
                            proxies={'http': None, 'https': None},
                            headers={'User-Agent': 'GeoQueryEngine/1.0 (Educational Project)'}
                        )
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    if data:
                        result = {
                            'lat': float(data[0]['lat']),
                            'lon': float(data[0]['lon']),
                            'display_name': data[0].get('display_name', location)
                        }
                        if 'boundingbox' in data[0]:
                            bb = data[0]['boundingbox']
                            result['bbox'] = [float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])]
                        print(f"   ✓ Nominatim parsed successfully: {result['display_name'][:60]}...")
                        return result
                        
                except Exception as e:
                    # 只在代理失败时打印警告
                    if use_proxy and prefer_proxy:
                        print(f"   ⚠️ Nominatim proxy query failed, trying direct connection...")
                    continue
        
        return None
    
    def _geocode_with_amap(self, location: str, get_bbox: bool = False, city: str = None) -> Optional[Dict[str, Any]]:
        """
        🆕 使用高德 API 进行地理编码（国内地名更准确、更稳定、无需代理）
        
        策略：
        1. 对于行政区划（省/市/县/区），使用 v3/config/district API 获取完整边界
        2. 对于其他地址，使用 v3/geocode/geo API
        
        Args:
            location: 地名或地址
            get_bbox: 是否获取边界框
            city: 城市名称（用于限定搜索范围，提高准确性）
            
        Returns:
            {'lat': float, 'lon': float, 'bbox': [south, north, west, east]} 或 None
        """
        if not self.amap_key:
            return None
        
        # 检查是否是行政区划名称（省/市/县/区）
        # 包含这些关键词的都视为行政区划
        admin_keywords = ['省', '市', '县', '区', '镇', '乡', '街道', '自治州', '自治县', '盟', '旗']
        is_admin_region = any(kw in location for kw in admin_keywords)
        
        # 🆕 使用LLM智能推断城市（提高覆盖率和鲁棒性）
        if not city and self.llm:
            city = self._infer_city_with_llm(location)
        
        try:
            # 🆕 对于行政区划，优先使用 district API（返回完整边界）
            if is_admin_region and get_bbox:
                district_result = self._geocode_admin_with_amap(location)
                if district_result:
                    return district_result
            
            # 使用普通地理编码 API
            params = {
                'key': self.amap_key,
                'address': location
            }
            # 🆕 添加城市参数以提高定位准确性
            if city:
                params['city'] = city
            
            response = requests.get(self.AMAP_GEOCODE_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') != '1' or not data.get('geocodes'):
                return None
            
            geocode = data['geocodes'][0]
            location_coords = geocode.get('location', '').split(',')
            
            if len(location_coords) != 2:
                return None
            
            gcj_lon, gcj_lat = float(location_coords[0]), float(location_coords[1])
            
            # 🔧 GCJ-02 转 WGS-84，使坐标在 QGIS/OpenStreetMap 中正确显示
            lon, lat = self._gcj02_to_wgs84(gcj_lon, gcj_lat)
            
            result = {
                'lat': lat,
                'lon': lon,
                'display_name': geocode.get('formatted_address', location),
                'source': 'AMap',
                'gcj02_lat': gcj_lat,  # 保留原始高德坐标（可选）
                'gcj02_lon': gcj_lon
            }
            
            # 如果请求边界框，从高德返回的矩形范围计算
            if get_bbox:
                # 高德返回的矩形范围（格式：左下角经度,左下角纬度;右上角经度,右上角纬度）
                rectangle = geocode.get('rectangle', '')
                if rectangle:
                    try:
                        parts = rectangle.split(';')
                        if len(parts) == 2:
                            bottom_left = parts[0].split(',')
                            top_right = parts[1].split(',')
                            if len(bottom_left) == 2 and len(top_right) == 2:
                                min_lon_gcj, min_lat_gcj = float(bottom_left[0]), float(bottom_left[1])
                                max_lon_gcj, max_lat_gcj = float(top_right[0]), float(top_right[1])
                                # 转换边界框坐标为 WGS-84
                                min_lon, min_lat = self._gcj02_to_wgs84(min_lon_gcj, min_lat_gcj)
                                max_lon, max_lat = self._gcj02_to_wgs84(max_lon_gcj, max_lat_gcj)
                                # 转换为 [south, north, west, east]
                                result['bbox'] = [min_lat, max_lat, min_lon, max_lon]
                    except Exception:
                        pass
                
                # 如果没有矩形范围，使用默认范围（约1km）
                if 'bbox' not in result:
                    delta = 0.005  # 约500米
                    result['bbox'] = [lat - delta, lat + delta, lon - delta, lon + delta]
            
            print(f"   🗺️ Gaode geocoding: {location} -> ({lat:.4f}, {lon:.4f}) [WGS-84]")
            return result
            
        except Exception as e:
            print(f"   ⚠️ Gaode geocoding failed: {str(e)[:50]}")
            return None
    
    def _geocode_admin_with_amap(self, location: str) -> Optional[Dict[str, Any]]:
        """
        🆕 使用高德行政区划 API 获取完整边界（适用于省/市/县/区）
        
        高德行政区划 API: https://restapi.amap.com/v3/config/district
        
        Args:
            location: 行政区划名称
            
        Returns:
            {'lat': float, 'lon': float, 'bbox': [south, north, west, east]} 或 None
        """
        import re
        
        try:
            # 🆕 高德行政区划 API 需要简化的关键词
            # 从完整地址提取各个行政区划单元
            keywords_to_try = [location]
            
            # 用非贪婪模式提取单个行政区划单元（省/市/县/区等）
            admin_pattern = r'([\u4e00-\u9fa5]+?(?:省|市|县|区|自治州|自治县|盟|旗|镇|乡|街道))'
            matches = re.findall(admin_pattern, location)
            if matches:
                # 优先使用最后一个（最具体的），如"宿松县"
                keywords_to_try = [matches[-1]] + keywords_to_try
            
            for keywords in keywords_to_try:
                params = {
                    'key': self.amap_key,
                    'keywords': keywords,
                    'subdistrict': 0,
                    'extensions': 'all'  # 返回边界坐标
                }
                
                response = requests.get(self.AMAP_API_URL, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                if data.get('status') == '1' and data.get('districts'):
                    break
            else:
                return None
            
            if data.get('status') != '1' or not data.get('districts'):
                return None
            
            district = data['districts'][0]
            center = district.get('center', '').split(',')
            
            if len(center) != 2:
                return None
            
            gcj_lon, gcj_lat = float(center[0]), float(center[1])
            # 🔧 GCJ-02 转 WGS-84
            lon, lat = self._gcj02_to_wgs84(gcj_lon, gcj_lat)
            
            result = {
                'lat': lat,
                'lon': lon,
                'display_name': district.get('name', location),
                'source': 'AMap (行政区划)',
                'level': district.get('level', 'unknown')
            }
            
            # 解析边界坐标，计算边界框
            polyline = district.get('polyline', '')
            if polyline:
                coords = []
                for seg in polyline.split('|'):
                    for pt in seg.split(';'):
                        if pt:
                            parts = pt.split(',')
                            if len(parts) == 2:
                                try:
                                    # 🔧 GCJ-02 转 WGS-84
                                    wgs_lon, wgs_lat = self._gcj02_to_wgs84(float(parts[0]), float(parts[1]))
                                    coords.append((wgs_lon, wgs_lat))
                                except ValueError:
                                    continue
                
                if coords:
                    lons = [c[0] for c in coords]
                    lats = [c[1] for c in coords]
                    # bbox 格式: [south, north, west, east]
                    result['bbox'] = [min(lats), max(lats), min(lons), max(lons)]
                    print(f"   🗺️ Gaode admin division: {location} ({district.get('level')}) -> ({lat:.4f}, {lon:.4f}) [WGS-84], boundary points: {len(coords)}")
                    return result
            
            # 如果没有边界，使用默认范围
            delta = 0.1  # 约10km
            result['bbox'] = [lat - delta, lat + delta, lon - delta, lon + delta]
            print(f"   🗺️ Gaode admin division: {location} -> ({lat:.4f}, {lon:.4f})")
            return result
            
        except Exception as e:
            print(f"   ⚠️ Gaode admin division query failed: {str(e)[:50]}")
            return None
    
    def search_poi_with_amap(self, city: str, poi_type: str = None, 
                              keywords: str = None, property_filters: Dict[str, Any] = None,
                              limit: int = 100) -> List['POIResult']:
        """
        🆕 使用高德 POI 搜索 API（Overpass 备选，国内更稳定）
        
        高德 POI 搜索 API: https://restapi.amap.com/v3/place/text
        
        Args:
            city: 城市/区县名称（如"宿松县"、"北京市"）
            poi_type: POI 类型（如"药店"、"餐厅"、"酒店"）
            keywords: 搜索关键词（可选，如品牌名称）
            property_filters: 属性过滤条件（高德支持有限，主要用于显示）
            limit: 返回数量限制（高德每页最多25条，会自动分页）
            
        Returns:
            POI 结果列表
        """
        if not self.amap_key:
            return []
        
        # 构建搜索关键词
        search_keywords = poi_type or ''
        if keywords:
            search_keywords = f"{keywords} {search_keywords}".strip()
        
        if not search_keywords:
            search_keywords = 'POI'  # 默认搜索
        
        print(f"   🗺️ Gaode POI search: searching '{search_keywords}' in {city}...")
        
        results = []
        page = 1
        max_pages = (limit + 24) // 25  # 高德每页最多25条
        
        while len(results) < limit and page <= max_pages:
            try:
                params = {
                    'key': self.amap_key,
                    'keywords': search_keywords,
                    'city': city,
                    'citylimit': 'true',  # 限制在指定城市内
                    'offset': 25,  # 每页数量
                    'page': page,
                    'extensions': 'all'
                }
                
                response = requests.get(self.AMAP_POI_URL, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                if data.get('status') != '1':
                    print(f"   ⚠️ Gaode POI search failed: {data.get('info', 'unknown error')}")
                    break
                
                pois = data.get('pois', [])
                if not pois:
                    break
                
                for poi in pois:
                    location_str = poi.get('location', '')
                    if not location_str or ',' not in location_str:
                        continue
                    
                    gcj_lon, gcj_lat = location_str.split(',')
                    # 🔧 GCJ-02 转 WGS-84
                    lon, lat = self._gcj02_to_wgs84(float(gcj_lon), float(gcj_lat))
                    
                    # 构建 tags（高德返回的扩展信息）
                    tags = {
                        'name': poi.get('name', ''),
                        'type': poi.get('type', ''),
                        'typecode': poi.get('typecode', ''),
                        'address': poi.get('address', ''),
                        'tel': poi.get('tel', ''),
                        'source': 'AMap'
                    }
                    
                    # 添加营业时间（如果有）
                    biz_ext = poi.get('biz_ext', {})
                    if biz_ext:
                        if biz_ext.get('open_time'):
                            tags['opening_hours'] = biz_ext.get('open_time')
                        if biz_ext.get('rating'):
                            tags['rating'] = biz_ext.get('rating')
                    
                    results.append(POIResult(
                        osm_id=int(poi.get('id', 0)) if poi.get('id', '').isdigit() else hash(poi.get('id', '')),
                        name=poi.get('name', '未命名'),
                        poi_type=poi_type or poi.get('type', 'unknown').split(';')[0],
                        lat=lat,  # 已转换为 WGS-84
                        lon=lon,  # 已转换为 WGS-84
                        distance_meters=float(poi.get('distance', 0)) if poi.get('distance') else 0,
                        tags=tags,
                        address=poi.get('address', '') or poi.get('pname', '') + poi.get('cityname', '') + poi.get('adname', '')
                    ))
                
                page += 1
                
            except Exception as e:
                print(f"   ⚠️ Gaode POI search failed: {str(e)[:50]}")
                break
        
        if results:
            print(f"   ✓ Gaode found {len(results)} results")
        
        return results[:limit]
            
    def _geocode_with_llm(self, location: str) -> Optional[Dict[str, Any]]:
        """使用 LLM 推断地点坐标（备用方案）"""
        if not self.llm:
            return None
        
        prompt = f"""请告诉我 "{location}" 的大致经纬度坐标。

请直接返回 JSON 格式，不要其他内容：
{{"lat": 纬度, "lon": 经度}}

示例：
- "清华大学" -> {{"lat": 40.0084, "lon": 116.3268}}
- "埃菲尔铁塔" -> {{"lat": 48.8584, "lon": 2.2945}}
"""
        
        try:
            response = self.llm.chat(prompt)
            if response:
                import json
                response = response.strip()
                if response.startswith('```'):
                    response = response.split('\n', 1)[1]
                if response.endswith('```'):
                    response = response.rsplit('\n', 1)[0]
                
                data = json.loads(response.strip())
                if 'lat' in data and 'lon' in data:
                    print(f"   🤖 LLM inferred coordinates: {location} -> ({data['lat']}, {data['lon']})")
                    return {
                        'lat': float(data['lat']),
                        'lon': float(data['lon']),
                        'display_name': location
                    }
        except Exception as e:
            pass
        
            return None
    
    def get_admin_boundary(self, region: str, city: Optional[str] = None, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """
        获取行政区域的真实多边形边界（通过 Nominatim）
        
        Args:
            region: 区域名称（如 "柏林", "北京", "Berlin"）
            city: 城市名称（如 "北京", "Beijing"），用于提高搜索准确性
            max_retries: 最大重试次数
            
        Returns:
            {
                'name': str,           # 区域名称
                'bbox': [s, n, w, e],  # 边界框
                'geometry': {...},     # GeoJSON 格式的多边形
                'geojson_file': Path   # 保存的 GeoJSON 文件路径
            }
            或 None
        """
        print(f"   🔍 Getting administrative boundary for '{region}'...")
        
        # 🔧 如果有城市参数，优先使用 "region, city" 格式搜索（提高准确性）
        search_queries = []
        if city:
            # 尝试多种格式，优先使用带城市的查询（提高准确性，避免地名歧义）
            search_queries.append(f"{region}, {city}")
            search_queries.append(f"{region} {city}")
            # 如果城市是中文，也尝试英文城市名（如果region是英文）
            if self._is_chinese_text(city):
                # 尝试获取城市的英文名（简单映射）
                city_en_map = {
                    '北京': 'Beijing', '上海': 'Shanghai', '广州': 'Guangzhou',
                    '深圳': 'Shenzhen', '杭州': 'Hangzhou', '成都': 'Chengdu',
                    '武汉': 'Wuhan', '西安': 'Xi\'an', '南京': 'Nanjing',
                    '天津': 'Tianjin', '重庆': 'Chongqing'
                }
                city_en = city_en_map.get(city)
                if city_en:
                    search_queries.append(f"{region}, {city_en}")
                    search_queries.append(f"{region} {city_en}")
        
        # 使用 LLM 获取地名变体以提高匹配率
        region_variants = self._get_region_name_variants(region) if self.llm else [region]
        
        # 🆕 对于大学/学院查询，添加 "campus"、"main campus" 等变体以获取主校区边界
        university_keywords = ['university', 'college', 'institute', '大学', '学院']
        is_university_query = any(kw in region.lower() for kw in university_keywords)
        if is_university_query:
            # 在原始变体基础上添加 campus 变体（优先搜索）
            campus_variants = []
            for variant in region_variants[:3]:  # 只对前3个变体添加
                campus_variants.append(f"{variant} main campus")
                campus_variants.append(f"{variant} campus")
            # 将 campus 变体放在搜索列表前面（优先）
            search_queries.extend(campus_variants)
            print(f"   🎓 University query detected, adding campus variants: {campus_variants[:2]}...")
        
        # 如果有城市，为每个变体也添加城市（优先）
        if city:
            for variant in region_variants:
                search_queries.append(f"{variant}, {city}")
                search_queries.append(f"{variant} {city}")
                # 如果城市是中文，也尝试英文城市名
                if self._is_chinese_text(city):
                    city_en_map = {
                        '北京': 'Beijing', '上海': 'Shanghai', '广州': 'Guangzhou',
                        '深圳': 'Shenzhen', '杭州': 'Hangzhou', '成都': 'Chengdu',
                        '武汉': 'Wuhan', '西安': 'Xi\'an', '南京': 'Nanjing',
                        '天津': 'Tianjin', '重庆': 'Chongqing'
                    }
                    city_en = city_en_map.get(city)
                    if city_en:
                        search_queries.append(f"{variant}, {city_en}")
                        search_queries.append(f"{variant} {city_en}")
        
        # 最后添加原始变体（不带城市）- 作为最后的备选
        search_queries.extend(region_variants)
        
        for query in search_queries:
            # 方法1: 尝试使用 curl（更稳定）
            result = self._get_boundary_via_curl(query, region)
            if result:
                return result
            
            # 方法2: 使用 requests（带重试）
            for retry in range(max_retries):
                params = {
                    'q': query,
                    'format': 'geojson',
                    'polygon_geojson': 1,  # 请求返回多边形
                    'limit': 10,  # 🆕 增加到10个结果，提高找到正确边界的概率
                    'addressdetails': 1  # 获取详细地址信息用于判断类型
                }
                
                for nominatim_url in self.NOMINATIM_URLS:
                    url = f"{nominatim_url}/search"
                    
                    try:
                        response = self.session.get(url, params=params, timeout=60)
                        response.raise_for_status()
                        data = response.json()
                        
                        result = self._process_boundary_response(data, region, query)
                        if result:
                            # 🔧 验证结果：如果提供了城市参数，检查结果是否在合理范围内
                            if city and result.get('bbox'):
                                bbox = result['bbox']
                                # 检查bbox是否在中国范围内（仅当城市是真正的中国城市名时）
                                # 🆕 排除外国城市的中文名（如"纽约"、"伦敦"等）
                                if self._is_chinese_text(city) and self._is_chinese_city(city):
                                    # 中国大致范围：经度 73-135，纬度 18-54
                                    lon_center = (bbox[2] + bbox[3]) / 2
                                    lat_center = (bbox[0] + bbox[1]) / 2
                                    if not (73 <= lon_center <= 135 and 18 <= lat_center <= 54):
                                        print(f"   ⚠️ Result coordinates outside China, skipping: {bbox}")
                                        continue
                            return result
                        
                    except Exception as e:
                        if retry < max_retries - 1:
                            import time
                            time.sleep(2)  # 等待后重试
                        continue
        
        # 🆕 Nominatim 全部失败，尝试高德地图 (国内稳定)
        # 但排除国外国家名称（高德地图主要面向中国，对国外地名识别不准确）
        is_foreign_country = region.strip() in self.FOREIGN_COUNTRIES or \
                            any(country in region for country in self.FOREIGN_COUNTRIES if len(country) <= len(region))
        
        if self.amap_key and self._is_chinese_text(region) and not is_foreign_country:
            result = self._get_boundary_via_amap(region)
            if result:
                return result
        
        print(f"   ⚠️ Cannot get administrative boundary polygon for '{region}'")
        return None
    
    def _is_chinese_text(self, text: str) -> bool:
        """检测文本是否包含中文字符"""
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                return True
        return False
    
    def _is_chinese_city(self, city_name: str) -> bool:
        """
        检测城市名是否是真正的中国城市（排除外国城市的中文名）
        
        例如："北京" -> True, "纽约" -> False
        """
        # 外国城市/国家的常见中文名（这些虽然是中文字符，但不是中国城市）
        foreign_places_cn = {
            # 美国
            '纽约', '洛杉矶', '芝加哥', '旧金山', '华盛顿', '波士顿', '西雅图', '迈阿密',
            '拉斯维加斯', '费城', '休斯顿', '达拉斯', '亚特兰大', '丹佛', '凤凰城',
            # 欧洲
            '伦敦', '巴黎', '柏林', '罗马', '马德里', '阿姆斯特丹', '维也纳', '苏黎世',
            '慕尼黑', '米兰', '巴塞罗那', '布鲁塞尔', '日内瓦', '斯德哥尔摩', '哥本哈根',
            # 亚洲（非中国）
            '东京', '大阪', '首尔', '新加坡', '曼谷', '吉隆坡', '雅加达', '马尼拉', '河内',
            # 大洋洲
            '悉尼', '墨尔本', '奥克兰', '惠灵顿',
            # 其他
            '多伦多', '温哥华', '蒙特利尔', '迪拜', '开罗', '开普敦',
            # 国家名
            '美国', '英国', '法国', '德国', '日本', '韩国', '澳大利亚', '加拿大',
            '意大利', '西班牙', '荷兰', '瑞士', '瑞典', '挪威', '丹麦', '芬兰',
        }
        
        # 检查城市名是否在外国地名列表中
        city_clean = city_name.strip()
        if city_clean in foreign_places_cn:
            return False
        
        # 检查是否包含外国地名（如"纽约市"包含"纽约"）
        for foreign_place in foreign_places_cn:
            if foreign_place in city_clean:
                return False
        
        # 默认认为是中国城市
        return True
    
    def _gcj02_to_wgs84(self, lng: float, lat: float) -> tuple:
        """
        🔧 GCJ-02 (火星坐标/高德坐标) 转 WGS-84 (国际标准坐标)
        
        高德、百度、腾讯等中国地图服务使用 GCJ-02 坐标系，
        与 WGS-84 (GPS/OpenStreetMap 使用) 有约 500-700 米偏移。
        此函数将高德坐标转换为 WGS-84，使其在 QGIS 等 GIS 软件中正确显示。
        
        Args:
            lng: GCJ-02 经度
            lat: GCJ-02 纬度
            
        Returns:
            (wgs84_lng, wgs84_lat) 转换后的 WGS-84 坐标
        """
        import math
        
        def transform_lat(x, y):
            ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
            ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
            ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
            ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
            return ret
        
        def transform_lng(x, y):
            ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
            ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
            ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
            ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
            return ret
        
        dlat = transform_lat(lng - 105.0, lat - 35.0)
        dlng = transform_lng(lng - 105.0, lat - 35.0)
        radlat = lat / 180.0 * math.pi
        magic = math.sin(radlat)
        magic = 1 - self._GCJ02_EE * magic * magic
        sqrtmagic = math.sqrt(magic)
        dlat = (dlat * 180.0) / ((self._GCJ02_A * (1 - self._GCJ02_EE)) / (magic * sqrtmagic) * math.pi)
        dlng = (dlng * 180.0) / (self._GCJ02_A / sqrtmagic * math.cos(radlat) * math.pi)
        
        return lng - dlng, lat - dlat
    
    def _get_boundary_via_curl(self, variant: str, original_region: str) -> Optional[Dict[str, Any]]:
        """
        使用 curl 获取边界（更稳定的备选方案）
        
        注意：Windows 上可能没有 curl，会自动跳过此方法
        """
        import subprocess
        import urllib.parse
        import shutil
        
        # 检查 curl 是否可用（跨平台兼容）
        curl_path = shutil.which('curl')
        if not curl_path:
            # Windows 上通常没有 curl，直接返回 None，使用 requests 方法
            return None
        
        try:
            encoded_variant = urllib.parse.quote(variant)
            # 🔧 修改：获取多个结果以便选择最合适的行政边界
            url = f"https://nominatim.openstreetmap.org/search?q={encoded_variant}&format=geojson&polygon_geojson=1&limit=5&addressdetails=1"
            
            # 跨平台兼容的 curl 命令
            cmd = [curl_path, '-s', '--max-time', '30', '-H', 'User-Agent: GeoQueryEngine/1.0']
            
            # 如果有代理，添加代理参数
            if self.proxy_url:
                cmd.extend(['-x', self.proxy_url])
            
            cmd.append(url)
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
            
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                return self._process_boundary_response(data, original_region, variant)
                
        except Exception as e:
            # curl 失败，返回 None，让代码使用 requests 方法
            pass
        
        return None
    
    def _get_boundary_via_amap(self, region: str) -> Optional[Dict[str, Any]]:
        """
        🆕 使用高德地图 API 获取行政边界（国内稳定，Nominatim 备选）
        
        高德 API 文档: https://lbs.amap.com/api/webservice/guide/api/district
        
        Args:
            region: 区域名称（如 "清华大学", "北京市海淀区"）
            
        Returns:
            与 Nominatim 相同格式的边界数据，或 None
        """
        if not self.amap_key:
            return None
        
        try:
            print(f"   🗺️ Trying Gaode Map API...")
            
            params = {
                'key': self.amap_key,
                'keywords': region,
                'subdistrict': 0,  # 不返回下级行政区
                'extensions': 'all'  # 返回边界坐标
            }
            
            response = requests.get(self.AMAP_API_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') != '1' or not data.get('districts'):
                # 尝试使用地理编码 API
                return self._get_boundary_via_amap_geocode(region)
            
            district = data['districts'][0]
            polyline = district.get('polyline', '')
            
            if not polyline:
                return self._get_boundary_via_amap_geocode(region)
            
            # 转换高德 polyline 为 GeoJSON Polygon
            geometry = self._amap_polyline_to_geojson(polyline)
            if not geometry:
                return None
            
            # 计算边界框
            center = district.get('center', '').split(',')
            if len(center) == 2:
                gcj_lon, gcj_lat = float(center[0]), float(center[1])
                # 🔧 GCJ-02 转 WGS-84（仅用于日志，实际 bbox 从 geometry 计算）
                lon, lat = self._gcj02_to_wgs84(gcj_lon, gcj_lat)
                # 从 geometry 计算 bbox（geometry 中的坐标已在 _amap_polyline_to_geojson 中转换）
                bbox = self._calculate_bbox_from_geometry(geometry)
            else:
                bbox = None
            
            if not bbox:
                return None
            
            # 保存边界
            # 🔧 修复：使用 self.output_dir 而不是硬编码的 'downloaded_data'
            boundary_dir = Path(self.output_dir) / 'boundaries'
            boundary_dir.mkdir(parents=True, exist_ok=True)
            safe_name = self._sanitize_name(region)
            boundary_file = boundary_dir / f"boundary_{safe_name}.geojson"
            
            geojson_data = {
                'type': 'FeatureCollection',
                'features': [{
                    'type': 'Feature',
                    'properties': {
                        'name': region,
                        'display_name': district.get('name', region),
                        'source': 'AMap (高德地图)'
                    },
                    'geometry': geometry
                }]
            }
            
            with open(boundary_file, 'w', encoding='utf-8') as f:
                json.dump(geojson_data, f, ensure_ascii=False, indent=2)
            
            print(f"   ✓ Gaode Map got administrative boundary for '{region}' ({geometry['type']})")
            print(f"   ✓ Boundary saved: {boundary_file}")
            
            # 🔧 确保返回绝对路径
            return {
                'name': region,
                'bbox': bbox,
                'geometry': geometry,
                'geojson_file': str(boundary_file.resolve()),
                'source': 'AMap'
            }
            
        except Exception as e:
            print(f"   ⚠️ Gaode Map API failed: {str(e)[:50]}")
            return None
    
    def _get_boundary_via_amap_geocode(self, region: str) -> Optional[Dict[str, Any]]:
        """使用高德地理编码 API 获取坐标（没有边界时的回退）"""
        if not self.amap_key:
            return None
        
        try:
            params = {
                'key': self.amap_key,
                'address': region
            }
            
            response = requests.get(self.AMAP_GEOCODE_URL, params=params, timeout=10)
            data = response.json()
            
            if data.get('status') != '1' or not data.get('geocodes'):
                return None
            
            geocode = data['geocodes'][0]
            location = geocode.get('location', '').split(',')
            
            if len(location) != 2:
                return None
            
            gcj_lon, gcj_lat = float(location[0]), float(location[1])
            # 🔧 GCJ-02 转 WGS-84
            lon, lat = self._gcj02_to_wgs84(gcj_lon, gcj_lat)
            
            # 没有真实边界，创建一个小范围的边界框
            delta = 0.01  # 约 1km
            bbox = [lat - delta, lat + delta, lon - delta, lon + delta]
            
            # 创建一个简单的矩形 Polygon（使用 WGS-84 坐标）
            geometry = {
                'type': 'Polygon',
                'coordinates': [[
                    [lon - delta, lat - delta],
                    [lon + delta, lat - delta],
                    [lon + delta, lat + delta],
                    [lon - delta, lat + delta],
                    [lon - delta, lat - delta]
                ]]
            }
            
            # 保存边界文件（即使只是矩形）
            # 🔧 修复：使用 self.output_dir 而不是硬编码的 'downloaded_data'
            boundary_dir = Path(self.output_dir) / 'boundaries'
            boundary_dir.mkdir(parents=True, exist_ok=True)
            safe_name = self._sanitize_name(region)
            boundary_file = boundary_dir / f"boundary_{safe_name}.geojson"
            
            geojson_data = {
                'type': 'FeatureCollection',
                'features': [{
                    'type': 'Feature',
                    'properties': {
                        'name': region,
                        'display_name': geocode.get('formatted_address', region),
                        'source': 'AMap_Geocode (矩形近似)'
                    },
                    'geometry': geometry
                }]
            }
            
            with open(boundary_file, 'w', encoding='utf-8') as f:
                json.dump(geojson_data, f, ensure_ascii=False, indent=2)
            
            print(f"   ✓ Gaode Map got coordinates for '{region}' (no real boundary, using 1km range)")
            print(f"   ✓ Boundary saved: {boundary_file}")
            
            # 🔧 确保返回绝对路径
            return {
                'name': region,
                'bbox': bbox,
                'geometry': geometry,
                'geojson_file': str(boundary_file.resolve()),
                'source': 'AMap_Geocode'
            }
            
        except Exception as e:
            return None
    
    def _amap_polyline_to_geojson(self, polyline: str) -> Optional[Dict]:
        """
        将高德 polyline 格式转换为 GeoJSON Polygon/MultiPolygon
        
        高德格式: "lon1,lat1;lon2,lat2;...|lon1,lat1;lon2,lat2;..."
        多个区域用 | 分隔，坐标用 ; 分隔
        
        🔧 所有坐标从 GCJ-02 转换为 WGS-84
        """
        if not polyline:
            return None
        
        try:
            # 分割多个区域
            regions = polyline.split('|')
            polygons = []
            
            for region_str in regions:
                if not region_str.strip():
                    continue
                    
                coords = []
                points = region_str.split(';')
                
                for point in points:
                    if ',' in point:
                        gcj_lon, gcj_lat = point.split(',')
                        # 🔧 GCJ-02 转 WGS-84
                        wgs_lon, wgs_lat = self._gcj02_to_wgs84(float(gcj_lon), float(gcj_lat))
                        coords.append([wgs_lon, wgs_lat])
                
                if len(coords) >= 3:
                    # 确保闭合
                    if coords[0] != coords[-1]:
                        coords.append(coords[0])
                    polygons.append([coords])
            
            if len(polygons) == 0:
                return None
            elif len(polygons) == 1:
                return {'type': 'Polygon', 'coordinates': polygons[0]}
            else:
                return {'type': 'MultiPolygon', 'coordinates': polygons}
                
        except Exception as e:
            return None
    
    def _calculate_bbox_from_geometry(self, geometry: Dict) -> Optional[List[float]]:
        """从 GeoJSON geometry 计算边界框 [south, north, west, east]"""
        try:
            coords = geometry.get('coordinates', [])
            geom_type = geometry.get('type', '')
            
            all_points = []
            
            if geom_type == 'Polygon':
                for ring in coords:
                    all_points.extend(ring)
            elif geom_type == 'MultiPolygon':
                for polygon in coords:
                    for ring in polygon:
                        all_points.extend(ring)
            
            if not all_points:
                return None
            
            lons = [p[0] for p in all_points]
            lats = [p[1] for p in all_points]
            
            return [min(lats), max(lats), min(lons), max(lons)]
            
        except Exception:
            return None
    
    def _process_boundary_response(self, data: Dict, original_region: str, variant: str) -> Optional[Dict[str, Any]]:
        """处理 Nominatim 边界响应，智能选择最合适的多边形（避免地名歧义）"""
        if not data.get('features'):
            return None
        
        # 判断用户是否在查询行政区划
        admin_keywords_cn = ['省', '市', '县', '区', '镇', '乡', '街道', '自治州', '自治县', '盟', '旗', '新区']
        admin_keywords_en = ['district', 'city', 'county', 'province', 'prefecture', 'region', 'municipality', 
                            'pudong', 'haidian', 'chaoyang', 'futian', 'nanshan']  # 常见行政区名
        region_lower = original_region.lower()
        is_admin_query = (any(kw in original_region for kw in admin_keywords_cn) or 
                         any(kw in region_lower for kw in admin_keywords_en))
        
        # 🆕 判断是否为地标/机构查询（大学、公园、医院等）- 应选择主体而非子设施
        landmark_keywords_cn = ['大学', '学院', '公园', '医院', '博物馆', '图书馆', '体育场', '机场', '景区', '故宫', '颐和园']
        landmark_keywords_en = ['university', 'college', 'park', 'hospital', 'museum', 'library', 'stadium', 
                               'airport', 'campus', 'institute', 'garden', 'palace', 'zoo']
        is_landmark_query = (any(kw in original_region for kw in landmark_keywords_cn) or 
                            any(kw in region_lower for kw in landmark_keywords_en))
        
        # 🔧 修复：检测是否可能是简单的城市/国家名称（如 "Berlin", "London", "Paris", "Germany"）
        # 这些应该被视为行政查询，而非地标查询
        if not is_admin_query and not is_landmark_query:
            words = original_region.strip().split()
            # 1-2个单词，每个单词首字母大写，不包含地标关键词
            if len(words) <= 2 and all(w and w[0].isupper() for w in words):
                is_admin_query = True  # 将简单的地名视为行政查询
        
        # 🆕 子设施/附属设施关键词（应严重惩罚，避免选错）
        sub_facility_keywords = [
            # 英文子设施
            'heliport', 'helipad', 'parking', 'gate', 'entrance', 'station', 'stop', 'terminal',
            'annex', 'extension', 'branch', 'satellite', 'outpost', 'center heliport',
            # 中文子设施
            '停机坪', '停车场', '大门', '入口', '分院', '分校', '新校区', '附属'
        ]
        
        # 筛选有效的多边形特征
        valid_features = []
        for f in data['features']:
            geom = f.get('geometry', {})
            geom_type = geom.get('type', '')
            bbox = f.get('bbox')
            props = f.get('properties', {})
            
            if geom_type in ['Polygon', 'MultiPolygon'] and bbox:
                display_name = props.get('display_name', '')
                display_name_lower = display_name.lower()
                importance = props.get('importance', 0)
                osm_type = props.get('osm_type', '')  # relation, way, node
                category = props.get('category', '')  # boundary, building, amenity 等
                place_type = props.get('type', '')    # administrative, building 等
                
                # 计算边界框面积
                bbox_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                
                # 智能评分：基础分数
                score = importance * 100
                
                # 🔧 强力加分：行政边界类型（category=boundary, type=administrative）
                if category == 'boundary' and place_type == 'administrative':
                    score += 500  # 行政边界优先级最高
                elif category == 'boundary':
                    score += 300  # 其他边界类型也给予加分
                elif osm_type == 'relation':
                    score += 200  # relation 类型通常是区域边界
                
                # 🆕 地标查询时：严重惩罚子设施，优先选择面积大的主体
                if is_landmark_query:
                    # 检查是否为子设施
                    is_sub_facility = any(kw in display_name_lower for kw in sub_facility_keywords)
                    if is_sub_facility:
                        score -= 1000  # 严重惩罚子设施（如 Heliport）
                        print(f"      ⚠️ Sub-facility detected, penalty applied: {display_name[:50]}...")
                    else:
                        # 对于主体地标，面积越大越好（按面积对数加分，避免极端值）
                        if bbox_area > 0:
                            import math
                            area_bonus = min(300, math.log10(bbox_area + 1) * 50)
                            score += area_bonus
                
                # 🔧 新增：优先选择与查询名称直接匹配的行政区
                if is_admin_query:
                    # 检查地名中是否直接包含查询的行政区名（如 "浦东新区" 包含 "浦东"）
                    search_terms = [original_region.lower(), variant.lower()]
                    for term in search_terms:
                        term_parts = term.replace(',', ' ').split()
                        for part in term_parts:
                            if len(part) > 1 and part in display_name.lower():
                                # 如果是行政区划类型匹配，加更多分
                                if '新区' in display_name or '区' in display_name or 'district' in display_name.lower():
                                    score += 150
                                    break
                
                # 🔧 如果是行政区划查询，严重惩罚非行政类型（学校、建筑、交通设施等）
                if is_admin_query:
                    # 🔧 修复：添加英文的大学、学院等关键词，并使用小写比较
                    non_admin_keywords_cn = ['大学', '学院', '学校', '医院', '公司', '工厂', '商场', '酒店', '中心', '公园', 
                                              '敬老院', '养老院', '幼儿园', '小学', '中学', '培训', '银行', '超市', '药店',
                                              '机场', '火车站', '汽车站', '地铁站', '港口', '码头', '高铁站', '客运站',
                                              '迪士尼', '度假区', '景区', '游乐园', '乐园']
                    non_admin_keywords_en = ['university', 'college', 'school', 'hospital', 'institute', 'academy',
                                              'airport', 'station', 'terminal', 'port', 'hub', 'campus', 'museum',
                                              'library', 'park', 'garden', 'zoo', 'stadium', 'arena', 'theater', 'theatre']
                    
                    # 中文关键词直接检查
                    for keyword in non_admin_keywords_cn:
                        if keyword in display_name:
                            score -= 300  # 严重惩罚
                            break
                    
                    # 英文关键词使用小写比较
                    for keyword in non_admin_keywords_en:
                        if keyword in display_name_lower:
                            score -= 300  # 严重惩罚
                            break
                
                # 奖励：地址中包含知名城区（海淀、朝阳等）- 仅在非特定查询时
                main_districts = ['海淀', '朝阳', '西城', '东城', '浦东', '福田', '南山', '天河']
                for district in main_districts:
                    if district in display_name:
                        score += 50
                        break
                
                # 惩罚：地址中包含"新校区"、"分校"、"分院"等
                penalty_keywords = ['新校区', '新燕园', '分校', '分院', '昌平', '大兴', '顺义', '通州', '房山']
                for keyword in penalty_keywords:
                    if keyword in display_name:
                        score -= 100
                        break
                
                valid_features.append((f, score, bbox_area, display_name))
        
        if not valid_features:
            return None
        
        # 按评分排序，评分相同则按面积排序
        valid_features.sort(key=lambda x: (x[1], x[2]), reverse=True)
        
        if len(valid_features) > 1:
            print(f"   ℹ️ Found {len(valid_features)} matching results:")
            for i, (f, score, area, name) in enumerate(valid_features[:3]):
                marker = "✓" if i == 0 else " "
                print(f"      {marker} [{i+1}] {name[:50]}... (score: {score:.0f}, area: {area:.6f})")
        
        # 🆕 最低分数阈值：如果最高分都低于 -500，说明所有结果都是子设施，应该拒绝
        best_score = valid_features[0][1]
        best_area = valid_features[0][2]
        
        if best_score < -500:
            print(f"   ⚠️ All results have low scores (best: {best_score:.0f}), likely sub-facilities, rejecting...")
            return None
        
        # 🆕 最小面积阈值：如果面积太小（约 <50m x 50m），很可能是点状设施而非区域
        # 在 WGS84 坐标系中，0.0001 度 ≈ 11 米，0.0001² ≈ 120 平方米
        MIN_AREA_THRESHOLD = 0.00001  # 约 100m x 100m 的面积
        if best_area < MIN_AREA_THRESHOLD:
            print(f"   ⚠️ Best result area too small ({best_area:.8f}), likely a point facility, rejecting...")
            return None
        
        feature = valid_features[0][0]
        geom_type = feature.get('geometry', {}).get('type', '')
        bbox = feature.get('bbox')  # [minlon, minlat, maxlon, maxlat]
        
        # 转换 bbox 为 [south, north, west, east]
        bbox_converted = [bbox[1], bbox[3], bbox[0], bbox[2]]
        
        # 保存边界为 GeoJSON 文件
        # 🔧 修复：使用 self.output_dir 而不是硬编码的 'downloaded_data'
        boundary_dir = Path(self.output_dir) / 'boundaries'
        boundary_dir.mkdir(parents=True, exist_ok=True)
        
        safe_name = self._sanitize_name(original_region)
        boundary_file = boundary_dir / f"boundary_{safe_name}.geojson"
        
        # 构建完整的 GeoJSON FeatureCollection
        # 🔧 添加 CRS 信息，确保 QGIS 正确识别坐标系统为 EPSG:4326 (WGS84)
        geojson_data = {
            'type': 'FeatureCollection',
            'crs': {
                'type': 'name',
                'properties': {
                    'name': 'urn:ogc:def:crs:EPSG::4326'
                }
            },
            'features': [{
                'type': 'Feature',
                'properties': {
                    'name': original_region,
                    'display_name': feature.get('properties', {}).get('display_name', original_region),
                    'source': 'Nominatim'
                },
                'geometry': feature.get('geometry')
            }]
        }
        
        with open(boundary_file, 'w', encoding='utf-8') as f:
            json.dump(geojson_data, f, ensure_ascii=False, indent=2)
        
        print(f"   ✓ Got real administrative boundary for '{original_region}' ({geom_type})")
        print(f"   ✓ Boundary saved: {boundary_file}")
        
        # 🔧 确保返回绝对路径和完整的元数据信息
        return {
            'name': original_region,
            'display_name': feature.get('properties', {}).get('display_name', original_region),
            'bbox': bbox_converted,
            'geometry': feature.get('geometry'),
            'geojson_file': str(boundary_file.resolve()),
            'source': 'Nominatim',
            'crs': 'EPSG:4326',  # Nominatim 返回的数据都是 WGS84 经纬度坐标
            'crs_unit': 'degrees',  # 坐标单位是度，不是米
            'note': '此数据为EPSG:4326坐标系，距离单位是度。进行buffer等距离操作时，需要先重投影到EPSG:3857（米为单位）'
        }
    
    def _sanitize_name(self, name: str) -> str:
        """清理名称使其适合作为文件名"""
        import re
        # 替换不安全字符
        safe = re.sub(r'[<>:"/\\|?*\s]', '_', name)
        return safe[:50]  # 限制长度
    
    def reverse_geocode(self, lat: float, lon: float) -> str:
        """
        将坐标转换为地址
        """
        try:
            url = f"{self.NOMINATIM_URL}/reverse"
            params = {
                'lat': lat,
                'lon': lon,
                'format': 'json'
            }
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            return data.get('display_name', f"{lat}, {lon}")
            
        except Exception as e:
            return f"{lat}, {lon}"
    
    # -------------------------------------------------------------------------
    # POI 查询 (Overpass API)
    # -------------------------------------------------------------------------
    
    def search_poi_nearby(self, lat: float, lon: float, 
                          poi_type: str, radius: int = 500) -> List[POIResult]:
        """
        搜索指定位置周围的 POI
        
        Args:
            lat: 纬度
            lon: 经度
            poi_type: POI 类型 (如 "pharmacy", "restaurant")
            radius: 搜索半径（米）
            
        Returns:
            POI 结果列表
        """
        # 解析 POI 类型（支持 LLM 动态推断）
        osm_tag = self._get_osm_tag_for_poi(poi_type)
        tag_key, tag_value = osm_tag.split('=')
        
        # 构建 Overpass QL 查询
        query = f"""
        [out:json][timeout:{self.timeout}];
        (
          node["{tag_key}"="{tag_value}"](around:{radius},{lat},{lon});
          way["{tag_key}"="{tag_value}"](around:{radius},{lat},{lon});
        );
        out body center;
        """
        
        try:
            response = self.session.post(
                self.OVERPASS_URL,
                data={'data': query},
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            for element in data.get('elements', []):
                # 获取坐标
                if element['type'] == 'node':
                    poi_lat = element['lat']
                    poi_lon = element['lon']
                elif element['type'] == 'way' and 'center' in element:
                    poi_lat = element['center']['lat']
                    poi_lon = element['center']['lon']
                else:
                    continue
                
                # 计算距离
                distance = self._haversine_distance(lat, lon, poi_lat, poi_lon)
                
                tags = element.get('tags', {})
                results.append(POIResult(
                    osm_id=element['id'],
                    name=tags.get('name', tags.get('name:zh', tags.get('name:en', '未命名'))),
                    poi_type=poi_type,
                    lat=poi_lat,
                    lon=poi_lon,
                    distance_meters=distance,
                    tags=tags,
                    address=tags.get('addr:full', tags.get('addr:street', ''))
                ))
            
            # 按距离排序
            results.sort(key=lambda x: x.distance_meters)
            return results
            
        except Exception as e:
            print(f"   ⚠️ POI query failed: {e}")
            return []
    
    # OSM 属性过滤标签映射（用户友好名称 -> OSM 标签）
    PROPERTY_FILTER_MAPPING = {
        # 酒店星级
        'stars': 'stars',
        '星级': 'stars',
        '五星级': ('stars', '5'),
        '四星级': ('stars', '4'),
        '三星级': ('stars', '3'),
        '二星级': ('stars', '2'),
        '一星级': ('stars', '1'),
        '5星': ('stars', '5'),
        '4星': ('stars', '4'),
        '3星': ('stars', '3'),
        
        # 营业时间
        '24小时': ('opening_hours', '24/7'),
        '24小时营业': ('opening_hours', '24/7'),
        'opening_hours': 'opening_hours',
        
        # 无障碍设施
        '轮椅': ('wheelchair', 'yes'),
        '无障碍': ('wheelchair', 'yes'),
        'wheelchair': 'wheelchair',
        
        # 支付方式
        '支持现金': ('payment:cash', 'yes'),
        '支持刷卡': ('payment:credit_cards', 'yes'),
        
        # 网络
        'wifi': ('internet_access', 'wlan'),
        '免费wifi': ('internet_access:fee', 'no'),
        
        # 停车
        '有停车场': ('parking', 'yes'),
        '免费停车': ('parking:fee', 'no'),
        
        # 餐饮特性
        '素食': ('diet:vegetarian', 'yes'),
        '清真': ('diet:halal', 'yes'),
        '外卖': ('delivery', 'yes'),
        
        # 住宿特性
        '游泳池': ('leisure', 'swimming_pool'),
        '健身房': ('leisure', 'fitness_centre'),
    }
    
    def _parse_property_filters(self, property_filters: Dict[str, Any]) -> List[str]:
        """
        将用户友好的属性过滤条件转换为 Overpass QL 过滤表达式
        
        Args:
            property_filters: 属性过滤字典，如 {"stars": 5, "24小时营业": True}
            
        Returns:
            Overpass QL 过滤表达式列表
        """
        osm_filters = []
        
        for key, value in property_filters.items():
            # 检查是否有预定义映射
            if key in self.PROPERTY_FILTER_MAPPING:
                mapping = self.PROPERTY_FILTER_MAPPING[key]
                if isinstance(mapping, tuple):
                    # 预定义的 (tag, value) 对
                    osm_filters.append(f'["{mapping[0]}"="{mapping[1]}"]')
                else:
                    # 只有标签名，使用传入的值
                    osm_filters.append(f'["{mapping}"="{value}"]')
            else:
                # 直接使用用户提供的键值对
                if isinstance(value, bool):
                    if value:
                        osm_filters.append(f'["{key}"]')
                else:
                    osm_filters.append(f'["{key}"="{value}"]')
        
        return osm_filters
    
    def search_poi_in_region(self, region_name: str, 
                              poi_type: str = None,
                              brand_name: str = None,
                              property_filters: Dict[str, Any] = None,
                              limit: int = 1000) -> List[POIResult]:
        """
        在指定区域内搜索 POI（按类型、品牌名称或属性过滤）
        
        这个方法支持复杂的属性过滤，如：
        - "北京的五星级酒店" -> region_name="北京", poi_type="hotel", property_filters={"stars": "5"}
        - "上海24小时营业的药店" -> region_name="上海", poi_type="pharmacy", property_filters={"24小时营业": True}
        - "广州有停车场的餐厅" -> region_name="广州", poi_type="restaurant", property_filters={"有停车场": True}
        
        Args:
            region_name: 区域名称（如 "北京市", "上海", "Berlin"）
            poi_type: POI 类型（可选，如 "cafe", "restaurant", "hotel"）
            brand_name: 品牌名称（支持正则，如 "星巴克|Starbucks"）
            property_filters: 属性过滤条件（如 {"stars": "5", "24小时营业": True}）
            limit: 返回数量限制
            
        Returns:
            POI 结果列表
        """
        # 构建 Overpass QL 查询
        # 使用 area 查询方式，可以按行政区域搜索
        
        # 构建过滤条件
        filters = []
        
        if brand_name:
            # 使用正则匹配品牌名称（支持中英文）
            # 例如: ["name"~"星巴克|Starbucks",i] 表示不区分大小写匹配
            filters.append(f'["name"~"{brand_name}",i]')
        
        if poi_type:
            # 使用 LLM 动态推断 OSM 标签（保证泛化性）
            osm_tag = self._get_osm_tag_for_poi(poi_type)
            if '=' in osm_tag:
                tag_key, tag_value = osm_tag.split('=', 1)
                filters.append(f'["{tag_key}"="{tag_value}"]')
            else:
                filters.append(f'["{poi_type}"]')
        
        # 添加属性过滤条件
        if property_filters:
            property_filter_strs = self._parse_property_filters(property_filters)
            filters.extend(property_filter_strs)
            if property_filter_strs:
                print(f"   🔧 Property filters: {property_filters} -> {property_filter_strs}")
        
        # 如果既没有类型也没有品牌，默认搜索所有 amenity
        if not filters:
            filters.append('["amenity"]')
        
        filter_str = ''.join(filters)
        
        # 使用 LLM 生成多语言地名变体（保证跨语言泛化性）
        region_names_to_try = self._get_region_name_variants(region_name)
        
        print(f"   🔍 Overpass API: searching {brand_name or poi_type or 'POI'} in {region_name}...")
        
        # 🆕 获取可用端点列表（只返回可用端点）
        available_endpoints = self._get_available_overpass_endpoints()
        
        # 🆕 根据端点可用性调整超时时间
        if getattr(self, '_no_available_endpoints', False):
            # 没有可用端点，使用极短超时快速失败
            request_timeout = 5
            query_timeout = 10
            # 只尝试第一个区域名称，快速失败
            region_names_to_try = region_names_to_try[:1]
            print("   ⚠️ No available endpoints, will try quickly then give up...")
        else:
            # 有可用端点，使用正常超时
            request_timeout = min(self.timeout, 30)
            query_timeout = min(self.timeout, 60)
        
        # 依次尝试不同的区域名称
        for try_region in region_names_to_try:
            # 使用 area 查询方式
            query = f"""
            [out:json][timeout:{query_timeout}];
            area["name"="{try_region}"]->.search_area;
            (
              node(area.search_area){filter_str};
              way(area.search_area){filter_str};
            );
            out body center {limit};
            """
            
            # 🆕 使用智能排序的端点列表
            for endpoint_url in available_endpoints:
                try:
                    # 直接连接（不使用代理，Overpass API 通常可以直接访问）
                    import requests as req_direct
                    response = req_direct.post(
                        endpoint_url,
                        data={'data': query},
                        timeout=request_timeout,  # 🆕 使用更短的超时
                        proxies={'http': None, 'https': None}  # 显式禁用代理
                    )
                    response.raise_for_status()
                    
                    data = response.json()
                    elements = data.get('elements', [])
                    
                    # 如果找到结果，解析并返回
                    if elements:
                        results = []
                        for element in elements:
                            # 获取坐标
                            if element['type'] == 'node':
                                poi_lat = element['lat']
                                poi_lon = element['lon']
                            elif element['type'] == 'way' and 'center' in element:
                                poi_lat = element['center']['lat']
                                poi_lon = element['center']['lon']
                            else:
                                continue
                            
                            tags = element.get('tags', {})
                            name = tags.get('name', tags.get('name:zh', tags.get('name:en', '未命名')))
                            
                            # 获取地址信息
                            address_parts = []
                            if tags.get('addr:city'):
                                address_parts.append(tags['addr:city'])
                            if tags.get('addr:district'):
                                address_parts.append(tags['addr:district'])
                            if tags.get('addr:street'):
                                address_parts.append(tags['addr:street'])
                            if tags.get('addr:housenumber'):
                                address_parts.append(tags['addr:housenumber'])
                            address = ''.join(address_parts) or tags.get('addr:full', '')
                            
                            results.append(POIResult(
                                osm_id=element['id'],
                                name=name,
                                poi_type=poi_type or tags.get('amenity', tags.get('shop', 'unknown')),
                                lat=poi_lat,
                                lon=poi_lon,
                                distance_meters=0,  # 区域查询不计算距离
                                tags=tags,
                                address=address
                            ))
                        
                        print(f"   ✓ Found {len(results)} results using region name '{try_region}'")
                        return results
                    else:
                        # 没找到结果，尝试下一个区域名称
                        print(f"   ℹ️ No results found for region '{try_region}', trying other names...")
                        break  # 跳出端点循环，尝试下一个区域名称
                        
                except Exception as e:
                    # 🆕 更新端点健康状态（标记为不可用）
                    import time
                    self._endpoint_health[endpoint_url] = {
                        'available': False,
                        'last_check': time.time()
                    }
                    print(f"   ⚠️ Endpoint {endpoint_url[:50]}... failed: {str(e)[:50]}")
                    continue
        
        print(f"   ✓ Found 0 results")
        return []
    
    def _haversine_distance(self, lat1: float, lon1: float, 
                            lat2: float, lon2: float) -> float:
        """计算两点之间的球面距离（米）"""
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371000  # 地球半径（米）
        
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c
    
    # -------------------------------------------------------------------------
    # 路由计算 (OSRM)
    # -------------------------------------------------------------------------
    
    def calculate_route(self, origin_lat: float, origin_lon: float,
                        dest_lat: float, dest_lon: float,
                        mode: str = "driving") -> Optional[RouteResult]:
        """
        计算两点之间的路由 (使用 OSM 官方路由服务，失败时自动切换备用)
        
        Args:
            origin_lat, origin_lon: 起点坐标（WGS-84）
            dest_lat, dest_lon: 终点坐标（WGS-84）
            mode: 交通方式 (driving, walking, cycling)
            
        Returns:
            RouteResult 或 None
        """
        # OSM 路由服务使用不同的端点
        # https://routing.openstreetmap.de/routed-{profile}/route/v1/driving/
        profile_map = {
            "driving": "car",
            "walking": "foot",
            "cycling": "bike",
            "car": "car",
            "foot": "foot",
            "bike": "bike"
        }
        profile = profile_map.get(mode.lower(), "car")
        
        # 尝试多个路由端点（OSRM 不需要代理，直连更快更稳定）
        endpoints = [
            # OSM 官方路由服务（最推荐，比 OSRM 公共服务器更稳定）
            f"{self.OSM_ROUTING_BASE}/routed-{profile}/route/v1/driving/{origin_lon},{origin_lat};{dest_lon},{dest_lat}",
            # OSRM 公共服务器（备用，经常 502/504 错误）
            f"{self.OSRM_FALLBACK_URL}/route/v1/{profile}/{origin_lon},{origin_lat};{dest_lon},{dest_lat}",
        ]
        
        params = {
            'overview': 'full',
            'geometries': 'geojson',
            'steps': 'true'
        }
        
        last_error = None
        for i, url in enumerate(endpoints):
            try:
                # 【重要】OSRM 不需要代理，直连更快更稳定
                # 第一个端点使用较短超时，备用端点使用较长超时
                timeout = 30 if i == 0 else 60
                response = requests.get(
                    url, 
                    params=params, 
                    timeout=timeout,
                    headers={'User-Agent': 'GeoQueryEngine/1.0'},
                    proxies={'http': None, 'https': None}  # 不使用代理
                )
                response.raise_for_status()
                
                data = response.json()
                
                if data.get('code') != 'Ok' or not data.get('routes'):
                    continue  # 尝试下一个端点
                
                route = data['routes'][0]
                
                # 解析步骤 - 生成详细的中文导航指令
                steps = []
                all_steps = []
                for leg in route.get('legs', []):
                    all_steps.extend(leg.get('steps', []))
                
                for i, step in enumerate(all_steps):
                    maneuver = step.get('maneuver', {})
                    maneuver_type = maneuver.get('type', '')
                    modifier = maneuver.get('modifier', '')
                    road_name = step.get('name', '')
                    distance = step.get('distance', 0)
                    duration = step.get('duration', 0)
                    
                    # 方向映射
                    direction_map = {
                        'left': '左转',
                        'right': '右转',
                        'straight': '直行',
                        'slight left': '稍向左转',
                        'slight right': '稍向右转',
                        'sharp left': '向左急转',
                        'sharp right': '向右急转',
                        'uturn': '掉头'
                    }
                    
                    # 根据类型和修饰符生成详细导航指令
                    instruction = ''
                    action = ''
                    
                    if maneuver_type == 'depart':
                        if road_name:
                            instruction = f"从 {road_name} 出发"
                        else:
                            instruction = "出发"
                        action = 'depart'
                    
                    elif maneuver_type == 'arrive':
                        instruction = "到达目的地"
                        action = 'arrive'
                    
                    elif maneuver_type == 'turn':
                        direction = direction_map.get(modifier, '转弯')
                        if road_name:
                            instruction = f"{direction}，进入 {road_name}"
                        else:
                            instruction = direction
                        action = 'turn'
                    
                    elif maneuver_type == 'new name':
                        # 道路名称变化，继续沿新道路行驶
                        if road_name:
                            instruction = f"继续直行，进入 {road_name}"
                        else:
                            instruction = "继续直行"
                        action = 'continue'
                    
                    elif maneuver_type == 'continue':
                        direction = direction_map.get(modifier, '')
                        if direction and road_name:
                            instruction = f"{direction}继续，沿 {road_name} 行驶"
                        elif road_name:
                            instruction = f"沿 {road_name} 继续行驶"
                        elif direction:
                            instruction = f"{direction}继续"
                        else:
                            instruction = "继续直行"
                        action = 'continue'
                    
                    elif maneuver_type == 'merge':
                        direction = direction_map.get(modifier, '')
                        if road_name:
                            instruction = f"汇入 {road_name}"
                        else:
                            instruction = f"{direction}汇入主路" if direction else "汇入主路"
                        action = 'merge'
                    
                    elif maneuver_type == 'fork':
                        direction = direction_map.get(modifier, '前方')
                        if road_name:
                            instruction = f"在岔路口{direction}，进入 {road_name}"
                        else:
                            instruction = f"在岔路口{direction}"
                        action = 'fork'
                    
                    elif maneuver_type in ['roundabout', 'rotary']:
                        exit_num = maneuver.get('exit', '')
                        if exit_num and road_name:
                            instruction = f"进入环岛，在第 {exit_num} 出口驶出，进入 {road_name}"
                        elif exit_num:
                            instruction = f"进入环岛，在第 {exit_num} 出口驶出"
                        elif road_name:
                            instruction = f"经过环岛，进入 {road_name}"
                        else:
                            instruction = "经过环岛"
                        action = 'roundabout'
                    
                    elif maneuver_type == 'end of road':
                        direction = direction_map.get(modifier, '转弯')
                        if road_name:
                            instruction = f"到达路的尽头，{direction}进入 {road_name}"
                        else:
                            instruction = f"到达路的尽头，{direction}"
                        action = 'end'
                    
                    elif maneuver_type == 'notification':
                        continue  # 跳过通知类型
                    
                    else:
                        # 默认处理
                        direction = direction_map.get(modifier, '')
                        if direction and road_name:
                            instruction = f"{direction}，进入 {road_name}"
                        elif road_name:
                            instruction = f"沿 {road_name} 行驶"
                        elif direction:
                            instruction = direction
                        else:
                            instruction = "继续前进"
                        action = 'other'
                    
                    # 获取下一步的道路名（用于更详细的指令）
                    next_road = ''
                    if i + 1 < len(all_steps):
                        next_road = all_steps[i + 1].get('name', '')
                    
                        steps.append({
                        'instruction': instruction,
                        'distance': distance,
                        'duration': duration,
                        'name': road_name,
                        'next_road': next_road,
                        'type': maneuver_type,
                        'modifier': modifier,
                        'action': action
                        })
                
                return RouteResult(
                    origin=f"{origin_lat}, {origin_lon}",
                    destination=f"{dest_lat}, {dest_lon}",
                    distance_meters=route.get('distance', 0),
                    duration_seconds=route.get('duration', 0),
                    geometry=route.get('geometry', {}).get('coordinates', []),
                    steps=steps,
                    transport_mode=mode
                )
                
            except Exception as e:
                last_error = e
                if i < len(endpoints) - 1:
                    print(f"   ⚠️ Endpoint {i+1} failed, trying backup endpoint...")
                continue
        
        # 所有端点都失败
        print(f"   ⚠️ Route calculation failed: {last_error}")
        return None


# ============================================================================
# Wikidata 适配器 (SPARQL 查询)
# ============================================================================

class WikidataAdapter:
    """Wikidata 适配器 - 语义知识图谱查询"""
    
    # Wikidata SPARQL 端点
    WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
    
    # 常用实体类型的 Wikidata ID
    ENTITY_TYPE_MAPPING = {
        # 住宿
        "hotel": "Q27686",       # 酒店
        "hostel": "Q654772",     # 青年旅社
        "motel": "Q216212",      # 汽车旅馆
        
        # 餐饮
        "restaurant": "Q11707",  # 餐厅
        "cafe": "Q30022",        # 咖啡馆
        "bar": "Q187456",        # 酒吧
        
        # 教育
        "university": "Q3918",   # 大学
        "school": "Q3914",       # 学校
        "library": "Q7075",      # 图书馆
        
        # 文化
        "museum": "Q33506",      # 博物馆
        "theater": "Q24354",     # 剧院
        "cinema": "Q41253",      # 电影院
        "art_gallery": "Q1007870",  # 美术馆
        
        # 医疗
        "hospital": "Q16917",    # 医院
        "pharmacy": "Q656365",   # 药店
        "clinic": "Q1774898",    # 诊所
        
        # 交通
        "airport": "Q1248784",   # 机场
        "train_station": "Q55488", # 火车站
        "bus_station": "Q494829",  # 汽车站
        
        # 景点
        "monument": "Q4989906",  # 纪念碑
        "park": "Q22698",        # 公园
        "tourist_attraction": "Q570116",  # 旅游景点
        
        # 世界遗产
        "world_heritage": "Q9259",       # 世界遗产
        "heritage_site": "Q9259",        # 遗产地
        "cultural_heritage": "Q210272",  # 文化遗产
        "world_heritage_site": "Q9259",  # 世界遗产地
        "unesco_heritage": "Q9259",      # 联合国教科文组织世界遗产
        
        # 购物
        "shopping_mall": "Q11315",  # 购物中心
        "supermarket": "Q180846",   # 超市
    }
    
    # 城市/地区的 Wikidata ID
    LOCATION_MAPPING = {
        # 中国主要城市
        "北京": "Q956",
        "beijing": "Q956",
        "上海": "Q8686",
        "shanghai": "Q8686",
        "广州": "Q16572",
        "guangzhou": "Q16572",
        "深圳": "Q15174",
        "shenzhen": "Q15174",
        "杭州": "Q4970",
        "hangzhou": "Q4970",
        "南京": "Q16666",
        "nanjing": "Q16666",
        "成都": "Q30002",
        "chengdu": "Q30002",
        "西安": "Q5826",
        "xian": "Q5826",
        "武汉": "Q11746",
        "wuhan": "Q11746",
        "重庆": "Q11725",
        "chongqing": "Q11725",
        "天津": "Q11736",
        "tianjin": "Q11736",
        "苏州": "Q42622",
        "suzhou": "Q42622",
        "香港": "Q8646",
        "hong kong": "Q8646",
        "澳门": "Q14773",
        "macau": "Q14773",
        "台北": "Q1867",
        "taipei": "Q1867",
        
        # 欧洲城市
        "伦敦": "Q84",
        "london": "Q84",
        "巴黎": "Q90",
        "paris": "Q90",
        "柏林": "Q64",        # 【新增】德国首都
        "berlin": "Q64",
        "慕尼黑": "Q1726",
        "munich": "Q1726",
        "法兰克福": "Q1794",
        "frankfurt": "Q1794",
        "阿姆斯特丹": "Q727",
        "amsterdam": "Q727",
        "布鲁塞尔": "Q239",
        "brussels": "Q239",
        "维也纳": "Q1741",
        "vienna": "Q1741",
        "罗马": "Q220",
        "rome": "Q220",
        "米兰": "Q490",
        "milan": "Q490",
        "马德里": "Q2807",
        "madrid": "Q2807",
        "巴塞罗那": "Q1492",
        "barcelona": "Q1492",
        "隆德": "Q25287",
        "lund": "Q25287",
        "斯德哥尔摩": "Q1754",
        "stockholm": "Q1754",
        "哥本哈根": "Q1748",
        "copenhagen": "Q1748",
        "莫斯科": "Q649",
        "moscow": "Q649",
        "苏黎世": "Q72",
        "zurich": "Q72",
        "日内瓦": "Q71",
        "geneva": "Q71",
        
        # 亚洲城市
        "东京": "Q1490",
        "tokyo": "Q1490",
        "首尔": "Q8684",
        "seoul": "Q8684",
        "新加坡": "Q334",
        "singapore": "Q334",
        "曼谷": "Q1861",
        "bangkok": "Q1861",
        "吉隆坡": "Q1865",
        "kuala lumpur": "Q1865",
        "河内": "Q1858",
        "hanoi": "Q1858",
        "雅加达": "Q3630",
        "jakarta": "Q3630",
        "德里": "Q1353",
        "delhi": "Q1353",
        "孟买": "Q1156",
        "mumbai": "Q1156",
        "迪拜": "Q612",
        "dubai": "Q612",
        
        # 美洲城市
        "纽约": "Q60",
        "new york": "Q60",
        "洛杉矶": "Q65",
        "los angeles": "Q65",
        "芝加哥": "Q1297",
        "chicago": "Q1297",
        "旧金山": "Q62",
        "san francisco": "Q62",
        "华盛顿": "Q61",
        "washington": "Q61",
        "多伦多": "Q172",
        "toronto": "Q172",
        "温哥华": "Q24639",
        "vancouver": "Q24639",
        "墨西哥城": "Q1489",
        "mexico city": "Q1489",
        "圣保罗": "Q174",
        "sao paulo": "Q174",
        "里约热内卢": "Q8678",
        "rio de janeiro": "Q8678",
        
        # 大洋洲城市
        "悉尼": "Q3130",
        "sydney": "Q3130",
        "墨尔本": "Q3141",
        "melbourne": "Q3141",
        "奥克兰": "Q37100",
        "auckland": "Q37100",
    }
    
    # 属性 ID 映射
    PROPERTY_MAPPING = {
        "stars": "P1151",           # 酒店星级 (已废弃，使用 P1151 或其他)
        "rating": "P1151",          # 评级
        "founded": "P571",          # 成立时间
        "opening_date": "P1619",    # 开业时间
        "coordinates": "P625",      # 坐标
        "located_in": "P131",       # 位于行政区
        "country": "P17",           # 国家
        "official_website": "P856", # 官网
        "image": "P18",             # 图片
        "phone": "P1329",           # 电话
        "address": "P6375",         # 地址
    }
    
    def __init__(self, timeout: int = 30, proxy_url: str = None, llm: 'LLMClient' = None):
        self.timeout = timeout  # 缩短超时时间，避免卡太久
        self.proxy_url = proxy_url  # Wikidata 专用代理
        self.llm = llm  # LLM 客户端，用于动态生成 SPARQL 条件
        self._proxy_checked = False  # 标记是否已检查代理
        # 🆕 使用 ProxySession 支持自动代理切换
        self.session = ProxySession(proxy_url=proxy_url, auto_switch=True)
        self.session.headers.update({
            'Accept': 'application/sparql-results+json'
        })
        # if proxy_url:
        #     print(f"   ℹWikidata 使用代理: {proxy_url}")
    
    def _generate_sparql_filter_with_llm(self, entity_type: str, property_filters: Dict[str, Any]) -> str:
        """
        使用 LLM 动态生成 Wikidata SPARQL 过滤条件
        
        Args:
            entity_type: 实体类型 (hotel, museum, etc.)
            property_filters: 属性过滤条件 (如 {"stars": 5, "有泳池": true})
            
        Returns:
            SPARQL WHERE 子句片段
        """
        if not self.llm or not property_filters:
            return ""
        
        # 构建 LLM 提示
        prompt = f"""你是 Wikidata SPARQL 专家。请将以下属性过滤条件转换为 Wikidata SPARQL WHERE 子句片段。

实体类型: {entity_type}
过滤条件: {property_filters}

【Wikidata 实体类型参考】
酒店类:
- Q5（酒店，通用）
- Q27686（酒店）
- Q3915610（五星级酒店）
- Q4359621（豪华酒店）
- Q110371199（四星级酒店）

博物馆类:
- Q33506（博物馆）
- Q207694（美术馆）

餐厅类:
- Q11707（餐厅）

【属性参考】
- wdt:P31（实例类型）
- wdt:P279（子类型）
- wdt:P131（位于行政区）
- wdt:P625（坐标）

【输出要求】
1. 只返回 WHERE 子句内部的三元组模式
2. 使用 {{ }} UNION {{ }} 格式连接多个可能的类型
3. 变量名必须使用 ?item
4. 如果无法映射，返回空字符串

【示例】
查询"五星级酒店"，应返回:
{{ ?item wdt:P31 wd:Q3915610 . }} UNION {{ ?item wdt:P31 wd:Q4359621 . }}

查询"博物馆"，应返回:
{{ ?item wdt:P31 wd:Q33506 . }} UNION {{ ?item wdt:P31 wd:Q207694 . }}

仅返回 SPARQL 代码片段，不要任何解释文字。"""

        try:
            response = self.llm.chat(prompt)
            sparql_filter = response.strip()
            
            # 清理可能的 markdown 代码块标记
            if sparql_filter.startswith('```'):
                sparql_filter = sparql_filter.split('\n', 1)[-1]
            if sparql_filter.endswith('```'):
                sparql_filter = sparql_filter.rsplit('\n', 1)[0]
            sparql_filter = sparql_filter.strip()
            
            # 验证返回的是有效的 SPARQL 片段
            if sparql_filter and '?item' in sparql_filter and 'wdt:P31' in sparql_filter:
                print(f"   🧠 LLM generated SPARQL filter: {sparql_filter[:100]}...")
                return sparql_filter
            elif sparql_filter == '' or sparql_filter.lower() == 'none':
                return ""
            else:
                print(f"   ⚠️ LLM returned invalid SPARQL: {sparql_filter[:50]}...")
                return ""
        except Exception as e:
            print(f"   ⚠️ LLM SPARQL generation failed: {e}")
            return ""
    
    def _execute_sparql(self, query: str, max_retries: int = 1) -> List[Dict[str, Any]]:
        """
        执行 SPARQL 查询（带自动代理切换）
        
        使用通用 proxy_request 函数，自动处理代理切换
        """
        headers = {
            'Accept': 'application/sparql-results+json'
        }
        params = {'query': query, 'format': 'json'}
        
        try:
            response = proxy_request(
                'get', self.WIKIDATA_SPARQL_URL,
                proxy_url=self.proxy_url,
                timeout=self.timeout,
                params=params,
                headers=headers
            )
            data = response.json()
            return data.get('results', {}).get('bindings', [])
        except Exception as e:
            # 代理失败，尝试直连
            try:
                response = proxy_request(
                    'get', self.WIKIDATA_SPARQL_URL,
                    proxy_url=None,  # 直连
                    timeout=15,
                    auto_switch=False,  # 不再尝试切换
                    params=params,
                    headers=headers
                )
                data = response.json()
                return data.get('results', {}).get('bindings', [])
            except:
                pass
        
        return []
    
    def _lookup_location_id(self, location: str) -> str:
        """
        动态查询 Wikidata 中的位置 ID
        
        Args:
            location: 位置名称（中文或英文）
            
        Returns:
            Wikidata ID (如 Q64) 或空字符串
        """
        # SPARQL 查询：查找城市/行政区实体
        query = f"""
        SELECT ?item ?itemLabel WHERE {{
            ?item rdfs:label "{location}"@zh .
            {{ ?item wdt:P31 wd:Q515 . }}  # 城市
            UNION
            {{ ?item wdt:P31 wd:Q1549591 . }}  # 大城市
            UNION
            {{ ?item wdt:P31 wd:Q200250 . }}  # 一级行政区
            UNION
            {{ ?item wdt:P31 wd:Q3624078 . }}  # 主权国家
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "zh,en" . }}
        }}
        LIMIT 1
        """
        
        try:
            results = self._execute_sparql(query)
            if results:
                item_uri = results[0].get('item', {}).get('value', '')
                if item_uri:
                    location_id = item_uri.split('/')[-1]
                    print(f"   ℹ️ Dynamic location lookup: {location} -> {location_id}")
                    # 缓存到 LOCATION_MAPPING
                    self.LOCATION_MAPPING[location.lower()] = location_id
                    return location_id
        except Exception as e:
            print(f"   ⚠️ Location lookup failed: {e}")
        
        # 尝试英文名称
        query_en = f"""
        SELECT ?item ?itemLabel WHERE {{
            ?item rdfs:label "{location}"@en .
            {{ ?item wdt:P31 wd:Q515 . }}
            UNION
            {{ ?item wdt:P31 wd:Q1549591 . }}
            UNION
            {{ ?item wdt:P31 wd:Q200250 . }}
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,zh" . }}
        }}
        LIMIT 1
        """
        
        try:
            results = self._execute_sparql(query_en)
            if results:
                item_uri = results[0].get('item', {}).get('value', '')
                if item_uri:
                    location_id = item_uri.split('/')[-1]
                    print(f"   ℹ️ Dynamic location lookup: {location} -> {location_id}")
                    self.LOCATION_MAPPING[location.lower()] = location_id
                    return location_id
        except Exception as e:
            pass
        
        return ""
    
    def query_entities_by_type_and_location(
        self, 
        entity_type: str, 
        location: str,
        property_filters: Dict[str, Any] = None,
        limit: int = 500
    ) -> List[WikidataEntity]:
        """
        按类型和位置查询实体
        
        Args:
            entity_type: 实体类型 (hotel, museum, etc.)
            location: 位置 (北京, 上海, etc.)
            property_filters: 属性过滤条件
            limit: 返回数量限制
            
        Returns:
            WikidataEntity 列表
        """
        # 获取类型 ID
        type_id = self.ENTITY_TYPE_MAPPING.get(entity_type.lower())
        if not type_id:
            print(f"   ⚠️ Unknown entity type: {entity_type}")
            return []
        
        # 获取位置 ID
        location_id = self.LOCATION_MAPPING.get(location.lower())
        if not location_id:
            # 尝试模糊匹配
            for key, value in self.LOCATION_MAPPING.items():
                if location.lower() in key.lower() or key.lower() in location.lower():
                    location_id = value
                    break
        
        # 【重要】如果找不到位置 ID，尝试动态查询
        if not location_id:
            location_id = self._lookup_location_id(location)
        
        # 【重要】如果仍然找不到位置 ID，给出警告而不是返回全球数据
        if not location_id:
            print(f"   ⚠️ Cannot identify location: {location}, will use coordinate filtering as fallback")
        
        # 构建属性过滤条件 (使用 LLM 动态生成)
        property_filter_clause = ""
        if property_filters:
            # 优先使用 LLM 生成 SPARQL 过滤条件
            property_filter_clause = self._generate_sparql_filter_with_llm(entity_type, property_filters)
            
            # 如果 LLM 不可用或失败，使用硬编码的常见过滤
            if not property_filter_clause:
                for key, value in property_filters.items():
                    # 处理星级过滤
                    if key in ['stars', '星级', '五星级', '四星级', '三星级']:
                        if key == '五星级' or (key == 'stars' and str(value) == '5'):
                            property_filter_clause = """
                            { ?item wdt:P31 wd:Q3915610 . }
                            UNION
                            { ?item wdt:P31 wd:Q4359621 . }
                            """
                            print(f"   🏨 Filter: 5-star hotel (fallback)")
                        elif key == '四星级' or (key == 'stars' and str(value) == '4'):
                            property_filter_clause = """
                            { ?item wdt:P31 wd:Q110371199 . }
                            """
                            print(f"   🏨 Filter: 4-star hotel (fallback)")
        
        # 构建 SPARQL 查询 (简化版，避免递归查询超时)
        # 使用 wdt:P31 直接实例查询，wdt:P131+ 行政区归属路径
        if location_id:
            if property_filter_clause:
                # 有属性过滤条件时：只查询符合属性条件的实体
                # property_filter_clause 已经包含了类型约束（如 ?item wdt:P31 wd:Q3915610）
                sparql_query = f"""
                SELECT DISTINCT ?item ?itemLabel ?itemDescription ?coord
                WHERE {{
                    {property_filter_clause}
                    ?item wdt:P131+ wd:{location_id} .
                    
                    OPTIONAL {{ ?item wdt:P625 ?coord . }}
                    
                    SERVICE wikibase:label {{ bd:serviceParam wikibase:language "zh,en" . }}
                }}
                LIMIT {limit}
                """
                print(f"   📝 Using property filtered SPARQL query")
            else:
                sparql_query = f"""
                SELECT DISTINCT ?item ?itemLabel ?itemDescription ?coord
                WHERE {{
                    ?item wdt:P31 wd:{type_id} .
                    ?item wdt:P131+ wd:{location_id} .
                    
                    OPTIONAL {{ ?item wdt:P625 ?coord . }}
                    
                    SERVICE wikibase:label {{ bd:serviceParam wikibase:language "zh,en" . }}
                }}
                LIMIT {limit}
                """
        else:
            # 回退: 使用文本匹配位置名称（效率较低但更灵活）
            sparql_query = f"""
            SELECT DISTINCT ?item ?itemLabel ?itemDescription ?coord ?placeLabel
            WHERE {{
                ?item wdt:P31 wd:{type_id} .
                ?item wdt:P131 ?place .
                
                OPTIONAL {{ ?item wdt:P625 ?coord . }}
                
                SERVICE wikibase:label {{ bd:serviceParam wikibase:language "zh,en,de,fr" . }}
                
                FILTER(CONTAINS(LCASE(STR(?placeLabel)), LCASE("{location}")))
            }}
            LIMIT {limit}
            """
        
        print(f"   🔍 Querying Wikidata: {entity_type} in {location}")
        
        results = self._execute_sparql(sparql_query)
        
        entities = []
        for binding in results:
            # 解析坐标
            lat, lon = None, None
            if 'coord' in binding:
                coord_str = binding['coord']['value']
                # 格式: Point(lon lat)
                match = re.search(r'Point\(([0-9.-]+)\s+([0-9.-]+)\)', coord_str)
                if match:
                    lon = float(match.group(1))
                    lat = float(match.group(2))
            
            # 提取 Wikidata ID
            item_uri = binding.get('item', {}).get('value', '')
            wikidata_id = item_uri.split('/')[-1] if item_uri else ''
            
            entity = WikidataEntity(
                wikidata_id=wikidata_id,
                name=binding.get('itemLabel', {}).get('value', ''),
                entity_type=entity_type,
                description=binding.get('itemDescription', {}).get('value', ''),
                lat=lat,
                lon=lon,
                wikipedia_url=f"https://www.wikidata.org/wiki/{wikidata_id}"
            )
            entities.append(entity)
        
        print(f"   ✓ Found {len(entities)} results")
        return entities
    
    def query_entity_details(self, wikidata_id: str) -> Optional[WikidataEntity]:
        """
        查询实体详细信息
        
        Args:
            wikidata_id: Wikidata ID (如 Q123456)
            
        Returns:
            WikidataEntity 或 None
        """
        sparql_query = f"""
        SELECT ?itemLabel ?itemDescription ?coord ?image ?website ?founded
        WHERE {{
            BIND(wd:{wikidata_id} AS ?item)
            
            OPTIONAL {{ ?item wdt:P625 ?coord . }}
            OPTIONAL {{ ?item wdt:P18 ?image . }}
            OPTIONAL {{ ?item wdt:P856 ?website . }}
            OPTIONAL {{ ?item wdt:P571 ?founded . }}
            
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "zh,en" . }}
        }}
        LIMIT 1
        """
        
        results = self._execute_sparql(sparql_query)
        
        if not results:
            return None
        
        binding = results[0]
        
        # 解析坐标
        lat, lon = None, None
        if 'coord' in binding:
            coord_str = binding['coord']['value']
            match = re.search(r'Point\(([0-9.-]+)\s+([0-9.-]+)\)', coord_str)
            if match:
                lon = float(match.group(1))
                lat = float(match.group(2))
        
        return WikidataEntity(
            wikidata_id=wikidata_id,
            name=binding.get('itemLabel', {}).get('value', ''),
            description=binding.get('itemDescription', {}).get('value', ''),
            lat=lat,
            lon=lon,
            image_url=binding.get('image', {}).get('value', ''),
            wikipedia_url=f"https://www.wikidata.org/wiki/{wikidata_id}",
            properties={
                'founded': binding.get('founded', {}).get('value', ''),
                'website': binding.get('website', {}).get('value', '')
            }
        )
    
    def search_by_name(self, name: str, limit: int = 10) -> List[WikidataEntity]:
        """
        按名称搜索实体（使用 Wikidata 搜索 API，速度更快）
        
        Args:
            name: 实体名称
            limit: 返回数量限制
            
        Returns:
            WikidataEntity 列表
        """
        # 使用 Wikidata 搜索 API（比 SPARQL 模糊匹配快得多）
        search_url = "https://www.wikidata.org/w/api.php"
        params = {
            'action': 'wbsearchentities',
            'search': name,
            'language': 'zh',
            'uselang': 'zh',
            'format': 'json',
            'limit': min(limit, 20)
        }
        
        entities = []
        
        try:
            response = proxy_request(
                'get', search_url,
                proxy_url=self.proxy_url,
                timeout=15,
                params=params
            )
            data = response.json()
            
            search_results = data.get('search', [])
            
            for item in search_results:
                wikidata_id = item.get('id', '')
                
                # 创建基础实体
                entity = WikidataEntity(
                    wikidata_id=wikidata_id,
                    name=item.get('label', ''),
                    description=item.get('description', ''),
                    lat=None,
                    lon=None,
                    wikipedia_url=f"https://www.wikidata.org/wiki/{wikidata_id}"
                )
                
                # 尝试获取坐标（使用快速 SPARQL 查询）
                if wikidata_id:
                    coord_query = f"""
                    SELECT ?coord WHERE {{
                        wd:{wikidata_id} wdt:P625 ?coord .
                    }}
                    LIMIT 1
                    """
                    coord_results = self._execute_sparql(coord_query)
                    if coord_results:
                        coord_str = coord_results[0].get('coord', {}).get('value', '')
                        match = re.search(r'Point\(([0-9.-]+)\s+([0-9.-]+)\)', coord_str)
                        if match:
                            entity.lon = float(match.group(1))
                            entity.lat = float(match.group(2))
                
                entities.append(entity)
                
        except Exception as e:
            print(f"   ⚠️ Wikidata search failed: {type(e).__name__}")
            
            # 回退到 SPARQL（更慢但更稳定）
            if not entities:
                sparql_query = f"""
                SELECT ?item ?itemLabel ?itemDescription ?coord
                WHERE {{
                    ?item rdfs:label "{name}"@zh .
                    OPTIONAL {{ ?item wdt:P625 ?coord . }}
                    SERVICE wikibase:label {{ bd:serviceParam wikibase:language "zh,en" . }}
                }}
                LIMIT {limit}
                """
                
                results = self._execute_sparql(sparql_query)
                
                for binding in results:
                    lat, lon = None, None
                    if 'coord' in binding:
                        coord_str = binding['coord']['value']
                        match = re.search(r'Point\(([0-9.-]+)\s+([0-9.-]+)\)', coord_str)
                        if match:
                            lon = float(match.group(1))
                            lat = float(match.group(2))
                    
                    item_uri = binding.get('item', {}).get('value', '')
                    wikidata_id = item_uri.split('/')[-1] if item_uri else ''
                    
                    entity = WikidataEntity(
                        wikidata_id=wikidata_id,
                        name=binding.get('itemLabel', {}).get('value', ''),
                        description=binding.get('itemDescription', {}).get('value', ''),
                        lat=lat,
                        lon=lon,
                        wikipedia_url=f"https://www.wikidata.org/wiki/{wikidata_id}"
                    )
                    entities.append(entity)
        
        return entities


# ============================================================================
# WorldKG 适配器 (OSM 语义知识图谱)
# ============================================================================

class WorldKGAdapter:
    """
    WorldKG/LinkedGeoData 适配器 - OSM 语义知识图谱查询
    
    将 OpenStreetMap 数据语义化的知识图谱，提供:
    - OSM 实体的语义关系
    - 地理实体间的拓扑关系
    - 与 OSM ID 的直接关联
    
    注意: WorldKG 原端点已下线，现使用 LinkedGeoData 作为替代
    LinkedGeoData: http://linkedgeodata.org/
    """
    
    # SPARQL 端点 (LinkedGeoData 作为主端点)
    WORLDKG_ENDPOINTS = [
        "http://linkedgeodata.org/sparql",       # LinkedGeoData (可用)
        "https://worldkg.2800.io/sparql",        # WorldKG (已下线)
    ]
    
    # LinkedGeoData / WorldKG 本体前缀
    PREFIXES = """
    PREFIX lgdo: <http://linkedgeodata.org/ontology/>
    PREFIX lgdm: <http://linkedgeodata.org/meta/>
    PREFIX lgd: <http://linkedgeodata.org/triplify/>
    PREFIX geo: <http://www.w3.org/2003/01/geo/wgs84_pos#>
    PREFIX geosparql: <http://www.opengis.net/ont/geosparql#>
    PREFIX geof: <http://www.opengis.net/def/function/geosparql/>
    PREFIX geom: <http://geovocab.org/geometry#>
    PREFIX ogc: <http://www.opengis.net/ont/geosparql#>
    PREFIX osm: <https://www.openstreetmap.org/>
    PREFIX osmnode: <http://linkedgeodata.org/triplify/node>
    PREFIX osmway: <http://linkedgeodata.org/triplify/way>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    """
    
    # LinkedGeoData 类型映射 (lgdo: ontology)
    # 参考: http://linkedgeodata.org/ontology/
    LGD_TYPE_MAPPING = {
        # 住宿
        "hotel": "lgdo:Hotel",
        "hostel": "lgdo:Hostel",
        "motel": "lgdo:Motel",
        
        # 餐饮
        "restaurant": "lgdo:Restaurant",
        "cafe": "lgdo:Cafe",
        "bar": "lgdo:Bar",
        "fast_food": "lgdo:FastFood",
        
        # 购物
        "supermarket": "lgdo:Supermarket",
        "shopping_mall": "lgdo:Mall",
        "convenience": "lgdo:Convenience",
        
        # 交通
        "bus_stop": "lgdo:BusStop",
        "railway_station": "lgdo:RailwayStation",
        "subway_station": "lgdo:SubwayEntrance",
        "parking": "lgdo:Parking",
        
        # 教育
        "school": "lgdo:School",
        "university": "lgdo:University",
        "kindergarten": "lgdo:Kindergarten",
        
        # 医疗
        "hospital": "lgdo:Hospital",
        "pharmacy": "lgdo:Pharmacy",
        "clinic": "lgdo:Clinic",
        
        # 文化/娱乐
        "museum": "lgdo:Museum",
        "cinema": "lgdo:Cinema",
        "theatre": "lgdo:Theatre",
        "library": "lgdo:Library",
        
        # 金融
        "bank": "lgdo:Bank",
        "atm": "lgdo:Atm",
        
        # 其他
        "police": "lgdo:PoliceStation",
        "fire_station": "lgdo:FireStation",
        "post_office": "lgdo:PostOffice",
    }
    
    def __init__(self, timeout: int = 60, proxy_url: str = None):
        """初始化 WorldKG 适配器"""
        self.timeout = timeout
        self.proxy_url = proxy_url
        # 🆕 使用 ProxySession 支持自动代理切换
        self.session = ProxySession(proxy_url=proxy_url, auto_switch=True)
        self.session.headers.update({
            'Accept': 'application/sparql-results+json'
        })
        
        self.current_endpoint = self.WORLDKG_ENDPOINTS[0]
    
    def _execute_sparql_direct(self, full_query: str, endpoint: str = None) -> List[Dict[str, Any]]:
        """
        直接执行完整的 SPARQL 查询（查询已包含前缀）
        
        Args:
            full_query: 完整的 SPARQL 查询语句（包含前缀）
            endpoint: 可选的端点 URL
            
        Returns:
            查询结果列表
        """
        endpoint = endpoint or self.current_endpoint
        
        for ep in ([endpoint] + [e for e in self.WORLDKG_ENDPOINTS if e != endpoint]):
            try:
                response = self.session.post(
                    ep,
                    data={'query': full_query},
                    timeout=self.timeout
                )
                response.raise_for_status()
                
                data = response.json()
                results = data.get('results', {}).get('bindings', [])
                
                self.current_endpoint = ep
                return results
                
            except Exception as e:
                print(f"   ⚠️ WorldKG endpoint {ep} query failed: {str(e)[:50]}")
                continue
        
        return []
    
    def _execute_sparql(self, query: str, endpoint: str = None) -> List[Dict[str, Any]]:
        """
        执行 SPARQL 查询（自动添加完整前缀）
        
        Args:
            query: SPARQL 查询语句（不含前缀）
            endpoint: 可选的端点 URL
            
        Returns:
            查询结果列表
        """
        endpoint = endpoint or self.current_endpoint
        full_query = self.PREFIXES + query
        
        for ep in ([endpoint] + [e for e in self.WORLDKG_ENDPOINTS if e != endpoint]):
            try:
                response = self.session.post(
                    ep,
                    data={'query': full_query},
                    timeout=self.timeout
                )
                response.raise_for_status()
                
                data = response.json()
                results = data.get('results', {}).get('bindings', [])
                
                # 更新当前端点为成功的端点
                self.current_endpoint = ep
                return results
                
            except Exception as e:
                print(f"   ⚠️ WorldKG endpoint {ep} query failed: {str(e)[:50]}")
                continue
        
        return []
    
    def query_entities_in_bbox(self, bbox: List[float], entity_type: str = None,
                               limit: int = 1000, dedupe_by_name: bool = True) -> List[Dict[str, Any]]:
        """
        查询边界框内的 OSM 实体 (使用 LinkedGeoData)
        
        Args:
            bbox: [south, north, west, east] 边界框
            entity_type: 可选的实体类型 (如 "hotel", "restaurant")
            limit: 返回数量限制
            dedupe_by_name: 是否按名称+位置去重（同一位置的同名实体只保留一个）
            
        Returns:
            实体列表
        """
        # 构建类型过滤
        type_filter = ""
        if entity_type and entity_type in self.LGD_TYPE_MAPPING:
            lgd_type = self.LGD_TYPE_MAPPING[entity_type]
            type_filter = f"?entity a {lgd_type} ."
        
        # LinkedGeoData SPARQL 查询
        # 使用 geo:lat 和 geo:long 获取坐标 (前缀 geo: 指向 wgs84_pos#)
        # 【重要】使用最小前缀集，避免 LinkedGeoData 超时
        # 【重要】SPARQL limit 要比目标 limit 大，因为后续会去重
        sparql_limit = limit * 5  # 请求更多数据以补偿去重损失
        
        minimal_prefixes = """
PREFIX geo: <http://www.w3.org/2003/01/geo/wgs84_pos#>
PREFIX lgdo: <http://linkedgeodata.org/ontology/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""
        query_body = f"""
SELECT DISTINCT ?entity ?name ?lat ?lon ?type
WHERE {{
    {type_filter if type_filter else "?entity a ?type ."}
    
    ?entity geo:lat ?lat ;
            geo:long ?lon .
    
    OPTIONAL {{ ?entity rdfs:label ?name }}
    
    FILTER(
        ?lat >= {bbox[0]} && ?lat <= {bbox[1]} &&
        ?lon >= {bbox[2]} && ?lon <= {bbox[3]}
    )
}}
LIMIT {sparql_limit}
"""
        full_query = minimal_prefixes + query_body
        
        results = self._execute_sparql_direct(full_query)
        
        # 第一步：按 osm_id 去重，合并同一实体的多个类型
        entities_dict = {}
        for r in results:
            try:
                lat_val = r.get('lat', {}).get('value', '0')
                lon_val = r.get('lon', {}).get('value', '0')
                osm_id = r.get('entity', {}).get('value', '').split('/')[-1]
                tag = r.get('type', {}).get('value', '')
                
                if osm_id in entities_dict:
                    # 合并类型标签
                    if tag and tag not in entities_dict[osm_id]['tags']:
                        entities_dict[osm_id]['tags'] += f", {tag.split('/')[-1]}"
                else:
                    entities_dict[osm_id] = {
                        'entity_uri': r.get('entity', {}).get('value', ''),
                        'name': r.get('name', {}).get('value', '') or '未命名',
                        'lat': float(lat_val) if lat_val else 0,
                        'lon': float(lon_val) if lon_val else 0,
                        'osm_id': osm_id,
                        'tags': tag.split('/')[-1] if tag else '',
                    }
            except (ValueError, TypeError):
                continue
        
        entities = list(entities_dict.values())
        
        # 第二步：按名称+位置去重（可选）
        # 同一位置（四舍五入到小数点后2位，约1km精度）的同名实体只保留一个
        # 这样可以合并同一公交站不同方向的站点等
        if dedupe_by_name:
            name_location_dict = {}
            for e in entities:
                # 使用名称+位置（约1km精度）作为key
                key = (e['name'], round(e['lat'], 2), round(e['lon'], 2))
                if key not in name_location_dict:
                    name_location_dict[key] = e
                else:
                    # 合并类型标签
                    existing_tags = name_location_dict[key]['tags']
                    new_tags = e['tags']
                    for tag in new_tags.split(', '):
                        if tag and tag not in existing_tags:
                            name_location_dict[key]['tags'] += f", {tag}"
            entities = list(name_location_dict.values())
        
        return entities[:limit]
    
    def query_nearby_entities(self, lat: float, lon: float, 
                              radius_km: float = 1.0,
                              entity_type: str = None,
                              limit: int = 500) -> List[Dict[str, Any]]:
        """
        查询指定点附近的实体
        
        Args:
            lat: 纬度
            lon: 经度
            radius_km: 搜索半径 (公里)
            entity_type: 可选的实体类型
            limit: 返回数量限制
            
        Returns:
            实体列表 (按距离排序)
        """
        # 使用边界框近似圆形搜索
        # 1度纬度约 111km
        delta_lat = radius_km / 111.0
        delta_lon = radius_km / (111.0 * abs(math.cos(math.radians(lat))))
        
        bbox = [lat - delta_lat, lat + delta_lat, lon - delta_lon, lon + delta_lon]
        
        entities = self.query_entities_in_bbox(bbox, entity_type, limit * 2)
        
        # 计算精确距离并过滤
        for entity in entities:
            entity['distance_km'] = self._haversine_distance(
                lat, lon, entity['lat'], entity['lon']
            )
        
        # 过滤超出半径的实体
        entities = [e for e in entities if e['distance_km'] <= radius_km]
        
        # 按距离排序
        entities.sort(key=lambda x: x['distance_km'])
        
        return entities[:limit]
    
    def _haversine_distance(self, lat1: float, lon1: float, 
                            lat2: float, lon2: float) -> float:
        """计算两点间的 Haversine 距离 (公里)"""
        R = 6371  # 地球半径 (公里)
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * 
             math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    def query_entity_relations(self, osm_id: str) -> List[Dict[str, Any]]:
        """
        查询 OSM 实体的语义关系
        
        Args:
            osm_id: OSM ID (如 "node/12345" 或 "way/67890")
            
        Returns:
            关系列表
        """
        # 解析 OSM ID
        if '/' in osm_id:
            osm_type, osm_num = osm_id.split('/')
            if osm_type == 'node':
                uri_pattern = f"osmnode:{osm_num}"
            elif osm_type == 'way':
                uri_pattern = f"osmway:{osm_num}"
            else:
                uri_pattern = f"osmrel:{osm_num}"
        else:
            uri_pattern = osm_id
        
        query = f"""
        SELECT ?entity ?predicate ?object ?objectLabel
        WHERE {{
            ?entity wkg:hasOSMId "{osm_id}" .
            ?entity ?predicate ?object .
            
            OPTIONAL {{ ?object rdfs:label ?objectLabel }}
        }}
        LIMIT 1000
        """
        
        results = self._execute_sparql(query)
        
        relations = []
        for r in results:
            relations.append({
                'entity': r.get('entity', {}).get('value', ''),
                'predicate': r.get('predicate', {}).get('value', ''),
                'object': r.get('object', {}).get('value', ''),
                'object_label': r.get('objectLabel', {}).get('value', '')
            })
        
        return relations
    
    def query_spatial_relations(self, osm_id: str, relation_type: str = "nearby") -> List[Dict[str, Any]]:
        """
        查询实体的空间关系
        
        Args:
            osm_id: OSM ID
            relation_type: 关系类型 (nearby, contains, within, intersects)
            
        Returns:
            相关实体列表
        """
        relation_predicate = {
            "nearby": "geof:nearby",
            "contains": "geof:sfContains",
            "within": "geof:sfWithin",
            "intersects": "geof:sfIntersects",
        }.get(relation_type, "geof:nearby")
        
        query = f"""
        SELECT ?relatedEntity ?relatedName ?relatedType ?distance
        WHERE {{
            ?entity wkg:hasOSMId "{osm_id}" ;
                    geo:hasGeometry ?geom1 .
            
            ?relatedEntity geo:hasGeometry ?geom2 .
            ?geom1 geo:asWKT ?wkt1 .
            ?geom2 geo:asWKT ?wkt2 .
            
            FILTER({relation_predicate}(?wkt1, ?wkt2, 1000, <http://www.opengis.net/def/uom/OGC/1.0/metre>))
            FILTER(?entity != ?relatedEntity)
            
            OPTIONAL {{ ?relatedEntity rdfs:label ?relatedName }}
            OPTIONAL {{ ?relatedEntity wkg:hasType ?relatedType }}
            
            BIND(geof:distance(?wkt1, ?wkt2, <http://www.opengis.net/def/uom/OGC/1.0/metre>) AS ?distance)
        }}
        ORDER BY ?distance
        LIMIT 1000
        """
        
        results = self._execute_sparql(query)
        
        related = []
        for r in results:
            related.append({
                'entity': r.get('relatedEntity', {}).get('value', ''),
                'name': r.get('relatedName', {}).get('value', ''),
                'type': r.get('relatedType', {}).get('value', ''),
                'distance': float(r.get('distance', {}).get('value', 0))
            })
        
        return related
    
    def search_by_name(self, name: str, entity_type: str = None, 
                       limit: int = 100) -> List[Dict[str, Any]]:
        """
        按名称搜索实体
        
        Args:
            name: 实体名称 (支持模糊匹配)
            entity_type: 可选的实体类型
            limit: 返回数量限制
            
        Returns:
            实体列表
        """
        tag_filter = ""
        if entity_type and entity_type in self.OSM_TAG_MAPPING:
            osm_tag = self.OSM_TAG_MAPPING[entity_type]
            key, value = osm_tag.split("=")
            tag_filter = f'FILTER(CONTAINS(STR(?tags), "{key}") && CONTAINS(STR(?tags), "{value}"))'
        
        query = f"""
        SELECT ?entity ?name ?lat ?lon ?osmId ?tags
        WHERE {{
            ?entity a wkg:OSMEntity ;
                    rdfs:label ?name ;
                    geo:hasGeometry ?geom ;
                    wkg:hasOSMId ?osmId .
            
            ?geom geo:asWKT ?wkt .
            
            OPTIONAL {{ ?entity wkg:hasTags ?tags }}
            
            FILTER(CONTAINS(LCASE(?name), LCASE("{name}")))
            
            BIND(geof:latitude(?wkt) AS ?lat)
            BIND(geof:longitude(?wkt) AS ?lon)
            
            {tag_filter}
        }}
        LIMIT {limit}
        """
        
        results = self._execute_sparql(query)
        
        entities = []
        for r in results:
            entities.append({
                'entity_uri': r.get('entity', {}).get('value', ''),
                'name': r.get('name', {}).get('value', ''),
                'lat': float(r.get('lat', {}).get('value', 0)) if r.get('lat') else None,
                'lon': float(r.get('lon', {}).get('value', 0)) if r.get('lon') else None,
                'osm_id': r.get('osmId', {}).get('value', ''),
                'tags': r.get('tags', {}).get('value', '')
            })
        
        return entities


# ============================================================================
# 任务拆解器 (Task Decomposer)
# ============================================================================

TASK_DECOMPOSITION_PROMPT = """你是一个任务规划专家。请将复杂的地理查询拆解为多个可执行的子任务。

## 可用的子任务类型

1. **spatial_proximity** - 空间邻近查询（需要参考位置）
   - 必需参数: poi_type (英文), reference_location (参考地点)
   - 可选参数: radius_meters (默认500)
   - 示例: 查找故宫附近的咖啡店 → poi_type="cafe", reference_location="故宫"

2. **poi_search** - 区域POI搜索（在某个城市/区域内搜索）
   - 必需参数: poi_type (英文), search_region (城市/区域名)
   - 示例: 柏林的酒店 → poi_type="hotel", search_region="柏林"
   - 示例: 搜索北京的博物馆 → poi_type="museum", search_region="北京"

3. **routing** - 路由导航
   - 必需参数: origin (起点), destination (终点)
   - 可选参数: transport_mode (walking/driving/cycling，默认walking)
   - 示例: 从故宫到咖啡店 → origin="故宫", destination="咖啡店"

4. **knowledge** - 知识图谱查询 (Wikidata)
   - 必需参数: entity_type (英文), location_filter (位置)
   - 示例: 北京的博物馆 → entity_type="museum", location_filter="北京"

5. **worldkg** - OSM语义查询 (WorldKG/LinkedGeoData)
   - 必需参数: entity_type (英文), region (区域名)
   - 示例: 柏林酒店的OSM语义信息 → entity_type="hotel", region="柏林"

6. **osm_data** - OSM基础数据下载
   - 必需参数: region (区域名)
   - 可选参数: data_types (["roads", "buildings", "waterways"])
   - 示例: 下载柏林道路数据 → region="柏林", data_types=["roads"]

7. **geocode** - 地理编码
   - 必需参数: location (地名)
   - 示例: 获取故宫坐标 → location="故宫"

## 用户查询
{user_query}

## 请输出 JSON 格式的任务拆解结果 (只输出JSON，不要其他内容):
{{
    "summary": "一句话概括任务目标",
    "sub_tasks": [
        {{
            "order": 1,
            "type": "poi_search",
            "description": "在柏林搜索酒店",
            "params": {{
                "poi_type": "hotel",
                "search_region": "柏林"
            }},
            "depends_on": null,
            "output_name": "hotels"
        }},
        {{
            "order": 2,
            "type": "worldkg",
            "description": "查询酒店的OSM语义信息",
            "params": {{
                "entity_type": "hotel",
                "region": "柏林"
            }},
            "depends_on": 1,
            "output_name": "hotel_semantics"
        }}
    ],
    "final_output": "最终输出描述"
}}

【重要】
1. params 字段必须包含该任务类型所需的所有参数！
2. 如果涉及某个区域，params 中务必包含 region 或 search_region 或 location_filter
3. 后续任务如果依赖前序任务的区域，也要在 params 中明确指定区域名"""


class TaskDecomposer:
    """任务拆解器 - 将复杂查询拆解为子任务"""
    
    def __init__(self, llm_client: 'LLMClient'):
        self.llm = llm_client
    
    def decompose(self, query: str) -> List[Dict[str, Any]]:
        """
        将复杂查询拆解为子任务列表
        
        Args:
            query: 用户的复杂查询
            
        Returns:
            子任务列表
        """
        prompt = TASK_DECOMPOSITION_PROMPT.format(user_query=query)
        response = self.llm.chat(prompt)
        
        if response:
            parsed = self.llm.parse_json_response(response)
            if parsed:
                return parsed.get('sub_tasks', [])
        
        return []


# ============================================================================
# 遥感数据适配器
# ============================================================================

# 🔧 修复：在模块级别设置PROJ数据库路径（必须在导入sentinelhub/pyproj之前）
# 注意：必须在导入任何使用PROJ的库之前设置环境变量
import os
import sys

# 如果PROJ_LIB未设置或路径无效，尝试查找并设置
if not os.environ.get('PROJ_LIB') or not os.path.exists(os.path.join(os.environ.get('PROJ_LIB', ''), 'proj.db')):
    # 尝试从conda环境或QGIS环境找到PROJ数据库
    proj_paths = [
        # Conda环境中的PROJ路径（Windows）
        os.path.join(sys.prefix, 'Library', 'share', 'proj'),
        # Conda环境中的PROJ路径（Linux/Mac）
        os.path.join(sys.prefix, 'share', 'proj'),
        # QGIS环境中的PROJ路径
        os.path.join(os.environ.get('QGIS_PREFIX_PATH', ''), 'share', 'proj'),
        # 尝试从conda环境变量获取
        os.path.join(os.environ.get('CONDA_PREFIX', ''), 'Library', 'share', 'proj'),
        os.path.join(os.environ.get('CONDA_PREFIX', ''), 'share', 'proj'),
    ]
    
    for proj_path in proj_paths:
        if proj_path and os.path.exists(proj_path):
            proj_db = os.path.join(proj_path, 'proj.db')
            if os.path.exists(proj_db):
                os.environ['PROJ_LIB'] = proj_path
                # 同时设置PROJ_DATA（某些版本需要）
                os.environ['PROJ_DATA'] = proj_path
                break

def _setup_proj_database():
    """设置PROJ数据库路径（用于运行时调用）"""
    # 如果已经设置过，直接返回
    if os.environ.get('PROJ_LIB') and os.path.exists(os.path.join(os.environ['PROJ_LIB'], 'proj.db')):
        return True
    
    # 尝试从conda环境或QGIS环境找到PROJ数据库
    proj_paths = [
        os.path.join(sys.prefix, 'Library', 'share', 'proj'),
        os.path.join(sys.prefix, 'share', 'proj'),
        os.path.join(os.environ.get('QGIS_PREFIX_PATH', ''), 'share', 'proj'),
        os.path.join(os.environ.get('CONDA_PREFIX', ''), 'Library', 'share', 'proj'),
        os.path.join(os.environ.get('CONDA_PREFIX', ''), 'share', 'proj'),
    ]
    
    for proj_path in proj_paths:
        if proj_path and os.path.exists(proj_path):
            proj_db = os.path.join(proj_path, 'proj.db')
            if os.path.exists(proj_db):
                os.environ['PROJ_LIB'] = proj_path
                os.environ['PROJ_DATA'] = proj_path
                return True
    
    return False

class SentinelHubAdapter:
    """
    Sentinel Hub API 适配器
    
    支持 Sentinel-2、Landsat、MODIS 等卫星数据下载
    文档: https://docs.sentinel-hub.com/api/latest/
    """
    
    # Sentinel Hub API 端点
    PROCESS_API_URL = "https://shapps.dataspace.copernicus.eu/api/v1/process"
    OGC_API_URL = "https://shapps.dataspace.copernicus.eu/ogc/wms"
    
    # 支持的卫星类型
    SUPPORTED_SATELLITES = {
        "sentinel-2": "SENTINEL-2",
        "sentinel-2-l2a": "SENTINEL-2_L2A",
        "landsat-8": "LANDSAT_8",
        "landsat-9": "LANDSAT_9",
        "modis": "MODIS"
    }
    
    def __init__(self, client_id: str = None, client_secret: str = None, timeout: int = 300):
        """
        初始化 Sentinel Hub 适配器
        
        Args:
            client_id: Sentinel Hub Client ID（从 local_settings 或环境变量读取）
            client_secret: Sentinel Hub Client Secret（从 local_settings 或环境变量读取）
            timeout: 请求超时时间（秒），遥感数据处理可能需要较长时间
        """
        self.timeout = timeout
        self.session = requests.Session()
        
        # 从 local_settings 或环境变量读取凭证
        if client_id:
            self.client_id = client_id
        elif local_settings is not None and hasattr(local_settings, 'SENTINEL_HUB_CLIENT_ID'):
            self.client_id = getattr(local_settings, 'SENTINEL_HUB_CLIENT_ID')
        else:
            self.client_id = os.environ.get('SENTINEL_HUB_CLIENT_ID')
        
        if client_secret:
            self.client_secret = client_secret
        elif local_settings is not None and hasattr(local_settings, 'SENTINEL_HUB_CLIENT_SECRET'):
            self.client_secret = getattr(local_settings, 'SENTINEL_HUB_CLIENT_SECRET')
        else:
            self.client_secret = os.environ.get('SENTINEL_HUB_CLIENT_SECRET')
        
        if not self.client_id or not self.client_secret:
            print("   ⚠️ Sentinel Hub credentials not configured, cannot download Sentinel-2 data")
            print("   ℹ️ Please set SENTINEL_HUB_CLIENT_ID and SENTINEL_HUB_CLIENT_SECRET in local_settings.py")
            print("   ℹ️ Or set environment variables SENTINEL_HUB_CLIENT_ID and SENTINEL_HUB_CLIENT_SECRET")
            print("   ℹ️ Register at: https://shapps.dataspace.copernicus.eu/dashboard/#/")
    
    def download_imagery(self, bbox: List[float], time_range: str, 
                        satellite: str = "sentinel-2", cloud_cover_max: float = 70.0,
                        bands: List[str] = None, processing: str = "",
                        region: str = "", output_dir: str = "downloaded_data") -> Optional[str]:
        """
        下载遥感影像
        
        注意: CDSE 免费版不支持 Process API，直接使用 Sentinel Hub Python 库下载数据。
        如需使用 Process API（商业版），请参考注释中的代码。
        
        Args:
            bbox: 边界框 [south, north, west, east]
            time_range: 时间范围 "YYYY-MM-DD,YYYY-MM-DD" 或 "YYYY-MM"
            satellite: 卫星类型 (sentinel-2, landsat-8, etc.)
            cloud_cover_max: 最大云量百分比
            bands: 波段列表 (如 ["B04", "B08"] 或 ["RGB"])
            processing: 处理类型 (NDVI, NDWI, RGB, false_color, 空=原始波段)
            region: 区域名称（用于文件命名）
            output_dir: 输出目录（默认 downloaded_data）
            
        Returns:
            下载的 GeoTIFF 文件路径，或 None
        """
        if not self.client_id or not self.client_secret:
            return None
        
        # 标准化卫星名称
        satellite_normalized = satellite.lower().replace('_', '-')
        if satellite_normalized not in self.SUPPORTED_SATELLITES:
            print(f"   ⚠️ Unsupported satellite type: {satellite}")
            return None
        
        print(f"   Sentinel Hub: Downloading {satellite} data...")
        
        # 解析时间范围
        time_start, time_end = self._parse_time_range(time_range)
        if not time_start or not time_end:
            print(f"   ⚠️ Invalid time range: {time_range}")
            return None
        
        # CDSE 免费版不支持 Process API，直接使用 Sentinel Hub Python 库
        # 这是更高效的方式，避免了不必要的 API 请求
        return self._download_with_sentinelhub_library(
            bbox, time_start, time_end, satellite_normalized, 
            cloud_cover_max, bands, processing, region, output_dir
        )
        
        # ========== 以下为 Process API 代码（商业版可用，当前已注释） ==========
        # 如果将来需要使用 Process API（商业版 Sentinel Hub），可以取消注释以下代码
        # 并注释掉上面的 _download_with_sentinelhub_library 调用
        #
        # evalscript = self._build_evalscript(satellite_normalized, bands, processing)
        # payload = {
        #     "input": {
        #         "bounds": {
        #             "bbox": [bbox[2], bbox[0], bbox[3], bbox[1]]  # [west, south, east, north]
        #         },
        #         "data": [{
        #             "type": self.SUPPORTED_SATELLITES[satellite_normalized],
        #             "dataFilter": {
        #                 "timeRange": {
        #                     "from": time_start,
        #                     "to": time_end
        #                 },
        #                 "mosaickingOrder": "leastCC"  # 选择云量最少的影像
        #             }
        #         }]
        #     },
        #     "output": {
        #         "width": 512,
        #         "height": 512,
        #         "responses": [{
        #             "identifier": "default",
        #             "format": {
        #                 "type": "image/tiff"
        #             }
        #         }]
        #     },
        #     "evalscript": evalscript
        # }
        # 
        # try:
        #     token = self._get_access_token()
        #     if not token:
        #         print(f"   ⚠️ 无法获取访问令牌，请检查凭证配置")
        #         return None
        #     
        #     headers = {
        #         "Authorization": f"Bearer {token}",
        #         "Content-Type": "application/json"
        #     }
        #     
        #     print(f"   🔍 请求 Process API: {self.PROCESS_API_URL}")
        #     response = self.session.post(
        #         self.PROCESS_API_URL,
        #         json=payload,
        #         headers=headers,
        #         timeout=self.timeout
        #     )
        #     
        #     if response.status_code == 404:
        #         print(f"   ⚠️ Process API 端点不存在 (404)")
        #         return None
        #     elif response.status_code == 401:
        #         print(f"   ⚠️ 认证失败 (401)，请检查 Client ID 和 Client Secret")
        #         return None
        #     elif response.status_code == 403:
        #         print(f"   ⚠️ 权限不足 (403)，请检查账户权限")
        #         return None
        #     
        #     response.raise_for_status()
        #     
        #     from datetime import datetime
        #     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        #     safe_satellite = satellite_normalized.replace('-', '_')
        #     filename = f"sentinel_{safe_satellite}_{timestamp}.tif"
        #     filepath = Path('downloaded_data') / 'remote_sensing' / filename
        #     filepath.parent.mkdir(parents=True, exist_ok=True)
        #     
        #     with open(filepath, 'wb') as f:
        #         f.write(response.content)
        #     
        #     print(f"   ✓ Sentinel Hub Process API 下载成功: {filepath}")
        #     return str(filepath)
        #     
        # except requests.exceptions.HTTPError as e:
        #     error_msg = str(e)
        #     if hasattr(e.response, 'text'):
        #         error_msg += f"\n   响应内容: {e.response.text[:200]}"
        #     print(f"   ⚠️ Sentinel Hub HTTP 错误: {error_msg[:150]}")
        #     return None
        # except Exception as e:
        #     print(f"   ⚠️ Sentinel Hub 下载失败: {str(e)[:100]}")
        #     import traceback
        #     print(f"   📋 详细错误: {traceback.format_exc()[:200]}")
        #     return None
    
    def _get_access_token(self) -> Optional[str]:
        """获取 Sentinel Hub 访问令牌"""
        try:
            response = requests.post(
                "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data.get('access_token')
        except Exception as e:
            print(f"   ⚠️ Failed to get access token: {str(e)[:50]}")
            return None
    
    def _parse_time_range(self, time_range: str) -> tuple:
        """解析时间范围字符串"""
        try:
            if ',' in time_range:
                # "2024-01-01,2024-01-31"
                parts = time_range.split(',')
                return parts[0].strip(), parts[1].strip()
            elif len(time_range) == 7:
                # "2024-01" -> "2024-01-01,2024-01-31"
                from datetime import datetime
                start = f"{time_range}-01"
                year, month = map(int, time_range.split('-'))
                if month == 12:
                    end = f"{year}-12-31"
                else:
                    next_month = datetime(year, month + 1, 1)
                    end = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")
                return start, end
            else:
                return None, None
        except Exception:
            return None, None
    
    def _build_evalscript(self, satellite: str, bands: List[str], processing: str) -> str:
        """构建 Sentinel Hub evalscript"""
        if satellite.startswith("sentinel-2"):
            if processing == "NDVI":
                return """
                //VERSION=3
                function setup() {
                    return {
                        input: [{
                            bands: ["B04", "B08"]
                        }],
                        output: {
                            bands: 1,
                            sampleType: "FLOAT32"
                        }
                    };
                }
                function evaluatePixel(sample) {
                    let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
                    return [ndvi];
                }
                """
            elif processing == "NDWI":
                return """
                //VERSION=3
                function setup() {
                    return {
                        input: [{
                            bands: ["B03", "B08"]
                        }],
                        output: {
                            bands: 1,
                            sampleType: "FLOAT32"
                        }
                    };
                }
                function evaluatePixel(sample) {
                    let ndwi = (sample.B03 - sample.B08) / (sample.B03 + sample.B08);
                    return [ndwi];
                }
                """
            elif processing == "RGB" or (bands and "RGB" in bands):
                return """
                //VERSION=3
                function setup() {
                    return {
                        input: [{
                            bands: ["B04", "B03", "B02"]
                        }],
                        output: {
                            bands: 3
                        }
                    };
                }
                function evaluatePixel(sample) {
                    return [2.5 * sample.B04, 2.5 * sample.B03, 2.5 * sample.B02];
                }
                """
            elif processing == "false_color":
                return """
                //VERSION=3
                function setup() {
                    return {
                        input: [{
                            bands: ["B08", "B04", "B03"]
                        }],
                        output: {
                            bands: 3
                        }
                    };
                }
                function evaluatePixel(sample) {
                    return [2.5 * sample.B08, 2.5 * sample.B04, 2.5 * sample.B03];
                }
                """
            else:
                # 默认返回所有波段
                return """
                //VERSION=3
                function setup() {
                    return {
                        input: [{
                            bands: ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B11", "B12"]
                        }],
                        output: {
                            bands: 12
                        }
                    };
                }
                function evaluatePixel(sample) {
                    return [sample.B01, sample.B02, sample.B03, sample.B04, sample.B05, 
                            sample.B06, sample.B07, sample.B08, sample.B8A, sample.B09, 
                            sample.B11, sample.B12];
                }
                """
        else:
            # Landsat 或其他卫星的默认脚本
            return """
            //VERSION=3
            function setup() {
                return {
                    input: [{
                        bands: ["B04", "B03", "B02"]
                    }],
                    output: {
                        bands: 3
                    }
                };
            }
            function evaluatePixel(sample) {
                return [sample.B04, sample.B03, sample.B02];
            }
            """
    
    def _download_with_sentinelhub_library(self, bbox: List[float], time_start: str, 
                                          time_end: str, satellite: str,
                                          cloud_cover_max: float, bands: List[str],
                                          processing: str, region: str = "",
                                          output_dir: str = "downloaded_data") -> Optional[str]:
        """
        使用 Sentinel Hub Python 库下载数据（CDSE 主要方案）
        
        CDSE 免费版不支持 Process API，因此直接使用 Sentinel Hub Python 库下载数据。
        这是推荐的方式，更高效且稳定。
        
        Args:
            bbox: 边界框 [south, north, west, east]
            time_start: 开始时间 "YYYY-MM-DD"
            time_end: 结束时间 "YYYY-MM-DD"
            satellite: 卫星类型 (sentinel-2, etc.)
            cloud_cover_max: 最大云量百分比
            bands: 波段列表
            processing: 处理类型
            region: 区域名称（用于文件命名）
            output_dir: 输出目录（默认 downloaded_data）
            
        Returns:
            下载的 GeoTIFF 文件路径，或 None
        """
        try:
            # 🔧 修复：确保PROJ数据库路径已设置（模块级别已设置，这里再次确认）
            _setup_proj_database()
            
            # 尝试导入 sentinelhub 库（必须在PROJ路径设置之后）
            try:
                # 🔧 修复：临时禁用PROJ网络功能，避免数据库上下文错误
                original_proj_network = os.environ.get('PROJ_NETWORK', '')
                os.environ['PROJ_NETWORK'] = 'OFF'
                
                from sentinelhub import (
                    SHConfig, SentinelHubRequest, DataCollection, 
                    MimeType, BBox, CRS, bbox_to_dimensions
                )
                
                # 恢复原始设置
                if original_proj_network:
                    os.environ['PROJ_NETWORK'] = original_proj_network
                elif 'PROJ_NETWORK' in os.environ:
                    del os.environ['PROJ_NETWORK']
                    
            except ImportError:
                print(f"   ⚠️ Sentinel Hub Python library not installed")
                print(f"   ℹ️ Please install: pip install sentinelhub")
                print(f"   ℹ️ Documentation: https://sentinelhub-py.readthedocs.io/")
                return None
            except Exception as e:
                error_msg = str(e)
                if 'no database context specified' in error_msg or 'proj_create' in error_msg:
                    print(f"   ⚠️ PROJ database path issue, trying to fix...")
                    print(f"   ℹ️ This may be due to pyproj and PROJ library version mismatch in conda environment")
                    print(f"   ℹ️ Suggested solutions:")
                    print(f"      1. Reinstall pyproj: conda install -c conda-forge pyproj")
                    print(f"      2. Or set environment variable: set PROJ_LIB={os.environ.get('PROJ_LIB', '')}")
                    print(f"   ⚠️ Sentinel Hub download function temporarily unavailable")
                    return None
                else:
                    raise
            
            print(f"   Using Sentinel Hub Python library to download data...")
            
            # 配置 Sentinel Hub (CDSE 端点)
            config = SHConfig()
            config.sh_client_id = self.client_id
            config.sh_client_secret = self.client_secret
            # CDSE 使用不同的端点
            config.sh_base_url = "https://sh.dataspace.copernicus.eu"
            config.sh_token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
            
            # 构建边界框（使用字符串CRS避免PROJ错误）
            try:
                bbox_obj = BBox(bbox=[bbox[2], bbox[0], bbox[3], bbox[1]], crs=CRS.WGS84)
            except Exception as e:
                # 如果CRS.WGS84失败，尝试使用字符串
                print(f"   ⚠️ Using CRS.WGS84 failed, trying string CRS: {e}")
                try:
                    from sentinelhub import CRS as SentinelCRS
                    bbox_obj = BBox(bbox=[bbox[2], bbox[0], bbox[3], bbox[1]], crs=SentinelCRS('EPSG:4326'))
                except Exception as e2:
                    print(f"   ⚠️ Failed to build bounding box: {e2}")
                    return None
            
            # 计算输出尺寸（保持合理的分辨率，限制最大尺寸避免超时）
            resolution = 10  # 10米分辨率
            size = bbox_to_dimensions(bbox_obj, resolution=resolution)
            # 限制最大尺寸为 2500x2500（避免下载超时）
            max_size = 2500
            if size[0] > max_size or size[1] > max_size:
                scale = max(size[0], size[1]) / max_size
                size = (int(size[0] / scale), int(size[1] / scale))
                print(f"   ⚠️ Area too large, adjusting resolution: {size}")
            else:
                print(f"   Output size: {size}")
            
            # 🔑 关键: 定义 CDSE 版本的数据集合（覆盖 service_url）
            # CDSE 免费版使用不同的端点，需要重新定义数据集合
            if satellite.startswith("sentinel-2"):
                data_collection = DataCollection.define_from(
                    DataCollection.SENTINEL2_L2A,
                    'CDSE_SENTINEL2_L2A',
                    service_url='https://sh.dataspace.copernicus.eu'
                )
            elif satellite.startswith("landsat"):
                # Landsat 数据: CDSE 目前不直接支持，尝试使用 Sentinel-2 作为替代
                # 或者用户可以配置商业版 Sentinel Hub（支持 Landsat）
                print(f"   ⚠️ CDSE free version doesn't support Landsat, trying similar Sentinel-2 data...")
                print(f"   ℹ️ Sentinel-2 is similar to Landsat, 10-60m resolution, suitable for medium-scale analysis")
                data_collection = DataCollection.define_from(
                    DataCollection.SENTINEL2_L2A,
                    'CDSE_SENTINEL2_L2A',
                    service_url='https://sh.dataspace.copernicus.eu'
                )
            else:
                data_collection = DataCollection.define_from(
                    DataCollection.SENTINEL2_L2A,
                    'CDSE_SENTINEL2_L2A',
                    service_url='https://sh.dataspace.copernicus.eu'
                )
            
            # 构建 evalscript
            evalscript = self._build_evalscript(satellite, bands, processing)
            
            # 创建请求
            # 🔧 使用 leastCC 合成策略，优先选择云量最少的影像，减少轨道接缝问题
            from sentinelhub import MosaickingOrder
            request = SentinelHubRequest(
                evalscript=evalscript,
                input_data=[
                    SentinelHubRequest.input_data(
                        data_collection=data_collection,
                        time_interval=(time_start, time_end),
                        mosaicking_order=MosaickingOrder.LEAST_CC,  # 优先选择云量最少的影像
                        maxcc=cloud_cover_max / 100.0 if cloud_cover_max else 0.3,  # 最大云量
                    )
                ],
                responses=[
                    SentinelHubRequest.output_response('default', MimeType.TIFF)
                ],
                bbox=bbox_obj,
                size=size,
                config=config
            )
            
            print(f"   ⏳ Downloading data (may take a few minutes)...")
            image_data = request.get_data()[0]
            
            # 保存为 GeoTIFF - 改进文件命名
            from datetime import datetime
            import re
            
            # 构建有意义的文件名: {region}_{satellite}_{time}_{processing}.tif
            safe_satellite = satellite.replace('-', '_')
            # 清理区域名（移除特殊字符）
            safe_region = re.sub(r'[^\w\u4e00-\u9fff]', '_', region) if region else "unknown"
            safe_region = safe_region[:30]  # 限制长度
            # 时间范围
            time_str = f"{time_start[:7]}_{time_end[:7]}" if time_start != time_end else time_start[:7]
            time_str = time_str.replace('-', '')
            # 处理类型
            proc_str = f"_{processing}" if processing else ""
            
            filename = f"{safe_region}_{safe_satellite}_{time_str}{proc_str}.tif"
            filepath = Path(output_dir) / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存图像数据
            import numpy as np
            if isinstance(image_data, np.ndarray):
                # 使用 rasterio 保存 GeoTIFF
                try:
                    import rasterio
                    from rasterio.transform import from_bounds
                    
                    # 计算地理变换参数
                    transform = from_bounds(bbox[2], bbox[0], bbox[3], bbox[1], 
                                          image_data.shape[1], image_data.shape[0])
                    
                    # 保存为 GeoTIFF
                    with rasterio.open(
                        filepath,
                        'w',
                        driver='GTiff',
                        height=image_data.shape[0],
                        width=image_data.shape[1],
                        count=image_data.shape[2] if len(image_data.shape) > 2 else 1,
                        dtype=image_data.dtype,
                        crs='EPSG:4326',
                        transform=transform
                    ) as dst:
                        if len(image_data.shape) > 2:
                            for i in range(image_data.shape[2]):
                                dst.write(image_data[:, :, i], i + 1)
                        else:
                            dst.write(image_data, 1)
                    
                    print(f"   ✓ Sentinel Hub Python library download successful: {filepath}")
                    return str(filepath)
                except ImportError:
                    print(f"   ⚠️ rasterio not installed, cannot save GeoTIFF")
                    print(f"   ℹ️ Please install: pip install rasterio")
                    # 保存为 numpy 数组（临时方案）
                    np.save(str(filepath).replace('.tif', '.npy'), image_data)
                    print(f"   ⚠️ Saved as numpy array: {filepath.replace('.tif', '.npy')}")
                    return None
            else:
                print(f"   ⚠️ Unexpected data type: {type(image_data)}")
                return None
                
        except Exception as e:
            print(f"   ⚠️ Sentinel Hub Python library download failed: {str(e)[:150]}")
            import traceback
            print(f"   Detailed error: {traceback.format_exc()[:300]}")
            return None


class USGSAdapter:
    """
    USGS EarthExplorer API 适配器
    
    支持 Landsat 系列卫星数据下载
    文档: https://earthexplorer.usgs.gov/inventory/documentation
    """
    
    # USGS API 端点 (注意: 路径包含 /api/api/json/)
    API_BASE_URL = "https://m2m.cr.usgs.gov/api/api/json/stable"
    
    # 支持的 Landsat 产品 (Collection 2 Level-2)
    LANDSAT_PRODUCTS = {
        "landsat-8": "landsat_ot_c2_l2",   # Landsat 8-9 OLI/TIRS Collection 2 Level-2
        "landsat-9": "landsat_ot_c2_l2",   # Landsat 8-9 共用同一数据集
        "landsat-5": "landsat_tm_c2_l2",   # Landsat 4-5 TM Collection 2 Level-2
        "landsat-7": "landsat_etm_c2_l2"   # Landsat 7 ETM+ Collection 2 Level-2
    }
    
    def __init__(self, username: str = None, token: str = None, timeout: int = 300, proxy_url: str = None):
        """
        初始化 USGS 适配器
        
        Args:
            username: USGS 用户名（从 local_settings 或环境变量读取）
            token: USGS API Token（从 local_settings 或环境变量读取）
            timeout: 请求超时时间（秒）
            proxy_url: 代理服务器地址（国内访问 USGS 可能需要代理）
        
        注意: USGS M2M API 现在使用 API Token 而非密码认证
              登录 EarthExplorer -> Profile -> API Token -> Generate
        """
        self.timeout = timeout
        self.session = requests.Session()
        
        # 🆕 配置代理（国内访问 USGS API 可能需要代理）
        self.proxy_url = proxy_url
        if self.proxy_url:
            self.session.proxies = {
                'http': self.proxy_url,
                'https': self.proxy_url
            }
            # print(f"   ℹ️ USGS 使用代理: {self.proxy_url}")
        
        # 从 local_settings 或环境变量读取凭证
        if username:
            self.username = username
        elif local_settings is not None and hasattr(local_settings, 'USGS_USERNAME'):
            self.username = getattr(local_settings, 'USGS_USERNAME')
        else:
            self.username = os.environ.get('USGS_USERNAME')
        
        # 🆕 优先使用 API Token（新认证方式）
        if token:
            self.token = token
        elif local_settings is not None and hasattr(local_settings, 'USGS_TOKEN'):
            self.token = getattr(local_settings, 'USGS_TOKEN')
        else:
            self.token = os.environ.get('USGS_TOKEN')
        
        self.api_key = None
        
        if not self.username or not self.token:
            print("   ⚠️ USGS credentials not configured, cannot download Landsat data")
            print("   ℹ️ Please set USGS_USERNAME and USGS_TOKEN in local_settings.py")
            print("   ℹ️ Get API Token: Login EarthExplorer -> Profile -> API Token -> Generate")
            print("   ℹ️ Register at: https://ers.cr.usgs.gov/register/")
    
    def download_landsat(self, bbox: List[float], time_range: str,
                        satellite: str = "landsat-8", cloud_cover_max: float = 10.0,
                        region: str = "", output_dir: str = "downloaded_data") -> Optional[str]:
        """
        下载 Landsat 数据
        
        Args:
            bbox: 边界框 [south, north, west, east]
            time_range: 时间范围 "YYYY-MM-DD,YYYY-MM-DD"
            satellite: 卫星类型 (landsat-8, landsat-9)
            cloud_cover_max: 最大云量百分比
            region: 区域名称（用于文件命名）
            output_dir: 输出目录（默认 downloaded_data）
            
        Returns:
            下载的 GeoTIFF 文件路径，或 None
        """
        if not self.username or not self.token:
            return None
        
        satellite_normalized = satellite.lower().replace('_', '-')
        if satellite_normalized not in self.LANDSAT_PRODUCTS:
            print(f"   ⚠️ Unsupported Landsat type: {satellite}")
            return None
        
        print(f"   🛰️ USGS: downloading {satellite} data...")
        
        try:
            # 登录获取 API Key
            if not self.api_key:
                self.api_key = self._login()
                if not self.api_key:
                    return None
            
            # 解析时间范围
            time_start, time_end = self._parse_time_range(time_range)
            if not time_start or not time_end:
                print(f"   ⚠️ Invalid time range: {time_range}")
                return None
            
            # 搜索场景
            scenes = self._search_scenes(bbox, time_start, time_end, satellite_normalized, cloud_cover_max)
            if not scenes:
                print(f"   ⚠️ No Landsat scenes matching criteria found")
                return None
            
            # 选择云量最少的场景
            best_scene = min(scenes, key=lambda x: x.get('cloudCover', 100))
            scene_id = best_scene.get('entityId')
            
            print(f"   ✓ Found scene: {scene_id} (cloud cover: {best_scene.get('cloudCover', 0):.1f}%)")
            
            # 下载场景
            filepath = self._download_scene(scene_id, satellite_normalized, region, output_dir)
            return filepath
            
        except Exception as e:
            print(f"   ⚠️ USGS download failed: {str(e)[:100]}")
            return None
    
    def _login(self) -> Optional[str]:
        """
        登录 USGS API 获取 API Key
        
        使用 login-token 端点（USGS M2M API 新认证方式）
        
        智能重试策略：
        1. 先尝试直连（不用代理）
        2. 如果直连失败，再尝试使用代理
        """
        # 🆕 使用 login-token 端点（替代已弃用的 login 端点）
        login_url = f"{self.API_BASE_URL}/login-token"
        login_data = {
            "username": self.username,
            "token": self.token
        }
        
        # 策略：先直连，再代理
        attempts = [
            ("直连", {'http': None, 'https': None}),  # 不使用代理
        ]
        if self.proxy_url:
            attempts.append(("代理", {'http': self.proxy_url, 'https': self.proxy_url}))
        
        for attempt_name, proxies in attempts:
            try:
                print(f"   USGS login ({attempt_name})...")
                response = requests.post(
                    login_url,
                    json=login_data,
                    timeout=60,  # 增加超时时间
                    proxies=proxies
                )
                
                # 检查 HTTP 状态码
                if response.status_code == 404:
                    print(f"   ⚠️ USGS login endpoint not found (404)")
                    print(f"   ℹ️ Please check USGS API endpoint: {login_url}")
                    return None
                
                response.raise_for_status()
                data = response.json()
                
                if data.get('errorCode'):
                    error_msg = data.get('errorMessage', 'unknown error')
                    print(f"   ⚠️ USGS login failed: {error_msg}")
                    # 认证错误不重试
                    if 'AUTH_INVALID' in str(data.get('errorCode', '')):
                        return None
                    continue
                
                api_key = data.get('data')
                if api_key:
                    print(f"   ✓ USGS login successful ({attempt_name})")
                    return api_key
                    
            except requests.exceptions.Timeout:
                print(f"   ⚠️ USGS {attempt_name} timeout, {'trying next strategy...' if attempt_name == 'direct' and self.proxy_url else 'giving up'}")
                continue
            except requests.exceptions.ProxyError:
                print(f"   ⚠️ USGS proxy connection failed")
                continue
            except requests.exceptions.ConnectionError as e:
                print(f"   ⚠️ USGS {attempt_name} connection failed: {str(e)[:80]}")
                continue
            except Exception as e:
                print(f"   ⚠️ USGS {attempt_name} failed: {str(e)[:100]}")
                continue
        
        print(f"   ⚠️ USGS login failed: all connection methods failed")
        print(f"   ℹ️ Please check network connection or USGS credentials")
        return None
    
    def _parse_time_range(self, time_range: str) -> tuple:
        """
        解析时间范围字符串
        
        支持的格式:
        - "YYYY-MM-DD,YYYY-MM-DD" (完整日期范围)
        - "YYYY-MM" (单月，自动扩展为月初到月末)
        - "YYYY" (单年，自动扩展为年初到年末)
        """
        import calendar
        try:
            time_range = time_range.strip()
            
            # 格式1: "YYYY-MM-DD,YYYY-MM-DD"
            if ',' in time_range:
                parts = time_range.split(',')
                return parts[0].strip(), parts[1].strip()
            
            # 格式2: "YYYY-MM" (单月)
            if len(time_range) == 7 and time_range[4] == '-':
                year = int(time_range[:4])
                month = int(time_range[5:7])
                last_day = calendar.monthrange(year, month)[1]
                return f"{time_range}-01", f"{time_range}-{last_day:02d}"
            
            # 格式3: "YYYY" (单年)
            if len(time_range) == 4 and time_range.isdigit():
                return f"{time_range}-01-01", f"{time_range}-12-31"
            
            return None, None
        except Exception:
            return None, None
    
    def _search_scenes(self, bbox: List[float], time_start: str, time_end: str,
                      satellite: str, cloud_cover_max: float) -> List[Dict]:
        """搜索符合条件的场景"""
        try:
            product = self.LANDSAT_PRODUCTS[satellite]
            
            # 构建搜索条件 (USGS M2M API v1.5+ 格式)
            search_params = {
                "datasetName": product,
                "maxResults": 10,
                "sceneFilter": {
                    "spatialFilter": {
                        "filterType": "mbr",
                        "lowerLeft": {
                            "latitude": bbox[0],
                            "longitude": bbox[2]
                        },
                        "upperRight": {
                            "latitude": bbox[1],
                            "longitude": bbox[3]
                        }
                    },
                    "acquisitionFilter": {
                        "start": time_start,
                        "end": time_end
                    },
                    "cloudCoverFilter": {
                        "max": cloud_cover_max
                    }
                }
            }
            
            response = self.session.post(
                f"{self.API_BASE_URL}/scene-search",
                json=search_params,
                headers={"X-Auth-Token": self.api_key},
                timeout=90
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('errorCode'):
                print(f"   ⚠️ USGS search failed: {data.get('errorMessage', 'unknown error')}")
                return []
            
            return data.get('data', {}).get('results', [])
            
        except Exception as e:
            print(f"   ⚠️ USGS scene search failed: {str(e)[:50]}")
            return []
    
    def _download_scene(self, scene_id: str, satellite: str, 
                        region: str = "", output_dir: str = "downloaded_data") -> Optional[str]:
        """下载场景数据"""
        try:
            # 获取下载 URL
            product = self.LANDSAT_PRODUCTS[satellite]
            response = self.session.post(
                f"{self.API_BASE_URL}/download-options",
                json={
                    "datasetName": product,
                    "entityIds": [scene_id]
                },
                headers={"X-Auth-Token": self.api_key},
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('errorCode'):
                print(f"   ⚠️ Failed to get download link: {data.get('errorMessage', 'unknown error')}")
                return None
            
            download_options = data.get('data', [])
            if not download_options:
                return None
            
            # 选择第一个可用的下载选项
            download_url = download_options[0].get('downloadUrl')
            if not download_url:
                return None
            
            # 下载文件 - 改进文件命名
            import re
            
            # 构建有意义的文件名: {region}_{satellite}_{scene_id}.tar.gz
            safe_satellite = satellite.replace('-', '_')
            # 清理区域名
            safe_region = re.sub(r'[^\w\u4e00-\u9fff]', '_', region) if region else "unknown"
            safe_region = safe_region[:30]  # 限制长度
            
            filename = f"{safe_region}_{safe_satellite}_{scene_id}.tar.gz"
            filepath = Path(output_dir) / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            download_response = self.session.get(download_url, timeout=self.timeout, stream=True)
            download_response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in download_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"   ✓ USGS download successful: {filepath}")
            return str(filepath)
            
        except Exception as e:
            print(f"   ⚠️ USGS scene download failed: {str(e)[:50]}")
            return None


# ============================================================================
# 统一地理查询引擎
# ============================================================================

class GeoQueryEngine:
    """统一地理查询引擎"""
    
    def __init__(self, catalog_path: str = None, data_root: str = None,
                 output_dir: str = None, use_llm: bool = True,
                 api_key: str = None, base_url: str = None, model: str = None):
        """
        初始化查询引擎
        
        Args:
            catalog_path: 本地数据目录文件路径
            data_root: 数据根目录
            output_dir: 输出目录
            use_llm: 是否使用 LLM
        """
        self.use_llm = use_llm
        self.output_dir = output_dir or "downloaded_data"
        
        # 初始化 LLM 客户端
        if use_llm:
            self.llm = LLMClient(
                api_key or DASHSCOPE_API_KEY,
                base_url or DASHSCOPE_BASE_URL,
                model or DEFAULT_MODEL
            )
        else:
            self.llm = None
        
        # 初始化本地数据搜索器
        if catalog_path:
            self.local_searcher = SmartDataSearcherWithClip(
                catalog_path,
                data_root=data_root,
                output_dir=output_dir,
                use_llm=use_llm,
                api_key=api_key,
                base_url=base_url,
                model=model
            )
        else:
            self.local_searcher = None
        
        # 初始化 OSM 适配器（传入 LLM 用于跨语言地名解析，使用代理 + 本地高德 Key）
        amap_key = None
        if local_settings is not None and hasattr(local_settings, "AMAP_API_KEY"):
            amap_key = getattr(local_settings, "AMAP_API_KEY")
        self.osm = OSMAdapter(llm=self.llm, proxy_url=OSM_PROXY_URL, amap_key=amap_key, output_dir=self.output_dir)
        
        # 初始化 Wikidata 适配器（使用专用代理，缩短超时时间避免卡太久）
        self.wikidata = WikidataAdapter(timeout=30, proxy_url=WIKIDATA_PROXY_URL, llm=self.llm)
        
        # 初始化 WorldKG 适配器（使用代理）
        self.worldkg = WorldKGAdapter(proxy_url=WORLDKG_PROXY_URL)
        
        # 🆕 初始化遥感数据适配器
        self.sentinel_hub = SentinelHubAdapter()
        self.usgs = USGSAdapter(proxy_url=USGS_PROXY_URL)
        
        # 初始化任务拆解器
        if use_llm and self.llm:
            self.task_decomposer = TaskDecomposer(self.llm)
        else:
            self.task_decomposer = None
        
        # 🆕 启动时自动检测代理（快速检测，不等太久）
        proxy_status = "未配置"
        if WIKIDATA_PROXY_URL:
            try:
                proxy_mgr = get_proxy_manager()
                current_node = proxy_mgr.get_current_node()
                if current_node and current_node != 'DIRECT':
                    proxy_status = f"已连接 ({current_node[:15]}...)" if len(current_node) > 15 else f"已连接 ({current_node})"
                else:
                    proxy_status = "DIRECT 模式（需切换节点）"
            except:
                proxy_status = "无法连接 Clash API"
        
        # 初始化完成（已移除详细输出）
    
    # -------------------------------------------------------------------------
    # 意图分析
    # -------------------------------------------------------------------------
    
    def analyze_intent(self, query: str) -> IntentAnalysis:
        """
        分析用户查询意图
        
        Args:
            query: 用户的自然语言查询
            
        Returns:
            IntentAnalysis 意图分析结果
        """
        if not self.use_llm or not self.llm:
            return self._analyze_intent_fallback(query)
        
        print("\nAnalyzing query intent...")
        
        prompt = INTENT_ANALYSIS_PROMPT.format(user_query=query)
        response = self.llm.chat(prompt)
        
        if response:
            parsed = self.llm.parse_json_response(response)
            if parsed:
                intent_str = parsed.get('intent', 'unknown')
                try:
                    intent = QueryIntent(intent_str)
                except ValueError:
                    intent = QueryIntent.UNKNOWN
                
                analysis = IntentAnalysis(
                    intent=intent,
                    confidence=parsed.get('confidence', 0.5),
                    summary=parsed.get('summary', query),
                    data_type=parsed.get('data_type', ''),
                    geographic_extent=parsed.get('geographic_extent', []),
                    target_region=parsed.get('target_region', ''),
                    needs_clip=parsed.get('needs_clip', False),
                    poi_type=parsed.get('poi_type', ''),
                    reference_location=parsed.get('reference_location', ''),
                    radius_meters=parsed.get('radius_meters', 500),
                    country=parsed.get('country', ''),
                    city=parsed.get('city', ''),
                    search_region=parsed.get('search_region', ''),
                    brand_name=parsed.get('brand_name', ''),
                    origin=parsed.get('origin', ''),
                    destination=parsed.get('destination', ''),
                    transport_mode=parsed.get('transport_mode', 'driving'),
                    facility_type=parsed.get('facility_type', ''),
                    criteria=parsed.get('criteria', []),
                    location_context=parsed.get('location_context', ''),
                    entity_type=parsed.get('entity_type', ''),
                    entity_name=parsed.get('entity_name', ''),  # 🆕 直接实体查询
                    property_filters=parsed.get('property_filters', {}),
                    location_filter=parsed.get('location_filter', ''),
                    osm_region=parsed.get('osm_region', ''),
                    osm_data_types=parsed.get('osm_data_types', []),
                    satellite=parsed.get('satellite', ''),
                    time_range=parsed.get('time_range', ''),
                    cloud_cover_max=parsed.get('cloud_cover_max', 0),
                    bands=parsed.get('bands', []),
                    processing=parsed.get('processing', ''),
                    remote_sensing_region=parsed.get('remote_sensing_region', ''),
                    sub_tasks=parsed.get('sub_tasks', []),
                    reasoning=parsed.get('reasoning', '')
                )
                
                print(f"   ✓ Intent type: {intent.value}")
                print(f"   ✓ Confidence: {analysis.confidence:.0%}")
                print(f"   ✓ Summary: {analysis.summary}")
                
                return analysis
        
        return self._analyze_intent_fallback(query)
    
    def _analyze_intent_fallback(self, query: str) -> IntentAnalysis:
        """Fallback intent analysis"""
        query_lower = query.lower()
        
        # Routing keywords
        routing_keywords = ['路线', '路径', '怎么走', '怎么去', '从', '到', 
                           'route', 'path', 'direction', 'from', 'to']
        
        # Proximity query keywords
        proximity_keywords = ['附近', '周围', '内的', '米内', '公里内',
                             'nearby', 'within', 'around', 'near']
        
        # POI type keywords
        poi_keywords = ['咖啡', '餐厅', '酒店', '药店', '医院', '学校', '超市',
                       'cafe', 'restaurant', 'hotel', 'pharmacy', 'hospital']
        
        # Local data keywords
        local_keywords = ['数据', '河流', '道路', '土地', 'dem', '高程',
                         'data', 'river', 'road', 'land', 'elevation']
        
        # Determine intent
        has_routing = any(kw in query_lower for kw in routing_keywords)
        has_proximity = any(kw in query_lower for kw in proximity_keywords)
        has_poi = any(kw in query_lower for kw in poi_keywords)
        has_local = any(kw in query_lower for kw in local_keywords)
        
        if has_routing and ('从' in query_lower or 'from' in query_lower):
            return IntentAnalysis(
                intent=QueryIntent.ROUTING,
                confidence=0.7,
                summary=query,
                reasoning="Detected routing keywords"
            )
        elif has_proximity and has_poi:
            return IntentAnalysis(
                intent=QueryIntent.SPATIAL_PROXIMITY,
                confidence=0.7,
                summary=query,
                reasoning="Detected spatial proximity query keywords"
            )
        else:
            return IntentAnalysis(
                intent=QueryIntent.UNKNOWN,
                confidence=0.3,
                summary=query,
                reasoning="Cannot determine intent"
            )
    
    # -------------------------------------------------------------------------
    # 统一查询入口
    # -------------------------------------------------------------------------
    
    def query(self, user_query: str, top_k: int = 5) -> UnifiedQueryResult:
        """
        统一查询入口
        
        Args:
            user_query: 用户的自然语言查询
            top_k: 返回结果数量
            
        Returns:
            UnifiedQueryResult 统一查询结果
        """
        import time
        start_time = time.time()
        
        # 🆕 重置代理切换标记，确保每次新查询都有机会自动切换
        reset_proxy_switch_flag()
        
        print(f"\n{'='*58}")
        print(f"Unified Geographic Query Engine")
        print(f"Query: {user_query}")
        print(f"{'='*58}")
        
        # Step 1: 意图分析
        intent = self.analyze_intent(user_query)
        
        # Step 2: 根据意图路由到对应处理器
        result = UnifiedQueryResult(
            query=user_query,
            intent=intent,
            source="unknown",
            timestamp=datetime.now().isoformat()
        )
        
        if intent.intent == QueryIntent.SPATIAL_PROXIMITY:
            self._handle_proximity_query(intent, result)
            result.source = "osm"
        
        elif intent.intent == QueryIntent.POI_SEARCH:
            self._handle_poi_search_query(intent, result)
            result.source = "osm"
            
        elif intent.intent == QueryIntent.ROUTING:
            self._handle_routing_query(intent, result)
            result.source = "osm"
            
        elif intent.intent == QueryIntent.RECOMMENDATION:
            self._handle_recommendation_query(intent, result)
            result.source = "wikidata+osm"
            
        elif intent.intent == QueryIntent.KNOWLEDGE:
            self._handle_knowledge_query(intent, result)
            result.source = "wikidata"
            
        elif intent.intent == QueryIntent.OSM_DATA:
            self._handle_osm_data_query(intent, result)
            result.source = "osm"
        
        elif intent.intent == QueryIntent.REMOTE_SENSING_DATA:
            self._handle_remote_sensing_query(intent, result)
            result.source = "remote_sensing"
            
        elif intent.intent == QueryIntent.WORLDKG:
            # 兼容旧的 worldkg 意图，重定向到语义分析
            self._handle_semantic_analysis_query(intent, result)
            result.source = "worldkg"
            
        elif intent.intent == QueryIntent.SEMANTIC_ANALYSIS:
            self._handle_semantic_analysis_query(intent, result)
            result.source = "worldkg"
            
        elif intent.intent == QueryIntent.COMPLEX:
            self._handle_complex_query(intent, result, user_query)
            result.source = "hybrid"
            
        elif intent.intent == QueryIntent.HYBRID:
            self._handle_hybrid_query(intent, result, top_k)
            result.source = "hybrid"
            
        else:
            result.warnings.append("Unable to determine the query intent, attempting a local data search.")
            if self.local_searcher:
                self._handle_local_data_query(intent, result, top_k)
                result.source = "local"
        
        # 计算处理时间
        result.processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Auto-save online query results to file
        self._auto_save_online_results(result, intent)
        
        print(f"\nQuery completed (elapsed {result.processing_time_ms}ms)")
        
        return result
    
    def _auto_save_online_results(self, result: UnifiedQueryResult, intent: IntentAnalysis):
        """
        自动保存在线查询结果到文件
        
        对于 POI、路由、知识查询等在线数据，自动保存为 GeoJSON 文件
        """
        if not self.output_dir:
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_files = []
        
        # 1. 保存 POI 结果
        if result.poi_results:
            # 支持多种查询类型的参数: poi_search (brand_name/poi_type/search_region), 
            # spatial_proximity (poi_type/reference_location), recommendation (facility_type)
            poi_type = (intent.brand_name or intent.poi_type or 
                       intent.facility_type or intent.entity_type or "poi")
            # 清理品牌名称中的正则符号（如 "星巴克|Starbucks" -> "星巴克_Starbucks"）
            poi_type = poi_type.replace('|', '_').replace('*', '').replace('?', '')
            location = (intent.search_region or intent.reference_location or 
                       intent.location_context or intent.location_filter or 
                       intent.target_region or intent.osm_region or
                       self._extract_location_from_query(result.query))
            poi_type_safe = self._sanitize_filename(poi_type, max_length=30)
            location_safe = self._sanitize_filename(location, max_length=20)
            filename = f"{poi_type_safe}_{location_safe}_{timestamp}"
            
            poi_file = self._save_poi_to_geojson(result.poi_results, self.output_dir, filename)
            if poi_file:
                saved_files.append(poi_file)
        
        # 2. 保存路由结果
        if result.route_result and result.route_result.geometry:
            origin = self._sanitize_filename(intent.origin or "start", max_length=15)
            dest = self._sanitize_filename(intent.destination or "end", max_length=15)
            mode = intent.transport_mode or "route"
            filename = f"route_{origin}_to_{dest}_{mode}_{timestamp}"
            
            route_file = self._save_route_to_geojson(result.route_result, self.output_dir, filename)
            if route_file:
                saved_files.append(route_file)
        
        # 3. 保存知识查询结果 (Wikidata/WorldKG)
        if result.knowledge_results:
            entity_type = intent.entity_type or intent.facility_type or "entity"
            # 从所有可能的位置字段中获取位置信息
            location = (intent.location_filter or intent.location_context or 
                       intent.search_region or intent.reference_location or 
                       intent.target_region or intent.osm_region or 
                       self._extract_location_from_query(result.query))
            entity_safe = self._sanitize_filename(entity_type)
            location_safe = self._sanitize_filename(location, max_length=20)
            filename = f"{entity_safe}_{location_safe}_{timestamp}"
            
            knowledge_file = self._save_knowledge_to_geojson(result.knowledge_results, self.output_dir, filename)
            if knowledge_file:
                saved_files.append(knowledge_file)
        
        # 更新结果中的下载文件列表
        if saved_files:
            result.downloaded_files.extend(saved_files)
    
    # -------------------------------------------------------------------------
    # 查询处理器
    # -------------------------------------------------------------------------
    
    def _handle_local_data_query(self, intent: IntentAnalysis, 
                                  result: UnifiedQueryResult, top_k: int):
        """处理本地数据查询"""
        print("\n📂 Executing local data search...")
        
        if not self.local_searcher:
            result.warnings.append("本地搜索器未初始化")
            return
        
        # 调用本地搜索器
        output = self.local_searcher.search_and_clip(
            result.query,
            top_k=top_k,
            auto_clip=intent.needs_clip
        )
        
        result.local_results = output.get('results', [])
        result.clip_results = output.get('clip_results', [])
        
        availability = output.get('availability', {})
        if not availability.get('is_available', True):
            result.warnings.extend(availability.get('warnings', []))
            result.suggestions.extend(availability.get('suggestions', []))
    
    def _handle_proximity_query(self, intent: IntentAnalysis, 
                                 result: UnifiedQueryResult):
        """处理空间邻近查询"""
        print("\nExecuting spatial proximity query (OSM)...")
        
        if not intent.reference_location:
            result.warnings.append("未指定参考位置")
            return
        
        # 🆕 Step 1: 构建完整的位置字符串（包含国家/城市上下文）
        # 对于国际地名，组合 "reference_location, city, country" 形式
        full_location = intent.reference_location
        location_parts = [intent.reference_location]
        
        if intent.city:
            location_parts.append(intent.city)
        if intent.country:
            location_parts.append(intent.country)
        
        # 如果有国家/城市信息，说明是国际地名，使用完整地址
        is_international = bool(intent.country or intent.city)
        if is_international:
            full_location = ", ".join(location_parts)
            print(f"   Geocoding (international): {full_location}")
        else:
            print(f"   Geocoding: {intent.reference_location}")
        
        # 对于国际地名，直接使用 Nominatim，跳过高德
        coords = self.osm.geocode(full_location, force_nominatim=is_international)
        
        if not coords:
            result.warnings.append(f"无法解析位置: {full_location}")
            result.suggestions.append("请提供更具体的地址或地名")
            return
        
        print(f"   ✓ Coordinates: ({coords['lat']:.6f}, {coords['lon']:.6f})")
        print(f"   ✓ Address: {coords.get('display_name', '')[:60]}...")
        
        # Step 2: 搜索周围 POI
        poi_type = intent.poi_type or "amenity"
        radius = intent.radius_meters or 500
        
        print(f"   Searching for {poi_type} within {radius}m...")
        
        pois = self.osm.search_poi_nearby(
            coords['lat'], coords['lon'],
            poi_type, radius
        )
        
        result.poi_results = pois
        
        if pois:
            print(f"   ✓ Found {len(pois)} results")
        else:
            result.warnings.append(f"在 {radius}m 范围内未找到 {poi_type}")
            result.suggestions.append("可以尝试增大搜索半径")
    
    def _handle_poi_search_query(self, intent: IntentAnalysis, 
                                  result: UnifiedQueryResult):
        """
        处理区域 POI 搜索查询 (品牌门店/设施统计)
        
        使用 Overpass API 在指定区域内搜索 POI。
        比 Wikidata 更适合商业品牌门店查询（星巴克、瑞幸等）。
        
        参考: https://jishuzhan.net/article/1994731667102171138
        """
        print("\nExecuting regional POI search (Overpass API)...")
        
        # 获取搜索区域
        search_region = intent.search_region or intent.location_filter or intent.osm_region
        if not search_region:
            result.warnings.append("未指定搜索区域")
            result.suggestions.append("请指定一个城市或区域，如 '北京'、'上海'")
            return
        
        # 获取品牌名称和 POI 类型
        brand_name = intent.brand_name
        poi_type = intent.poi_type
        
        if not brand_name and not poi_type:
            # 尝试从 entity_type 获取
            if intent.entity_type:
                poi_type = intent.entity_type
            else:
                result.warnings.append("未指定搜索条件（品牌或类型）")
                return
        
        print(f"   Search region: {search_region}")
        if brand_name:
            print(f"   Brand name: {brand_name}")
        if poi_type:
            print(f"   POI type: {poi_type}")
        
        # 获取属性过滤条件
        property_filters = intent.property_filters if intent.property_filters else None
        if property_filters:
            print(f"   Property filters: {property_filters}")
        
        # 调用 OSMAdapter 的区域搜索方法
        pois = self.osm.search_poi_in_region(
            region_name=search_region,
            poi_type=poi_type,
            brand_name=brand_name,
            property_filters=property_filters,
            limit=1000  # 商业门店可能很多
        )
        
        result.poi_results = pois
        
        # 🆕 area 查询失败，尝试边界框查询回退
        if not pois:
            print(f"   ℹ️ Area query found no results, trying bounding box query...")
            try:
                # 获取区域的边界框
                location_info = self.osm.geocode(search_region, get_bbox=True)
                if location_info:
                    bbox = location_info.get('bbox')
                    if bbox:
                        # 使用边界框查询
                        bbox_pois = self._search_poi_in_bbox_for_poi_search(
                            bbox, poi_type, brand_name, property_filters, 1000
                        )
                        if bbox_pois:
                            print(f"   ✓ Bounding box query found {len(bbox_pois)} results")
                            pois = bbox_pois
                            result.poi_results = pois
            except Exception as e:
                print(f"   ⚠️ Bounding box query failed: {str(e)[:50]}")
        
        # 🆕 Overpass 全部失败，回退到高德 POI 搜索（国内更稳定）
        # 但排除国外国家名称（高德地图主要面向中国，对国外地名识别不准确）
        is_foreign_country = search_region.strip() in self.osm.FOREIGN_COUNTRIES or \
                            any(country in search_region for country in self.osm.FOREIGN_COUNTRIES if len(country) <= len(search_region))
        
        if not pois and self.osm.amap_key and self.osm._is_chinese_text(search_region) and not is_foreign_country:
            print(f"   ℹ️ Overpass query failed, trying Amap POI search...")
            try:
                # 从完整地址提取城市/区县名称
                import re
                admin_pattern = r'([\u4e00-\u9fa5]+?(?:省|市|县|区|自治州|自治县|盟|旗|镇|乡|街道))'
                matches = re.findall(admin_pattern, search_region)
                city = matches[-1] if matches else search_region
                
                amap_pois = self.osm.search_poi_with_amap(
                    city=city,
                    poi_type=poi_type,
                    keywords=brand_name,
                    property_filters=property_filters,
                    limit=200  # 高德免费版限制
                )
                
                if amap_pois:
                    pois = amap_pois
                    result.poi_results = pois
                    result.data_source = 'amap'  # Mark data source
                    print(f"   ✓ Gaode POI search successful")
            except Exception as e:
                print(f"   ⚠️ Gaode POI search failed: {str(e)[:50]}")
        
        if pois:
            print(f"\n   Statistics:")
            print(f"      Total: {len(pois)}")
            
            # 统计名称分布（如果查询的是品牌）
            if brand_name:
                name_counts = {}
                for poi in pois:
                    name = poi.name
                    name_counts[name] = name_counts.get(name, 0) + 1
                
                # 显示前 5 个最常见的名称
                sorted_names = sorted(name_counts.items(), key=lambda x: -x[1])[:5]
                if len(sorted_names) > 1:
                    print(f"      Name distribution (top 5):")
                    for name, count in sorted_names:
                        print(f"         - {name}: {count} items")
        else:
            if brand_name:
                result.warnings.append(f"No {brand_name} stores found in {search_region}")
            else:
                result.warnings.append(f"No {poi_type} POIs found in {search_region}")
            result.suggestions.append("No results found in OpenStreetMap and Gaode, please check the search conditions")
    
    def _handle_routing_query(self, intent: IntentAnalysis, 
                               result: UnifiedQueryResult):
        """处理路由导航查询"""
        print("\nExecuting routing calculation (OSRM)...")
        
        if not intent.origin or not intent.destination:
            result.warnings.append("No origin or destination specified")
            return
        
        # Step 0: 使用 LLM 验证和补充地名（解决英文地名等问题）
        query_context = f"Routing query: from {intent.origin} to {intent.destination}"
        
        origin_name = intent.origin
        dest_name = intent.destination
        
        # 验证并补充起点
        origin_validation = self._validate_location_with_llm(origin_name, query_context)
        if origin_validation.get('enriched_name') and origin_validation.get('enriched_name') != origin_name:
            origin_name = origin_validation.get('enriched_name')
            print(f"   Enriched origin: {origin_name}")
        
        # 验证并补充终点
        dest_validation = self._validate_location_with_llm(dest_name, query_context)
        if dest_validation.get('enriched_name') and dest_validation.get('enriched_name') != dest_name:
            dest_name = dest_validation.get('enriched_name')
            print(f"   Enriched destination: {dest_name}")
        
        # Step 1: 地理编码起点和终点
        print(f"   Origin: {origin_name}")
        origin = self.osm.geocode(origin_name)
        if not origin:
            result.warnings.append(f"Unable to parse origin: {origin_name}")
            return
        
        print(f"   Destination: {dest_name}")
        dest = self.osm.geocode(dest_name)
        if not dest:
            result.warnings.append(f"Unable to parse destination: {dest_name}")
            return
        
        # Step 2: 计算路由
        mode = intent.transport_mode or "driving"
        print(f"   Calculating {mode} route...")
        
        route = self.osm.calculate_route(
            origin['lat'], origin['lon'],
            dest['lat'], dest['lon'],
            mode
        )
        
        if route:
            route.origin = origin.get('display_name', intent.origin)
            route.destination = dest.get('display_name', intent.destination)
            result.route_result = route
            
            distance_km = route.distance_meters / 1000
            duration_min = route.duration_seconds / 60
            print(f"   Distance: {distance_km:.2f} km")
            print(f"   Estimated time: {duration_min:.0f} minutes")
        else:
            result.warnings.append("Unable to calculate route")
            result.suggestions.append("Please check if the origin and destination are within the road network coverage")
    
    def _handle_recommendation_query(self, intent: IntentAnalysis, 
                                      result: UnifiedQueryResult):
        """
        处理推荐查询 - 结合 Wikidata 和 OSM
        
        流程:
        1. 先从 Wikidata 查询符合语义条件的实体 (如五星级酒店)
        2. 如果有位置上下文，使用 OSM 进行空间过滤
        3. 合并结果
        """
        print("\nExecuting recommendation query (Wikidata + OSM)...")
        
        entity_type = intent.facility_type or intent.entity_type
        
        # 智能组合位置信息
        location_parts = []
        if intent.location_filter:
            location_parts.append(intent.location_filter)
        if intent.location_context and intent.location_context not in (intent.location_filter or ''):
            location_parts.append(intent.location_context)
        if intent.reference_location and intent.reference_location not in ' '.join(location_parts):
            location_parts.append(intent.reference_location)
        
        location = ' '.join(location_parts) if location_parts else ''
        
        # 如果位置信息太模糊（如只有"市中心"），尝试从原始查询中提取城市名
        vague_terms = ['市中心', '中心', '附近', '旁边', '周围', 'center', 'downtown', 'nearby']
        if location and any(v in location for v in vague_terms) and len(location) <= 5:
            # 从查询摘要中尝试提取更完整的位置
            if intent.summary:
                import re
                city_pattern = r'(北京|上海|广州|深圳|成都|杭州|南京|武汉|西安|天津|重庆|苏州|青岛|大连|厦门)'
                match = re.search(city_pattern, intent.summary)
                if match:
                    location = f"{match.group(1)}{location}"
                    print(f"   Enriched location: {location}")
        
        if not entity_type:
            result.warnings.append("Recommendation query requires specifying facility type")
            return
        
        # Step 1: 从 Wikidata 查询实体
        print(f"   Querying Wikidata knowledge graph...")
        knowledge_results = self.wikidata.query_entities_by_type_and_location(
            entity_type=entity_type,
            location=location or "",
            property_filters=intent.property_filters,
            limit=1000
        )
        
        if knowledge_results:
            result.knowledge_results = knowledge_results
            print(f"   Wikidata returned {len(knowledge_results)} results")
        
        # Step 2: 如果有具体的参考位置，同时查询 OSM POI
        if intent.reference_location:
            print(f"   Combining OSM spatial proximity query...")
            intent.poi_type = entity_type
            if not intent.radius_meters or intent.radius_meters < 1000:
                intent.radius_meters = 2000  # 推荐查询使用较大半径
            
            self._handle_proximity_query(intent, result)
        
        # Step 3: 应用条件过滤
        if intent.criteria:
            criteria_str = ", ".join(intent.criteria)
            print(f"   Applying filter criteria: {criteria_str}")
            result.suggestions.append(f"Filter criteria applied: {criteria_str}")
        
        if not result.knowledge_results and not result.poi_results:
            result.warnings.append("No recommendation results found with the specified criteria")
            result.suggestions.append("Try loosening the search conditions or changing the location")
    def _handle_knowledge_query(self, intent: IntentAnalysis, 
                                 result: UnifiedQueryResult):
        """
        处理知识查询 - 支持两种模式:
        1. 直接实体查询 (entity_name): 查询某个具体地点/实体的信息
        2. 类型+位置查询 (entity_type + location): 查询某位置的某类型实体
        
        优先 Wikidata，失败时回退到 Overpass API
        """
        print("\nExecuting knowledge graph query (Wikidata)...")
        
        entity_name = intent.entity_name  # 直接实体名称（如"故宫"）
        entity_type = intent.entity_type or intent.facility_type
        location = intent.location_filter
        
        # 模式 1: 直接实体查询（如"故宫的历史信息"）
        if entity_name:
            print(f"   Directly querying entity: {entity_name}")
            knowledge_results = self.wikidata.search_by_name(entity_name, limit=10)
            
            if knowledge_results:
                result.knowledge_results = knowledge_results
                print(f"   Found {len(knowledge_results)} matching entities")
                
                # 显示第一个结果的详细信息
                first = knowledge_results[0]
                print(f"      {first.name}")
                if first.description:
                    print(f"      {first.description[:100]}...")
                if first.lat and first.lon:
                    print(f"      Coordinates: ({first.lat:.4f}, {first.lon:.4f})")
                    
                # 尝试获取更详细的信息
                if first.wikidata_id:
                    details = self.wikidata.query_entity_details(first.wikidata_id)
                    if details and details.properties:
                        # 更新第一个结果的属性
                        knowledge_results[0] = details
                        print(f"      Detailed property information obtained")
            else:
                print(f"   Entity '{entity_name}' not found in Wikidata")
                result.warnings.append(f"Entity not found: {entity_name}")
            return
        
        # 模式 2: 类型+位置查询（如"北京的博物馆"）
        if not entity_type and not location:
            result.warnings.append("Knowledge query requires specifying entity name or entity type + location")
            return
        
        # 执行 Wikidata 查询
        knowledge_results = []
        if entity_type:
            print(f"   Querying Wikidata: {entity_type} in {location or '(global)'}")
            knowledge_results = self.wikidata.query_entities_by_type_and_location(
                entity_type=entity_type,
                location=location or "",
                property_filters=intent.property_filters,
                limit=1000
            )
            
            if knowledge_results:
                result.knowledge_results = knowledge_results
                print(f"   Found {len(knowledge_results)} entities")
            else:
                # Wikidata 失败，尝试回退到 Overpass API（保留属性过滤条件）
                print(f"   Wikidata returned no results, trying Overpass API fallback...")
                fallback_intent = IntentAnalysis(
                    intent=QueryIntent.POI_SEARCH,
                    confidence=0.8,
                    summary=f"Wikidata fallback: {entity_type} in {location}",
                    poi_type=entity_type,
                    search_region=location,
                    property_filters=intent.property_filters  # 传递属性过滤条件
                )
                self._handle_poi_search_query(fallback_intent, result)
                if result.poi_results:
                    filter_info = f" (filter: {intent.property_filters})" if intent.property_filters else ""
                    print(f"   Overpass API fallback successful: found {len(result.poi_results)} POIs{filter_info}")
                else:
                    result.warnings.append(f"No {entity_type} data found for {location or ''}")
        else:
            result.warnings.append("Please specify the entity type to query")
    
    # 预定义的常用城市边界框 (当 Nominatim 不可用时使用)
    # 格式: [south, north, west, east] (纬度南, 纬度北, 经度西, 经度东)
    # 约 50km x 50km 范围，以城市中心为基准
    PREDEFINED_CITY_BBOX = {
        # 中国主要城市
        "北京": [39.67, 40.17, 116.12, 116.62],
        "beijing": [39.67, 40.17, 116.12, 116.62],
        "上海": [31.03, 31.53, 121.22, 121.72],
        "shanghai": [31.03, 31.53, 121.22, 121.72],
        "广州": [22.92, 23.42, 113.06, 113.56],
        "guangzhou": [22.92, 23.42, 113.06, 113.56],
        "深圳": [22.37, 22.87, 113.78, 114.28],
        "shenzhen": [22.37, 22.87, 113.78, 114.28],
        "杭州": [30.05, 30.55, 119.97, 120.47],
        "hangzhou": [30.05, 30.55, 119.97, 120.47],
        "南京": [31.82, 32.32, 118.54, 119.04],
        "nanjing": [31.82, 32.32, 118.54, 119.04],
        "成都": [30.40, 30.90, 103.85, 104.35],
        "chengdu": [30.40, 30.90, 103.85, 104.35],
        "武汉": [30.35, 30.85, 114.05, 114.55],
        "wuhan": [30.35, 30.85, 114.05, 114.55],
        "西安": [34.05, 34.55, 108.70, 109.20],
        "xian": [34.05, 34.55, 108.70, 109.20],
        "天津": [38.87, 39.37, 117.00, 117.50],
        "tianjin": [38.87, 39.37, 117.00, 117.50],
        "重庆": [29.30, 29.80, 106.30, 106.80],
        "chongqing": [29.30, 29.80, 106.30, 106.80],
        "苏州": [31.07, 31.57, 120.37, 120.87],
        "suzhou": [31.07, 31.57, 120.37, 120.87],
        
        # 国际主要城市
        "tokyo": [35.47, 35.97, 139.50, 140.00],
        "东京": [35.47, 35.97, 139.50, 140.00],
        "london": [51.30, 51.70, -0.35, 0.15],
        "伦敦": [51.30, 51.70, -0.35, 0.15],
        "paris": [48.67, 49.07, 2.15, 2.55],
        "巴黎": [48.67, 49.07, 2.15, 2.55],
        "new york": [40.50, 41.00, -74.25, -73.75],
        "纽约": [40.50, 41.00, -74.25, -73.75],
        "los angeles": [33.75, 34.25, -118.50, -118.00],
        "洛杉矶": [33.75, 34.25, -118.50, -118.00],
        "berlin": [52.35, 52.75, 13.15, 13.65],
        "柏林": [52.35, 52.75, 13.15, 13.65],
        "singapore": [1.15, 1.55, 103.60, 104.10],
        "新加坡": [1.15, 1.55, 103.60, 104.10],
        "sydney": [-34.10, -33.60, 150.85, 151.35],
        "悉尼": [-34.10, -33.60, 150.85, 151.35],
        "seoul": [37.40, 37.70, 126.75, 127.15],
        "首尔": [37.40, 37.70, 126.75, 127.15],
        "moscow": [55.55, 55.95, 37.35, 37.85],
        "莫斯科": [55.55, 55.95, 37.35, 37.85],
    }
    
    def _get_city_bbox(self, region: str) -> Optional[List[float]]:
        """
        获取城市边界框，多源获取策略：
        1. Nominatim API
        2. Photon API (Komoot) - 更稳定的备用
        3. 预定义边界框
        4. LLM 推断坐标
        
        Args:
            region: 区域名称
            
        Returns:
            [south, north, west, east] 或 None
        """
        region_lower = region.lower().strip()
        
        # 策略 1: 尝试使用 Nominatim (带重试)
        for attempt in range(2):
            try:
                location_info = self.osm.geocode(region, get_bbox=True)
                if location_info and location_info.get('bbox'):
                    return location_info['bbox']
                elif location_info:
                    lat, lon = location_info['lat'], location_info['lon']
                    delta = 0.25  # 约 25km
                    return [lat - delta, lat + delta, lon - delta, lon + delta]
            except Exception as e:
                if attempt == 0:
                    print(f"    Nominatim query failed (retrying...): {str(e)[:50]}")
                    import time
                    time.sleep(1)
                continue
        
        # 策略 2: 尝试 Photon API (Komoot) - 更稳定
        try:
            bbox = self._get_bbox_from_photon(region)
            if bbox:
                print(f"   Using Photon API to get bbox: {region}")
                return bbox
        except Exception as e:
            print(f"   Photon API failed: {str(e)[:50]}")
        
        # 策略 3: 使用预定义边界框
        for key in [region_lower, region, region.replace(" ", "")]:
            if key in self.PREDEFINED_CITY_BBOX:
                print(f"   Using predefined bounding box: {region}")
                return self.PREDEFINED_CITY_BBOX[key]
        
        for key, bbox in self.PREDEFINED_CITY_BBOX.items():
            if key in region_lower or region_lower in key:
                print(f"   Using predefined bounding box (fuzzy match '{key}'): {region}")
                return bbox
        
        # 策略 4: 使用 LLM 推断坐标
        if self.llm:
            coords = self._llm_infer_coordinates(region)
            if coords:
                print(f"   LLM inferred coordinates: {region} -> ({coords['lat']}, {coords['lon']})")
                delta = 0.25
                return [coords['lat'] - delta, coords['lat'] + delta, 
                       coords['lon'] - delta, coords['lon'] + delta]
        
        return None
    
    def _get_bbox_from_photon(self, region: str) -> Optional[List[float]]:
        """
        使用 Photon API (Komoot) 获取城市边界框
        Photon 通常比 Nominatim 更稳定
        
        Returns:
            [south, north, west, east] 或 None
        """
        import requests as req
        
        url = 'https://photon.komoot.io/api/'
        params = {'q': region, 'limit': 1}
        
        response = req.get(url, params=params, timeout=15,
                          headers={'User-Agent': 'GeoQueryEngine/1.0'})
        
        if response.status_code == 200:
            data = response.json()
            features = data.get('features', [])
            if features:
                props = features[0].get('properties', {})
                extent = props.get('extent')  # [minlon, maxlat, maxlon, minlat]
                if extent and len(extent) == 4:
                    # 转换为 [south, north, west, east]
                    return [extent[3], extent[1], extent[0], extent[2]]
                
                # 如果没有 extent，使用点坐标
                coords = features[0].get('geometry', {}).get('coordinates')
                if coords:
                    lon, lat = coords[0], coords[1]
                    delta = 0.25
                    return [lat - delta, lat + delta, lon - delta, lon + delta]
        
        return None
    
    def _handle_osm_data_query(self, intent: IntentAnalysis,
                                result: UnifiedQueryResult):
        """
        处理 OSM 区域数据下载 - 从 OpenStreetMap 下载底图/基础地理数据
        
        支持下载的数据类型:
        - roads: 道路网络
        - buildings: 建筑物
        - waterways: 水系 (河流、湖泊)
        - landuse: 土地利用
        - railways: 铁路
        - natural: 自然要素 (森林、草地等)
        
        优化: 支持使用真实行政边界裁剪，而非正方形边界框
        """
        print("\nExecuting OSM region data download...")
        
        region = intent.osm_region
        data_types = intent.osm_data_types
        
        if not region:
            result.warnings.append("OSM data download requires a region")
            return
        
        # Default basemap data types
        if not data_types:
            data_types = ["roads", "buildings", "waterways", "landuse"]
            print(f"   No data types specified, using defaults: {data_types}")
        
        # Step 1: Get region bounding box (with retry and fallback)
        print(f"   Getting region boundary: {region}")
        bbox = self._get_city_bbox(region)
        
        if not bbox:
            result.warnings.append(f"Cannot get location info for region '{region}', please try using English city name or check network connection")
            result.suggestions.append("Supported cities: Beijing, Shanghai, Guangzhou, Shenzhen, Hangzhou, etc.")
            return
        
        # Step 1.5: 检查是否有真实行政边界可用
        boundary_file = None
        use_admin_boundary = False
        region_id = None
        admin_bbox = None  # 行政边界的 bbox
        
        # 首先检查本地行政边界数据
        if self.local_searcher and hasattr(self.local_searcher, 'region_manager'):
            region_manager = self.local_searcher.region_manager
            region_id = region_manager.normalize_region_id(region)
            boundary_file = region_manager.extract_region_geometry(region_id)
            
            if boundary_file and boundary_file.exists():
                use_admin_boundary = True
                # 获取行政边界的 bbox（从 region_index 中）
                region_info = region_manager.get_region_info(region_id)
                if region_info and 'bbox' in region_info:
                    admin_bbox = region_info['bbox']  # [minx, miny, maxx, maxy]
                    # 转换为 [south, north, west, east] 格式
                    bbox = [admin_bbox[1], admin_bbox[3], admin_bbox[0], admin_bbox[2]]
                    print(f"   Found local administrative boundary: {region_id}")
                    print(f"   Using full administrative boundary for download")
                else:
                    print(f"   Found local administrative boundary: {region_id}")
                    # 扩大 bbox 10% 确保覆盖边界
                    lat_range = bbox[1] - bbox[0]
                    lon_range = bbox[3] - bbox[2]
                    bbox = [
                        bbox[0] - lat_range * 0.1,
                        bbox[1] + lat_range * 0.1,
                        bbox[2] - lon_range * 0.1,
                        bbox[3] + lon_range * 0.1
                    ]
        
        # If no local administrative boundary, check saved boundary files in boundaries directory first
        if not use_admin_boundary:
            boundary_dir = Path(self.output_dir) / 'boundaries'
            if boundary_dir.exists():
                # Try both original name and sanitized name (spaces → underscores)
                safe_name = self.osm._sanitize_name(region) if hasattr(self.osm, '_sanitize_name') else region.replace(' ', '_')
                candidates = [
                    boundary_dir / f'boundary_{safe_name}.geojson',       # e.g. boundary_Stanford_University.geojson
                    boundary_dir / f'boundary_{region}.geojson',          # e.g. boundary_Stanford University.geojson
                ]
                for candidate in candidates:
                    if candidate.exists():
                        boundary_file = candidate
                        use_admin_boundary = True
                        region_id = region
                        print(f"   ✓ Found saved boundary file: {candidate.name}")
                        # Read bbox from boundary file
                        try:
                            import json as _json
                            with open(candidate, 'r', encoding='utf-8') as _f:
                                _geojson = _json.load(_f)
                            _coords = []
                            for feat in _geojson.get('features', [_geojson]):
                                geom = feat.get('geometry', {})
                                if geom.get('type') == 'Polygon':
                                    for ring in geom.get('coordinates', []):
                                        _coords.extend(ring)
                                elif geom.get('type') == 'MultiPolygon':
                                    for poly in geom.get('coordinates', []):
                                        for ring in poly:
                                            _coords.extend(ring)
                            if _coords:
                                lons = [c[0] for c in _coords]
                                lats = [c[1] for c in _coords]
                                # bbox format: [south, north, west, east]
                                bbox = [min(lats), max(lats), min(lons), max(lons)]
                                # Expand bbox by 5% to ensure full coverage for OSM download
                                lat_range_exp = bbox[1] - bbox[0]
                                lon_range_exp = bbox[3] - bbox[2]
                                bbox = [
                                    bbox[0] - lat_range_exp * 0.05,
                                    bbox[1] + lat_range_exp * 0.05,
                                    bbox[2] - lon_range_exp * 0.05,
                                    bbox[3] + lon_range_exp * 0.05
                                ]
                        except Exception as _e:
                            print(f"   ⚠️ Failed to read bbox from boundary file: {_e}")
                        break
        
        # If still no boundary, try to get real polygon boundary from Nominatim online
        if not use_admin_boundary:
            print(f"   ℹ️ No local administrative boundary for '{region}', trying online...")
            online_boundary = self.osm.get_admin_boundary(region)
            
            if online_boundary:
                use_admin_boundary = True
                boundary_file = online_boundary['geojson_file']
                bbox = online_boundary['bbox']
                region_id = region
                print(f"   ✓ Online administrative boundary fetched successfully")
            else:
                print(f"   ⚠️ Cannot get administrative boundary for '{region}', will use rectangular bbox")
        
        # 检查边界框是否太大 (大于 1 度约 110km)
        lat_range = bbox[1] - bbox[0]
        lon_range = bbox[3] - bbox[2]
        
        # Only limit range when no real administrative boundary
        if not use_admin_boundary and (lat_range > 1.0 or lon_range > 1.0):
            # For large cities, limit bbox size to avoid excessive data
            print(f"   ⚠️ Region too large, limiting download range (original ~{lat_range*111:.0f}km × {lon_range*111:.0f}km)")
            # Center-based limit, ~50km x 50km
            lat_center = (bbox[0] + bbox[1]) / 2
            lon_center = (bbox[2] + bbox[3]) / 2
            max_delta = 0.25  # ~25km
            bbox = [lat_center - max_delta, lat_center + max_delta, 
                    lon_center - max_delta, lon_center + max_delta]
        elif use_admin_boundary and (lat_range > 1.0 or lon_range > 1.0):
            # Has administrative boundary but large range, notify user
            print(f"   ℹ️ Administrative boundary range ~{lat_range*111:.0f}km × {lon_range*111:.0f}km, download may take a while")
        
        print(f"   ✓ Download bbox: [{bbox[0]:.4f}, {bbox[1]:.4f}, {bbox[2]:.4f}, {bbox[3]:.4f}]")
        print(f"   ✓ Range ~{(bbox[1]-bbox[0])*111:.1f}km × {(bbox[3]-bbox[2])*111:.1f}km")
        
        if use_admin_boundary:
            print(f"   ✓ Will use real administrative boundary for clipping (non-rectangular)")
        
        # Step 2: 下载各类型数据
        downloaded_files = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        region_safe = self._sanitize_filename(region, max_length=30)
        
        # OSM 数据类型映射到 Overpass 查询
        osm_type_map = {
            "roads": {
                "query": 'way["highway"]',
                "name": "roads",
                "geometry": "LineString"
            },
            "buildings": {
                "query": 'way["building"]',
                "name": "buildings",
                "geometry": "Polygon"
            },
            "waterways": {
                "query": 'way["waterway"]',
                "name": "waterways",
                "geometry": "LineString"
            },
            "landuse": {
                "query": 'way["landuse"]',
                "name": "landuse",
                "geometry": "Polygon"
            },
            "railways": {
                "query": 'way["railway"]',
                "name": "railways",
                "geometry": "LineString"
            },
            "natural": {
                "query": 'way["natural"]',
                "name": "natural",
                "geometry": "Polygon"
            },
            # 🆕 地标/景区边界
            "boundaries": {
                "query": 'relation["boundary"]',
                "name": "boundaries",
                "geometry": "Polygon"
            },
            "parks": {
                "query": 'way["leisure"="park"]',
                "name": "parks",
                "geometry": "Polygon"
            },
            "attractions": {
                "query": 'way["tourism"]',
                "name": "attractions",
                "geometry": "Polygon"
            }
        }
        
        # 🆕 特殊处理：获取地标边界（如"获取颐和园的边界"）
        if data_types == ["boundaries"] and region:
            landmark_boundary = self._get_landmark_boundary(region)
            if landmark_boundary:
                result.osm_data = landmark_boundary
                # 🔧 修复：将边界文件添加到 downloaded_files，以便自动添加到catalog和向量数据库
                if 'geojson_file' in landmark_boundary:
                    boundary_file_path = landmark_boundary['geojson_file']
                    if boundary_file_path:
                        # geojson_file 现在已经是绝对路径字符串，直接使用
                        if boundary_file_path not in downloaded_files:
                            downloaded_files.append(boundary_file_path)
                            print(f"   ✓ Boundary file added to download list: {os.path.basename(boundary_file_path)}")
                # 设置结果
                if downloaded_files:
                    result.downloaded_files = downloaded_files
                    result.message = f"Successfully obtained boundary data for {region}"
                return
        
        for data_type in data_types:
            if data_type not in osm_type_map:
                print(f"   Unsupported data type: {data_type}")
                continue
            
            type_info = osm_type_map[data_type]
            print(f"   Downloading {data_type}...")
            
            try:
                features = self._query_osm_area_data(bbox, type_info["query"])
                
                if features:
                    # 保存为 GeoJSON
                    filename = f"osm_{type_info['name']}_{region_safe}_{timestamp}"
                    filepath = self._save_osm_data_to_geojson(
                        features, 
                        self.output_dir, 
                        filename,
                        data_type
                    )
                    
                    if filepath:
                        # Step 3: 如果有真实行政边界，进行裁剪
                        if use_admin_boundary and boundary_file:
                            clipped_filepath = self._clip_osm_to_boundary(
                                filepath, boundary_file, region_id or region_safe
                            )
                            if clipped_filepath:
                                # 删除原始正方形文件，使用裁剪后的文件
                                try:
                                    os.remove(filepath)
                                except:
                                    pass
                                filepath = clipped_filepath
                                print(f"      {len(features)} features → clipped to administrative boundary → {os.path.basename(filepath)}")
                            else:
                                print(f"      {len(features)} features → {os.path.basename(filepath)} (clipping failed, original file retained)")
                        else:
                            print(f"      {len(features)} features → {os.path.basename(filepath)}")
                        
                        downloaded_files.append(filepath)
                else:
                    print(f"      No {data_type} data found")
                    
            except Exception as e:
                print(f"      Download failed: {e}")
                result.warnings.append(f"Download {data_type} failed: {str(e)}")
        
        # 设置结果
        if downloaded_files:
            result.downloaded_files = downloaded_files
            clip_info = "(clipped by admin boundary)" if use_admin_boundary else "(bounding box)"
            result.message = f"Successfully downloaded {len(downloaded_files)} data files from OSM to {self.output_dir}/ {clip_info}"
            print(f"\n   Download complete: {len(downloaded_files)} files {clip_info}")
        else:
            result.warnings.append("Failed to download any OSM data")
    
    def _handle_remote_sensing_query(self, intent: IntentAnalysis,
                                     result: UnifiedQueryResult):
        """
        Handling remote sensing data download query
        
        支持 Sentinel-2 和 Landsat 数据下载
        """
        print("\nExecuting remote sensing data download...")
        
        # 获取参数
        satellite = intent.satellite or "sentinel-2"
        time_range = intent.time_range
        cloud_cover_max = intent.cloud_cover_max if intent.cloud_cover_max > 0 else DEFAULT_CLOUD_COVER_MAX
        bands = intent.bands if intent.bands else []
        processing = intent.processing or ""
        region = intent.remote_sensing_region or intent.osm_region or intent.target_region
        
        if not region:
            result.warnings.append("Remote sensing data download requires specifying a region")
            result.suggestions.append("Please specify a region, e.g. 'Beijing', 'Germany'")
            return
        
        # 🔧 修复：如果没有指定时间范围，使用默认值（最近3个月）
        if not time_range:
            from datetime import datetime, timedelta
            end_date = datetime.now()
            start_date = end_date - timedelta(days=90)
            time_range = f"{start_date.strftime('%Y-%m-%d')},{end_date.strftime('%Y-%m-%d')}"
            print(f"   No time range specified, using default (last 3 months): {time_range}")
        
        print(f"   Download region: {region}")
        print(f"   Satellite type: {satellite}")
        print(f"   Time range: {time_range}")
        print(f"   Max cloud cover: {cloud_cover_max}%")
        if processing:
            print(f"   Processing type: {processing}")
        if bands:
            print(f"   Band selection: {bands}")
        
        # 🆕 检查是否有真实行政边界（用于后续裁剪）
        boundary_file = None
        use_admin_boundary = False
        region_id = None
        admin_bbox = None  # 行政边界的完整范围
        admin_bbox_source = None  # 来源: 'local' 或 'online'
        
        # 首先检查本地行政边界数据
        if self.local_searcher and hasattr(self.local_searcher, 'region_manager'):
            region_manager = self.local_searcher.region_manager
            region_id = region_manager.normalize_region_id(region)
            boundary_file = region_manager.extract_region_geometry(region_id)
            
            if boundary_file and boundary_file.exists():
                use_admin_boundary = True
                # 获取行政边界的完整范围
                region_info = region_manager.get_region_info(region_id)
                if region_info and 'bbox' in region_info:
                    admin_bbox = region_info['bbox']  # [minx, miny, maxx, maxy]
                    admin_bbox_source = 'local'  # 标记来源
                print(f"   ✓ Found local administrative boundary: {region_id}")
        
        # 如果本地没有，尝试在线获取
        if not use_admin_boundary:
            # Check if there are saved boundary files in the downloaded_data/boundaries directory
            boundary_dir = Path(self.output_dir) / 'boundaries'
            if boundary_dir.exists():
                # Use exact matching first to avoid issues with "Beijing" matching "Peking University"
                boundary_file = None
                
                # 第一优先级：精确匹配 boundary_{region}.geojson
                exact_match = boundary_dir / f'boundary_{region}.geojson'
                if exact_match.exists():
                    boundary_file = exact_match
                    print(f"   Found exact match boundary file: {boundary_file.name}")
                else:
                    # 第二优先级：模糊匹配，但需要过滤掉不正确的结果
                    possible_boundaries = list(boundary_dir.glob(f'boundary_{region}*.geojson')) + \
                                        list(boundary_dir.glob(f'*{region}*.geojson'))
                    
                    # Filter out files that contain region but are actually different locations
                    # 例如：当region="北京"时，排除"boundary_北京大学.geojson"
                    filtered_boundaries = []
                    for bf in possible_boundaries:
                        # 提取边界文件中的地名部分
                        bf_name = bf.stem  # e.g. boundary_Peking University
                        if bf_name.startswith('boundary_'):
                            place_name = bf_name[9:]  # 例如: 北京大学
                        else:
                            place_name = bf_name
                        
                        # 检查是否是精确匹配或真正的子集关系
                        # region="北京" 不应该匹配 place_name="北京大学"
                        # 但 region="北京市" 可以匹配 place_name="北京"
                        if place_name == region:
                            # 精确匹配
                            filtered_boundaries.insert(0, bf)  # 优先使用
                        elif region in place_name and place_name != region:
                            # region是place_name的子串，但不是精确匹配
                            # 例如：region="北京", place_name="北京大学" → 跳过
                            # 这种情况下，"北京"和"北京大学"是完全不同的地点
                            continue
                        elif place_name in region:
                            # place_name是region的子串
                            # 例如：region="北京市", place_name="北京" → 可以使用
                            filtered_boundaries.append(bf)
                    
                    if filtered_boundaries:
                        boundary_file = filtered_boundaries[0]
                        print(f"   Found local saved boundary file: {boundary_file.name}")
                
                if boundary_file:
                    use_admin_boundary = True
                    region_id = region
                    
                    # 读取边界文件获取bbox
                    try:
                        import json
                        with open(boundary_file, 'r', encoding='utf-8') as f:
                            boundary_data = json.load(f)
                        
                        # 计算bbox
                        from shapely.geometry import shape
                        if 'features' in boundary_data:
                            geom = shape(boundary_data['features'][0]['geometry'])
                        else:
                            geom = shape(boundary_data['geometry'])
                        bounds = geom.bounds  # (minx, miny, maxx, maxy)
                        # 转换为 [south, north, west, east] 格式
                        admin_bbox = [bounds[1], bounds[3], bounds[0], bounds[2]]  # [miny, maxy, minx, maxx] = [south, north, west, east]
                        admin_bbox_source = 'local'
                    except Exception as e:
                        print(f"   Failed to read boundary file: {e}")
                        use_admin_boundary = False
            
            # 如果本地没有，尝试在线获取
            if not use_admin_boundary:
                print(f"   ℹ️ Trying to get administrative boundary online for '{region}'...")
                
                # 🆕 判断是否是地标而非行政区
                landmark_keywords = ['大学', '学院', '公园', '景区', '博物馆', '寺', '宫', '园', '山', 
                                   'university', 'college', 'park', 'museum', 'temple', 'palace']
                is_landmark = any(kw in region.lower() for kw in landmark_keywords)
                
                if is_landmark:
                    # 尝试获取地标边界
                    landmark_boundary = self._get_landmark_boundary(region)
                    if landmark_boundary and landmark_boundary.get('geojson_file'):
                        use_admin_boundary = True
                        boundary_file = Path(landmark_boundary['geojson_file'])
                        region_id = region
                        if 'bbox' in landmark_boundary:
                            admin_bbox = landmark_boundary['bbox']
                            admin_bbox_source = 'online'
                        print(f"   ✓ Online landmark boundary fetched successfully")
                
                # 如果不是地标或地标边界获取失败，尝试行政边界
                if not use_admin_boundary:
                    online_boundary = self.osm.get_admin_boundary(region)
                    
                    if online_boundary and online_boundary.get('geojson_file'):
                        use_admin_boundary = True
                        boundary_file = Path(online_boundary['geojson_file'])
                        region_id = region
                        # 在线边界也有 bbox - 已经是 [south, north, west, east] 格式
                        if 'bbox' in online_boundary:
                            admin_bbox = online_boundary['bbox']  # [south, north, west, east]
                            admin_bbox_source = 'online'  # 标记来源，避免重复转换
                        print(f"   ✓ Online administrative boundary fetched successfully")
        
        if use_admin_boundary:
            print(f"   Download will be clipped to administrative boundary (non-rectangular)")
        
        # Get region bounding box
        print(f"   🔍 Getting region bounding box...")
        
        # 🆕 优先使用行政边界的完整范围
        # admin_bbox_source 在上面获取边界时已设置：'local' 或 'online'
        
        if admin_bbox:
            if len(admin_bbox) == 4:
                if admin_bbox_source == 'online':
                    # 在线获取的 bbox 已经是 [south, north, west, east] 格式，直接使用
                    bbox = list(admin_bbox)
                elif admin_bbox_source == 'local':
                    # 🔧 修复：从本地边界文件读取的bbox已经是 [south, north, west, east] 格式，直接使用
                    bbox = list(admin_bbox)
                else:
                    # local_searcher的 bbox 是 [minx, miny, maxx, maxy] 格式，需要转换
                    bbox = [admin_bbox[1], admin_bbox[3], admin_bbox[0], admin_bbox[2]]
                print(f"   ✓ Using full administrative boundary extent")
            else:
                bbox = self._get_city_bbox(region)
        else:
            bbox = self._get_city_bbox(region)
        
        if not bbox:
            result.warnings.append(f"Cannot get location information for region '{region}'")
            result.suggestions.append("Please check if the region name is correct")
            return
        
        print(f"   Bounding box: [{bbox[0]:.4f}, {bbox[1]:.4f}, {bbox[2]:.4f}, {bbox[3]:.4f}]")
        print(f"   Extent approx. {(bbox[1]-bbox[0])*111:.1f}km × {(bbox[3]-bbox[2])*111:.1f}km")
        
        # 根据卫星类型选择数据源
        satellite_normalized = satellite.lower().replace('_', '-')
        filepath = None
        
        if satellite_normalized.startswith('sentinel-2'):
            # 使用 Sentinel Hub
            if not self.sentinel_hub.client_id:
                result.warnings.append("Sentinel Hub credentials not configured, cannot download Sentinel-2 data")
                result.suggestions.append("Please set SENTINEL_HUB_CLIENT_ID and SENTINEL_HUB_CLIENT_SECRET in local_settings.py")
                return
            
            filepath = self.sentinel_hub.download_imagery(
                bbox=bbox,
                time_range=time_range,
                satellite=satellite_normalized,
                cloud_cover_max=cloud_cover_max,
                bands=bands,
                processing=processing,
                region=region,
                output_dir=str(self.output_dir)
            )
            
        elif satellite_normalized.startswith('landsat'):
            # 策略：先尝试 USGS，失败后回退到 Sentinel Hub
            
            # 方案1: 使用 USGS API
            if self.usgs.username:
                filepath = self.usgs.download_landsat(
                    bbox=bbox,
                    time_range=time_range,
                    satellite=satellite_normalized,
                    cloud_cover_max=cloud_cover_max,
                    region=region,
                    output_dir=str(self.output_dir)
                )
            
            # 方案2: USGS 失败，尝试 Sentinel Hub（也支持 Landsat）
            if not filepath and self.sentinel_hub.client_id:
                print(f"   ℹ️ USGS download failed, trying Sentinel Hub for Landsat...")
                # Sentinel Hub 支持 Landsat-8 (USGS)
                # 将 landsat-8 映射到 Sentinel Hub 的数据集
                filepath = self.sentinel_hub.download_imagery(
                    bbox=bbox,
                    time_range=time_range,
                    satellite=satellite_normalized,  # Sentinel Hub 也支持 landsat-8
                    cloud_cover_max=cloud_cover_max,
                    bands=bands,
                    processing=processing,
                    region=region,
                    output_dir=str(self.output_dir)
                )
            
            # 两种方式都失败
            if not filepath and not self.usgs.username and not self.sentinel_hub.client_id:
                result.warnings.append("USGS and Sentinel Hub credentials not configured, cannot download Landsat data")
                result.suggestions.append("Please set USGS or Sentinel Hub credentials in local_settings.py")
                return
            
        else:
            result.warnings.append(f"Unsupported satellite type: {satellite}")
            result.suggestions.append(f"Supported satellite types: sentinel-2, landsat-8, landsat-9")
            return
        
        if filepath:
            # 🆕 如果有行政边界，进行裁剪
            if use_admin_boundary and boundary_file:
                clipped_filepath = self._clip_raster_to_boundary(
                    filepath, boundary_file, region_id or region
                )
                if clipped_filepath:
                    filepath = clipped_filepath
                    print(f"   ✓ Clipped to administrative boundary")
                else:
                    print(f"   Clipping failed, original rectangular range retained")
            
            result.remote_sensing_data = filepath
            result.downloaded_files.append(filepath)
            clip_info = "(clipped to administrative boundary)" if use_admin_boundary and '_boundary' in filepath else "(bounding box extent)"
            result.message = f"Remote sensing data downloaded successfully: {Path(filepath).name} {clip_info}"
            print(f"\n   Remote sensing data download complete {clip_info}")
            print(f"   File path: {filepath}")
        else:
            result.warnings.append("Remote sensing data download failed")
            result.suggestions.append("Please check network connection and API credentials configuration")
    
    def _clip_osm_to_boundary(self, input_filepath: str, boundary_file, region_id: str) -> Optional[str]:
        """
        Clip OSM data using real administrative boundary
        
        Args:
            input_filepath: Original GeoJSON file path
            boundary_file: Administrative boundary GeoJSON file
            region_id: Region ID
            
        Returns:
            Clipped file path, returns None on failure
        """
        try:
            import subprocess
            
            # Generate output file name (use region name directly, without _clipped suffix to avoid ambiguity)
            # 原命名：osm_roads_20260115_上海浦东_clipped.geojson
            # New naming: osm_roads_Shanghai Pudong.geojson (more clearly indicating this is the complete Shanghai Pudong road data)
            input_path = Path(input_filepath)
            # Extract data type from original file name (e.g. osm_roads, osm_buildings, etc.)
            stem = input_path.stem
            # 移除时间戳和旧的区域名
            parts = stem.split('_')
            # 保留前两部分（如 osm_roads）
            data_type = '_'.join(parts[:2]) if len(parts) >= 2 else parts[0]
            output_filename = f"{data_type}_{region_id}.geojson"
            output_filepath = input_path.parent / output_filename
            
            # 使用 ogr2ogr 进行裁剪（跨平台兼容）
            import shutil
            ogr2ogr_path = shutil.which('ogr2ogr')
            if not ogr2ogr_path:
                # ogr2ogr 不可用，直接使用 Python 方法
                return self._clip_osm_to_boundary_python(input_filepath, boundary_file, output_filepath)
            
            cmd = [
                ogr2ogr_path,
                '-f', 'GeoJSON',
                '-clipsrc', str(boundary_file),
                str(output_filepath),
                str(input_filepath)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0 and output_filepath.exists():
                # 检查裁剪后的文件是否有内容
                with open(output_filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('features') and len(data['features']) > 0:
                        return str(output_filepath)
                    else:
                        # 裁剪后没有要素，删除空文件
                        os.remove(output_filepath)
                        return None
            else:
                # ogr2ogr 失败，尝试使用 Python 方法
                return self._clip_osm_to_boundary_python(input_filepath, boundary_file, output_filepath)
                
        except subprocess.TimeoutExpired:
            print(f"      Clipping timed out")
            return None
        except FileNotFoundError:
            # ogr2ogr 不可用，使用 Python 方法
            return self._clip_osm_to_boundary_python(input_filepath, boundary_file, 
                                                     input_path.parent / output_filename)
        except Exception as e:
            print(f"      Clipping failed: {e}")
            return None
    
    def _clip_osm_to_boundary_python(self, input_filepath: str, boundary_file, 
                                      output_filepath) -> Optional[str]:
        """
        Use pure Python method to clip OSM data (simplified version based on bounding box)
        
        Fallback when ogr2ogr is not available
        """
        try:
            # Read boundary file to get bounding box
            with open(boundary_file, 'r', encoding='utf-8') as f:
                boundary_data = json.load(f)
            
            # Extract boundary box from boundary geometry
            boundary_coords = []
            for feat in boundary_data.get('features', []):
                geom = feat.get('geometry', {})
                coords = geom.get('coordinates', [])
                if geom.get('type') == 'Polygon':
                    boundary_coords.extend(coords[0])
                elif geom.get('type') == 'MultiPolygon':
                    for poly in coords:
                        boundary_coords.extend(poly[0])
            
            if not boundary_coords:
                return None
            
            # Calculate bounding box
            lons = [c[0] for c in boundary_coords]
            lats = [c[1] for c in boundary_coords]
            minx, maxx = min(lons), max(lons)
            miny, maxy = min(lats), max(lats)
            
            # Read input file
            with open(input_filepath, 'r', encoding='utf-8') as f:
                input_data = json.load(f)
            
            # Filter features (simplified version: based on bounding box)
            filtered_features = []
            for feature in input_data.get('features', []):
                geom = feature.get('geometry', {})
                geom_type = geom.get('type', '')
                coords = geom.get('coordinates', [])
                
                # Check if intersects with bounding box
                if self._geometry_in_bbox(geom_type, coords, [minx, miny, maxx, maxy]):
                    filtered_features.append(feature)
            
            if not filtered_features:
                return None
            
            # Save clipped file
            output_data = {
                "type": "FeatureCollection",
                "name": input_data.get('name', 'clipped_data'),
                "crs": input_data.get('crs', {
                    "type": "name",
                    "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
                }),
                "features": filtered_features
            }
            
            with open(output_filepath, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False)
            
            return str(output_filepath)
            
        except Exception as e:
            print(f"      Python clipping failed: {e}")
            return None
    
    def _geometry_in_bbox(self, geom_type: str, coords, bbox: List[float]) -> bool:
        """Check if geometry is within bounding box (at least one point within bounding box)"""
        minx, miny, maxx, maxy = bbox
        
        def point_in_bbox(point):
            return minx <= point[0] <= maxx and miny <= point[1] <= maxy
        
        def check_coords(c):
            if isinstance(c[0], (int, float)):
                return point_in_bbox(c)
            else:
                return any(check_coords(sub) for sub in c)
        
        try:
            return check_coords(coords)
        except:
            return False
    
    def _clip_raster_to_boundary(self, input_filepath: str, boundary_file, region_id: str) -> Optional[str]:
        """
        Use real administrative boundary to clip raster (remote sensing) data
        
        After clipping, pixels outside the administrative boundary will be set to transparent (nodata),
        When displayed in QGIS, the region outside the boundary will not be displayed.
        
        Args:
            input_filepath: Original GeoTIFF file path
            boundary_file: Administrative boundary GeoJSON file
            region_id: Region ID (for file naming)
            
        Returns:
            Clipped file path, returns None on failure
        """
        try:
            import rasterio
            from rasterio.mask import mask
            import numpy as np
            import json
            
            # Generate output file name (use region name to identify, avoid using _clipped to avoid ambiguity)
            # 原命名：北京_sentinel_2_202510_202601_clipped.tif
            # New naming: Beijing_sentinel_2_202510_202601.tif (overwrite original file, because the clipped one is needed)
            input_path = Path(input_filepath)
            # If the file name already contains region information, overwrite the original file
            output_filename = input_path.stem + "_boundary.tif"  # Use _boundary to indicate the boundary range
            output_filepath = input_path.parent / output_filename
            
            print(f"   Clipping raster data to administrative boundary...")
            
            # Read boundary GeoJSON
            with open(boundary_file, 'r', encoding='utf-8') as f:
                boundary_data = json.load(f)
            
            # Extract boundary geometry
            geometries = []
            if 'features' in boundary_data:
                for feat in boundary_data['features']:
                    if feat.get('geometry'):
                        geometries.append(feat['geometry'])
            elif 'geometry' in boundary_data:
                geometries.append(boundary_data['geometry'])
            
            if not geometries:
                print(f"   Boundary file does not contain valid geometry")
                return None
            
            # Use rasterio to clip
            with rasterio.open(input_filepath) as src:
                # Set nodata value (pixels outside the boundary will be set to this value)
                # For uint8 type, use 255 as nodata (white/transparent)
                # For other types, use 0
                dtype = src.dtypes[0]
                if dtype == 'uint8':
                    nodata_val = 0  # Black as nodata
                elif 'float' in str(dtype):
                    nodata_val = np.nan
                else:
                    nodata_val = 0
                
                # Clip raster - crop=True will clip to the boundary box, pixels outside the boundary will be set to nodata
                out_image, out_transform = mask(
                    src, 
                    geometries, 
                    crop=True,           # Clip to boundary box
                    nodata=nodata_val,   # 边界外像素值
                    filled=True,         # 填充边界外区域
                    all_touched=True     # 包含所有接触的像素
                )
                
                # 创建输出元数据 - 使用 QGIS 兼容的格式
                out_meta = {
                    "driver": "GTiff",
                    "dtype": dtype,
                    "width": out_image.shape[2],
                    "height": out_image.shape[1],
                    "count": out_image.shape[0],
                    "crs": src.crs,
                    "transform": out_transform,
                    "nodata": nodata_val,  # 设置 nodata 值
                    # QGIS 兼容性选项
                    "tiled": True,         # 分块存储
                    "blockxsize": 256,
                    "blockysize": 256,
                    "compress": "lzw",     # LZW 压缩（兼容性最好）
                }
                
                # 保存裁剪后的栅格
                with rasterio.open(output_filepath, "w", **out_meta) as dest:
                    dest.write(out_image)
            
            # 删除原始文件，返回裁剪后的文件
            try:
                os.remove(input_filepath)
            except:
                pass
            
            print(f"   Raster clipping complete: {output_filename}")
            print(f"   Pixels outside boundary set to nodata={nodata_val}, displayed as transparent in QGIS")
            return str(output_filepath)
            
        except ImportError:
            print(f"   rasterio not installed, cannot clip raster")
            print(f"   Please install: pip install rasterio")
            return None
        except Exception as e:
            print(f"   Raster clipping failed: {str(e)[:100]}")
            import traceback
            print(f"   Detailed: {traceback.format_exc()[:200]}")
            return None
    
    # Overpass API fallback endpoints
    OVERPASS_ENDPOINTS = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]
    
    def _get_landmark_english_name_direct(self, landmark_name: str) -> Optional[str]:
        """
        使用LLM获取地标的英文名称（GeoQueryEngine版本）
        """
        if not self.llm:
            return None
        
        prompt = f"""请将以下中文地名翻译成其在OpenStreetMap中使用的标准英文名称。

地名：{landmark_name}

要求：
1. 返回该地名在国际上通用的英文名称
2. 对于大学，使用官方英文名（如"清华大学"="Tsinghua University"）
3. 对于景点，使用常用英文名（如"故宫"="Forbidden City"）
4. 只返回英文名称，不要其他内容
"""
        try:
            response = self.llm.chat(prompt, temperature=0.1)
            if response:
                english_name = response.strip().strip('"').strip("'")
                if english_name and len(english_name) > 2:
                    return english_name
        except Exception:
            pass
        return None
    
    def _get_landmark_boundary(self, landmark_name: str) -> Optional[Dict]:
        """
        🆕 获取地标/景区的边界多边形
        
        适用于：颐和园、故宫、清华大学、西湖等具体地标
        
        Args:
            landmark_name: 地标名称（如"颐和园"、"故宫"）
            
        Returns:
            包含边界信息的字典，或 None
        """
        # 🔧 修复：首先检查本地是否已有边界文件（无论是行政区还是地标）
        # 这可以避免重复查询并使用已有的正确结果
        safe_name = self.osm._sanitize_name(landmark_name)
        boundary_dir = Path(self.output_dir) / 'boundaries'
        boundary_file = boundary_dir / f"boundary_{safe_name}.geojson"
        
        # 🆕 优化：支持模糊匹配已有的边界文件
        # 例如：当查找 "Hyde Park, London" 时，能够匹配到 "boundary_Hyde_Park.geojson"
        matched_boundary_file = None
        
        if boundary_file.exists():
            matched_boundary_file = boundary_file
        else:
            # 模糊匹配：提取核心地标名称（去除城市/国家后缀）
            # "Hyde Park, London" -> "Hyde Park"
            # "Central Park, New York" -> "Central Park"
            core_name = landmark_name.split(',')[0].strip()
            safe_core_name = self.osm._sanitize_name(core_name)
            
            if safe_core_name != safe_name:
                core_boundary_file = boundary_dir / f"boundary_{safe_core_name}.geojson"
                if core_boundary_file.exists():
                    matched_boundary_file = core_boundary_file
                    print(f"   🔍 Fuzzy matched: '{landmark_name}' -> '{core_name}'")
            
            # 如果还没找到，尝试在边界目录中搜索包含核心名称的文件
            if not matched_boundary_file and boundary_dir.exists():
                # 搜索包含核心名称的边界文件（不区分大小写）
                core_name_lower = core_name.lower().replace(' ', '_')
                for bf in boundary_dir.glob('boundary_*.geojson'):
                    bf_name_lower = bf.stem.lower()
                    # 确保是地标边界（不是行政区边界），且名称匹配
                    if core_name_lower in bf_name_lower:
                        # 排除包含城市/国家后缀的文件（可能是错误的行政区边界）
                        # 例如：避免用 "boundary_Hyde_Park,_London.geojson" 匹配
                        if ',' not in bf.stem:
                            matched_boundary_file = bf
                            print(f"   🔍 Found similar boundary: {bf.name}")
                            break
        
        if matched_boundary_file:
            # 如果本地已有边界文件，直接使用（避免重复查询导致选择错误结果）
            try:
                with open(matched_boundary_file, 'r', encoding='utf-8') as f:
                    geojson_data = json.load(f)
                
                if geojson_data.get('features'):
                    feature = geojson_data['features'][0]
                    geom = feature.get('geometry', {})
                    bbox = self.osm._calculate_bbox_from_geometry(geom)
                    
                    if bbox:
                        print(f"   ✓ Using existing boundary file: {matched_boundary_file}")
                        return {
                            'name': landmark_name,
                            'bbox': bbox,
                            'geojson_file': str(matched_boundary_file),
                            'source': 'local_cache'
                        }
            except Exception as e:
                print(f"   Failed to read local boundary file: {e}")
        
        # Check if it is an administrative region (province/city/county/district, etc.), if so, skip the landmark search
        # 行政区划应该由 get_admin_boundary 直接处理，不需要通过地标搜索
        admin_keywords_cn = ['省', '市', '县', '区', '镇', '乡', '街道', '自治州', '自治县', '盟', '旗']
        # 🔧 修复：添加英文行政区划关键词
        admin_keywords_en = ['state', 'city', 'county', 'province', 'district', 'region', 'municipality', 
                            'country', 'nation', 'territory', 'prefecture']
        
        is_admin_region = (any(kw in landmark_name for kw in admin_keywords_cn) or
                          any(kw in landmark_name.lower() for kw in admin_keywords_en))
        
        # 🆕 检测是否可能是简单的城市/国家名称（如 "Berlin", "London", "Paris", "Germany"）
        # 首字母大写的单词或短语，且不包含典型地标关键词
        if not is_admin_region:
            words = landmark_name.strip().split()
            # 1-2个单词，每个单词首字母大写
            if len(words) <= 2 and all(w and w[0].isupper() for w in words):
                # 检查是否不包含典型的非行政实体关键词
                non_admin_keywords = ['university', 'college', 'park', 'museum', 'airport', 'station', 
                                     'hospital', 'school', 'institute', 'center', 'centre', 'tower',
                                     'temple', 'palace', 'garden', 'zoo', 'stadium', 'arena',
                                     '大学', '学院', '公园', '博物馆', '医院', '学校', '机场', '车站']
                if not any(kw in landmark_name.lower() for kw in non_admin_keywords):
                    is_admin_region = True
        
        if is_admin_region:
            print(f"   '{landmark_name}' appears to be an administrative region, skipping landmark search")
            return None  # Let system use get_admin_boundary result
        
        print(f"   Getting landmark boundary: {landmark_name}")
        
        # Use LLM to infer city (improve search accuracy)
        city = self.osm._infer_city_with_llm(landmark_name) if self.osm.llm else None
        if city:
            print(f"   Inferred city: {city}")
        
        # For Chinese landmarks, prioritize Chinese search (more accurate, avoids campus ambiguity)
        is_chinese_landmark = self.osm._is_chinese_text(landmark_name)
        
        if is_chinese_landmark:
            # Method 1: Prioritize Chinese name search in Nominatim (more accurate for Chinese landmarks)
            boundary = self.osm.get_admin_boundary(landmark_name, city=city)
            if boundary:
                print(f"   ✓ Nominatim found boundary (Chinese search)")
                result = self._process_landmark_boundary_result(landmark_name, boundary)
                if result:
                    return result
        
        # Method 2: Use LLM to get English name, then search with English (fallback)
        english_name = self.osm._get_landmark_english_name(landmark_name) if hasattr(self.osm, '_get_landmark_english_name') else None
        if not english_name and self.osm.llm:
            english_name = self._get_landmark_english_name_direct(landmark_name)
        
        if english_name:
            print(f"   Trying English name search: {english_name}")
            boundary = self.osm.get_admin_boundary(english_name, city=city)
            if boundary:
                # 验证坐标：仅当推断的城市是真正的中国城市时，检查结果是否在中国
                # 🆕 排除外国城市的中文名（如"纽约"、"伦敦"等）
                if city and self.osm._is_chinese_text(city) and self.osm._is_chinese_city(city) and boundary.get('bbox'):
                    bbox = boundary['bbox']
                    lon_center = (bbox[2] + bbox[3]) / 2
                    lat_center = (bbox[0] + bbox[1]) / 2
                    if not (73 <= lon_center <= 135 and 18 <= lat_center <= 54):
                        print(f"   ⚠️ English search result coordinates outside China, skipping")
                        boundary = None
                
                if boundary:
                    print(f"   ✓ Nominatim found boundary (English search)")
                    result = self._process_landmark_boundary_result(landmark_name, boundary)
                    if result:
                        return result
        
        # 方法3: 对于非中文地标，尝试中文搜索（作为备用）
        if not is_chinese_landmark:
            boundary = self.osm.get_admin_boundary(landmark_name, city=city)
            if boundary:
                print(f"   ✓ Nominatim found boundary (original name search)")
                result = self._process_landmark_boundary_result(landmark_name, boundary)
                if result:
                    return result
        
        # 方法2: 使用高德+Overpass组合查询（备用）
        return self._get_landmark_boundary_fallback(landmark_name)
    
    def _process_landmark_boundary_result(self, landmark_name: str, boundary: Dict) -> Optional[Dict]:
        """
        处理地标边界搜索结果，确保保存为正确格式的GeoJSON文件
        
        Args:
            landmark_name: 地标名称
            boundary: get_admin_boundary返回的边界数据
            
        Returns:
            处理后的结果字典，包含geojson_file路径
        """
        result = {
            'name': landmark_name,
            'bbox': boundary['bbox'],
            'source': boundary.get('source', 'Nominatim')
        }
        # geojson_file 可能不存在（如高德地理编码回退）
        if 'geojson_file' in boundary:
            # 🔧 确保是绝对路径
            geojson_file = boundary['geojson_file']
            # 处理 Path 对象或字符串
            if isinstance(geojson_file, Path):
                geojson_file_path = geojson_file
            else:
                geojson_file_path = Path(geojson_file)
            
            if not geojson_file_path.is_absolute():
                geojson_file_path = Path(self.output_dir) / geojson_file_path
            result['geojson_file'] = str(geojson_file_path.resolve())
        elif 'geometry' in boundary:
            # 如果没有保存的文件，但有 geometry，保存为标准文件名（不带时间戳，避免重复创建）
            boundary_dir = Path(self.output_dir) / 'boundaries'
            boundary_dir.mkdir(parents=True, exist_ok=True)
            safe_name = self._sanitize_filename(landmark_name)
            boundary_file = boundary_dir / f"boundary_{safe_name}.geojson"
            
            geojson_data = {
                'type': 'FeatureCollection',
                'features': [{
                    'type': 'Feature',
                    'properties': {'name': landmark_name},
                    'geometry': boundary['geometry']
                }]
            }
            
            # 只有当文件不存在时才保存（避免覆盖已有的正确文件）
            if not boundary_file.exists():
                with open(boundary_file, 'w', encoding='utf-8') as f:
                    json.dump(geojson_data, f, ensure_ascii=False, indent=2)
                print(f"   ✓ Boundary saved: {boundary_file}")
            else:
                print(f"   ℹ️ Boundary file already exists, using existing: {boundary_file}")
            
            # 🔧 确保是绝对路径
            result['geojson_file'] = str(boundary_file.resolve())
        
        return result
    
    def _get_landmark_boundary_fallback(self, landmark_name: str) -> Optional[Dict]:
        """
        使用高德+Overpass组合查询获取地标边界（备用方法）
        """
        # 方法2: 使用高德 POI 搜索获取位置，然后 Overpass 搜索周边
        # 但排除国外国家名称（高德地图主要面向中国，对国外地名识别不准确）
        is_foreign_country = landmark_name.strip() in self.osm.FOREIGN_COUNTRIES or \
                            any(country in landmark_name for country in self.osm.FOREIGN_COUNTRIES if len(country) <= len(landmark_name))
        
        if self.osm.amap_key and self.osm._is_chinese_text(landmark_name) and not is_foreign_country:
            print(f"   ℹ️ Trying Amap + Overpass combined query...")
            
            # 先用高德获取位置
            location = self.osm._geocode_with_amap(landmark_name, get_bbox=True)
            if location:
                lat, lon = location['lat'], location['lon']
                print(f"   ✓ Amap location: ({lat:.4f}, {lon:.4f})")
                
                # 使用 Overpass 查询该位置周围的大学/机构边界
                bbox = [lat - 0.02, lat + 0.02, lon - 0.02, lon + 0.02]  # 约 2km 范围
                
                # 🔧 修复：查询大学的实际边界，而不是建筑物或艺术品
                # 大学的边界通常是 relation[place=university] 或 relation[boundary] 或 way[place=university]
                queries = [
                    f'relation["place"="university"]["name"~"{landmark_name}"]',
                    f'relation["amenity"="university"]["name"~"{landmark_name}"]',
                    f'relation["boundary"]["name"~"{landmark_name}"]',
                    f'way["place"="university"]["name"~"{landmark_name}"]',
                    f'way["amenity"="university"]["name"~"{landmark_name}"]',
                    # 备用：查询公园、景区（适用于景区类地标）
                    f'relation["leisure"="park"]["name"~"{landmark_name}"]',
                    f'relation["tourism"]["name"~"{landmark_name}"]',
                ]
                
                for query in queries:
                    try:
                        features = self._query_osm_area_data(bbox, query, max_retries=1)
                        if features:
                            # 🔧 过滤：只保留真正的边界/区域，排除建筑物、艺术品等
                            valid_features = []
                            for feature in features:
                                props = feature.get('properties', {})
                                # 排除建筑物
                                if props.get('building'):
                                    continue
                                # 排除艺术品
                                if props.get('tourism') == 'artwork':
                                    continue
                                # 排除博物馆（除非是景区本身）
                                if props.get('tourism') == 'museum' and 'museum' not in landmark_name.lower():
                                    continue
                                # 只保留有边界意义的要素（place, boundary, leisure, tourism=attraction等）
                                if props.get('place') or props.get('boundary') or \
                                   props.get('leisure') or props.get('tourism') in ['attraction', 'theme_park'] or \
                                   props.get('historic'):
                                    valid_features.append(feature)
                            
                            if not valid_features:
                                continue
                                
                            print(f"   ✓ Overpass found {len(valid_features)} matching boundaries (filtered out {len(features) - len(valid_features)} non-boundary features)")
                            
                            # 保存为 GeoJSON
                            from datetime import datetime
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"boundary_{self._sanitize_filename(landmark_name)}_{timestamp}"
                            filepath = self._save_osm_data_to_geojson(
                                valid_features, self.output_dir, filename, "boundary"
                            )
                            
                            if filepath:
                                return {
                                    'name': landmark_name,
                                    'features': len(valid_features),
                                    'geojson_file': str(filepath),
                                    'source': 'Overpass API',
                                    'location': {'lat': lat, 'lon': lon}
                                }
                    except Exception as e:
                        continue
        
        print(f"   ⚠️ Cannot retrieve boundary for '{landmark_name}'")
        return None
    
    def _query_osm_area_data(self, bbox: List[float], overpass_query: str, 
                              max_retries: int = 3) -> List[Dict]:
        """
        使用 Overpass API 查询区域内的 OSM 数据 (带重试和备用端点)
        
        Args:
            bbox: [south, north, west, east] 边界框
            overpass_query: Overpass 查询字符串 (如 'way["highway"]')
            max_retries: 最大重试次数
            
        Returns:
            GeoJSON 格式的要素列表
        """
        import time
        
        # 构建 Overpass QL 查询
        # bbox 格式: (south, west, north, east)
        bbox_str = f"({bbox[0]},{bbox[2]},{bbox[1]},{bbox[3]})"
        
        query = f"""
        [out:json][timeout:180];
        (
            {overpass_query}{bbox_str};
        );
        out body;
        >;
        out skel qt;
        """
        
        last_error = None
        
        # 尝试多个端点
        for endpoint in self.OVERPASS_ENDPOINTS:
            for attempt in range(max_retries):
                try:
                    response = self.osm.session.post(
                        endpoint,
                        data={'data': query},
                        timeout=180
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    # 解析 OSM 数据为 GeoJSON 格式
                    features = self._osm_to_geojson_features(data)
                    if features:
                        return features
                    
                except Exception as e:
                    last_error = e
                    error_msg = str(e)[:60]
                    
                    # 判断错误类型
                    if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                        if attempt < max_retries - 1:
                            print(f"      Timeout, retrying ({attempt + 2}/{max_retries})...")
                            time.sleep(2)
                            continue
                    elif "429" in error_msg or "Too Many" in error_msg:
                        # 请求过多，等待后重试
                        print(f"      Request too many, waiting 5 seconds and retrying...")
                        time.sleep(5)
                        continue
                    elif "502" in error_msg or "503" in error_msg or "504" in error_msg:
                        # Server error, try fallback endpoint
                        break
                    else:
                        # Other errors, try next endpoint
                        break
            
            # Current endpoint failed, try next endpoint
            if endpoint != self.OVERPASS_ENDPOINTS[-1]:
                print(f"      Trying fallback Overpass endpoint...")
        
        print(f"      All Overpass endpoints failed: {str(last_error)[:50]}")
        return []
    
    def _osm_to_geojson_features(self, osm_data: Dict) -> List[Dict]:
        """
        Convert OSM data returned by Overpass API to GeoJSON features
        
        Args:
            osm_data: Overpass API 返回的 JSON 数据
            
        Returns:
            GeoJSON 格式的要素列表
        """
        features = []
        elements = osm_data.get('elements', [])
        
        # First collect all nodes
        nodes = {}
        for elem in elements:
            if elem['type'] == 'node':
                nodes[elem['id']] = (elem['lon'], elem['lat'])
        
        # 处理 way 元素
        for elem in elements:
            if elem['type'] == 'way':
                node_ids = elem.get('nodes', [])
                coords = []
                
                for nid in node_ids:
                    if nid in nodes:
                        coords.append(nodes[nid])
                
                if len(coords) < 2:
                    continue
                
                # 判断是否为闭合多边形
                if coords[0] == coords[-1] and len(coords) >= 4:
                    geometry = {
                        "type": "Polygon",
                        "coordinates": [coords]
                    }
                else:
                    geometry = {
                        "type": "LineString",
                        "coordinates": coords
                    }
                
                # 提取标签作为属性
                tags = elem.get('tags', {})
                properties = {
                    "osm_id": elem['id'],
                    "osm_type": "way",
                    **tags
                }
                
                features.append({
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": properties
                })
        
        return features
    
    def _save_osm_data_to_geojson(self, features: List[Dict], 
                                   output_dir: str, 
                                   filename: str,
                                   data_type: str) -> Optional[str]:
        """将 OSM 数据保存为 GeoJSON 文件"""
        if not features:
            return None
        
        os.makedirs(output_dir, exist_ok=True)
        
        geojson = {
            "type": "FeatureCollection",
            "name": filename,
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
            },
            "properties": {
                "source": "OpenStreetMap",
                "data_type": data_type,
                "download_time": datetime.now().isoformat()
            },
            "features": features
        }
        
        output_file = os.path.join(output_dir, f"{filename}.geojson")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)
        
        return output_file

    def _handle_semantic_analysis_query(self, intent: IntentAnalysis,
                                        result: UnifiedQueryResult):
        """
        处理语义分析查询 - WorldKG 语义增强与类型统计
        
        WorldKG 的核心优势:
        - 将 OSM 标签映射到语义本体类型 (lgdo:Restaurant, lgdo:University 等)
        - 提供区域功能画像（各类设施的分布和占比）
        - 语义类型归一化（同类设施聚合）
        
        工作流程:
        1. 用 Overpass API 获取区域内的所有 POI（数据更全）
        2. 用 WorldKG 获取语义类型标签
        3. 统计各类型分布
        4. 生成区域功能画像
        """
        print("\nExecuting semantic analysis (WorldKG semantic enhancement)...")
        
        # 提取查询参数
        entity_type = intent.entity_type or intent.poi_type
        # [Fix] Check osm_region first, because complex queries will use this field
        location = intent.osm_region or intent.location_filter or intent.reference_location
        
        if not location:
            result.warnings.append("WorldKG query requires specifying location or entity type")
            return
        
        # [Fix] When querying "XXX contains which facilities", XXX is the location, not the entity type
        # 如果 entity_type 是地点类型词（如 university, park, school），且与 location 相关
        # Should clear entity_type, change to query all facilities within the location
        location_type_words = {'university', 'park', 'school', 'museum', 'hospital', 
                              'station', 'airport', 'mall', 'center', 'garden', 
                              'tourism', 'attraction', 'landmark', 'temple', 'palace'}
        if entity_type and entity_type.lower() in location_type_words:
            # 检查 location 是否包含该类型词（如"清华大学"包含"大学"的英文对应词）
            location_lower = location.lower()
            # 中文地点类型映射
            zh_type_mapping = {
                'university': ['大学', '学院'],
                'park': ['公园', '园', '园林'],
                'school': ['学校', '中学', '小学'],
                'museum': ['博物馆', '博物院'],
                'hospital': ['医院'],
                'station': ['站', '车站'],
                'airport': ['机场'],
                'mall': ['商场', '商城'],
                'center': ['中心'],
                'garden': ['花园', '园林', '园'],
                'tourism': ['景区', '景点', '园', '宫', '庙', '寺'],
                'attraction': ['景区', '景点', '园'],
                'landmark': ['地标', '塔', '桥'],
                'temple': ['寺', '庙', '庵'],
                'palace': ['宫', '殿', '府']
            }
            zh_words = zh_type_mapping.get(entity_type.lower(), [])
            if any(w in location for w in zh_words) or entity_type.lower() in location_lower:
                print(f"   Detected location type query: {location} is {entity_type} type")
                print(f"   Corrected to query all facilities within {location}")
                entity_type = None  # Clear entity type, query all facilities within the location
        
        print(f"   Querying: {entity_type or 'all facilities'} in {location}")
        
        try:
            # 首先获取位置的坐标
            location_info = self.osm.geocode(location, get_bbox=True)
            
            if not location_info:
                # 尝试使用预定义边界框
                bbox = self._get_city_bbox(location)
                if not bbox:
                    result.warnings.append(f"Cannot get location information for '{location}'")
                    return
            else:
                bbox = location_info.get('bbox')
                lat, lon = location_info['lat'], location_info['lon']
                
                if not bbox:
                    # 没有 bbox，使用较小的默认范围（约 2km）
                    delta = 0.02
                    bbox = [lat - delta, lat + delta, lon - delta, lon + delta]
                else:
                    # 检查 bbox 范围
                    lat_range = bbox[1] - bbox[0]
                    lon_range = bbox[3] - bbox[2]
                    min_range = 0.01  # 最小约 1km
                    max_range = 0.05  # 最大约 5km（避免覆盖整个城区）
                    
                    # 如果 bbox 太大，限制到最大范围
                    if lat_range > max_range or lon_range > max_range:
                        delta = max_range / 2
                        bbox = [lat - delta, lat + delta, lon - delta, lon + delta]
                        print(f"   Original bounding box too large, search range limited")
                    elif lat_range < min_range or lon_range < min_range:
                        # bbox 太小，扩展到最小范围
                        delta = max(min_range / 2, 0.02)
                        bbox = [lat - delta, lat + delta, lon - delta, lon + delta]
                        print(f"   Original bounding box too small, search range expanded")
            
            print(f"   Bounding box: [{bbox[0]:.4f}, {bbox[1]:.4f}, {bbox[2]:.4f}, {bbox[3]:.4f}]")
            
            # [New] Try to get real polygon boundary for precise filtering
            real_boundary = None
            try:
                boundary_info = self.osm.get_admin_boundary(location, max_retries=1)
                if boundary_info and boundary_info.get('geometry'):
                    real_boundary = boundary_info['geometry']
                    print(f"   Real polygon boundary for {location} obtained, will be used for precise filtering")
            except Exception as e:
                print(f"   Cannot get real boundary: {str(e)[:30]}")
            
            # 执行 WorldKG 查询
            entities = self.worldkg.query_entities_in_bbox(
                bbox=bbox,
                entity_type=entity_type,
                limit=1000
            )
            
            if entities:
                # 【新增】如果有真实边界，过滤结果（但结果太少时回退到边界框）
                if real_boundary:
                    original_count = len(entities)
                    filtered_entities = self._filter_entities_by_polygon(entities, real_boundary)
                    filtered_count = len(filtered_entities)
                    
                    # 🆕 智能回退：如果过滤后结果太少（<10个）或过滤比例太高（>90%），使用边界框
                    FILTER_MIN_THRESHOLD = 10  # 最少保留10个结果
                    FILTER_RATIO_THRESHOLD = 0.1  # 至少保留10%的结果
                    
                    if filtered_count < FILTER_MIN_THRESHOLD or (filtered_count / original_count) < FILTER_RATIO_THRESHOLD:
                        print(f"   Real boundary filtering too strict: {original_count} → {filtered_count} entities (retention rate {filtered_count/original_count:.1%})")
                        print(f"   Too few results, falling back to bbox filtering (keeping {original_count} entities)")
                        entities = entities  # Use original boundary box results
                    else:
                        entities = filtered_entities
                        if original_count != filtered_count:
                            print(f"   ✓ Real boundary filtering: {original_count} → {filtered_count} entities (retention rate {filtered_count/original_count:.1%})")
                else:
                    print(f"   ℹ️ Real boundary not available, using bbox results ({len(entities)} entities)")
                
                # 转换为 WikidataEntity 格式以复用现有显示逻辑
                worldkg_results = []
                for e in entities:
                    entity = WikidataEntity(
                        wikidata_id=e.get('osm_id', ''),
                        name=e.get('name', '未命名'),
                        name_en='',
                        entity_type=entity_type or 'osm_entity',
                        description=f"OSM 实体: {e.get('tags', '')}",
                        lat=e.get('lat'),
                        lon=e.get('lon'),
                        properties={
                            'osm_id': e.get('osm_id', ''),
                            'entity_uri': e.get('entity_uri', ''),
                            'tags': e.get('tags', ''),
                            'source': 'WorldKG'
                        }
                    )
                    worldkg_results.append(entity)
                
                result.knowledge_results = worldkg_results
                print(f"   ✓ Found {len(worldkg_results)} WorldKG entities")
                
                # 🆕 语义类型统计分析
                semantic_stats = self._analyze_semantic_types(entities)
                if semantic_stats:
                    print(f"\n   📊 Semantic type statistics:")
                    for category, info in sorted(semantic_stats.items(), 
                                                 key=lambda x: x[1]['count'], reverse=True)[:10]:
                        pct = info['percentage']
                        print(f"      • {category}: {info['count']} entities ({pct:.1f}%)")
                    
                    # 生成区域功能画像
                    top_categories = list(semantic_stats.keys())[:3]
                    if top_categories:
                        profile = "、".join(top_categories)
                        result.message = f"Semantic analysis completed: {location} is mainly **{profile}** functional area, with {len(worldkg_results)} facilities"
                        result.suggestions.append(f"Functional area profile: {profile}")
                    else:
                        result.message = f"Semantic analysis completed, found {len(worldkg_results)} OSM entities"
                    
                    # 将统计结果添加到 properties
                    result.properties = result.properties or {}
                    result.properties['semantic_analysis'] = {
                        'total_entities': len(worldkg_results),
                        'type_distribution': semantic_stats,
                        'top_categories': top_categories,
                        'region': location
                    }
                else:
                    result.message = f"Semantic analysis completed, found {len(worldkg_results)} OSM entities"
            else:
                # WorldKG 无结果，尝试用 Overpass API 获取 POI 并进行语义标签分析
                print(f"   WorldKG has no results, trying Overpass API + semantic label analysis...")
                # 🆕 使用边界框查询而不是area查询（更可靠）
                poi_results = self._search_poi_in_bbox(bbox, limit=500)
                
                if poi_results:
                    print(f"   Overpass API found {len(poi_results)} POIs")
                    
                    # 分析 POI 的语义类型
                    poi_semantic_stats = self._analyze_poi_semantic_types(poi_results)
                    if poi_semantic_stats:
                        print(f"\n   📊 POI semantic type statistics:")
                        for category, info in sorted(poi_semantic_stats.items(), 
                                                     key=lambda x: x[1]['count'], reverse=True)[:10]:
                            pct = info['percentage']
                            print(f"      • {category}: {info['count']} entities ({pct:.1f}%)")
                        
                        # 将 POI 转换为知识结果格式
                        result.poi_results = poi_results
                        result.properties = result.properties or {}
                        result.properties['semantic_analysis'] = {
                            'total_entities': len(poi_results),
                            'type_distribution': poi_semantic_stats,
                            'top_categories': list(poi_semantic_stats.keys())[:3],
                            'region': location,
                            'source': 'Overpass API (OSM tags)'
                        }
                        
                        top_cats = list(poi_semantic_stats.keys())[:3]
                        profile = "、".join(top_cats)
                        result.message = f"Semantic analysis completed (Overpass): {location} is mainly **{profile}** functional area"
                    else:
                        result.message = f"Semantic analysis completed, found {len(poi_results)} POIs"
                else:
                    result.warnings.append(f"Cannot get facility data for {location}")
                    result.suggestions.append("Please check if the region name is correct, or try a larger region range")
                
        except Exception as e:
            print(f"   ✗ Semantic analysis failed: {e}")
            result.warnings.append(f"Semantic analysis failed: {str(e)[:50]}")
            result.suggestions.append("Suggest using poi_search intent instead")
    
    def _search_poi_in_bbox_for_poi_search(self, bbox: List[float], poi_type: str = None,
                                           brand_name: str = None, property_filters: Dict[str, Any] = None,
                                           limit: int = 1000) -> List[POIResult]:
        """
        在边界框内搜索 POI（支持类型、品牌、属性过滤）- 用于 poi_search 回退
        
        Args:
            bbox: [south, north, west, east]
            poi_type: POI 类型（可选）
            brand_name: 品牌名称（可选）
            property_filters: 属性过滤条件（可选）
            limit: 返回数量限制
            
        Returns:
            POI 结果列表
        """
        # bbox 格式转换为 Overpass: (south, west, north, east)
        bbox_str = f"({bbox[0]},{bbox[2]},{bbox[1]},{bbox[3]})"
        
        # 构建过滤条件
        filters = []
        
        if brand_name:
            filters.append(f'["name"~"{brand_name}",i]')
        
        if poi_type:
            osm_tag = self.osm._get_osm_tag_for_poi(poi_type)
            if '=' in osm_tag:
                tag_key, tag_value = osm_tag.split('=', 1)
                filters.append(f'["{tag_key}"="{tag_value}"]')
            else:
                filters.append(f'["{poi_type}"]')
        
        # 添加属性过滤条件
        if property_filters:
            property_filter_strs = self.osm._parse_property_filters(property_filters)
            filters.extend(property_filter_strs)
        
        # 如果既没有类型也没有品牌，默认搜索所有 amenity
        if not filters:
            filters.append('["amenity"]')
        
        filter_str = ''.join(filters)
        
        # 🆕 获取可用端点
        available_endpoints = self.osm._get_available_overpass_endpoints()
        
        # 🆕 根据端点可用性调整超时
        if getattr(self.osm, '_no_available_endpoints', False):
            request_timeout = 5
            query_timeout = 10
        else:
            request_timeout = 30
            query_timeout = 60
        
        # 构建查询
        query = f"""
        [out:json][timeout:{query_timeout}];
        (
          node{filter_str}[{bbox_str}];
          way{filter_str}[{bbox_str}];
        );
        out body center {limit};
        """
        
        for endpoint_url in available_endpoints:
            try:
                import requests as req_direct
                response = req_direct.post(
                    endpoint_url,
                    data={'data': query},
                    timeout=request_timeout,
                    proxies={'http': None, 'https': None}
                )
                response.raise_for_status()
                
                data = response.json()
                elements = data.get('elements', [])
                
                if elements:
                    results = []
                    for element in elements:
                        # 获取坐标
                        if element['type'] == 'node':
                            poi_lat = element['lat']
                            poi_lon = element['lon']
                        elif element['type'] == 'way' and 'center' in element:
                            poi_lat = element['center']['lat']
                            poi_lon = element['center']['lon']
                        else:
                            continue
                        
                        tags = element.get('tags', {})
                        name = tags.get('name', tags.get('name:zh', tags.get('name:en', '未命名')))
                        
                        # 获取地址信息
                        address_parts = []
                        if tags.get('addr:city'):
                            address_parts.append(tags['addr:city'])
                        if tags.get('addr:district'):
                            address_parts.append(tags['addr:district'])
                        if tags.get('addr:street'):
                            address_parts.append(tags['addr:street'])
                        if tags.get('addr:housenumber'):
                            address_parts.append(tags['addr:housenumber'])
                        address = ''.join(address_parts) or tags.get('addr:full', '')
                        
                        poi_type_actual = poi_type or tags.get('amenity', tags.get('shop', 'unknown'))
                        
                        results.append(POIResult(
                            osm_id=element['id'],
                            name=name,
                            poi_type=poi_type_actual,
                            lat=poi_lat,
                            lon=poi_lon,
                            distance_meters=0,
                            tags=tags,
                            address=address
                        ))
                    
                    return results
                    
            except Exception as e:
                print(f"   Overpass bbox query failed: {str(e)[:50]}")
                continue
        
        return []
    
    def _search_poi_in_bbox(self, bbox: List[float], limit: int = 500) -> List[POIResult]:
        """
        在边界框内搜索所有 POI（使用 Overpass API）
        
        Args:
            bbox: [south, north, west, east]
            limit: 返回数量限制
            
        Returns:
            POI 结果列表
        """
        # bbox 格式转换为 Overpass: (south, west, north, east)
        bbox_str = f"({bbox[0]},{bbox[2]},{bbox[1]},{bbox[3]})"
        
        # 🆕 获取可用端点
        available_endpoints = self.osm._get_available_overpass_endpoints()
        
        # 🆕 根据端点可用性调整超时
        if getattr(self.osm, '_no_available_endpoints', False):
            request_timeout = 5
            query_timeout = 10
        else:
            request_timeout = 30
            query_timeout = 60
        
        # 查询所有 amenity 和 shop
        query = f"""
        [out:json][timeout:{query_timeout}];
        (
          node["amenity"][{bbox_str}];
          node["shop"][{bbox_str}];
          node["tourism"][{bbox_str}];
          node["leisure"][{bbox_str}];
          way["amenity"][{bbox_str}];
          way["shop"][{bbox_str}];
          way["tourism"][{bbox_str}];
          way["leisure"][{bbox_str}];
        );
        out body center {limit};
        """
        
        for endpoint_url in available_endpoints:
            try:
                import requests as req_direct
                response = req_direct.post(
                    endpoint_url,
                    data={'data': query},
                    timeout=request_timeout,
                    proxies={'http': None, 'https': None}
                )
                response.raise_for_status()
                
                data = response.json()
                elements = data.get('elements', [])
                
                if elements:
                    results = []
                    for element in elements:
                        # 获取坐标
                        if element['type'] == 'node':
                            poi_lat = element['lat']
                            poi_lon = element['lon']
                        elif element['type'] == 'way' and 'center' in element:
                            poi_lat = element['center']['lat']
                            poi_lon = element['center']['lon']
                        else:
                            continue
                        
                        tags = element.get('tags', {})
                        name = tags.get('name', tags.get('name:zh', tags.get('name:en', '未命名')))
                        
                        # 获取地址信息
                        address_parts = []
                        if tags.get('addr:city'):
                            address_parts.append(tags['addr:city'])
                        if tags.get('addr:district'):
                            address_parts.append(tags['addr:district'])
                        if tags.get('addr:street'):
                            address_parts.append(tags['addr:street'])
                        if tags.get('addr:housenumber'):
                            address_parts.append(tags['addr:housenumber'])
                        address = ''.join(address_parts) or tags.get('addr:full', '')
                        
                        poi_type = tags.get('amenity') or tags.get('shop') or tags.get('tourism') or tags.get('leisure') or 'unknown'
                        
                        results.append(POIResult(
                            osm_id=element['id'],
                            name=name,
                            poi_type=poi_type,
                            lat=poi_lat,
                            lon=poi_lon,
                            distance_meters=0,
                            tags=tags,
                            address=address
                        ))
                    
                    return results
                    
            except Exception as e:
                print(f"   Overpass bbox query failed: {str(e)[:50]}")
                continue
        
        return []
    
    def _analyze_semantic_types(self, entities: List[Dict]) -> Dict[str, Dict]:
        """
        分析 WorldKG 实体的语义类型分布
        
        将 OSM/WorldKG 标签映射到语义类别:
        - 餐饮类: Restaurant, Cafe, FastFood, Bar, Pub
        - 教育类: School, University, Kindergarten, College
        - 医疗类: Hospital, Clinic, Pharmacy, Doctors
        - 交通类: BusStop, Station, Parking, Taxi
        - 商业类: Shop, Mall, Bank, ATM
        - 旅游类: Hotel, Attraction, Museum, Viewpoint
        - 生活服务: Post, Police, FireStation, Toilets
        """
        if not entities:
            return {}
        
        # 语义类别映射
        category_keywords = {
            '餐饮类': ['Restaurant', 'Cafe', 'FastFood', 'Bar', 'Pub', 'Food', 'Bakery'],
            '教育类': ['School', 'University', 'Kindergarten', 'College', 'Library', 'Education'],
            '医疗类': ['Hospital', 'Clinic', 'Pharmacy', 'Doctors', 'Dentist', 'Veterinary'],
            '交通类': ['BusStop', 'Station', 'Parking', 'Taxi', 'Fuel', 'PublicTransport', 'Highway'],
            '商业类': ['Shop', 'Mall', 'Bank', 'ATM', 'Marketplace', 'Supermarket'],
            '旅游类': ['Hotel', 'Attraction', 'Museum', 'Viewpoint', 'Tourism', 'Monument', 'Historic'],
            '生活服务': ['Post', 'Police', 'FireStation', 'Toilets', 'Telephone', 'WasteBasket'],
            '自然景观': ['Park', 'Garden', 'Water', 'Forest', 'Peak', 'Natural'],
            '宗教场所': ['Church', 'Temple', 'Mosque', 'Religion', 'PlaceOfWorship'],
            '娱乐休闲': ['Cinema', 'Theatre', 'Nightclub', 'Sports', 'Fitness', 'Swimming'],
        }
        
        # 统计各类别
        category_counts = {cat: {'count': 0, 'entities': []} for cat in category_keywords}
        category_counts['其他'] = {'count': 0, 'entities': []}
        
        for entity in entities:
            tags = entity.get('tags', '')
            matched = False
            
            for category, keywords in category_keywords.items():
                for keyword in keywords:
                    if keyword.lower() in tags.lower():
                        category_counts[category]['count'] += 1
                        category_counts[category]['entities'].append(entity.get('name', ''))
                        matched = True
                        break
                if matched:
                    break
            
            if not matched:
                category_counts['其他']['count'] += 1
        
        # 计算百分比，过滤空类别
        total = len(entities)
        result = {}
        for category, info in category_counts.items():
            if info['count'] > 0:
                result[category] = {
                    'count': info['count'],
                    'percentage': (info['count'] / total) * 100,
                    'examples': info['entities'][:5]  # 最多5个示例
                }
        
        # 按数量排序
        return dict(sorted(result.items(), key=lambda x: x[1]['count'], reverse=True))
    
    def _analyze_poi_semantic_types(self, poi_results: List) -> Dict[str, Dict]:
        """
        分析 Overpass API POI 的语义类型分布
        
        基于 OSM amenity/shop/tourism 等标签进行分类
        """
        if not poi_results:
            return {}
        
        # OSM 标签到语义类别的映射
        tag_category_mapping = {
            # 餐饮类
            'restaurant': '餐饮类', 'cafe': '餐饮类', 'fast_food': '餐饮类',
            'bar': '餐饮类', 'pub': '餐饮类', 'food_court': '餐饮类', 'bakery': '餐饮类',
            # 教育类
            'school': '教育类', 'university': '教育类', 'college': '教育类',
            'kindergarten': '教育类', 'library': '教育类',
            # 医疗类
            'hospital': '医疗类', 'clinic': '医疗类', 'pharmacy': '医疗类',
            'doctors': '医疗类', 'dentist': '医疗类',
            # 交通类
            'bus_station': '交通类', 'parking': '交通类', 'fuel': '交通类',
            'taxi': '交通类', 'bicycle_parking': '交通类',
            # 商业类
            'bank': '商业类', 'atm': '商业类', 'marketplace': '商业类',
            'supermarket': '商业类', 'convenience': '商业类', 'shop': '商业类',
            # 旅游类
            'hotel': '旅游类', 'hostel': '旅游类', 'museum': '旅游类',
            'attraction': '旅游类', 'viewpoint': '旅游类', 'monument': '旅游类',
            # 生活服务
            'post_office': '生活服务', 'police': '生活服务', 'toilets': '生活服务',
            'fire_station': '生活服务', 'post_box': '生活服务',
            # 娱乐休闲
            'cinema': '娱乐休闲', 'theatre': '娱乐休闲', 'nightclub': '娱乐休闲',
            'sports_centre': '娱乐休闲', 'fitness_centre': '娱乐休闲',
        }
        
        # 统计各类别
        category_counts = {}
        
        for poi in poi_results:
            poi_type = poi.poi_type.lower() if poi.poi_type else ''
            
            # 查找匹配的类别
            category = tag_category_mapping.get(poi_type, '其他')
            
            if category not in category_counts:
                category_counts[category] = {'count': 0, 'entities': []}
            
            category_counts[category]['count'] += 1
            category_counts[category]['entities'].append(poi.name or poi_type)
        
        # 计算百分比
        total = len(poi_results)
        result = {}
        for category, info in category_counts.items():
            if info['count'] > 0:
                result[category] = {
                    'count': info['count'],
                    'percentage': (info['count'] / total) * 100,
                    'examples': info['entities'][:5]
                }
        
        return dict(sorted(result.items(), key=lambda x: x[1]['count'], reverse=True))
    
    def _filter_entities_by_polygon(self, entities: List[Dict], geometry: Dict) -> List[Dict]:
        """
        使用真实多边形边界过滤实体列表
        
        Args:
            entities: 实体列表，每个实体需要有 lat, lon 字段
            geometry: GeoJSON 格式的几何对象 (Polygon 或 MultiPolygon)
            
        Returns:
            过滤后的实体列表（只保留在多边形内的实体）
        """
        if not geometry or not entities:
            return entities
        
        geom_type = geometry.get('type', '')
        coords = geometry.get('coordinates', [])
        
        if not coords:
            return entities
        
        def point_in_polygon(lat: float, lon: float, polygon_coords: List) -> bool:
            """射线法判断点是否在多边形内"""
            # polygon_coords 是 [外环, 内环1, 内环2, ...]
            # 外环是 [[lon, lat], [lon, lat], ...]
            if not polygon_coords:
                return False
            
            ring = polygon_coords[0]  # 只检查外环
            n = len(ring)
            inside = False
            
            j = n - 1
            for i in range(n):
                xi, yi = ring[i][0], ring[i][1]  # lon, lat
                xj, yj = ring[j][0], ring[j][1]
                
                if ((yi > lat) != (yj > lat)) and \
                   (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
                    inside = not inside
                j = i
            
            return inside
        
        def point_in_geometry(lat: float, lon: float) -> bool:
            """判断点是否在几何对象内"""
            if geom_type == 'Polygon':
                return point_in_polygon(lat, lon, coords)
            elif geom_type == 'MultiPolygon':
                # MultiPolygon: [[[外环], [内环]], [[外环], [内环]], ...]
                for polygon_coords in coords:
                    if point_in_polygon(lat, lon, polygon_coords):
                        return True
                return False
            else:
                # 不支持的几何类型，默认返回 True
                return True
        
        filtered = []
        for entity in entities:
            lat = entity.get('lat', 0)
            lon = entity.get('lon', 0)
            if lat and lon and point_in_geometry(lat, lon):
                filtered.append(entity)
        
        return filtered
    
    def _handle_complex_query(self, intent: IntentAnalysis, 
                               result: UnifiedQueryResult, user_query: str):
        """
        处理复杂查询 - 任务拆解与执行
        
        将复杂查询拆解为多个子任务，按依赖关系顺序执行
        """
        print("\n🔀 Executing complex query (task decomposition)...")
        
        # 获取子任务列表
        sub_tasks = intent.sub_tasks
        
        # 如果意图分析没有提供子任务，使用任务拆解器
        if not sub_tasks and self.task_decomposer:
            print("   Decomposing tasks...")
            sub_tasks = self.task_decomposer.decompose(user_query)
        
        if not sub_tasks:
            result.warnings.append("Cannot decompose complex query")
            # 回退到混合查询
            self._handle_hybrid_query(intent, result, top_k=5)
            return
        
        print(f"   Decomposed into {len(sub_tasks)} sub-tasks")
        
        # 存储中间结果
        task_outputs = {}
        
        # 按顺序执行子任务
        for task in sorted(sub_tasks, key=lambda x: x.get('order', 0)):
            task_id = task.get('order', 0)
            task_type = task.get('type', '')
            task_desc = task.get('description', '')
            task_params = task.get('params', {})
            depends_on = task.get('depends_on')
            output_name = task.get('output_name', f'task_{task_id}')
            
            print(f"\n   [{task_id}] {task_desc}")
            
            sub_result = SubTaskResult(
                task_id=task_id,
                task_type=task_type,
                description=task_desc
            )
            
            try:
                # 替换依赖参数
                if depends_on and depends_on in task_outputs:
                    prev_output = task_outputs[depends_on]
                    # 如果前一个任务输出了坐标，用于当前任务
                    if isinstance(prev_output, dict) and 'lat' in prev_output:
                        task_params['reference_coords'] = prev_output
                
                # 执行子任务
                if task_type == 'spatial_proximity':
                    # 从 params 或描述中提取参数
                    poi_type = task_params.get('poi_type', '')
                    ref_location = task_params.get('reference_location', '')
                    radius = task_params.get('radius_meters', 500)
                    
                    # 如果参数缺失，尝试从描述中提取
                    if not poi_type or not ref_location:
                        extracted = self._extract_params_from_description(task_desc, 'spatial_proximity')
                        poi_type = poi_type or extracted.get('poi_type', 'cafe')
                        ref_location = ref_location or extracted.get('reference_location', '')
                    
                    sub_intent = IntentAnalysis(
                        intent=QueryIntent.SPATIAL_PROXIMITY,
                        confidence=1.0,
                        summary=task_desc,
                        poi_type=poi_type,
                        reference_location=ref_location,
                        radius_meters=radius
                    )
                    temp_result = UnifiedQueryResult(
                        query=task_desc, intent=sub_intent, source="osm"
                    )
                    self._handle_proximity_query(sub_intent, temp_result)
                    sub_result.result = temp_result.poi_results
                    result.poi_results.extend(temp_result.poi_results)
                    
                    # 保存参考位置和第一个结果的坐标供后续任务使用
                    if temp_result.poi_results:
                        first_poi = temp_result.poi_results[0]
                        task_outputs[output_name] = {
                            'lat': first_poi.lat, 
                            'lon': first_poi.lon,
                            'name': first_poi.name
                        }
                        # 【重要】保存 POI 查询的参考位置，供后续路由任务作为起点
                        if ref_location:
                            ref_coords = self.osm.geocode(ref_location)
                            if ref_coords:
                                task_outputs['poi_reference_location'] = {
                                    'name': ref_location,
                                    'lat': ref_coords['lat'],
                                    'lon': ref_coords['lon']
                                }
                        print(f"      ✓ Found {len(temp_result.poi_results)} POIs")
                
                elif task_type == 'poi_search':
                    # 区域 POI 搜索（如"柏林的酒店"、"北京的博物馆"）
                    poi_type = task_params.get('poi_type', '')
                    search_region = task_params.get('search_region', '')
                    
                    # 如果参数缺失，尝试从描述中提取
                    if not poi_type or not search_region:
                        extracted = self._extract_params_from_description(task_desc, 'poi_search')
                        poi_type = poi_type or extracted.get('poi_type', 'hotel')
                        search_region = search_region or extracted.get('search_region', '')
                    
                    if search_region:
                        sub_intent = IntentAnalysis(
                            intent=QueryIntent.POI_SEARCH,
                            confidence=1.0,
                            summary=task_desc,
                            poi_type=poi_type,
                            search_region=search_region
                        )
                        temp_result = UnifiedQueryResult(
                            query=task_desc, intent=sub_intent, source="osm"
                        )
                        self._handle_poi_search_query(sub_intent, temp_result)
                        sub_result.result = temp_result.poi_results
                        result.poi_results.extend(temp_result.poi_results)
                        
                        # 【重要】保存区域信息供后续 WorldKG 任务使用
                        task_outputs['query_region'] = search_region
                        
                        if temp_result.poi_results:
                            first_poi = temp_result.poi_results[0]
                            task_outputs[output_name] = {
                                'lat': first_poi.lat, 
                                'lon': first_poi.lon,
                                'name': first_poi.name
                            }
                            print(f"      ✓ Found {len(temp_result.poi_results)} POIs")
                            sub_result.success = True
                        else:
                            sub_result.error = "No POIs found"
                    else:
                        sub_result.success = False
                        sub_result.error = "Cannot extract search region from description"
                
                elif task_type == 'routing':
                    # 从 params 或描述中提取参数
                    origin = task_params.get('origin', '')
                    destination = task_params.get('destination', '')
                    mode = task_params.get('transport_mode', 'walking')
                    
                    # 如果参数缺失，尝试从描述中提取
                    if not origin or not destination:
                        extracted = self._extract_params_from_description(task_desc, 'routing')
                        origin = origin or extracted.get('origin', '')
                        destination = destination or extracted.get('destination', '')
                    
                    # 使用 LLM 验证起点和终点是否是有效地名
                    # 同时从查询上下文中提取城市信息，用于补充英文地名
                    query_context = f"原始查询: {user_query}, 任务描述: {task_desc}"
                    
                    # 验证起点
                    if origin:
                        origin_validation = self._validate_location_with_llm(origin, query_context)
                        if not origin_validation.get('is_valid', False):
                            print(f"      Invalid origin ({origin_validation.get('reason', '')})")
                            origin = ''
                        elif origin_validation.get('enriched_name') != origin:
                            # 使用补充完整后的地名
                            origin = origin_validation.get('enriched_name', origin)
                            print(f"      Enriched origin: {origin}")
                    
                    # 验证终点
                    if destination:
                        dest_validation = self._validate_location_with_llm(destination, query_context)
                        if not dest_validation.get('is_valid', False):
                            print(f"      Invalid destination ({dest_validation.get('reason', '')})")
                            destination = ''
                        elif dest_validation.get('enriched_name') != destination:
                            # 使用补充完整后的地名
                            destination = dest_validation.get('enriched_name', destination)
                            print(f"      Enriched destination: {destination}")
                    
                    # 如果有依赖的前序任务，使用其输出
                    if depends_on and str(depends_on) in task_outputs:
                        prev = task_outputs[str(depends_on)]
                        if isinstance(prev, dict) and 'name' in prev:
                            destination = destination or prev.get('name', '')
                    
                    # 【重要】如果起点为空，尝试使用 POI 查询的参考位置
                    if not origin and 'poi_reference_location' in task_outputs:
                        ref = task_outputs['poi_reference_location']
                        origin = ref['name']
                        origin_coords = {'lat': ref['lat'], 'lon': ref['lon']}
                        print(f"      Using POI reference location as origin: {origin}")
                    
                    # 存储已知的坐标，避免重复地理编码导致的错误
                    origin_coords = None
                    dest_coords = None
                    
                    # 【重要】如果终点为空，尝试从已收集的 POI 查询结果中获取
                    if not destination and result.poi_results:
                        # 使用最近的 POI 作为终点 - 直接使用坐标
                        nearest_poi = result.poi_results[0]
                        destination = nearest_poi.name if nearest_poi.name and nearest_poi.name != '未命名' else '最近POI'
                        dest_coords = {'lat': nearest_poi.lat, 'lon': nearest_poi.lon}
                        print(f"      Automatically selecting POI: {destination} ({nearest_poi.lat:.4f}, {nearest_poi.lon:.4f})")
                    
                    # 如果起点/终点仍为空，尝试从已收集的知识查询结果中获取
                    if (not origin or not destination) and result.knowledge_results:
                        # 获取有坐标的实体，并过滤掉重复/相似的（距离小于 200m 的视为相同）
                        entities_with_coords = []
                        for e in result.knowledge_results:
                            # 确保 lat 和 lon 是有效的数值（不是 None 或列表）
                            try:
                                lat = float(e.lat) if e.lat is not None else None
                                lon = float(e.lon) if e.lon is not None else None
                            except (TypeError, ValueError):
                                continue  # 跳过无效坐标
                            
                            if lat is not None and lon is not None:
                                # 检查是否与已有实体距离太近
                                is_duplicate = False
                                for existing in entities_with_coords:
                                    try:
                                        ex_lat = float(existing.lat)
                                        ex_lon = float(existing.lon)
                                        # 简单的距离计算（约 111km/度）
                                        dist = ((lat - ex_lat) ** 2 + (lon - ex_lon) ** 2) ** 0.5 * 111000
                                        if dist < 200:  # 200米内视为相同地点
                                            is_duplicate = True
                                            break
                                    except (TypeError, ValueError):
                                        continue
                                if not is_duplicate:
                                    entities_with_coords.append(e)
                        
                        if len(entities_with_coords) >= 2:
                            # 使用前两个不同的实体作为起点和终点
                            if not origin:
                                e = entities_with_coords[0]
                                origin = e.name
                                origin_coords = {'lat': float(e.lat), 'lon': float(e.lon)}
                            if not destination:
                                # 选择距离起点最远的实体作为终点
                                if origin_coords:
                                    best_dest = None
                                    max_dist = 0
                                    for e in entities_with_coords[1:]:
                                        try:
                                            e_lat, e_lon = float(e.lat), float(e.lon)
                                            dist = ((e_lat - origin_coords['lat']) ** 2 + 
                                                   (e_lon - origin_coords['lon']) ** 2) ** 0.5
                                            if dist > max_dist:
                                                max_dist = dist
                                                best_dest = e
                                        except (TypeError, ValueError):
                                            continue
                                    if best_dest:
                                        destination = best_dest.name
                                        dest_coords = {'lat': float(best_dest.lat), 'lon': float(best_dest.lon)}
                                else:
                                    e = entities_with_coords[1]
                                    destination = e.name
                                    dest_coords = {'lat': float(e.lat), 'lon': float(e.lon)}
                            print(f"      Automatically selecting (using known coordinates): {origin} → {destination}")
                        elif len(entities_with_coords) == 1:
                            # 只有一个有坐标的实体（或所有实体都在同一地点）
                            e = entities_with_coords[0]
                            try:
                                e_lat, e_lon = float(e.lat), float(e.lon)
                            except (TypeError, ValueError):
                                e_lat, e_lon = None, None
                            
                            if e_lat is not None and e_lon is not None:
                                if not origin:
                                    origin = e.name
                                    origin_coords = {'lat': e_lat, 'lon': e_lon}
                                    # 对于"游览路线"这类查询，设置合理的起点和终点
                                    if not destination:
                                        # 检测是否是景区游览类查询
                                        is_tour_query = any(kw in task_desc for kw in ['游览', '参观', '游玩', 'tour', 'visit'])
                                        if is_tour_query:
                                            destination = f"{e.name}北门" if '南' not in e.name else f"{e.name}出口"
                                            # 景区内游览，偏移约 800m 作为合理的游览距离
                                            dest_coords = {'lat': e_lat + 0.005, 'lon': e_lon + 0.003}
                                            print(f"      Tour route: from {origin} to {destination}")
                                        else:
                                            destination = f"{e.name}入口"
                                            dest_coords = {'lat': e_lat + 0.004, 'lon': e_lon + 0.002}
                                            print(f"      Single location, setting entrance to tour route")
                                elif not destination:
                                    destination = e.name
                                    dest_coords = {'lat': e_lat, 'lon': e_lon}
                    
                    # 检查是否有有效的起点和终点
                    if origin and destination:
                        print(f"\nExecuting routing calculation (OSRM)...")
                        
                        # 处理起点坐标 - 如果没有预存坐标，进行地理编码
                        if not origin_coords:
                            print(f"   Origin: {origin} (geocoding in progress...)")
                            geocoded = self.osm.geocode(origin)
                            if geocoded:
                                origin_coords = {'lat': geocoded['lat'], 'lon': geocoded['lon']}
                                print(f"   Origin coordinates: ({origin_coords['lat']:.4f}, {origin_coords['lon']:.4f})")
                            else:
                                print(f"      Cannot parse origin: {origin}")
                        else:
                            print(f"   Origin: {origin} ({origin_coords['lat']:.4f}, {origin_coords['lon']:.4f})")
                        
                        # 处理终点坐标 - 如果没有预存坐标，进行地理编码
                        if not dest_coords:
                            print(f"   Destination: {destination} (geocoding in progress...)")
                            geocoded = self.osm.geocode(destination)
                            if geocoded:
                                dest_coords = {'lat': geocoded['lat'], 'lon': geocoded['lon']}
                                print(f"   Destination coordinates: ({dest_coords['lat']:.4f}, {dest_coords['lon']:.4f})")
                            else:
                                print(f"      Cannot parse destination: {destination}")
                        else:
                            print(f"   Destination: {destination} ({dest_coords['lat']:.4f}, {dest_coords['lon']:.4f})")
                        
                        # 如果两个坐标都有，计算路由
                        if origin_coords and dest_coords:
                            print(f"   Calculating {mode} route...")
                            
                            route = self.osm.calculate_route(
                                origin_coords['lat'], origin_coords['lon'],
                                dest_coords['lat'], dest_coords['lon'],
                                mode
                            )
                            
                            if route:
                                route.origin = origin
                                route.destination = destination
                                result.route_result = route
                                sub_result.result = route
                                print(f"   Distance: {route.distance_meters/1000:.2f} km")
                                print(f"   Estimated time: {route.duration_seconds/60:.0f} minutes")
                                print(f"      Route: {route.distance_meters/1000:.1f}km, "
                                      f"approximately {route.duration_seconds/60:.0f} minutes")
                            else:
                                print(f"      Route calculation failed")
                        else:
                            print(f"      Cannot get valid coordinates")
                            sub_result.success = False
                            sub_result.error = "Cannot get start or end coordinates"
                    else:
                        print(f"      Missing start or end (origin={origin}, destination={destination})")
                        sub_result.success = False
                        sub_result.error = "Cannot determine start or end"
                
                elif task_type == 'knowledge':
                    # 从 params 或描述中提取参数
                    entity_name = task_params.get('entity_name', '')  # New: direct entity name
                    entity_type = task_params.get('entity_type', '')
                    location_filter = task_params.get('location_filter', '')
                    query_mode = task_params.get('query_mode', '')
                    
                    # 如果参数缺失，尝试从描述中提取
                    if not entity_name and not entity_type:
                        extracted = self._extract_params_from_description(task_desc, 'knowledge')
                        query_mode = extracted.get('query_mode', 'type_location')
                        entity_name = extracted.get('entity_name', '')
                        entity_type = entity_type or extracted.get('entity_type', '')
                        location_filter = location_filter or extracted.get('location_filter', '')
                    
                    # 构建意图
                    sub_intent = IntentAnalysis(
                        intent=QueryIntent.KNOWLEDGE,
                        confidence=1.0,
                        summary=task_desc,
                        entity_name=entity_name,  # New: support direct entity query
                        entity_type=entity_type,
                        location_filter=location_filter,
                        property_filters=task_params.get('property_filters', {})
                    )
                    temp_result = UnifiedQueryResult(
                        query=task_desc, intent=sub_intent, source="wikidata"
                    )
                    self._handle_knowledge_query(sub_intent, temp_result)
                    sub_result.result = temp_result.knowledge_results
                    result.knowledge_results.extend(temp_result.knowledge_results)
                    
                    # 打印执行结果
                    if temp_result.knowledge_results:
                        print(f"      ✓ Found {len(temp_result.knowledge_results)} entities")
                        # 显示前3个结果
                        for entity in temp_result.knowledge_results[:3]:
                            print(f"         - {entity.name}")
                            if entity.description:
                                print(f"           {entity.description[:60]}...")
                        if len(temp_result.knowledge_results) > 3:
                                print(f"         ... and {len(temp_result.knowledge_results)-3} more")
                        
                        # 保存第一个结果的坐标供后续任务使用
                        first_entity = temp_result.knowledge_results[0]
                        if first_entity.lat and first_entity.lon:
                            task_outputs[output_name] = {
                                'lat': first_entity.lat, 
                                'lon': first_entity.lon,
                                'name': first_entity.name
                            }
                        # 【重要】保存查询区域供后续任务继承
                        if location_filter:
                            task_outputs['query_region'] = location_filter
                        elif entity_name:
                            task_outputs['query_region'] = entity_name
                    else:
                        print(f"      No related entities found")
                        sub_result.error = "Wikidata query returned no results"
                        # Even if failed, save region information
                        if location_filter:
                            task_outputs['query_region'] = location_filter
                
                elif task_type == 'osm_data':
                    # Extract OSM download parameters from params or description
                    region = task_params.get('region', '')
                    data_types = task_params.get('data_types', [])
                    
                    # 如果参数缺失，尝试从描述中提取
                    if not region:
                        extracted = self._extract_params_from_description(task_desc, 'osm_data')
                        region = extracted.get('region', '')
                        data_types = data_types or extracted.get('data_types', ['roads', 'buildings'])
                    
                    if region:
                        sub_intent = IntentAnalysis(
                            intent=QueryIntent.OSM_DATA,
                            confidence=1.0,
                            summary=task_desc,
                            osm_region=region,
                            osm_data_types=data_types if data_types else ['roads', 'buildings', 'waterways']
                        )
                        temp_result = UnifiedQueryResult(
                            query=task_desc, intent=sub_intent, source="osm"
                        )
                        self._handle_osm_data_query(sub_intent, temp_result)
                        sub_result.result = temp_result.downloaded_files
                        result.downloaded_files.extend(temp_result.downloaded_files)
                        
                        if temp_result.downloaded_files:
                            print(f"      ✓ Downloaded {len(temp_result.downloaded_files)} data files:")
                            for f in temp_result.downloaded_files:
                                print(f"         📁 {os.path.basename(f)}")
                        else:
                            sub_result.error = "OSM data download failed or no data"
                    else:
                        sub_result.success = False
                        sub_result.error = "Cannot extract region from description"
                
                elif task_type == 'worldkg':
                    # 从 params 或描述中提取 WorldKG 查询参数
                    entity_type = task_params.get('entity_type', '')
                    region = task_params.get('region', '')
                    
                    if not entity_type or not region:
                        extracted = self._extract_params_from_description(task_desc, 'worldkg')
                        entity_type = entity_type or extracted.get('entity_type', '')
                        region = region or extracted.get('region', '')
                    
                    # 【重要】如果区域仍为空，尝试从上游任务继承
                    if not region:
                        # 1. 从 task_outputs 中查找已知区域
                        if 'query_region' in task_outputs:
                            region = task_outputs['query_region']
                            print(f"      Inheriting upstream region: {region}")
                        # 2. 从依赖任务的结果中推断
                        elif depends_on and str(depends_on) in task_outputs:
                            prev = task_outputs[str(depends_on)]
                            if isinstance(prev, dict) and 'name' in prev:
                                # 尝试从实体名称推断区域（如 "柏林某酒店" -> "柏林"）
                                entity_name = prev.get('name', '')
                                inferred = self._infer_region_from_context(entity_name, task_desc)
                                if inferred:
                                    region = inferred
                                    print(f"      Inferring region from context: {region}")
                    
                    if region:
                        sub_intent = IntentAnalysis(
                            intent=QueryIntent.WORLDKG,
                            confidence=1.0,
                            summary=task_desc,
                            entity_type=entity_type,
                            osm_region=region
                        )
                        temp_result = UnifiedQueryResult(
                            query=task_desc, intent=sub_intent, source="worldkg"
                        )
                        self._handle_worldkg_query(sub_intent, temp_result)
                        sub_result.result = temp_result.knowledge_results
                        result.knowledge_results.extend(temp_result.knowledge_results)
                        
                        if temp_result.knowledge_results:
                            print(f"      ✓ Found {len(temp_result.knowledge_results)} WorldKG entities")
                        else:
                            sub_result.error = "WorldKG query returned no results"
                    else:
                        sub_result.success = False
                        sub_result.error = "Cannot extract region from description"
                
                elif task_type == 'geocode':
                    location = task_params.get('location', '')
                    coords = self.osm.geocode(location)
                    if coords:
                        sub_result.result = coords
                        task_outputs[output_name] = coords
                        print(f"      ✓ {location} -> ({coords['lat']:.4f}, {coords['lon']:.4f})")
                    else:
                        sub_result.success = False
                        sub_result.error = f"Cannot parse location: {location}"
                
                elif task_type == 'remote_sensing_data':
                    # 🆕 遥感数据下载子任务
                    satellite = task_params.get('satellite', 'sentinel-2')
                    time_range = task_params.get('time_range', '')
                    region = task_params.get('region', '')
                    cloud_cover_max = task_params.get('cloud_cover_max', DEFAULT_CLOUD_COVER_MAX)
                    processing = task_params.get('processing', '')
                    
                    # 如果参数缺失，尝试从描述中提取
                    if not region or not time_range:
                        extracted = self._extract_params_from_description(task_desc, 'remote_sensing_data')
                        region = region or extracted.get('region', '')
                        time_range = time_range or extracted.get('time_range', '')
                        satellite = satellite or extracted.get('satellite', 'sentinel-2')
                    
                    # 如果还没有时间范围，使用默认值（最近3个月）
                    if not time_range:
                        from datetime import datetime, timedelta
                        end_date = datetime.now()
                        start_date = end_date - timedelta(days=90)
                        time_range = f"{start_date.strftime('%Y-%m-%d')},{end_date.strftime('%Y-%m-%d')}"
                        print(f"      ℹ️ No time range specified, using default: {time_range}")
                    
                    if region:
                        sub_intent = IntentAnalysis(
                            intent=QueryIntent.REMOTE_SENSING_DATA,
                            confidence=1.0,
                            summary=task_desc,
                            satellite=satellite,
                            time_range=time_range,
                            cloud_cover_max=cloud_cover_max,
                            processing=processing,
                            remote_sensing_region=region
                        )
                        temp_result = UnifiedQueryResult(
                            query=task_desc, intent=sub_intent, source="remote_sensing"
                        )
                        self._handle_remote_sensing_query(sub_intent, temp_result)
                        
                        if temp_result.remote_sensing_data:
                            sub_result.result = temp_result.remote_sensing_data
                            result.remote_sensing_data = temp_result.remote_sensing_data
                            result.downloaded_files.extend(temp_result.downloaded_files)
                            print(f"      ✓ Remote sensing data download successful:")
                            print(f"         📁 {os.path.basename(temp_result.remote_sensing_data)}")
                        else:
                            sub_result.error = "Remote sensing data download failed"
                            if temp_result.warnings:
                                sub_result.error += f": {temp_result.warnings[0]}"
                    else:
                        sub_result.success = False
                        sub_result.error = "Cannot extract region from description"
                
                elif task_type == 'semantic_analysis':
                    # 🆕 语义分析子任务（WorldKG 设施类型统计）
                    region = task_params.get('region', '') or task_params.get('osm_region', '')
                    
                    # 如果参数缺失，尝试从描述中提取
                    if not region:
                        extracted = self._extract_params_from_description(task_desc, 'semantic_analysis')
                        region = extracted.get('region', '') or extracted.get('osm_region', '')
                    
                    if region:
                        sub_intent = IntentAnalysis(
                            intent=QueryIntent.SEMANTIC_ANALYSIS,
                            confidence=1.0,
                            summary=task_desc,
                            osm_region=region,
                            location_filter=region
                        )
                        temp_result = UnifiedQueryResult(
                            query=task_desc, intent=sub_intent, source="worldkg"
                        )
                        self._handle_semantic_analysis_query(sub_intent, temp_result)
                        
                        if temp_result.properties.get('semantic_analysis'):
                            sub_result.result = temp_result.properties['semantic_analysis']
                            result.properties['semantic_analysis'] = temp_result.properties['semantic_analysis']
                            print(f"      ✓ Semantic analysis completed")
                            
                            # 显示类型统计摘要
                            analysis = temp_result.properties['semantic_analysis']
                            if 'type_counts' in analysis:
                                top_types = sorted(analysis['type_counts'].items(), 
                                                  key=lambda x: x[1], reverse=True)[:3]
                                print(f"         Main types: {', '.join([f'{t[0]}({t[1]} entities)' for t in top_types])}")
                            sub_result.success = True
                        else:
                            sub_result.error = "Semantic analysis returned no results"
                            if temp_result.warnings:
                                print(f"      {temp_result.warnings[0]}")
                    else:
                        sub_result.success = False
                        sub_result.error = "Cannot extract region from description"
                
                else:
                    # 未知任务类型
                    sub_result.success = False
                    sub_result.error = f"Unknown task type: {task_type}"
                    print(f"      Unknown task type: {task_type}")
                
                # 注意: 只有在没有显式设置 success=False 的情况下，才设为 True
                if not sub_result.error or sub_result.result:
                    sub_result.success = True
                
            except Exception as e:
                sub_result.success = False
                sub_result.error = str(e)
                result.warnings.append(f"Sub-task {task_id} failed: {e}")
            
            result.sub_task_results.append(sub_result)
        
        # 总结执行结果
        success_count = sum(1 for t in result.sub_task_results if t.success)
        print(f"\n   ✓ Completed {success_count}/{len(result.sub_task_results)} sub-tasks")
    
    def _validate_location_with_llm(self, location_name: str, context: str = "") -> Dict[str, Any]:
        """
        Use LLM to validate and enrich location information
        
        Args:
            location_name: 待验证的地名
            context: 查询上下文（如原始查询、前序任务信息等）
            
        Returns:
            {
                "is_valid": bool,          # 是否是有效的具体地名
                "enriched_name": str,      # 补充完整后的地名
                "city": str,               # 所在城市
                "country": str,            # 所在国家
                "reason": str              # 判断原因
            }
        """
        if not self.llm:
            # Simple check when LLM is unavailable
            return {
                "is_valid": bool(location_name and len(location_name) > 2),
                "enriched_name": location_name,
                "city": "",
                "country": "",
                "reason": "LLM unavailable, using simple rules"
            }
        
        prompt = f"""Analyze whether the following place name is a specific, locatable place on a map.

Place name to verify: "{location_name}"
Query context: "{context}"

Please determine:
1. Whether the place name is a specific location (e.g., "Forbidden City", "Tiananmen", "Peking University")
2. Or an abstract reference (e.g., "the first museum", "nearby cafe", "user's current location")
3. Or a generic category word (e.g., standalone "museum", "restaurant", "hotel")

If it's a specific place, please enrich with complete information based on context (e.g., "Summer Palace" in Beijing context should be "Summer Palace, Beijing").

Return in JSON format (output JSON only, no other content):
{{
    "is_valid": true or false,
    "enriched_name": "enriched place name (if valid) or original (if invalid)",
    "city": "city name (if determinable)",
    "country": "country name (if determinable)",
    "reason": "judgment reason (brief explanation)"
}}

Notes:
- Reference words like "the first XX", "nearby XX", "user location", "current location" are invalid
- Standalone category words like "museum", "cafe", "hotel" are invalid
- Specific place names like "Forbidden City", "Tiananmen Square", "Peking University" are valid
- If it's an English place name and context mentions a Chinese city, should add city name (e.g., "Summer Palace" -> "Summer Palace, Beijing")
"""
        
        try:
            response = self.llm.chat(prompt)
            if response:
                parsed = self.llm.parse_json_response(response)
                if parsed:
                    return parsed
        except Exception as e:
            print(f"      ⚠️ LLM place name validation failed: {e}")
        
        # Default result when LLM fails
        return {
            "is_valid": bool(location_name and len(location_name) > 2),
            "enriched_name": location_name,
            "city": "",
            "country": "",
            "reason": "LLM parsing failed"
        }
    
    def _extract_params_from_description(self, description: str, task_type: str) -> Dict[str, Any]:
        """
        使用 LLM 从任务描述中提取参数（更鲁棒，支持多语言和口语化表达）
        """
        if not self.llm:
            return self._extract_params_regex_fallback(description, task_type)
        
        # 根据任务类型构建提取 prompt
        if task_type == 'spatial_proximity':
            prompt = f"""Extract parameters for spatial proximity query from the task description.
Support both Chinese and English.

Task description: "{description}"

Extract the following parameters and return as JSON (only JSON, no other content):
{{
    "poi_type": "POI type in English (e.g., cafe, restaurant, pharmacy, hotel, hospital, school, supermarket, bank, museum)",
    "reference_location": "reference location name (e.g., 故宫, Forbidden City, Times Square, 北京西站)",
    "radius_meters": search radius in meters, default 500 if not mentioned
}}

Notes:
- poi_type MUST be in English
- "咖啡店/coffee" -> cafe, "餐厅/restaurant" -> restaurant, "药店" -> pharmacy
- "博物馆/museum" -> museum, "酒店/hotel" -> hotel, "银行/bank" -> bank
- reference_location: extract pure location name, no verbs"""
        
        elif task_type == 'poi_search':
            prompt = f"""Extract parameters for regional POI search from the task description.
Support both Chinese and English.

Task description: "{description}"

Extract the following parameters and return as JSON (only JSON, no other content):
{{
    "poi_type": "POI type in English (e.g., hotel, restaurant, museum, cafe, hospital)",
    "search_region": "region/city name (e.g., 柏林, Berlin, 北京, Shanghai)"
}}

Notes:
- poi_type MUST be in English
- "酒店/hotel" -> hotel, "博物馆/museum" -> museum, "餐厅/restaurant" -> restaurant
- search_region: extract the city or region name"""
        
        elif task_type == 'routing':
            prompt = f"""Extract parameters for route planning from the task description.
Support both Chinese and English.

Task description: "{description}"

Extract the following parameters and return as JSON (only JSON, no other content):
{{
    "origin": "origin location name (e.g., 天安门, Tiananmen, Beijing Airport)",
    "destination": "destination location name (e.g., 故宫, Forbidden City, Shanghai Tower)",
    "transport_mode": "transport mode (walking/driving/cycling), default walking"
}}

Notes:
- If origin is unclear, use empty string
- Extract pure location names, no verbs or prepositions
- "步行" -> walking, "骑行/骑车" -> cycling, "驾车/开车" -> driving
- "by foot/walk" -> walking, "by bike" -> cycling, "by car" -> driving"""
        
        elif task_type == 'knowledge':
            prompt = f"""Extract parameters for knowledge graph query from the task description.
Support both Chinese and English.

Task description: "{description}"

There are TWO types of knowledge queries:
1. **Direct entity query**: Query info about a specific named place/entity (e.g., "故宫的历史", "埃菲尔铁塔简介")
2. **Type+location query**: Query entities of a type in a location (e.g., "北京的博物馆", "柏林的酒店")

Extract the following parameters and return as JSON (only JSON, no other content):
{{
    "query_mode": "direct_entity" or "type_location",
    "entity_name": "if direct_entity mode: the specific entity name (e.g., 故宫, Forbidden City, Eiffel Tower)",
    "entity_type": "if type_location mode: entity type in English (e.g., museum, hotel, university)",
    "location_filter": "if type_location mode: location/region name (e.g., 北京, Berlin)"
}}

Examples:
- "查询故宫的历史信息" -> {{"query_mode": "direct_entity", "entity_name": "故宫"}}
- "故宫的历史背景" -> {{"query_mode": "direct_entity", "entity_name": "故宫"}}
- "北京的博物馆" -> {{"query_mode": "type_location", "entity_type": "museum", "location_filter": "北京"}}
- "柏林有哪些酒店" -> {{"query_mode": "type_location", "entity_type": "hotel", "location_filter": "柏林"}}

Notes:
- If the query is about a specific named landmark/place, use direct_entity mode
- "XX的历史/简介/信息" patterns indicate direct_entity mode
- Preserve original entity/location names (Chinese or English)"""
        
        elif task_type == 'osm_data':
            prompt = f"""Extract parameters for OSM data download from the task description.
Support both Chinese and English.

Task description: "{description}"

Extract the following parameters and return as JSON (only JSON, no other content):
{{
    "region": "region name to download (e.g., 北京, Berlin, London, New York)",
    "data_types": ["data types to download, choose from: roads/buildings/waterways/landuse/railways"]
}}

Notes:
- Extract pure region name
- "底图/basemap/基础数据" -> ["roads", "buildings", "waterways"]
- "道路/roads" -> ["roads"], "建筑/buildings" -> ["buildings"]
- Accept both Chinese and English region names"""
        
        elif task_type == 'worldkg':
            prompt = f"""Extract parameters for WorldKG/OSM semantic query from the task description.
Support both Chinese and English.

Task description: "{description}"

Extract the following parameters and return as JSON (only JSON, no other content):
{{
    "entity_type": "entity type in English (e.g., restaurant, hotel, hospital, school, park, bank)",
    "region": "geographic region (e.g., 北京, Berlin, London, Shanghai)"
}}

Notes:
- If description mentions "these hotels/restaurants/etc", infer entity_type from context
- If no explicit region but mentions a city name anywhere, extract it
- For descriptions like "query OSM semantic info of these hotels", entity_type should be "hotel"
- Accept both Chinese and English location names"""
        
        elif task_type == 'remote_sensing_data':
            prompt = f"""Extract parameters for remote sensing/satellite imagery download from the task description.
Support both Chinese and English.

Task description: "{description}"

Extract the following parameters and return as JSON (only JSON, no other content):
{{
    "region": "region name to download (e.g., 北京, Germany, London, 上海)",
    "satellite": "satellite type: sentinel-2 or landsat-8 or landsat-9 (default sentinel-2)",
    "time_range": "time range in format YYYY-MM or YYYY-MM-DD,YYYY-MM-DD",
    "cloud_cover_max": cloud cover percentage (0-100, 0 if user does not mention cloud cover),
    "processing": "processing type: NDVI, NDWI, RGB, or empty for raw bands"
}}

Notes:
- "卫星影像/satellite imagery/遥感数据" -> extract region and time
- "Sentinel" -> satellite="sentinel-2", "Landsat" -> satellite="landsat-8"
- If time is not specified, use current year-month
- "NDVI/植被指数" -> processing="NDVI", "NDWI/水体指数" -> processing="NDWI"
- Accept both Chinese and English region names"""
        
        elif task_type == 'semantic_analysis':
            prompt = f"""Extract parameters for semantic analysis / facility type analysis from the task description.
Support both Chinese and English.

Task description: "{description}"

Extract the following parameters and return as JSON (only JSON, no other content):
{{
    "region": "region/landmark name to analyze (e.g., 故宫, 清华大学, Berlin, Times Square)",
    "osm_region": "same as region, the area to analyze"
}}

Notes:
- "分析XX内的设施类型" -> region=XX
- "统计XX的设施分布" -> region=XX
- Extract pure location/landmark name
- Accept both Chinese and English location names"""
        
        else:
            return {}
        
        try:
            response = self.llm.chat(prompt)
            if response:
                parsed = self.llm.parse_json_response(response)
                if parsed:
                    return parsed
        except Exception as e:
            print(f"      LLM parameter extraction failed: {e}")
        
        # LLM 失败时回退到正则方法
        return self._extract_params_regex_fallback(description, task_type)
    
    def _extract_params_regex_fallback(self, description: str, task_type: str) -> Dict[str, Any]:
        """
        正则表达式备用方案（当 LLM 不可用时）
        """
        params = {}
        
        if task_type == 'spatial_proximity':
            # 简单的 POI 类型映射
            poi_mapping = {
                '咖啡': 'cafe', 'coffee': 'cafe', 'cafe': 'cafe',
                '餐厅': 'restaurant', 'restaurant': 'restaurant',
                '酒店': 'hotel', 'hotel': 'hotel',
                '药店': 'pharmacy', 'pharmacy': 'pharmacy',
                '医院': 'hospital', 'hospital': 'hospital',
                '学校': 'school', 'school': 'school',
                '超市': 'supermarket', 'supermarket': 'supermarket',
            }
            desc_lower = description.lower()
            for keyword, poi_type in poi_mapping.items():
                if keyword in desc_lower:
                    params['poi_type'] = poi_type
                    break
            
            # 简单的位置提取
            import re
            # 中文: X附近
            match = re.search(r'([^\s，,查找搜索在]+?)(?:附近|周围|旁边)', description)
            if match:
                params['reference_location'] = match.group(1).strip()
            # 英文: near X
            match = re.search(r'near\s+([A-Za-z\s]+?)(?:\s|,|$)', description, re.IGNORECASE)
            if match:
                params['reference_location'] = match.group(1).strip()
        
        elif task_type == 'routing':
            import re
            # 中文: 从A到B
            match = re.search(r'从([^\s，,到]+)到([^\s，,]+)', description)
            if match:
                params['origin'] = match.group(1)
                params['destination'] = match.group(2)
            # 英文: from A to B
            match = re.search(r'from\s+(.+?)\s+to\s+(.+?)(?:\s|,|$)', description, re.IGNORECASE)
            if match:
                params['origin'] = match.group(1).strip()
                params['destination'] = match.group(2).strip()
            
            # 交通方式
            if any(w in description.lower() for w in ['步行', 'walk', 'foot', 'walking']):
                params['transport_mode'] = 'walking'
            elif any(w in description.lower() for w in ['驾车', 'drive', 'car', 'driving']):
                params['transport_mode'] = 'driving'
            elif any(w in description.lower() for w in ['骑', 'bike', 'cycling', 'bicycle']):
                params['transport_mode'] = 'cycling'
        
        return params
    
    def _handle_hybrid_query(self, intent: IntentAnalysis, 
                              result: UnifiedQueryResult, top_k: int):
        """处理混合查询"""
        print("\nExecuting hybrid query...")
        
        # 先执行本地数据搜索
        self._handle_local_data_query(intent, result, top_k)
        
        # 如果有 POI 相关意图，同时执行 OSM 查询
        if intent.poi_type:
            self._handle_proximity_query(intent, result)
        
        # 如果有知识查询意图，查询 Wikidata
        if intent.entity_type:
            self._handle_knowledge_query(intent, result)
    
    # -------------------------------------------------------------------------
    # 数据下载 (保存为 GeoJSON，方便 QGIS 分析)
    # -------------------------------------------------------------------------
    
    def download_results(self, result: UnifiedQueryResult, output_dir: str = None) -> List[str]:
        """
        将查询结果下载为本地 GeoJSON 文件，方便在 QGIS 中进行分析
        
        Args:
            result: 查询结果
            output_dir: 输出目录，默认使用 self.output_dir
            
        Returns:
            保存的文件路径列表
        """
        output_dir = output_dir or self.output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        saved_files = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 从意图中提取关键信息用于命名
        intent = result.intent
        
        # 1. 保存 POI 结果
        if result.poi_results:
            # 提取 POI 类型和位置作为文件名
            poi_type = intent.poi_type or result.poi_results[0].poi_type if result.poi_results else "poi"
            location = (intent.reference_location or intent.search_region or 
                       intent.location_filter or intent.target_region or 
                       self._extract_location_from_query(result.query))
            location = self._sanitize_filename(location)
            filename = f"{poi_type}_{location}_{timestamp}"
            poi_file = self._save_poi_to_geojson(result.poi_results, output_dir, filename)
            if poi_file:
                saved_files.append(poi_file)
        
        # 2. 保存路由结果
        if result.route_result:
            # 提取起点和终点作为文件名
            origin = self._sanitize_filename(intent.origin or "start")
            dest = self._sanitize_filename(intent.destination or "end")
            mode = intent.transport_mode or "route"
            filename = f"route_{origin}_to_{dest}_{mode}_{timestamp}"
            route_file = self._save_route_to_geojson(result.route_result, output_dir, filename)
            if route_file:
                saved_files.append(route_file)
        
        # 3. 保存 Wikidata 实体结果
        if result.knowledge_results:
            # 提取实体类型和位置作为文件名
            entity_type = intent.entity_type or intent.facility_type or "entity"
            location = self._sanitize_filename(intent.location_filter or "global")
            filename = f"{entity_type}_{location}_{timestamp}"
            knowledge_file = self._save_knowledge_to_geojson(result.knowledge_results, output_dir, filename)
            if knowledge_file:
                saved_files.append(knowledge_file)
        
        return saved_files
    
    def _infer_region_from_context(self, entity_name: str, task_desc: str) -> str:
        """从上下文推断区域（使用 LLM）"""
        if not self.llm:
            return ""
        
        prompt = f"""Based on the following context, infer the geographic region (city/country).
Only output the region name, nothing else. If no region can be inferred, output empty string.

Entity name: "{entity_name}"
Task description: "{task_desc}"

Region:"""
        try:
            response = self.llm.chat(prompt)
            if response:
                region = response.strip().strip('"').strip("'")
                if region and region.lower() not in ['none', 'null', '', 'n/a', 'unknown']:
                    return region
        except Exception:
            pass
        return ""
    
    def _extract_location_from_query(self, query: str) -> str:
        """从查询文本中提取位置信息（使用 LLM）"""
        if not self.llm or not query:
            return "region"  # 比 unknown 更有意义的默认值
        
        prompt = f"""Extract the geographic location (city/region/country) from the following query.
Only output the location name, nothing else. If no clear location, output "region".

Query: "{query}"
Location:"""
        try:
            response = self.llm.chat(prompt)
            if response:
                location = response.strip().strip('"').strip("'")
                # 过滤掉无效响应
                if location and location.lower() not in ['none', 'null', '无', '未知', 'n/a', 'region']:
                    return location
        except Exception:
            pass
        return "region"
    
    def _sanitize_filename(self, name: str, max_length: int = 20) -> str:
        """清理字符串使其适合作为文件名"""
        if not name:
            return "region"  # 比 unknown 更有意义的默认值
        # 移除或替换不安全的字符
        import re
        # 只保留字母、数字、中文和下划线
        safe_name = re.sub(r'[^\w\u4e00-\u9fff]', '_', name)
        # 移除连续的下划线
        safe_name = re.sub(r'_+', '_', safe_name)
        # 截断长度
        return safe_name[:max_length].strip('_')
    
    def _save_poi_to_geojson(self, poi_results: List[POIResult], 
                             output_dir: str, filename: str) -> Optional[str]:
        """将 POI 结果保存为 GeoJSON"""
        if not poi_results:
            return None
        
        features = []
        for poi in poi_results:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [poi.lon, poi.lat]
                },
                "properties": {
                    "osm_id": poi.osm_id,
                    "name": poi.name,
                    "poi_type": poi.poi_type,
                    "distance_meters": poi.distance_meters,
                    "address": poi.address,
                    **poi.tags
                }
            }
            features.append(feature)
        
        geojson = {
            "type": "FeatureCollection",
            "name": filename,
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
            },
            "features": features
        }
        
        output_file = os.path.join(output_dir, f"{filename}.geojson")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)
        
        print(f"   📥 POI data saved: {output_file} ({len(features)} features)")
        return output_file
    
    def _save_route_to_geojson(self, route: RouteResult, 
                               output_dir: str, filename: str) -> Optional[str]:
        """将路由结果保存为 GeoJSON (LineString)"""
        if not route or not route.geometry:
            return None
        
        # 路由几何
        route_feature = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": route.geometry
            },
            "properties": {
                "origin": route.origin,
                "destination": route.destination,
                "distance_meters": route.distance_meters,
                "duration_seconds": route.duration_seconds,
                "duration_minutes": round(route.duration_seconds / 60, 1),
                "transport_mode": route.transport_mode
            }
        }
        
        features = [route_feature]
        
        # 添加起点和终点标记
        if route.geometry:
            start_coords = route.geometry[0]
            end_coords = route.geometry[-1]
            
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": start_coords},
                "properties": {"type": "origin", "name": route.origin[:50]}
            })
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": end_coords},
                "properties": {"type": "destination", "name": route.destination[:50]}
            })
        
        geojson = {
            "type": "FeatureCollection",
            "name": filename,
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
            },
            "features": features
        }
        
        output_file = os.path.join(output_dir, f"{filename}.geojson")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)
        
        distance_km = route.distance_meters / 1000
        print(f"   Route data saved: {output_file} ({distance_km:.1f}km)")
        return output_file
    
    def _save_knowledge_to_geojson(self, entities: List[WikidataEntity], 
                                    output_dir: str, filename: str) -> Optional[str]:
        """将 Wikidata 实体保存为 GeoJSON"""
        if not entities:
            return None
        
        features = []
        for entity in entities:
            # 只有有坐标的实体才能保存为地理要素
            if entity.lat is not None and entity.lon is not None:
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [entity.lon, entity.lat]
                    },
                    "properties": {
                        "wikidata_id": entity.wikidata_id,
                        "name": entity.name,
                        "name_en": entity.name_en,
                        "entity_type": entity.entity_type,
                        "description": entity.description,
                        "wikipedia_url": entity.wikipedia_url,
                        **entity.properties
                    }
                }
                features.append(feature)
        
        if not features:
            print(f"   Wikidata results contain no entities with coordinates")
            return None
        
        geojson = {
            "type": "FeatureCollection",
            "name": filename,
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
            },
            "features": features
        }
        
        output_file = os.path.join(output_dir, f"{filename}.geojson")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)
        
        print(f"   Knowledge graph data saved: {output_file} ({len(features)} features)")
        return output_file
    
    # -------------------------------------------------------------------------
    # 结果格式化
    # -------------------------------------------------------------------------
    
    def format_result(self, result: UnifiedQueryResult) -> str:
        """格式化查询结果"""
        lines = []
        
        lines.append(f"\n{'='*58}")
        lines.append(f"Query results")
        lines.append(f"{'='*58}")
        
        # 意图信息
        lines.append(f"\nQuery: {result.query}")
        lines.append(f"Intent: {result.intent.intent.value} (confidence: {result.intent.confidence:.0%})")
        lines.append(f"Summary: {result.intent.summary}")
        lines.append(f"Data source: {result.source}")
        lines.append(f"Processing time: {result.processing_time_ms}ms")
        
        # 警告信息
        if result.warnings:
            lines.append(f"\nWarnings:")
            for warning in result.warnings:
                lines.append(f"   - {warning}")
        
        # 建议信息
        if result.suggestions:
            lines.append(f"\nSuggestions:")
            for suggestion in result.suggestions:
                lines.append(f"   - {suggestion}")
        
        # 本地数据结果
        if result.local_results:
            lines.append(f"\nLocal data results ({len(result.local_results)} items):")
            lines.append("-" * 50)
            for i, r in enumerate(result.local_results[:5], 1):
                # 🔧 修复：支持字典和对象两种格式
                if isinstance(r, dict):
                    name = r.get('name', 'Unknown')
                    file = r.get('file', '')
                    score = r.get('score', 0.0)
                    recommendation = r.get('recommendation', '')
                else:
                    name = r.name
                    file = r.file
                    score = r.score
                    recommendation = r.recommendation if hasattr(r, 'recommendation') else ''
                
                lines.append(f"  [{i}] {name}")
                lines.append(f"      File: {file}")
                lines.append(f"      Score: {score:.2%}")
                if recommendation:
                    lines.append(f"      Recommendation: {recommendation}")
        
        # 裁剪结果
        if result.clip_results:
            success = [c for c in result.clip_results if c.success]
            lines.append(f"\nClipping results ({len(success)}/{len(result.clip_results)} successful):")
            for c in success[:3]:
                lines.append(f"   ✓ {Path(c.clipped_file).name}")
        
        # POI 结果
        if result.poi_results:
            lines.append(f"\nPOI results ({len(result.poi_results)} items):")
            lines.append("-" * 50)
            for i, poi in enumerate(result.poi_results[:10], 1):
                lines.append(f"  [{i}] {poi.name}")
                lines.append(f"      Type: {poi.poi_type}")
                # 只有在空间邻近查询时（距离 > 0）才显示距离
                if poi.distance_meters > 0:
                    lines.append(f"      Distance: {poi.distance_meters:.0f}m")
                lines.append(f"      Coordinates: ({poi.lat:.6f}, {poi.lon:.6f})")
                if poi.address:
                    lines.append(f"      Address: {poi.address}")
        
        # 路由结果
        if result.route_result:
            route = result.route_result
            lines.append(f"\nRoute results:")
            lines.append("-" * 50)
            lines.append(f"  Start: {route.origin[:60]}...")
            lines.append(f"  End: {route.destination[:60]}...")
            lines.append(f"  Transportation mode: {route.transport_mode}")
            lines.append(f"  Distance: {route.distance_meters/1000:.2f} km")
            lines.append(f"  Estimated time: {route.duration_seconds/60:.0f} minutes")
            
            if route.steps:
                lines.append(f"\n Detailed navigation steps:")
                step_count = 0
                max_steps = 15  # 显示更多步骤
                
                for step in route.steps:
                    if step_count >= max_steps:
                        remaining = len(route.steps) - step_count
                        if remaining > 0:
                            lines.append(f"    ... and {remaining} more steps")
                        break
                    
                    instruction = step.get('instruction', '')
                    dist = step.get('distance', 0)
                    duration = step.get('duration', 0)
                    step_type = step.get('type', '')
                    action = step.get('action', '')
                    
                    # 跳过到达步骤和距离太短的无名步骤
                    if step_type == 'arrive' or action == 'arrive':
                        continue
                    if dist < 5 and not instruction:
                        continue
                    
                    # 格式化距离和时间
                    if dist >= 1000:
                        dist_str = f"{dist/1000:.1f}km"
                    else:
                        dist_str = f"{dist:.0f}m"
                    
                    # 格式化时间
                    if duration >= 60:
                        time_str = f"about {duration/60:.0f} minutes"
                    else:
                        time_str = f"about {duration:.0f} seconds"
                    
                    step_count += 1
                    lines.append(f"    {step_count}. {instruction}")
                    lines.append(f"       ↳ Driving {dist_str} ({time_str})")
        
        # Wikidata 知识图谱结果
        if result.knowledge_results:
            lines.append(f"\nKnowledge graph results ({len(result.knowledge_results)} items):")
            lines.append("-" * 50)
            for i, entity in enumerate(result.knowledge_results[:10], 1):
                lines.append(f"  [{i}] {entity.name}")
                if entity.description:
                    lines.append(f"      Description: {entity.description[:50]}...")
                if entity.lat and entity.lon:
                    lines.append(f"      Coordinates: ({entity.lat:.6f}, {entity.lon:.6f})")
                if entity.wikipedia_url:
                    lines.append(f"      Link: {entity.wikipedia_url}")
                if entity.properties:
                    props = ", ".join(f"{k}: {v}" for k, v in entity.properties.items() if v)
                    if props:
                        lines.append(f"      Properties: {props}")
        
        # 🆕 遥感数据结果
        if result.remote_sensing_data:
            lines.append(f"\nRemote sensing data:")
            lines.append("-" * 50)
            filepath = Path(result.remote_sensing_data)
            lines.append(f"   📁 File: {filepath.name}")
            lines.append(f"   📂 Path: {result.remote_sensing_data}")
            if filepath.exists():
                size_mb = filepath.stat().st_size / (1024 * 1024)
                lines.append(f"   Size: {size_mb:.2f} MB")
            if result.message:
                lines.append(f"   {result.message}")
        
        # 复杂查询子任务结果 (显示详细内容)
        if result.sub_task_results:
            lines.append(f"\nSub-task execution details:")
            lines.append("-" * 50)
            for task in result.sub_task_results:
                # 判断任务状态：成功(有结果) / 警告(无结果) / 失败(有错误)
                has_result = task.result and (
                    (isinstance(task.result, list) and len(task.result) > 0) or
                    (hasattr(task.result, 'distance_meters') and task.result.distance_meters > 0) or
                    (isinstance(task.result, dict) and task.result)
                )
                if not task.success or task.error:
                    status = "✗"  # 失败
                elif has_result:
                    status = "✓"  # 成功有结果
                else:
                    status = "⚠️"  # 执行了但无结果
                
                lines.append(f"  {status} [{task.task_id}] {task.description}")
                
                if task.error:
                    lines.append(f"      ❌ Error: {task.error}")
                
                # 显示任务结果详情
                elif task.result:
                    if task.task_type == 'spatial_proximity' and isinstance(task.result, list):
                        lines.append(f"      Found {len(task.result)} POI")
                        for poi in task.result[:3]:
                            if hasattr(poi, 'name'):
                                lines.append(f"         - {poi.name} ({poi.distance_meters:.0f}m)")
                    
                    elif task.task_type == 'routing' and hasattr(task.result, 'distance_meters'):
                        route = task.result
                        lines.append(f"      Route: {route.distance_meters/1000:.1f}km, "
                                   f"about {route.duration_seconds/60:.0f} minutes")
                    
                    elif task.task_type == 'knowledge' and isinstance(task.result, list):
                        lines.append(f"      Found {len(task.result)} entities")
                        for entity in task.result[:3]:
                            if hasattr(entity, 'name'):
                                lines.append(f"         - {entity.name}")
                    
                    elif task.task_type == 'osm_data' and isinstance(task.result, list):
                        lines.append(f"      Downloaded {len(task.result)} files:")
                        for f in task.result:
                            lines.append(f"         - {os.path.basename(f)}")
                    
                    elif task.task_type == 'worldkg' and isinstance(task.result, list):
                        lines.append(f"      Found {len(task.result)} WorldKG entities")
                        for entity in task.result[:3]:
                            if hasattr(entity, 'name'):
                                lines.append(f"         - {entity.name}")
                    
                    elif task.task_type == 'remote_sensing_data' and task.result:
                        lines.append(f"      Remote sensing data download:")
                        # 支持字符串路径和字典格式的结果
                        if isinstance(task.result, str):
                            lines.append(f"         📁 {os.path.basename(task.result)}")
                        elif isinstance(task.result, dict) and 'local_file' in task.result:
                            lines.append(f"         📁 {os.path.basename(task.result['local_file'])} (local)")
                        else:
                            lines.append(f"         📁 {task.result}")
                    
                    elif task.task_type == 'geocode' and isinstance(task.result, dict):
                        lines.append(f"      Coordinates: ({task.result.get('lat', 0):.4f}, {task.result.get('lon', 0):.4f})")
        
        # OSM 数据下载结果 (非下载模式下也显示)
        if result.downloaded_files:
            lines.append(f"\nDownloaded files ({len(result.downloaded_files)} items):")
            lines.append("-" * 50)
            for f in result.downloaded_files:
                lines.append(f"   ✓ {f}")
        
        # 显示消息
        if result.message:
            lines.append(f"\n{result.message}")
        
        lines.append(f"\n{'='*58}")
        
        return '\n'.join(lines)
    
    def to_json(self, result: UnifiedQueryResult) -> str:
        """输出 JSON 格式结果"""
        output = {
            'query': result.query,
            'intent': {
                'type': result.intent.intent.value,
                'confidence': result.intent.confidence,
                'summary': result.intent.summary,
                'reasoning': result.intent.reasoning
            },
            'source': result.source,
            'timestamp': result.timestamp,
            'processing_time_ms': result.processing_time_ms,
            'warnings': result.warnings,
            'suggestions': result.suggestions,
            'local_results': [
                {
                    'id': r.id,
                    'name': r.name,
                    'file': r.file,
                    'score': r.score,
                    'recommendation': r.recommendation
                }
                for r in result.local_results
            ],
            'poi_results': [
                {
                    'osm_id': p.osm_id,
                    'name': p.name,
                    'poi_type': p.poi_type,
                    'lat': p.lat,
                    'lon': p.lon,
                    'distance_meters': p.distance_meters,
                    'address': p.address
                }
                for p in result.poi_results
            ],
            'knowledge_results': [
                {
                    'wikidata_id': e.wikidata_id,
                    'name': e.name,
                    'entity_type': e.entity_type,
                    'description': e.description,
                    'lat': e.lat,
                    'lon': e.lon,
                    'wikipedia_url': e.wikipedia_url,
                    'properties': e.properties
                }
                for e in result.knowledge_results
            ],
            'sub_task_results': [
                {
                    'task_id': t.task_id,
                    'task_type': t.task_type,
                    'description': t.description,
                    'success': t.success,
                    'error': t.error
                }
                for t in result.sub_task_results
            ],
            'route_result': None
        }
        
        if result.route_result:
            r = result.route_result
            output['route_result'] = {
                'origin': r.origin,
                'destination': r.destination,
                'distance_meters': r.distance_meters,
                'duration_seconds': r.duration_seconds,
                'transport_mode': r.transport_mode,
                'steps_count': len(r.steps)
            }
        
        return json.dumps(output, ensure_ascii=False, indent=2)


# ============================================================================
# 命令行接口
# ============================================================================

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='统一地理查询引擎 - 集成本地数据 + OSM + Wikidata',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例查询:
  本地数据:    "欧洲中部的河流数据"
  空间邻近:    "北京西单500米内的咖啡店"
  路由导航:    "从天安门到故宫的步行路线"
  推荐查询:    "推荐上海市中心的四星级酒店"
  知识查询:    "北京有哪些博物馆"
  复杂查询:    "找出故宫附近的咖啡店，并规划步行路线"
        """
    )
    
    parser.add_argument('query', nargs='?', default=None, help='查询文本')
    parser.add_argument('--catalog', '-c', 
                        default='data_catalog.json',
                        help='本地数据目录文件路径')
    parser.add_argument('--top-k', '-k', type=int, default=5, 
                        help='返回结果数量')
    parser.add_argument('--no-llm', action='store_true',
                        help='禁用 LLM 意图识别')
    parser.add_argument('--json', '-j', action='store_true',
                        help='以 JSON 格式输出')
    parser.add_argument('--download', '-d', action='store_true',
                        help='下载结果为 GeoJSON 文件 (方便 QGIS 分析)')
    parser.add_argument('--output', '-o', default='downloaded_data',
                        help='下载输出目录 (默认: downloaded_data)')
    
    args = parser.parse_args()
    
    # 检查本地数据目录是否存在
    catalog_path = args.catalog
    if not Path(catalog_path).exists():
        catalog_path = None
        print("Warning: Local data directory does not exist, only using OSM online query")
    
    # 初始化引擎
    engine = GeoQueryEngine(
        catalog_path=catalog_path,
        output_dir=args.output,
        use_llm=not args.no_llm
    )
    
    # 如果没有提供查询，进入交互模式
    if args.query is None:
        print("\nGeographic query engine")
        print("=" * 38)
        print("Supported query types:")
        print("  1. Local data: 'River data in the middle of Europe'")
        print("  2. Spatial proximity: 'Coffee shops within 500 meters of Xidan in Beijing'")
        print("  3. Routing: 'Walking route from Tiananmen to the Forbidden City'")
        print("  4. Recommendation query: 'Recommend a four-star hotel in the center of Shanghai' (Wikidata + OSM)")
        print("  5. Knowledge query: 'What museums are in Beijing' (Wikidata)")
        print("  6. Complex query: 'Find coffee shops near the Forbidden City and plan a walking route'")
        print("\nEnter 'quit' or 'q' to exit\n")
        
        while True:
            try:
                query = input("Enter query: ").strip()
                if query.lower() in ['quit', 'q', 'exit']:
                    print("Goodbye!")
                    break
                if not query:
                    continue
                
                result = engine.query(query, top_k=args.top_k)
                
                if args.json:
                    print(engine.to_json(result))
                else:
                    print(engine.format_result(result))
                
                # 下载结果
                if args.download:
                    saved_files = engine.download_results(result)
                    if saved_files:
                        print(f"\n✅ Downloaded {len(saved_files)} files to {args.output}/")
                
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
    else:
        # 命令行模式
        result = engine.query(args.query, top_k=args.top_k)
        
        if args.json:
            print(engine.to_json(result))
        else:
            print(engine.format_result(result))
        
        # 下载结果
        if args.download:
            print("\nDownloading data...")
            saved_files = engine.download_results(result)
            if saved_files:
                print(f"\n✅ Downloaded {len(saved_files)} files:")
                for f in saved_files:
                    print(f"   - {f}")
                print(f"\nNote: These GeoJSON files can be opened in QGIS for analysis")


if __name__ == '__main__':
    main()
