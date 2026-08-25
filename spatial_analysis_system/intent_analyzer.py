# -*- coding: utf-8 -*-
"""
Intent Analyzer Module

Analyzes user input spatial analysis requirements and determines task type:
- Data download task: only needs to download data
- Data download + code generation task: needs to download data and generate QGIS spatial analysis code
"""

import json
import re
from enum import Enum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .llm_client import LLMClient
from .config import Config, get_config


class TaskType(Enum):
    """Task type enumeration"""
    DATA_DOWNLOAD_ONLY = "data_download_only"       # Data download only
    DATA_AND_CODE = "data_and_code"                 # Data download + code generation
    CODE_ONLY = "code_only"                         # Code generation only (data exists)
    UNKNOWN = "unknown"                             # Unknown type


@dataclass
class DataRequirement:
    """Data requirement description"""
    data_type: str = ""              # Data type: raster, vector, osm, remote_sensing, poi
    region: str = ""                 # Region
    time_range: str = ""             # Time range
    satellite: str = ""              # Satellite type (for remote sensing data)
    osm_types: List[str] = field(default_factory=list)  # OSM data types
    description: str = ""            # Data description
    local_path: str = ""             # Local path (if data already exists)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "data_type": self.data_type,
            "region": self.region,
            "time_range": self.time_range,
            "satellite": self.satellite,
            "osm_types": self.osm_types,
            "description": self.description,
            "local_path": self.local_path,
        }


@dataclass
class AnalysisRequirement:
    """Analysis requirement description"""
    analysis_type: str = ""          # Analysis type: buffer, clip, intersection, etc.
    description: str = ""            # Analysis description
    parameters: Dict[str, Any] = field(default_factory=dict)  # Analysis parameters
    expected_output: str = ""        # Expected output description
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "analysis_type": self.analysis_type,
            "description": self.description,
            "parameters": self.parameters,
            "expected_output": self.expected_output,
        }


@dataclass
class RouteInfo:
    """Route planning information"""
    origin: str = ""                    # Origin
    destination: str = ""               # Destination
    waypoints: List[str] = field(default_factory=list)  # Waypoints
    mode: str = "driving"               # Travel mode: driving, walking, cycling
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "waypoints": self.waypoints,
            "mode": self.mode,
        }


@dataclass
class TaskIntent:
    """Task intent"""
    task_type: TaskType = TaskType.UNKNOWN
    original_query: str = ""                      # Original user query
    summary: str = ""                             # Task summary
    data_requirements: List[DataRequirement] = field(default_factory=list)
    analysis_requirements: List[AnalysisRequirement] = field(default_factory=list)
    route_info: Optional[RouteInfo] = None        # Route planning info
    confidence: float = 0.0                       # Confidence (0-1)
    reasoning: str = ""                           # Reasoning explanation
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_type": self.task_type.value,
            "original_query": self.original_query,
            "summary": self.summary,
            "data_requirements": [d.to_dict() for d in self.data_requirements],
            "analysis_requirements": [a.to_dict() for a in self.analysis_requirements],
            "route_info": self.route_info.to_dict() if self.route_info else None,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }
    
    def is_data_only(self) -> bool:
        """Whether only data download is needed (including route planning)"""
        return self.task_type == TaskType.DATA_DOWNLOAD_ONLY
    
    def needs_code_generation(self) -> bool:
        """Whether code generation is needed"""
        return self.task_type in [TaskType.DATA_AND_CODE, TaskType.CODE_ONLY]
    
    def needs_data_download(self) -> bool:
        """Whether data download is needed"""
        return self.task_type in [TaskType.DATA_DOWNLOAD_ONLY, TaskType.DATA_AND_CODE]


class IntentAnalyzer:
    """
    Intent Analyzer
    
    Uses LLM to analyze user input spatial analysis requirements, determine task type and extract key information.
    """
    
    SYSTEM_PROMPT = """You are a professional GIS spatial analysis task expert. Your task is to analyze user input spatial analysis requirements and determine if this is:
1. **Data download task** (data_download_only): User only needs to get/download data, no spatial analysis processing or visualization needed
2. **Data + code task** (data_and_code): User needs to get data first, then perform spatial analysis processing or load/display in QGIS
3. **Code only task** (code_only): User already has data, only needs to generate spatial analysis code

Judgment criteria:
- If user only says "download XX data", "get XX imagery", "query XX info", **without mentioning load, display, visualization needs**, this is a data download task
- If user needs spatial operations (like buffer, clip, overlay, statistics, convert, calculate NDVI, etc.), this is a data + code task
- **If user mentions "load", "display", "visualize", "show", "open", "on the map", etc., even if just downloading data, it should be identified as data + code task**, because QGIS code is needed to load data into GUI
- If user mentions specific local file paths and requests analysis, this is a code only task

Please return analysis results strictly in JSON format."""

    ANALYSIS_PROMPT_TEMPLATE = """Please analyze the following user requirement, determine task type and extract key information:

User requirement:
{query}

Please return results in the following JSON format:
```json
{{{{
    "task_type": "data_download_only" | "data_and_code" | "code_only",
    "summary": "Task summary description",
    "data_requirements": [
        {{{{
            "data_type": "vector" | "raster" | "osm" | "remote_sensing" | "poi",
            "region": "Region name",
            "time_range": "Time range (e.g., 2024-01)",
            "satellite": "Satellite type (e.g., sentinel-2, landsat-8)",
            "osm_types": ["roads", "buildings", "boundary"],
            "description": "Data description"
        }}}}
    ],
    "analysis_requirements": [
        {{{{
            "analysis_type": "buffer" | "clip" | "intersection" | "dissolve" | "raster_calc" | "statistics" | "load" | "visualize" | "other",
            "description": "Analysis description",
            "parameters": {{{{"distance": 1000}}}},
            "expected_output": "Expected output description"
        }}}}
    ],
    "route_info": {{{{
        "origin": "Origin name or coordinates",
        "destination": "Destination name or coordinates",
        "waypoints": ["waypoint1", "waypoint2"],
        "mode": "driving" | "walking" | "cycling"
    }}}},
    "confidence": 0.95,
    "reasoning": "Reasoning explanation"
}}}}
```

Notes:
1. If it's a pure data download task, analysis_requirements should be an empty array
2. If user mentions specific spatial analysis operations (buffer, overlay, clip, raster calculation, NDVI, etc.), it's data_and_code type
3. **If user mentions "load", "display", "visualize", "view on map", etc., it should be identified as data_and_code type, and add a "load" type analysis requirement in analysis_requirements**
4. confidence is your confidence in the judgment (0-1)
5. Carefully analyze user intent, distinguish between "getting data" and "analyzing/visualizing data"
6. When user says "download XX remote sensing imagery and set buffer", buffer operation should apply to **the study area boundary vector data**, not the raster imagery itself
7. **⚠️ Important: downloading boundaries of multiple independent geographic entities must be split into multiple independent data requirements**
   - If user says "download boundaries of A and B", must split into two independent data requirements:
     * Data requirement 1: region="A", data_type="osm", osm_types=["boundary"]
     * Data requirement 2: region="B", data_type="osm", osm_types=["boundary"]
   - Do not merge multiple geographic entities into one region field (e.g., "region": "A, B" is wrong)
   - Each geographic entity should be an independent data requirement
   **⚠️ Also important: downloading multiple different data types for the same region must also be split into multiple independent data requirements**
   - If user says "download boundary and road data of A", must split into two independent data requirements:
     * Data requirement 1: region="A", data_type="osm", osm_types=["boundary"]
     * Data requirement 2: region="A", data_type="osm", osm_types=["roads"]
   - Each different osm_type (boundary, roads, buildings, etc.) should be an independent data requirement
   - Do not merge multiple osm_types into one data requirement (e.g., osm_types=["boundary", "roads"] in a single requirement is wrong)
8. **⚠️ Route planning task: if user needs to calculate route/navigation/shortest path, set task_type to "data_download_only" and fill in route_info**
   - Extract origin, destination, waypoints, and mode
   - route_info field only needs to be filled for route planning tasks, set to null for other tasks

Examples:
- "Download Beijing road data" → data_download_only (download only, no load)
- "Download Beijing road data and load it" → data_and_code (need to generate code to load into QGIS GUI)
- "Download Beijing road data and display on map" → data_and_code (need to generate code for visualization)
- "Add buffer to Beijing hotels" → data_and_code (need spatial analysis)
- "Route from Tiananmen to Summer Palace" → data_download_only, route_info: {{origin: "Tiananmen", destination: "Summer Palace", mode: "driving"}}
- "Route from Peking University to Tsinghua University" → data_download_only, route_info: {{origin: "Peking University", destination: "Tsinghua University", mode: "walking"}}
- "Download Tsinghua University sentinel imagery and set buffer to 200 meters" → data_and_code, data requirements include: 1) remote_sensing imagery, 2) Tsinghua University boundary; analysis requirement: buffer on boundary
- "Download vector boundaries of Tsinghua University and Yuanmingyuan, set their buffer to 200 meters, show intersection area" → data_and_code
  * Data requirement 1: region="Tsinghua University", data_type="osm", osm_types=["boundary"]
  * Data requirement 2: region="Yuanmingyuan", data_type="osm", osm_types=["boundary"]
  * Analysis requirement: buffer(200m) + intersection
- "Download administrative boundary and road data from Stanford University" → data_download_only
  * Data requirement 1: region="Stanford University", data_type="osm", osm_types=["boundary"]
  * Data requirement 2: region="Stanford University", data_type="osm", osm_types=["roads"]"""

    def __init__(self, config: Optional[Config] = None, llm_client: Optional[LLMClient] = None):
        """
        Initialize intent analyzer
        
        Args:
            config: Configuration object
            llm_client: LLM client, creates new one if None
        """
        self.config = config or get_config()
        self.llm_client = llm_client or LLMClient(self.config)
    
    def analyze(self, query: str) -> TaskIntent:
        """
        Analyze user query
        
        Args:
            query: User's requirement description
        
        Returns:
            TaskIntent: Analyzed task intent
        """
        print(f"\n{'='*60}")
        print(f"Intent Analysis")
        print(f"{'='*60}")
        print(f"User requirement: {query}")
        
        # First do rule-based quick matching
        quick_result = self._quick_analyze(query)
        if quick_result is not None and quick_result.confidence >= 0.9:
            print(f"✓ Rule-based quick match: {quick_result.task_type.value}")
            print(f"  Confidence: {quick_result.confidence:.2f}")
            return quick_result
        
        # Use LLM for deep analysis
        prompt = self.ANALYSIS_PROMPT_TEMPLATE.format(query=query)
        
        response_text, token_stats = self.llm_client.chat(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.1  # Use low temperature for more deterministic results
        )
        
        if response_text is None:
            print("❌ LLM analysis failed, using rule-based result")
            if quick_result:
                return quick_result
            return TaskIntent(
                task_type=TaskType.UNKNOWN,
                original_query=query,
                confidence=0.0,
                reasoning="LLM analysis failed"
            )
        
        # Parse LLM response
        intent = self._parse_llm_response(response_text, query)
        
        print(f"✓ LLM analysis complete: {intent.task_type.value}")
        print(f"  Confidence: {intent.confidence:.2f}")
        print(f"  Data requirements: {len(intent.data_requirements)} items")
        print(f"  Analysis requirements: {len(intent.analysis_requirements)} items")
        print(f"  Token usage: input={token_stats['input_tokens']}, output={token_stats['output_tokens']}")
        
        return intent
    
    def _quick_analyze(self, query: str) -> Optional[TaskIntent]:
        """
        Rule-based quick analysis
        
        Args:
            query: User query
        
        Returns:
            TaskIntent or None (if cannot determine)
        """
        query_lower = query.lower()
        
        # Data download keywords
        download_keywords = [
            "download", "get", "fetch", "query", "search", "data",
        ]
        
        # Spatial analysis keywords
        analysis_keywords = [
            "buffer", "clip", "intersect", "dissolve", "merge",
            "raster calc", "ndvi", "statistics", "analysis", "process", "convert",
            "distance", "area", "slope", "aspect", "contour",
            "resample", "reproject", "vectorize", "rasterize", "interpolate",
            "density", "heatmap", "cluster", "classify", "extract",
        ]
        
        # Check if analysis keywords present
        has_analysis = any(kw in query_lower for kw in analysis_keywords)
        
        # Check if only download keywords
        has_download_only = any(kw in query_lower for kw in download_keywords)
        
        # Check if local file path mentioned
        has_local_path = bool(re.search(r'[a-zA-Z]:\\|/home/|\.shp|\.tif|\.geojson|\.gpkg', query))
        
        if has_analysis:
            if has_local_path:
                return TaskIntent(
                    task_type=TaskType.CODE_ONLY,
                    original_query=query,
                    confidence=0.85,
                    reasoning="Detected analysis keywords and local file path"
                )
            else:
                return TaskIntent(
                    task_type=TaskType.DATA_AND_CODE,
                    original_query=query,
                    confidence=0.85,
                    reasoning="Detected spatial analysis keywords"
                )
        elif has_download_only and not has_analysis:
            return TaskIntent(
                task_type=TaskType.DATA_DOWNLOAD_ONLY,
                original_query=query,
                confidence=0.80,
                reasoning="Only detected data download keywords"
            )
        
        return None
    
    def _parse_llm_response(self, response: str, original_query: str) -> TaskIntent:
        """
        Parse LLM response
        
        Args:
            response: LLM response text
            original_query: Original user query
        
        Returns:
            TaskIntent: Parsed task intent
        """
        # Try to extract JSON
        json_data = self.llm_client._extract_json_from_text(response)
        
        if json_data is None:
            # Try to parse directly
            try:
                json_data = json.loads(response)
            except json.JSONDecodeError:
                return TaskIntent(
                    task_type=TaskType.UNKNOWN,
                    original_query=original_query,
                    confidence=0.0,
                    reasoning="Cannot parse LLM response"
                )
        
        # Parse task type
        task_type_str = json_data.get("task_type", "unknown")
        task_type_map = {
            "data_download_only": TaskType.DATA_DOWNLOAD_ONLY,
            "data_and_code": TaskType.DATA_AND_CODE,
            "code_only": TaskType.CODE_ONLY,
        }
        task_type = task_type_map.get(task_type_str, TaskType.UNKNOWN)
        
        # Parse data requirements
        data_requirements = []
        for dr in json_data.get("data_requirements", []):
            data_requirements.append(DataRequirement(
                data_type=dr.get("data_type", ""),
                region=dr.get("region", ""),
                time_range=dr.get("time_range", ""),
                satellite=dr.get("satellite", ""),
                osm_types=dr.get("osm_types", []),
                description=dr.get("description", ""),
            ))
        
        # Parse analysis requirements
        analysis_requirements = []
        for ar in json_data.get("analysis_requirements", []):
            analysis_requirements.append(AnalysisRequirement(
                analysis_type=ar.get("analysis_type", ""),
                description=ar.get("description", ""),
                parameters=ar.get("parameters", {}),
                expected_output=ar.get("expected_output", ""),
            ))
        
        # Parse route planning info
        route_info = None
        route_data = json_data.get("route_info")
        if route_data and isinstance(route_data, dict):
            if route_data.get("origin") and route_data.get("destination"):
                route_info = RouteInfo(
                    origin=route_data.get("origin", ""),
                    destination=route_data.get("destination", ""),
                    waypoints=route_data.get("waypoints", []),
                    mode=route_data.get("mode", "driving")
                )
        
        return TaskIntent(
            task_type=task_type,
            original_query=original_query,
            summary=json_data.get("summary", ""),
            data_requirements=data_requirements,
            analysis_requirements=analysis_requirements,
            route_info=route_info,
            confidence=json_data.get("confidence", 0.5),
            reasoning=json_data.get("reasoning", ""),
        )
    
    def format_data_query(self, intent: TaskIntent) -> str:
        """
        Generate data download query string from intent (multiple requirements separated by ;)
        
        Args:
            intent: Task intent
        
        Returns:
            Formatted data download query
        """
        queries = self.format_data_queries_list(intent)
        return "; ".join(queries) if queries else intent.original_query
    
    def format_data_queries_list(self, intent: TaskIntent) -> list:
        """
        Generate data download query list from intent (each requirement independent)
        
        Args:
            intent: Task intent
        
        Returns:
            Formatted data download query list
        """
        if not intent.data_requirements:
            return [intent.original_query]
        
        queries = []
        for dr in intent.data_requirements:
            if dr.data_type == "remote_sensing":
                query = f"Download {dr.region} {dr.satellite or 'Sentinel-2'} imagery"
                if dr.time_range:
                    query += f", time range {dr.time_range}"
            elif dr.data_type == "osm":
                osm_types = dr.osm_types if dr.osm_types else []
                # For boundary data, use clearer description
                if "boundary" in osm_types or "boundaries" in osm_types:
                    query = f"Download {dr.region} vector boundary"
                else:
                    osm_types_str = ", ".join(osm_types) if osm_types else "roads"
                    query = f"Download {dr.region} {osm_types_str} data"
            elif dr.data_type == "poi":
                query = f"Query {dr.region} {dr.description or 'POI'} data"
            else:
                query = dr.description or f"Get {dr.region} {dr.data_type} data"
            queries.append(query)
        
        return queries

