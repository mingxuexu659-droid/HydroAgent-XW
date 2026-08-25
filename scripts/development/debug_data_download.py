# -*- coding: utf-8 -*-
"""
调试 data_download_only 任务
检查 API 返回的数据结构
"""

import os
import requests
import json
import time

BASE_URL = os.environ.get("AUTOGIS_API_BASE_URL", "http://127.0.0.1:8000")

def test_data_download_task():
    """测试数据下载任务"""
    print("=" * 60)
    print("测试 data_download_only 任务")
    print("=" * 60)
    print()
    
    # 1. 提交任务
    print("📤 提交任务...")
    payload = {
        "query": "查询北京有哪些酒店",
        "skip_download": False,
        "auto_run": True,
        "auto_optimize": True,
        "max_optimization_rounds": 3
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/analysis/submit", json=payload)
        response.raise_for_status()
        task_data = response.json()
        
        task_id = task_data.get('task_id')
        print(f"   ✅ 任务已提交: {task_id}")
        print(f"   初始状态: {task_data.get('status')}")
        print()
        
        # 2. 轮询任务状态
        print("⏳ 等待任务完成...")
        max_attempts = 60  # 最多等待60秒
        attempt = 0
        
        while attempt < max_attempts:
            time.sleep(2)
            attempt += 1
            
            status_response = requests.get(f"{BASE_URL}/api/analysis/task/{task_id}")
            status_response.raise_for_status()
            task_status = status_response.json()
            
            status = task_status.get('status')
            progress = task_status.get('progress', 0)
            current_step = task_status.get('current_step', '')
            
            print(f"   [{attempt}] 状态: {status} | 进度: {progress}% | 步骤: {current_step}")
            
            if status in ['completed', 'failed']:
                print()
                print("=" * 60)
                print(f"📊 任务完成 (状态: {status})")
                print("=" * 60)
                print()
                
                # 3. 检查关键字段
                print("🔍 检查关键字段:")
                print(f"   - task_id: {task_status.get('task_id')}")
                print(f"   - status: {task_status.get('status')}")
                print(f"   - task_type: {task_status.get('task_type')}")
                print(f"   - downloaded_files: {task_status.get('downloaded_files')}")
                print(f"   - output_files: {task_status.get('output_files')}")
                print(f"   - code: {'存在' if task_status.get('code') else '不存在'}")
                print()
                
                # 4. 打印 downloaded_files 详情
                downloaded_files = task_status.get('downloaded_files', [])
                if downloaded_files:
                    print("📁 下载的文件:")
                    for i, file in enumerate(downloaded_files, 1):
                        print(f"   [{i}] {json.dumps(file, ensure_ascii=False, indent=6)}")
                else:
                    print("⚠️  没有 downloaded_files")
                print()
                
                # 5. 打印完整响应
                print("📄 完整响应 (JSON):")
                print(json.dumps(task_status, ensure_ascii=False, indent=2))
                
                break
        
        if attempt >= max_attempts:
            print("❌ 任务超时")
    
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求失败: {e}")
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


def test_api_connection():
    """测试 API 连接"""
    print("🔗 测试 API 连接...")
    try:
        response = requests.get(f"{BASE_URL}/api/analysis/tasks")
        response.raise_for_status()
        print("   ✅ API 连接正常")
        return True
    except Exception as e:
        print(f"   ❌ API 连接失败: {e}")
        return False


if __name__ == '__main__':
    if test_api_connection():
        print()
        test_data_download_task()

