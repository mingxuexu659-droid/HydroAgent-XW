# -*- coding: utf-8 -*-
"""
Workflow Engine Module

Integrates intent analysis, data download, code generation, execution and optimization into a complete workflow.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .config import Config, get_config
from .llm_client import LLMClient
from .intent_analyzer import IntentAnalyzer, TaskIntent, TaskType
from .code_generator import CodeGenerator
from .code_executor import CodeExecutor, ExecutionResult
from .code_optimizer import CodeOptimizer, search_metadata_by_path


@dataclass
class WorkflowResult:
    """Workflow execution result"""
    success: bool
    task_type: TaskType = TaskType.UNKNOWN
    original_query: str = ""
    
    # Data download results
    downloaded_files: List[str] = field(default_factory=list)
    data_metadata: List[Dict[str, Any]] = field(default_factory=list)
    
    # Code generation results
    generated_code: str = ""
    code_file_path: str = ""
    script_path: str = ""  # Alias, consistent with code_file_path
    
    # Execution results
    execution_result: Optional[ExecutionResult] = None
    optimization_rounds: int = 0
    final_code: str = ""
    
    # Output files
    output_files: List[str] = field(default_factory=list)
    
    # Messages and warnings
    message: str = ""
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'task_type': self.task_type.value,
            'original_query': self.original_query,
            'downloaded_files': self.downloaded_files,
            'data_metadata': self.data_metadata,
            'generated_code': self.generated_code,
            'code_file_path': self.code_file_path,
            'script_path': self.script_path,  # Add script_path
            'execution_result': self.execution_result.to_dict() if self.execution_result else None,
            'optimization_rounds': self.optimization_rounds,
            'final_code': self.final_code,
            'output_files': self.output_files,
            'message': self.message,
            'warnings': self.warnings,
        }


class WorkflowEngine:
    """
    Automated Spatial Analysis Workflow Engine
    
    Integrates the following functions:
    1. Intent Analysis - Determine task type
    2. Data Download - Use the local-first data retrieval engine
    3. Code Generation - Generate QGIS code based on requirements and data
    4. Code Execution - Execute code in QGIS environment
    5. Code Optimization - Auto-optimize and retry on failure
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize workflow engine
        
        Args:
            config: Configuration object
        """
        self.config = config or get_config()
        
        # Initialize components
        self.llm_client = LLMClient(self.config)  # General LLM client (intent analysis, etc.)
        self.intent_analyzer = IntentAnalyzer(self.config, self.llm_client)
        self.code_generator = CodeGenerator(self.config)  # Don't pass llm_client, let it use dedicated code generation model
        self.code_executor = CodeExecutor(self.config)
        self.code_optimizer = CodeOptimizer(self.config)  # Don't pass llm_client, let it use dedicated code optimization model
        
        # Data retrieval engine (lazy import to avoid circular dependency)
        self._data_retrieval_engine = None
    
    def _get_data_retrieval_engine(self):
        """Get data retrieval engine"""
        if self._data_retrieval_engine is None:
            try:
                # Try to import existing data download module
                sys.path.insert(0, str(Path(__file__).parent.parent))
                from core.data_retrieval_engine import VectorLocalFirstGeoQueryEngine
                
                # Get parameters from config
                catalog_path = self.config.data.data_catalog_path
                output_dir = self.config.data.local_data_dir
                api_key = self.config.vector_embedding.api_key or self.config.llm.api_key
                
                self._data_retrieval_engine = VectorLocalFirstGeoQueryEngine(
                    catalog_path=catalog_path,
                    output_dir=output_dir,
                    use_llm=True,
                    api_key=api_key,
                    embedding_api_url=self.config.vector_embedding.api_url,
                    embedding_model_name=self.config.vector_embedding.model_name,
                    embedding_timeout=self.config.vector_embedding.timeout
                )
            except ImportError as e:
                print(f"⚠️ Cannot import data retrieval engine: {e}")
                self._data_retrieval_engine = None
            except Exception as e:
                print(f"⚠️ Failed to initialize data retrieval engine: {e}")
                import traceback
                traceback.print_exc()
                self._data_retrieval_engine = None
        return self._data_retrieval_engine
    
    def process(self, query: str) -> WorkflowResult:
        """
        Main entry point for processing user requests
        
        Args:
            query: User's spatial analysis requirement
        
        Returns:
            WorkflowResult: Workflow execution result
        """
        print(f"\n{'='*58}")
        print(f"AutoGIS Spatial Analysis Workflow")
        print(f"{'='*58}")
        print(f"User requirement: {query}")
        print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        result = WorkflowResult(
            success=False,
            original_query=query
        )
        
        try:
            # Step 1: Intent analysis
            intent = self.intent_analyzer.analyze(query)
            result.task_type = intent.task_type
            
            if intent.task_type == TaskType.UNKNOWN:
                result.message = "Cannot identify task type"
                result.warnings.append("Please provide a clearer requirement description")
                return result
            
            # Step 2: Process based on task type
            if intent.is_data_only():
                # Data download only
                return self._handle_data_only(intent, result)
            
            elif intent.needs_code_generation():
                # Needs code generation
                return self._handle_data_and_code(intent, result)
            
            else:
                result.message = f"Unsupported task type: {intent.task_type.value}"
                return result
        
        except Exception as e:
            result.success = False
            result.message = f"Workflow execution failed: {str(e)}"
            import traceback
            traceback.print_exc()
            return result
        
        finally:
            print(f"\n{'='*58}")
            print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Execution status: {'Success' if result.success else 'Failed'}")
            print(f"{'='*58}")
    
    def _handle_data_only(self, intent: TaskIntent, result: WorkflowResult) -> WorkflowResult:
        """Handle data download only task"""
        print(f"\n{'='*48}")
        print(f"Data Download Task")
        print(f"{'='*48}")
        
        # Check if it's a route planning task
        if hasattr(intent, 'route_info') and intent.route_info and intent.route_info.origin and intent.route_info.destination:
            return self._handle_route_planning(intent, result)
        
        # Use data_retrieval_engine to download data
        # Improvement: process each data requirement individually instead of merging into one compound query
        data_queries = self.intent_analyzer.format_data_queries_list(intent)
        
        engine = self._get_data_retrieval_engine()
        if engine:
            result.downloaded_files = []
            
            for i, data_query in enumerate(data_queries, 1):
                print(f"\n   Data requirement {i}/{len(data_queries)}: {data_query}")
                
                try:
                    query_result = engine.query(data_query)
                    
                    # Extract downloaded files and format as list of objects with detailed info
                    raw_files = query_result.downloaded_files or []
                    
                    for file_path in raw_files:
                        if isinstance(file_path, str) and os.path.exists(file_path):
                            file_name = os.path.basename(file_path)
                            file_info = {
                                'name': file_name.replace('.geojson', '').replace('.tif', '').replace('_', ' ').title(),
                                'path': file_path,
                                'type': 'geojson' if file_path.endswith('.geojson') else ('raster' if file_path.endswith('.tif') else 'unknown'),
                                'size': os.path.getsize(file_path)
                            }
                            # Avoid duplicates
                            if not any(d.get('path') == file_path for d in result.downloaded_files if isinstance(d, dict)):
                                result.downloaded_files.append(file_info)
                        elif isinstance(file_path, dict):
                            # If already in dict format, use directly
                            if file_path not in result.downloaded_files:
                                result.downloaded_files.append(file_path)
                    
                    # Extract remote sensing data
                    if query_result.remote_sensing_data:
                        if query_result.remote_sensing_data not in result.downloaded_files:
                            result.downloaded_files.append(query_result.remote_sensing_data)
                    
                    # Extract metadata
                    if hasattr(query_result, 'local_results') and query_result.local_results:
                        for lr in query_result.local_results:
                            if isinstance(lr, dict):
                                result.data_metadata.append(lr.get('metadata', lr))
                            else:
                                result.data_metadata.append({'file': str(lr)})
                    
                except Exception as e:
                    result.warnings.append(f"Data requirement {i} download warning: {str(e)}")
                    print(f"   ⚠️ Data requirement {i} download failed: {e}")
            
            print(f"\n   Total downloaded files: {len(result.downloaded_files)}")
            
            # Determine success
            result.success = len(result.downloaded_files) > 0
            
            if result.success:
                result.message = f"Data retrieval successful, {len(result.downloaded_files)} files total"
            else:
                result.message = "No matching data found"
        else:
            result.message = "Data retrieval engine unavailable"
            result.warnings.append("Please ensure data_retrieval_engine.py is properly configured")
        
        return result
    
    def _handle_route_planning(self, intent: TaskIntent, result: WorkflowResult) -> WorkflowResult:
        """Handle route planning task"""
        print(f"\n{'='*48}")
        print(f"Route Planning Task")
        print(f"{'='*48}")
        
        route_info = intent.route_info
        if not route_info:
            result.success = False
            result.message = "Route planning info missing"
            return result
        
        # Get data_retrieval_engine to access OSM adapter
        engine = self._get_data_retrieval_engine()
        if not engine or not hasattr(engine, 'osm'):
            result.success = False
            result.message = "Route planning engine unavailable"
            return result
        
        osm = engine.osm
        
        # 1. Geocoding: convert place names to coordinates
        print(f"📍 Origin: {route_info.origin}")
        print(f"📍 Destination: {route_info.destination}")
        
        origin_result = osm.geocode(route_info.origin, get_bbox=False)
        dest_result = osm.geocode(route_info.destination, get_bbox=False)
        
        if not origin_result or not dest_result:
            result.success = False
            result.message = "Cannot resolve origin or destination coordinates"
            return result
        
        origin_lat, origin_lon = origin_result['lat'], origin_result['lon']
        dest_lat, dest_lon = dest_result['lat'], dest_result['lon']
        
        print(f"✓ Origin coordinates: ({origin_lat}, {origin_lon})")
        print(f"✓ Destination coordinates: ({dest_lat}, {dest_lon})")
        
        # 2. Call route planning API
        try:
            route_result = osm.calculate_route(
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                mode=route_info.mode or 'driving'
            )
            
            if not route_result:
                result.success = False
                result.message = "Route planning failed"
                return result
            
            # 3. Save route as GeoJSON file
            import json
            from pathlib import Path
            from datetime import datetime
            
            output_dir = Path(self.config.output.script_output_dir).parent / "routes"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            origin_name = route_info.origin.replace(' ', '_').replace('/', '_')
            dest_name = route_info.destination.replace(' ', '_').replace('/', '_')
            filename = f"route_{origin_name}_to_{dest_name}_{timestamp}.geojson"
            output_path = output_dir / filename
            
            # Build complete GeoJSON (containing origin, destination, route)
            features = [
                # Route
                {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': route_result.geometry
                    },
                    'properties': {
                        'type': 'route',
                        'distance': route_result.distance_meters,
                        'duration': route_result.duration_seconds,
                        'mode': route_info.mode or 'driving'
                    }
                },
                # Origin
                {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [origin_lon, origin_lat]
                    },
                    'properties': {
                        'type': 'origin',
                        'name': route_info.origin
                    }
                },
                # Destination
                {
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [dest_lon, dest_lat]
                    },
                    'properties': {
                        'type': 'destination',
                        'name': route_info.destination
                    }
                }
            ]
            
            geojson = {
                'type': 'FeatureCollection',
                'features': features,
                'properties': {
                    'distance': route_result.distance_meters,
                    'duration': route_result.duration_seconds,
                    'mode': route_info.mode or 'driving'
                }
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(geojson, f, ensure_ascii=False, indent=2)
            
            print(f"✓ Route saved: {output_path}")
            
            # Add to downloaded files list
            result.downloaded_files.append({
                'name': f"Route {origin_name} → {dest_name}",
                'path': str(output_path),
                'type': 'geojson',
                'size': output_path.stat().st_size,
                'route_info': {
                    'distance_km': route_result.distance_meters / 1000,
                    'duration_min': route_result.duration_seconds / 60,
                    'mode': route_info.mode or 'driving'
                }
            })
            
            result.success = True
            distance_km = route_result.distance_meters / 1000
            duration_min = route_result.duration_seconds / 60
            result.message = f"Route planning complete: {distance_km:.2f} km, {duration_min:.1f} min"
            
        except Exception as e:
            import traceback
            result.success = False
            result.message = f"Route planning exception: {str(e)}"
            result.warnings.append(traceback.format_exc())
        
        return result
    
    def _handle_data_and_code(self, intent: TaskIntent, result: WorkflowResult) -> WorkflowResult:
        """Handle data download + code generation task"""
        
        # Step 1: Data download (if needed and not skipped)
        if intent.needs_data_download() and not self.config.workflow.skip_data_download:
            print(f"\n{'='*48}")
            print(f"Step 1: Data Download")
            print(f"{'='*48}")
            
            engine = self._get_data_retrieval_engine()
            
            if engine:
                # Improvement: process each data requirement individually instead of merging into one compound query
                data_queries = self.intent_analyzer.format_data_queries_list(intent)
                
                # Track local files and newly_downloaded_files
                local_files = []
                newly_downloaded_files = []
                
                for i, data_query in enumerate(data_queries, 1):
                    print(f"\n   Data requirement {i}/{len(data_queries)}: {data_query[:50]}...")
                    
                    try:
                        query_result = engine.query(data_query)
                        
                        # Extract local files
                        if hasattr(query_result, 'local_results') and query_result.local_results:
                            for lr in query_result.local_results:
                                if isinstance(lr, dict):
                                    file_path = lr.get('file', '')
                                    if file_path:
                                        abs_path = str(Path(file_path).resolve())
                                        if abs_path not in local_files:
                                            local_files.append(abs_path)
                                            # Important: local files also need to be added to result.downloaded_files for code generator
                                            # But won't trigger "auto-process downloaded files" (already fixed in data_retrieval_engine)
                                            if abs_path not in result.downloaded_files:
                                                result.downloaded_files.append(abs_path)
                                            # Add metadata
                                            metadata = lr.get('metadata', lr)
                                            if metadata not in result.data_metadata:
                                                result.data_metadata.append(metadata)
                        
                        # Extract newly downloaded files
                        if query_result.downloaded_files:
                            for f in query_result.downloaded_files:
                                abs_path = str(Path(f).resolve())
                                if abs_path not in newly_downloaded_files:
                                    newly_downloaded_files.append(abs_path)
                                if abs_path not in result.downloaded_files:
                                    result.downloaded_files.append(abs_path)
                        
                        # Check if osm_data has boundary files
                        if hasattr(query_result, 'osm_data') and query_result.osm_data:
                            osm_data = query_result.osm_data
                            if isinstance(osm_data, dict) and 'geojson_file' in osm_data:
                                boundary_file = osm_data['geojson_file']
                                # Ensure absolute path
                                boundary_file = str(Path(boundary_file).resolve())
                                if boundary_file and boundary_file not in result.downloaded_files:
                                    result.downloaded_files.append(boundary_file)
                                    if boundary_file not in newly_downloaded_files:
                                        newly_downloaded_files.append(boundary_file)
                                    # Add boundary metadata
                                    # Important: add CRS info to help code generator handle coordinate system correctly
                                    result.data_metadata.append({
                                        'name': osm_data.get('name', 'boundary'),
                                        'absolute_path': boundary_file,
                                        'format': 'GeoJSON',
                                        'geometry_type': 'Polygon',
                                        'category': 'boundary',
                                        'source': osm_data.get('source', 'OSM'),
                                        'crs': 'EPSG:4326',  # Nominatim returns WGS84 lat/lon coordinates
                                        'crs_unit': 'degrees',  # Coordinate unit is degrees, not meters
                                        'note': 'This data is in EPSG:4326 CRS, distance unit is degrees. For buffer and other distance operations, reproject to EPSG:3857 (meters) first'
                                    })
                        
                        # Check remote_sensing_data
                        if hasattr(query_result, 'remote_sensing_data') and query_result.remote_sensing_data:
                            rs_file = query_result.remote_sensing_data
                            abs_path = str(Path(rs_file).resolve())
                            if abs_path not in result.downloaded_files:
                                result.downloaded_files.append(abs_path)
                            if abs_path not in newly_downloaded_files:
                                newly_downloaded_files.append(abs_path)
                        
                    except Exception as e:
                        result.warnings.append(f"Data requirement {i} download warning: {str(e)}")
                        print(f"   ⚠️ Data requirement {i} download failed: {e}")
                
                # Optimized output: distinguish newly downloaded and local files
                total_files = len(newly_downloaded_files) + len(local_files)
                if total_files > 0:
                    print(f"\n✓ Data preparation complete, {total_files} files total")
                    if newly_downloaded_files:
                        print(f"   Newly downloaded: {len(newly_downloaded_files)}")
                    if local_files:
                        print(f"   📂 Using local: {len(local_files)}")
                    
                    # Show file details
                    print(f"\n   Data file info:")
                    if newly_downloaded_files:
                        print(f"      📥 Newly downloaded files:")
                        for file_path in newly_downloaded_files:
                            file_name = Path(file_path).name
                            print(f"         - {file_name}: {file_path}")
                    if local_files:
                        print(f"      📂 Local files used:")
                        for file_path in local_files:
                            file_name = Path(file_path).name
                            print(f"         - {file_name}: {file_path}")
                else:
                    print(f"\n✓ Data preparation complete")
        else:
            print(f"\nSkipping data download step")
        
        # Prepare data file info (for code generation)
        # Merge all files (including local and newly downloaded)
        all_files = []
        # Add downloaded files
        for file_path in result.downloaded_files:
            abs_path = str(Path(file_path).resolve())
            data_info = {
                'path': abs_path,
                'absolute_path': abs_path,
                'name': Path(file_path).name,
            }
            # Find corresponding metadata
            for metadata in result.data_metadata:
                if isinstance(metadata, dict) and metadata.get('absolute_path') == abs_path:
                    data_info.update(metadata)
                    data_info['path'] = abs_path
                    data_info['absolute_path'] = abs_path
                    break
            all_files.append(data_info)
        
        # Add local files (if not in downloaded_files)
        # Note: since we fixed _handle_osm_data_query, local files won't be in downloaded_files
        # But for code generation completeness, we need to extract from local_results
        # For now only using downloaded_files, as code generator mainly needs these
        
        # Step 2: Code Generation
        print(f"\n{'='*48}")
        print(f"Step 2: Code Generation")
        print(f"{'='*48}")
        
        generated_code = self.code_generator.generate(
            intent=intent,
            data_files=all_files,
            output_dir=self.config.output.result_output_dir
        )
        
        if generated_code is None:
            result.message = "Code generation failed"
            return result
        
        result.generated_code = generated_code
        
        # Save generated code
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        code_filename = f"analysis_{timestamp}.py"
        result.code_file_path = self.code_generator.save_code(generated_code, code_filename)
        result.script_path = result.code_file_path  # Sync set script_path
        result.final_code = generated_code
        
        # Step 3: Code Execution (if config enabled)
        if self.config.workflow.auto_run_script:
            print(f"\n{'='*48}")
            print(f"Step 3: Code Execution")
            print(f"{'='*48}")
            
            # Calculate timeout
            timeout = self.code_executor.calculate_timeout(generated_code)
            
            # Execute code
            exec_result = self.code_executor.execute(generated_code, timeout)
            result.execution_result = exec_result
            
            # Step 4: Optimize on failure (if config enabled)
            if not exec_result.success and self.config.workflow.auto_optimize_on_failure:
                result = self._optimize_and_retry(
                    intent=intent,
                    current_code=generated_code,
                    exec_result=exec_result,
                    result=result,
                    file_metadata=result.data_metadata
                )
            else:
                result.success = exec_result.success
                if exec_result.success:
                    result.message = "Code execution successful"
                    # Try to extract output files
                    result.output_files = self._extract_output_files(exec_result.output)
                else:
                    result.message = f"Code execution failed: {exec_result.error[:200]}"
        else:
            result.success = True
            result.message = "Code generated (not executed)"
        
        return result
    
    def _optimize_and_retry(
        self,
        intent: TaskIntent,
        current_code: str,
        exec_result: ExecutionResult,
        result: WorkflowResult,
        file_metadata: List[Dict[str, Any]]
    ) -> WorkflowResult:
        """Optimize code and retry execution"""
        
        max_rounds = self.config.workflow.max_optimization_rounds
        
        for round_num in range(1, max_rounds + 1):
            print(f"\n{'='*48}")
            print(f"Optimization Round {round_num}/{max_rounds}")
            print(f"{'='*48}")
            
            # Optimize code
            optimized_code = self.code_optimizer.optimize(
                original_code=current_code,
                error_result=exec_result,
                instruction=intent.original_query,
                file_metadata=file_metadata,
                round_num=round_num
            )
            
            if optimized_code is None:
                result.warnings.append(f"Round {round_num} optimization failed")
                continue
            
            # Save optimized code
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            opt_filename = f"analysis_opt{round_num}_{timestamp}.py"
            opt_path = self.code_generator.save_code(optimized_code, opt_filename)
            
            # Re-execute
            timeout = self.code_executor.calculate_timeout(optimized_code)
            exec_result = self.code_executor.execute(optimized_code, timeout)
            
            result.optimization_rounds = round_num
            result.execution_result = exec_result
            result.final_code = optimized_code
            result.code_file_path = opt_path  # Update to optimized script path
            result.script_path = opt_path  # Sync update script_path
            
            if exec_result.success:
                print(f"✓ Execution successful after round {round_num} optimization!")
                result.success = True
                result.message = f"Code executed successfully after round {round_num} optimization"
                result.output_files = self._extract_output_files(exec_result.output)
                return result
            else:
                print(f"✗ Still failed after round {round_num} optimization")
                current_code = optimized_code
        
        result.success = False
        result.message = f"Still failed after {max_rounds} optimization rounds"
        return result
    
    def _extract_output_files(self, output: str) -> List[str]:
        """Extract generated file paths from execution output"""
        import re
        
        files = []
        
        # Match common output file path patterns
        patterns = [
            r'Output file[：:]\s*(.+)',
            r'Output[：:]\s*(.+)',
            r'Saved to[：:]\s*(.+)',
            r'Results saved[：:]\s*(.+)',
            r'([A-Za-z]:\\[^\s]+\.(?:shp|tif|gpkg|geojson))',
            r'(/[^\s]+\.(?:shp|tif|gpkg|geojson))',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, output, re.IGNORECASE)
            for match in matches:
                path = match.strip().strip('"\'')
                if os.path.exists(path):
                    files.append(path)
        
        return list(set(files))
    
    def save_result(self, result: WorkflowResult, output_dir: Optional[str] = None) -> str:
        """
        Save workflow execution result
        
        Args:
            result: Workflow result
            output_dir: Output directory
        
        Returns:
            Saved file path
        """
        if output_dir is None:
            output_dir = self.config.output.log_dir
        
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"workflow_result_{timestamp}.json"
        filepath = Path(output_dir) / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        
        print(f"Result saved: {filepath}")
        return str(filepath)

