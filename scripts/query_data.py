#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据搜索 - 向量匹配本地优先版

基于 data_search_with_clip_online.py，修改本地数据查看逻辑：
1. 任务分解为DAG
2. DAG的每个节点先查看本地数据目录中是否有已下载的数据
3. 使用向量匹配：将节点需求转为向量，与本地数据的description字段做向量匹配
4. 选出Top N数据，让大模型判断是否能满足需求
5. 如果本地数据无法满足，再采用在线检索

向量化：使用百炼API (DashScope)
测试示例：使用 data_catalog_test.json 的前10条数据
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# 导入主引擎类
from core.data_retrieval_engine import VectorLocalFirstGeoQueryEngine


# ============================================================================
# 命令行接口
# ============================================================================

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='地理查询引擎 - 向量匹配本地优先版',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('query', nargs='?', default=None, help='查询文本')
    parser.add_argument('--catalog', '-c', 
                        default=str(PROJECT_ROOT / 'data' / 'data_catalog.json'),
                        help='本地数据目录文件路径')
    parser.add_argument('--top-k', '-k', type=int, default=5, 
                        help='向量匹配返回Top K个结果')
    parser.add_argument('--no-llm', action='store_true',
                        help='禁用 LLM 意图识别')
    parser.add_argument('--json', '-j', action='store_true',
                        help='以 JSON 格式输出')
    parser.add_argument('--download', '-d', action='store_true',
                        help='下载结果为 GeoJSON 文件')
    parser.add_argument('--output', '-o', default=str(PROJECT_ROOT / 'downloaded_data'),
                        help='下载输出目录')
    
    args = parser.parse_args()
    
    # 检查数据目录
    catalog_path = args.catalog
    if not Path(catalog_path).exists():
        print(f"⚠️ 数据目录不存在: {catalog_path}")
        catalog_path = None
    
    # 初始化引擎
    engine = VectorLocalFirstGeoQueryEngine(
        catalog_path=catalog_path,
        output_dir=args.output,
        use_llm=not args.no_llm,
        api_key=None  # 使用默认的API密钥
    )
    
    # 如果没有提供查询，进入交互模式
    if args.query is None:
        print("\n🌍 地理查询引擎 - 向量匹配本地优先版")
        print("=" * 50)
        print("输入 'quit' 或 'q' 退出\n")
        
        while True:
            try:
                query = input("请输入查询: ").strip()
                if query.lower() in ['quit', 'q', 'exit']:
                    print("再见!")
                    break
                if not query:
                    continue
                
                result = engine.query(query, top_k=args.top_k)
                
                if args.json:
                    print(engine.to_json(result))
                else:
                    print(engine.format_result(result))
                
                if args.download:
                    saved_files = engine.download_results(result)
                    if saved_files:
                        print(f"\n✅ 已下载 {len(saved_files)} 个文件到 {args.output}/")
                
            except KeyboardInterrupt:
                print("\n再见!")
                break
    else:
        # 命令行模式
        result = engine.query(args.query, top_k=args.top_k)
        
        if args.json:
            print(engine.to_json(result))
        else:
            print(engine.format_result(result))
        
        if args.download:
            print("\n📥 正在下载数据...")
            saved_files = engine.download_results(result)
            if saved_files:
                print(f"\n✅ 已下载 {len(saved_files)} 个文件:")
                for f in saved_files:
                    print(f"   - {f}")


if __name__ == '__main__':
    main()
