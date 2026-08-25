# -*- coding: utf-8 -*-
"""
data_download_only 任务类型单元测试
"""

import pytest
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from spatial_analysis_system.workflow_engine import WorkflowEngine, WorkflowResult, TaskType
from spatial_analysis_system.intent_analyzer import TaskIntent
from spatial_analysis_system.config import get_config


class TestDataDownloadOnly:
    """测试仅数据下载任务"""
    
    @pytest.fixture
    def engine(self):
        """创建工作流引擎实例"""
        config = get_config()
        return WorkflowEngine(config)
    
    def test_workflow_result_has_task_type(self):
        """测试 WorkflowResult 包含 task_type 字段"""
        result = WorkflowResult(success=True, task_type=TaskType.DATA_DOWNLOAD_ONLY)
        assert result.task_type == TaskType.DATA_DOWNLOAD_ONLY
        
        result_dict = result.to_dict()
        assert 'task_type' in result_dict
        assert result_dict['task_type'] == 'data_download_only'
    
    def test_workflow_result_has_downloaded_files(self):
        """测试 WorkflowResult 包含 downloaded_files 字段"""
        result = WorkflowResult(
            success=True,
            task_type=TaskType.DATA_DOWNLOAD_ONLY,
            downloaded_files=[
                {
                    'name': 'hotel_北京',
                    'path': '/path/to/hotel_北京.geojson',
                    'type': 'geojson',
                    'size': 1024
                }
            ]
        )
        
        assert len(result.downloaded_files) == 1
        assert result.downloaded_files[0]['name'] == 'hotel_北京'
        assert result.downloaded_files[0]['type'] == 'geojson'
        
        result_dict = result.to_dict()
        assert 'downloaded_files' in result_dict
        assert len(result_dict['downloaded_files']) == 1
    
    def test_data_download_only_intent(self):
        """测试数据下载意图识别"""
        intent = TaskIntent(
            raw_query="查询北京有哪些酒店",
            task_type=TaskType.DATA_DOWNLOAD_ONLY,
            data_requirements=["北京的酒店位置数据"],
            analysis_requirements=[]
        )
        
        assert intent.is_data_only() == True
        assert intent.needs_code_generation() == False
        assert intent.needs_data_download() == True
    
    @pytest.mark.skipif(
        not os.path.exists(os.path.join(BASE_DIR, "core", "data_retrieval_engine.py")),
        reason="data_retrieval_engine not available"
    )
    def test_handle_data_only_workflow(self, engine):
        """测试仅数据下载工作流（集成测试）"""
        # 这是一个集成测试，需要实际的数据下载引擎
        query = "下载北京市的边界数据"
        
        # 注意：这个测试可能会失败，因为需要实际的网络请求和API
        # 可以使用 mock 来替代
        result = engine.process(query)
        
        # 基本断言
        assert isinstance(result, WorkflowResult)
        assert result.task_type in [TaskType.DATA_DOWNLOAD_ONLY, TaskType.DATA_AND_CODE, TaskType.UNKNOWN]
        
        # 如果是数据下载任务
        if result.task_type == TaskType.DATA_DOWNLOAD_ONLY:
            assert isinstance(result.downloaded_files, list)
            # 成功时应该有下载文件
            if result.success:
                assert len(result.downloaded_files) > 0
                # 检查文件格式
                for file in result.downloaded_files:
                    if isinstance(file, dict):
                        assert 'name' in file or 'path' in file
    
    def test_downloaded_files_format(self):
        """测试下载文件格式的正确性"""
        # 预期的文件格式
        file_info = {
            'name': 'Hotel Beijing',
            'path': '/downloaded_data/hotel_beijing.geojson',
            'type': 'geojson',
            'size': 2048
        }
        
        result = WorkflowResult(
            success=True,
            task_type=TaskType.DATA_DOWNLOAD_ONLY,
            downloaded_files=[file_info]
        )
        
        assert len(result.downloaded_files) == 1
        file = result.downloaded_files[0]
        
        # 验证所有必需字段
        assert 'name' in file
        assert 'path' in file
        assert 'type' in file
        assert 'size' in file
        
        # 验证类型
        assert isinstance(file['name'], str)
        assert isinstance(file['path'], str)
        assert isinstance(file['type'], str)
        assert isinstance(file['size'], (int, float))
    
    def test_multiple_files_download(self):
        """测试多个文件下载"""
        files = [
            {'name': 'File1', 'path': '/path1.geojson', 'type': 'geojson', 'size': 100},
            {'name': 'File2', 'path': '/path2.geojson', 'type': 'geojson', 'size': 200},
            {'name': 'File3', 'path': '/path3.tif', 'type': 'raster', 'size': 300},
        ]
        
        result = WorkflowResult(
            success=True,
            task_type=TaskType.DATA_DOWNLOAD_ONLY,
            downloaded_files=files
        )
        
        assert len(result.downloaded_files) == 3
        assert result.downloaded_files[0]['name'] == 'File1'
        assert result.downloaded_files[2]['type'] == 'raster'


if __name__ == '__main__':
    # 运行测试
    pytest.main([__file__, '-v', '-s'])
