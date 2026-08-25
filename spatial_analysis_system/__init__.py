# -*- coding: utf-8 -*-
"""
AutoGIS 空间分析系统

自动化完成空间数据获取、QGIS代码生成和执行的系统。
"""

__version__ = "1.0.0"
__author__ = "AutoGIS Team"

from .config import Config, get_config
from .llm_client import LLMClient
from .intent_analyzer import IntentAnalyzer, TaskIntent, TaskType
from .code_generator import CodeGenerator
from .code_executor import CodeExecutor
from .code_optimizer import CodeOptimizer
from .workflow_engine import WorkflowEngine
from .catalog_builder import CatalogBuilder, build_catalog_from_config

__all__ = [
    "Config",
    "get_config",
    "LLMClient",
    "IntentAnalyzer",
    "TaskIntent",
    "TaskType",
    "CodeGenerator",
    "CodeExecutor",
    "CodeOptimizer",
    "WorkflowEngine",
    "CatalogBuilder",
    "build_catalog_from_config",
]

