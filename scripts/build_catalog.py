#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据目录构建工具

自动扫描指定目录，生成data_catalog.json和向量数据库。

使用方法：
    # 使用配置文件中的目录设置
    python scripts/build_catalog.py
    
    # 指定要扫描的目录
    python scripts/build_catalog.py --dir "D:/GIS_Data/vector" --dir "D:/GIS_Data/raster"
    
    # 指定输出路径
    python scripts/build_catalog.py --output "data/my_catalog.json"
    
    # 不使用LLM生成描述（更快）
    python scripts/build_catalog.py --no-llm
    
    # 不递归扫描子目录
    python scripts/build_catalog.py --no-recursive
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from spatial_analysis_system import Config, CatalogBuilder


def print_banner():
    """打印启动横幅"""
    banner = r"""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║     📁 AutoGIS 数据目录构建工具                           ║
    ║     Data Catalog Builder                                  ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    print(banner)


def main():
    parser = argparse.ArgumentParser(
        description="AutoGIS 数据目录构建工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/build_catalog.py                              # 使用配置文件设置
  python scripts/build_catalog.py --dir "D:/GIS_Data"          # 扫描指定目录
  python scripts/build_catalog.py --no-llm                     # 不使用LLM生成描述
"""
    )
    
    parser.add_argument(
        "--dir", "-d",
        action="append",
        dest="dirs",
        help="要扫描的数据目录（可多次指定）"
    )
    
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="输出的catalog JSON路径"
    )
    
    parser.add_argument(
        "--vector-db",
        default=None,
        help="输出的向量数据库路径"
    )
    
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="配置文件路径"
    )
    
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="不使用LLM生成描述（更快）"
    )
    
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="不递归扫描子目录"
    )
    
    args = parser.parse_args()
    
    print_banner()
    
    # 加载配置
    config = Config(args.config)
    
    # 应用命令行参数
    if args.no_llm:
        config.data.use_llm_for_description = False
    if args.no_recursive:
        config.data.recursive_scan = False
    
    # 创建构建器
    builder = CatalogBuilder(config)
    
    # 确定要扫描的目录
    data_dirs = args.dirs if args.dirs else None
    
    # 构建目录
    try:
        catalog, file_count = builder.build_catalog(
            data_dirs=data_dirs,
            output_catalog_path=args.output,
            output_vector_db_path=args.vector_db
        )
        
        print(f"\n{'='*60}")
        print(f"✅ 构建完成！")
        print(f"{'='*60}")
        print(f"  扫描文件数: {file_count}")
        print(f"  矢量数据集: {len(catalog.get('vector_data', {}).get('datasets', []))}")
        print(f"  栅格数据集: {len(catalog.get('raster_data', {}).get('datasets', []))}")
        
    except Exception as e:
        print(f"\n❌ 构建失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

