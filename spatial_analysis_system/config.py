# -*- coding: utf-8 -*-
"""
Configuration Management Module

Loads and manages system configuration, supports YAML config files and environment variables.
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "downloaded_data"
DEFAULT_CATALOG_PATH = PROJECT_ROOT / "data" / "data_catalog.json"
DEFAULT_VECTOR_DB_PATH = PROJECT_ROOT / "data" / "vector_db.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
DEFAULT_ALGORITHM_CSV_PATH = PROJECT_ROOT / "data" / "qgis_alg_detail.3.44.5.csv"


@dataclass
class LLMConfig:
    """LLM configuration - General"""
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_name: str = "qwen-max"
    temperature: float = 0.3
    max_tokens: int = 8192
    timeout: float = 120.0  # Request timeout (seconds), default 120s


@dataclass
class LLMCodeGeneratorConfig:
    """LLM configuration - Code generation specific"""
    enabled: bool = True  # Whether to use separate code generation model
    api_key: str = ""  # Empty to use general llm api_key
    base_url: str = ""  # Empty to use general llm base_url
    model_name: str = ""  # Code generation specific model
    temperature: float = 0.2  # Lower temperature recommended for code generation
    max_tokens: int = 15000
    timeout: float = 180.0  # Request timeout (seconds), code generation may take longer, default 180s


@dataclass
class LLMCodeOptimizerConfig:
    """LLM configuration - Code optimization specific"""
    enabled: bool = True  # Whether to use separate code optimization model
    api_key: str = ""  # Empty to use general llm api_key
    base_url: str = ""  # Empty to use general llm base_url
    model_name: str = ""  # Code optimization specific model
    temperature: float = 0.3  # Slightly higher temperature for creativity
    max_tokens: int = 15000
    timeout: float = 180.0  # Request timeout (seconds)


@dataclass
class WorkflowConfig:
    """Workflow configuration"""
    skip_data_download: bool = False
    auto_run_script: bool = True
    auto_optimize_on_failure: bool = True
    max_optimization_rounds: int = 3
    use_rag_for_optimization: bool = True


@dataclass
class QGISConfig:
    """QGIS configuration"""
    root_path: str = ""
    runqgis_bat_path: str = ""
    qgis_run_py_path: str = ""
    algorithm_csv_path: str = str(DEFAULT_ALGORITHM_CSV_PATH)
    script_timeout: int = 300
    timeout_per_tool: int = 20


@dataclass
class VectorEmbeddingConfig:
    """向量检索模型配置"""
    api_key: str = ""  # 留空则使用通用llm的api_key
    api_url: str = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
    model_name: str = "text-embedding-v2"  # 向量检索模型名称
    timeout: float = 10.0  # 请求超时时间（秒）


@dataclass
class DataConfig:
    """Data configuration"""
    local_data_dir: str = str(DEFAULT_DATA_DIR)
    data_catalog_path: str = str(DEFAULT_CATALOG_PATH)
    vector_db_path: str = str(DEFAULT_VECTOR_DB_PATH)
    
    # Raw data directories configuration
    raw_data_dirs: list = field(default_factory=lambda: [str(DEFAULT_DATA_DIR)])
    supported_extensions: dict = field(default_factory=lambda: {
        "vector": [".shp", ".geojson", ".gpkg", ".gdb", ".kml", ".json"],
        "raster": [".tif", ".tiff", ".img", ".jp2", ".ecw", ".nc"]
    })
    auto_scan_on_startup: bool = False
    use_llm_for_description: bool = True
    recursive_scan: bool = True
    exclude_patterns: list = field(default_factory=lambda: ["__pycache__", r"\.git", "temp", "backup"])


@dataclass
class OutputConfig:
    """Output configuration"""
    script_output_dir: str = str(DEFAULT_OUTPUT_DIR / "generated_scripts")
    result_output_dir: str = str(DEFAULT_OUTPUT_DIR / "results")
    log_dir: str = str(DEFAULT_OUTPUT_DIR / "logs")
    save_intermediate_results: bool = True


@dataclass
class RemoteSensingConfig:
    """遥感数据下载配置"""
    cloud_cover_max: float = 70.0  # 最大云量阈值 (0-100)
    default_satellite: str = "sentinel-2"  # 默认卫星类型


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    console_output: bool = True
    file_output: bool = True
    file_name_format: str = "autogis_{date}.log"


class Config:
    """
    系统配置管理类
    
    支持从YAML文件加载配置，并允许通过环境变量覆盖。
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认路径
        """
        self.llm = LLMConfig()
        self.llm_code_generator = LLMCodeGeneratorConfig()
        self.llm_code_optimizer = LLMCodeOptimizerConfig()
        self.vector_embedding = VectorEmbeddingConfig()
        self.workflow = WorkflowConfig()
        self.qgis = QGISConfig()
        self.data = DataConfig()
        self.output = OutputConfig()
        self.remote_sensing = RemoteSensingConfig()
        self.logging = LoggingConfig()
        
        # 默认配置文件路径
        if config_path is None:
            config_path = os.environ.get("AUTOGIS_CONFIG") or Path(__file__).parent / "config.yaml"
        
        self.config_path = Path(config_path)
        
        # 加载配置
        if self.config_path.exists():
            self._load_from_yaml()
        
        # 环境变量覆盖
        self._load_from_env()
        
        # 确保输出目录存在
        self._ensure_output_dirs()
    
    def _load_from_yaml(self) -> None:
        """从YAML文件加载配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f) or {}
            
            # LLM配置 - 通用
            if 'llm' in config_data:
                llm_cfg = config_data['llm']
                self.llm = LLMConfig(
                    api_key=llm_cfg.get('api_key', self.llm.api_key),
                    base_url=llm_cfg.get('base_url', self.llm.base_url),
                    model_name=llm_cfg.get('model_name', self.llm.model_name),
                    temperature=llm_cfg.get('temperature', self.llm.temperature),
                    max_tokens=llm_cfg.get('max_tokens', self.llm.max_tokens),
                    timeout=llm_cfg.get('timeout', self.llm.timeout),
                )
            
            # LLM配置 - 代码生成专用
            if 'llm_code_generator' in config_data:
                cg_cfg = config_data['llm_code_generator']
                self.llm_code_generator = LLMCodeGeneratorConfig(
                    enabled=cg_cfg.get('enabled', self.llm_code_generator.enabled),
                    api_key=cg_cfg.get('api_key', self.llm_code_generator.api_key),
                    base_url=cg_cfg.get('base_url', self.llm_code_generator.base_url),
                    model_name=cg_cfg.get('model_name', self.llm_code_generator.model_name),
                    temperature=cg_cfg.get('temperature', self.llm_code_generator.temperature),
                    max_tokens=cg_cfg.get('max_tokens', self.llm_code_generator.max_tokens),
                    timeout=cg_cfg.get('timeout', self.llm_code_generator.timeout),
                )
            
            # LLM配置 - 代码优化专用
            if 'llm_code_optimizer' in config_data:
                co_cfg = config_data['llm_code_optimizer']
                self.llm_code_optimizer = LLMCodeOptimizerConfig(
                    enabled=co_cfg.get('enabled', self.llm_code_optimizer.enabled),
                    api_key=co_cfg.get('api_key', self.llm_code_optimizer.api_key),
                    base_url=co_cfg.get('base_url', self.llm_code_optimizer.base_url),
                    model_name=co_cfg.get('model_name', self.llm_code_optimizer.model_name),
                    temperature=co_cfg.get('temperature', self.llm_code_optimizer.temperature),
                    max_tokens=co_cfg.get('max_tokens', self.llm_code_optimizer.max_tokens),
                    timeout=co_cfg.get('timeout', self.llm_code_optimizer.timeout),
                )
            
            # 向量检索模型配置
            if 'vector_embedding' in config_data:
                ve_cfg = config_data['vector_embedding']
                # 如果api_key为空，则使用通用llm的api_key
                api_key = ve_cfg.get('api_key', self.vector_embedding.api_key)
                if not api_key:
                    api_key = self.llm.api_key
                self.vector_embedding = VectorEmbeddingConfig(
                    api_key=api_key,
                    api_url=ve_cfg.get('api_url', self.vector_embedding.api_url),
                    model_name=ve_cfg.get('model_name', self.vector_embedding.model_name),
                    timeout=ve_cfg.get('timeout', self.vector_embedding.timeout),
                )
            
            # 工作流配置
            if 'workflow' in config_data:
                wf_cfg = config_data['workflow']
                self.workflow = WorkflowConfig(
                    skip_data_download=wf_cfg.get('skip_data_download', self.workflow.skip_data_download),
                    auto_run_script=wf_cfg.get('auto_run_script', self.workflow.auto_run_script),
                    auto_optimize_on_failure=wf_cfg.get('auto_optimize_on_failure', self.workflow.auto_optimize_on_failure),
                    max_optimization_rounds=wf_cfg.get('max_optimization_rounds', self.workflow.max_optimization_rounds),
                    use_rag_for_optimization=wf_cfg.get('use_rag_for_optimization', self.workflow.use_rag_for_optimization),
                )
            
            # QGIS配置
            if 'qgis' in config_data:
                qgis_cfg = config_data['qgis']
                self.qgis = QGISConfig(
                    root_path=qgis_cfg.get('root_path', self.qgis.root_path),
                    runqgis_bat_path=qgis_cfg.get('runqgis_bat_path', self.qgis.runqgis_bat_path),
                    qgis_run_py_path=qgis_cfg.get('qgis_run_py_path', self.qgis.qgis_run_py_path),
                    algorithm_csv_path=qgis_cfg.get('algorithm_csv_path', self.qgis.algorithm_csv_path),
                    script_timeout=qgis_cfg.get('script_timeout', self.qgis.script_timeout),
                    timeout_per_tool=qgis_cfg.get('timeout_per_tool', self.qgis.timeout_per_tool),
                )
            
            # 数据配置
            if 'data' in config_data:
                data_cfg = config_data['data']
                self.data = DataConfig(
                    local_data_dir=data_cfg.get('local_data_dir', self.data.local_data_dir),
                    data_catalog_path=data_cfg.get('data_catalog_path', self.data.data_catalog_path),
                    vector_db_path=data_cfg.get('vector_db_path', self.data.vector_db_path),
                    raw_data_dirs=data_cfg.get('raw_data_dirs', self.data.raw_data_dirs),
                    supported_extensions=data_cfg.get('supported_extensions', self.data.supported_extensions),
                    auto_scan_on_startup=data_cfg.get('auto_scan_on_startup', self.data.auto_scan_on_startup),
                    use_llm_for_description=data_cfg.get('use_llm_for_description', self.data.use_llm_for_description),
                    recursive_scan=data_cfg.get('recursive_scan', self.data.recursive_scan),
                    exclude_patterns=data_cfg.get('exclude_patterns', self.data.exclude_patterns),
                )
            
            # 输出配置
            if 'output' in config_data:
                out_cfg = config_data['output']
                self.output = OutputConfig(
                    script_output_dir=out_cfg.get('script_output_dir', self.output.script_output_dir),
                    result_output_dir=out_cfg.get('result_output_dir', self.output.result_output_dir),
                    log_dir=out_cfg.get('log_dir', self.output.log_dir),
                    save_intermediate_results=out_cfg.get('save_intermediate_results', self.output.save_intermediate_results),
                )
            
            # 日志配置
            if 'logging' in config_data:
                log_cfg = config_data['logging']
                self.logging = LoggingConfig(
                    level=log_cfg.get('level', self.logging.level),
                    console_output=log_cfg.get('console_output', self.logging.console_output),
                    file_output=log_cfg.get('file_output', self.logging.file_output),
                    file_name_format=log_cfg.get('file_name_format', self.logging.file_name_format),
                )
            
            # 遥感数据配置
            if 'remote_sensing' in config_data:
                rs_cfg = config_data['remote_sensing']
                self.remote_sensing = RemoteSensingConfig(
                    cloud_cover_max=rs_cfg.get('cloud_cover_max', self.remote_sensing.cloud_cover_max),
                    default_satellite=rs_cfg.get('default_satellite', self.remote_sensing.default_satellite),
                )
                
        except Exception as e:
            print(f"⚠️ Failed to load config file: {e}, using default configuration")
    
    def _load_from_env(self) -> None:
        """从环境变量加载配置（用于覆盖YAML配置）"""
        # LLM API Key
        if os.environ.get('OPENAI_API_KEY'):
            self.llm.api_key = os.environ['OPENAI_API_KEY']
        if os.environ.get('AUTOGIS_API_KEY'):
            self.llm.api_key = os.environ['AUTOGIS_API_KEY']
        
        # LLM Base URL
        if os.environ.get('OPENAI_BASE_URL'):
            self.llm.base_url = os.environ['OPENAI_BASE_URL']
        if os.environ.get('AUTOGIS_BASE_URL'):
            self.llm.base_url = os.environ['AUTOGIS_BASE_URL']
        
        # LLM Model
        if os.environ.get('AUTOGIS_MODEL'):
            self.llm.model_name = os.environ['AUTOGIS_MODEL']
        
        # 工作流配置
        if os.environ.get('AUTOGIS_SKIP_DOWNLOAD'):
            self.workflow.skip_data_download = os.environ['AUTOGIS_SKIP_DOWNLOAD'].lower() == 'true'
        if os.environ.get('AUTOGIS_AUTO_RUN'):
            self.workflow.auto_run_script = os.environ['AUTOGIS_AUTO_RUN'].lower() == 'true'
        if os.environ.get('AUTOGIS_AUTO_OPTIMIZE'):
            self.workflow.auto_optimize_on_failure = os.environ['AUTOGIS_AUTO_OPTIMIZE'].lower() == 'true'
        if os.environ.get('AUTOGIS_MAX_OPT_ROUNDS'):
            self.workflow.max_optimization_rounds = int(os.environ['AUTOGIS_MAX_OPT_ROUNDS'])
    
    def _ensure_output_dirs(self) -> None:
        """确保输出目录存在"""
        dirs_to_create = [
            self.output.script_output_dir,
            self.output.result_output_dir,
            self.output.log_dir,
            self.data.local_data_dir,
        ]
        for dir_path in dirs_to_create:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    def get_code_generator_llm_config(self) -> LLMConfig:
        """
        获取代码生成器应使用的LLM配置
        
        如果 llm_code_generator.enabled 为 True，则使用代码生成专用配置
        否则返回通用 LLM 配置
        
        Returns:
            LLMConfig: 代码生成器使用的LLM配置
        """
        if not self.llm_code_generator.enabled:
            return self.llm
        
        # 创建代码生成器专用的 LLMConfig
        # 如果某些字段为空，则回退到通用配置
        return LLMConfig(
            api_key=self.llm_code_generator.api_key or self.llm.api_key,
            base_url=self.llm_code_generator.base_url or self.llm.base_url,
            model_name=self.llm_code_generator.model_name,
            temperature=self.llm_code_generator.temperature,
            max_tokens=self.llm_code_generator.max_tokens,
            timeout=self.llm_code_generator.timeout,
        )
    
    def save_to_yaml(self, path: Optional[str] = None) -> None:
        """
        保存配置到YAML文件
        
        Args:
            path: 保存路径，如果为None则覆盖原配置文件
        """
        save_path = Path(path) if path else self.config_path
        
        config_data = {
            'llm': {
                'api_key': self.llm.api_key,
                'base_url': self.llm.base_url,
                'model_name': self.llm.model_name,
                'temperature': self.llm.temperature,
                'max_tokens': self.llm.max_tokens,
                'timeout': self.llm.timeout,
            },
            'llm_code_generator': {
                'enabled': self.llm_code_generator.enabled,
                'api_key': self.llm_code_generator.api_key,
                'base_url': self.llm_code_generator.base_url,
                'model_name': self.llm_code_generator.model_name,
                'temperature': self.llm_code_generator.temperature,
                'max_tokens': self.llm_code_generator.max_tokens,
                'timeout': self.llm_code_generator.timeout,
            },
            'vector_embedding': {
                'api_key': self.vector_embedding.api_key,
                'api_url': self.vector_embedding.api_url,
                'model_name': self.vector_embedding.model_name,
                'timeout': self.vector_embedding.timeout,
            },
            'workflow': {
                'skip_data_download': self.workflow.skip_data_download,
                'auto_run_script': self.workflow.auto_run_script,
                'auto_optimize_on_failure': self.workflow.auto_optimize_on_failure,
                'max_optimization_rounds': self.workflow.max_optimization_rounds,
                'use_rag_for_optimization': self.workflow.use_rag_for_optimization,
            },
            'qgis': {
                'root_path': self.qgis.root_path,
                'runqgis_bat_path': self.qgis.runqgis_bat_path,
                'qgis_run_py_path': self.qgis.qgis_run_py_path,
                'algorithm_csv_path': self.qgis.algorithm_csv_path,
                'script_timeout': self.qgis.script_timeout,
                'timeout_per_tool': self.qgis.timeout_per_tool,
            },
            'data': {
                'local_data_dir': self.data.local_data_dir,
                'data_catalog_path': self.data.data_catalog_path,
                'vector_db_path': self.data.vector_db_path,
            },
            'output': {
                'script_output_dir': self.output.script_output_dir,
                'result_output_dir': self.output.result_output_dir,
                'log_dir': self.output.log_dir,
                'save_intermediate_results': self.output.save_intermediate_results,
            },
            'logging': {
                'level': self.logging.level,
                'console_output': self.logging.console_output,
                'file_output': self.logging.file_output,
                'file_name_format': self.logging.file_name_format,
            },
        }
        
        with open(save_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    def __repr__(self) -> str:
        return (
            f"Config(\n"
            f"  llm={self.llm},\n"
            f"  llm_code_generator={self.llm_code_generator},\n"
            f"  workflow={self.workflow},\n"
            f"  qgis={self.qgis},\n"
            f"  data={self.data},\n"
            f"  output={self.output},\n"
            f"  logging={self.logging}\n"
            f")"
        )


# 全局默认配置实例
_default_config: Optional[Config] = None


def get_config() -> Config:
    """获取全局配置实例"""
    global _default_config
    if _default_config is None:
        _default_config = Config()
    return _default_config


def set_config(config: Config) -> None:
    """设置全局配置实例"""
    global _default_config
    _default_config = config

