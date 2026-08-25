# -*- coding: utf-8 -*-
"""
修复 data_download_only 任务类型的处理
添加必要的字段和逻辑
"""

import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


def patch_task_manager():
    """修改 task_manager.py"""
    file_path = os.path.join(BASE_DIR, "api", "services", "task_manager.py")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. 在 create_task 中添加 task_type 和 downloaded_files
    if '"task_type": None' not in content:
        content = content.replace(
            '"output_files": [],',
            '''        "output_files": [],
            "task_type": None,  # 任务类型: data_download_only, data_and_code, code_only
            "downloaded_files": [],  # 下载的数据文件列表'''
        )
    
    # 2. 在workflow_result处理时添加 task_type 和 downloaded_files
    if '"task_type": workflow_result.task_type' not in content:
        content = content.replace(
            '"output_files": workflow_result.output_files if hasattr(workflow_result, \'output_files\') else [],',
            '''"output_files": workflow_result.output_files if hasattr(workflow_result, 'output_files') else [],
                        "task_type": workflow_result.task_type.value if hasattr(workflow_result, 'task_type') else None,
                        "downloaded_files": workflow_result.downloaded_files if hasattr(workflow_result, 'downloaded_files') else [],'''
        )
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ 已修改: {file_path}")


def patch_task_response():
    """修改 api/schemas/analysis.py"""
    file_path = os.path.join(BASE_DIR, "api", "schemas", "analysis.py")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 添加 task_type 和 downloaded_files 字段
    if 'task_type: Optional[str]' not in content:
        # 在 TaskResponse 类中添加字段
        content = content.replace(
            'code: Optional[str] = Field(None, description="生成的代码")',
            '''code: Optional[str] = Field(None, description="生成的代码")
    task_type: Optional[str] = Field(None, description="任务类型: data_download_only, data_and_code, code_only")
    downloaded_files: Optional[List[Dict[str, Any]]] = Field(None, description="下载的数据文件列表")'''
        )
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ 已修改: {file_path}")


def patch_app_vue():
    """修改前端 App.vue"""
    file_path = os.path.join(BASE_DIR, "web", "src", "App.vue")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 修改任务完成监听逻辑
    old_watch = '''watch(() => currentTask.value?.status, async (status, oldStatus) => {
  console.log('[Watch] 任务状态变化:', oldStatus, '->', status)
  
  if (status === 'completed' && oldStatus !== 'completed' && currentTask.value) {
    console.log('✅ 任务完成，获取代码和执行结果...')
    console.log('[Watch] Task ID:', currentTask.value.task_id)
    
    try {
      // 获取生成的代码和脚本路径
      const code = await taskStore.fetchCode(currentTask.value.task_id)'''
    
    new_watch = '''watch(() => currentTask.value?.status, async (status, oldStatus) => {
  console.log('[Watch] 任务状态变化:', oldStatus, '->', status)
  
  if (status === 'completed' && oldStatus !== 'completed' && currentTask.value) {
    console.log('✅ 任务完成，获取代码和执行结果...')
    console.log('[Watch] Task ID:', currentTask.value.task_id)
    console.log('[Watch] Task Type:', currentTask.value.task_type)
    
    // 判断任务类型
    const taskType = currentTask.value.task_type || ''
    
    // 如果是仅下载数据类型，直接加载下载的数据到地图
    if (taskType === 'data_download_only') {
      console.log('📥 数据下载任务，自动加载下载的文件到地图...')
      const downloadedFiles = currentTask.value.downloaded_files || []
      
      if (downloadedFiles.length === 0) {
        showMessage('完成', '数据下载完成，但没有找到下载的文件', 'info')
        return
      }
      
      let loadedCount = 0
      let errorCount = 0
      
      for (const file of downloadedFiles) {
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
      }
      
      const message = `已下载 ${downloadedFiles.length} 个数据文件\\n成功加载到地图: ${loadedCount} 个${errorCount > 0 ? `\\n加载失败: ${errorCount} 个` : ''}`
      showMessage('下载完成', message, loadedCount > 0 ? 'success' : 'info')
      return
    }
    
    // 对于其他类型（data_and_code, code_only），获取代码并自动加载图层
    try {
      // 获取生成的代码和脚本路径
      const code = await taskStore.fetchCode(currentTask.value.task_id)'''
    
    if old_watch in content:
        content = content.replace(old_watch, new_watch)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ 已修改: {file_path}")
    else:
        print(f"⚠️  未找到需要替换的代码块，请手动修改")


def patch_types():
    """修改前端类型定义"""
    file_path = os.path.join(BASE_DIR, "web", "src", "types", "index.ts")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 在 Task 接口中添加字段
    if 'task_type?:' not in content:
        content = content.replace(
            'code?: string',
            '''code?: string
  task_type?: string  // 任务类型: data_download_only, data_and_code, code_only
  downloaded_files?: Array<{name: string, path: string, url?: string}>  // 下载的文件列表'''
        )
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ 已修改: {file_path}")


if __name__ == '__main__':
    print("=" * 60)
    print("修复 data_download_only 任务类型处理")
    print("=" * 60)
    print()
    
    try:
        patch_task_manager()
        patch_task_response()
        patch_types()
        patch_app_vue()
        
        print()
        print("=" * 60)
        print("✅ 所有修改完成！")
        print("=" * 60)
        print()
        print("下一步：重启前后端服务以应用更改")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

