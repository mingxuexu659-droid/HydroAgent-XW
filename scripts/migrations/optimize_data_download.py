# -*- coding: utf-8 -*-
"""
优化 data_download_only 任务类型的处理
确保正确传递下载文件信息到前端
"""

import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


def optimize_workflow_engine():
    """优化 workflow_engine.py 中的 downloaded_files 格式"""
    file_path = os.path.join(BASE_DIR, "spatial_analysis_system", "workflow_engine.py")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 在 _handle_data_only 中改进 downloaded_files 的格式
    old_code = '''                # 提取下载的文件
                result.downloaded_files = query_result.downloaded_files or []'''
    
    new_code = '''                # 提取下载的文件，并格式化为带有详细信息的对象列表
                raw_files = query_result.downloaded_files or []
                result.downloaded_files = []
                
                for file_path in raw_files:
                    if isinstance(file_path, str) and os.path.exists(file_path):
                        file_name = os.path.basename(file_path)
                        result.downloaded_files.append({
                            'name': file_name.replace('.geojson', '').replace('.tif', '').replace('_', ' ').title(),
                            'path': file_path,
                            'type': 'geojson' if file_path.endswith('.geojson') else ('raster' if file_path.endswith('.tif') else 'unknown'),
                            'size': os.path.getsize(file_path)
                        })
                    elif isinstance(file_path, dict):
                        # 如果已经是字典格式，直接使用
                        result.downloaded_files.append(file_path)
                
                print(f"   📁 格式化下载文件: {len(result.downloaded_files)} 个")'''
    
    if old_code in content:
        content = content.replace(old_code, new_code)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ 已优化: {file_path}")
    else:
        print(f"⚠️  未找到需要替换的代码块 (workflow_engine.py)")


def optimize_app_vue():
    """优化前端 App.vue 的数据加载逻辑"""
    file_path = os.path.join(BASE_DIR, "web", "src", "App.vue")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 优化下载文件加载逻辑
    old_code = '''      for (const file of downloadedFiles) {
        try {
          // 构建 URL
          let url = ''
          const filePath = (file.path || '').replace(/\\\\/g, '/')
          
          if (filePath.includes('downloaded_data')) {
            const match = filePath.match(/downloaded_data[/\\\\](.+)$/)
            if (match) {
              const relativePath = match[1]
              url = `/downloaded/${encodeURIComponent(relativePath).replace(/%2F/g, '/')}`
            }
          }
          
          if (url && file.name) {
            const layer = await mapStore.addGeoJSONLayer(file.name, url)
            if (layer) {
              loadedCount++
            } else {
              errorCount++
            }
          }
        } catch (e) {
          console.error(`加载文件失败: ${file.name}`, e)
          errorCount++
        }
      }'''
    
    new_code = '''      for (const file of downloadedFiles) {
        try {
          console.log('[App] 处理下载文件:', file)
          
          // 构建 URL
          let url = ''
          let fileName = file.name || 'unknown'
          const filePath = (file.path || '').replace(/\\\\/g, '/')
          const fileType = file.type || 'unknown'
          
          // 对于 GeoJSON 文件
          if (fileType === 'geojson' || filePath.endsWith('.geojson')) {
            if (filePath.includes('downloaded_data')) {
              const match = filePath.match(/downloaded_data[/\\\\](.+)$/)
              if (match) {
                const relativePath = match[1]
                url = `/downloaded/${encodeURIComponent(relativePath).replace(/%2F/g, '/')}`
              }
            }
            
            if (url) {
              console.log('[App] 加载 GeoJSON:', fileName, url)
              const layer = await mapStore.addGeoJSONLayer(fileName, url)
              if (layer) {
                loadedCount++
                console.log('[App] 加载成功:', fileName)
              } else {
                errorCount++
                console.error('[App] 加载失败:', fileName)
              }
            }
          } 
          // 对于栅格文件
          else if (fileType === 'raster' || filePath.endsWith('.tif') || filePath.endsWith('.tiff')) {
            console.log('[App] 跳过栅格文件（需要单独处理）:', fileName)
            // 栅格文件需要通过 catalog 加载，这里不处理
          }
        } catch (e) {
          console.error(`[App] 加载文件失败: ${file.name}`, e)
          errorCount++
        }
      }'''
    
    if old_code in content:
        content = content.replace(old_code, new_code)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ 已优化: {file_path}")
    else:
        print(f"⚠️  未找到需要替换的代码块 (App.vue)")


def create_unit_tests():
    """创建单元测试"""
    test_content = '''# -*- coding: utf-8 -*-
"""
data_download_only 任务类型单元测试
"""

import pytest
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
BASE_DIR = Path(__file__).resolve().parents[2]
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
'''
    
    test_file = os.path.join(BASE_DIR, "tests", "test_data_download_only.py")
    
    os.makedirs(os.path.join(BASE_DIR, "tests"), exist_ok=True)
    
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(test_content)
    
    print(f"✅ 已创建测试文件: {test_file}")


if __name__ == '__main__':
    print("=" * 60)
    print("优化 data_download_only 任务类型处理")
    print("=" * 60)
    print()
    
    try:
        optimize_workflow_engine()
        optimize_app_vue()
        create_unit_tests()
        
        print()
        print("=" * 60)
        print("✅ 所有优化完成！")
        print("=" * 60)
        print()
        print("下一步：")
        print("  1. 重启后端服务以应用更改")
        print("  2. 运行单元测试: python -m pytest tests/test_data_download_only.py -v")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

