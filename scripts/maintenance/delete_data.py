# -*- coding: utf-8 -*-
"""
AutoGIS 数据删除脚本
功能：删除指定文件，并从 data_catalog.json 和 vector_db.json 中移除相应记录

用法：
python scripts/maintenance/delete_data.py <文件路径>
python scripts/maintenance/delete_data.py "downloaded_data/example.geojson"
python scripts/maintenance/delete_data.py "osm_boundaries_Stanford_University_20260212_142843.geojson"

"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

# 配置路径
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_CATALOG_PATH = PROJECT_ROOT / "data" / "data_catalog.json"
VECTOR_DB_PATH = PROJECT_ROOT / "data" / "vector_db.json"


def normalize_path(path: str) -> str:
    """标准化路径，用于比较"""
    return os.path.normpath(os.path.abspath(path)).lower()


def load_json(filepath: Path) -> dict:
    """加载 JSON 文件"""
    if not filepath.exists():
        print(f"❌ 文件不存在: {filepath}")
        return None
    
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(filepath: Path, data: dict):
    """保存 JSON 文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 已保存: {filepath}")


def delete_from_catalog(catalog: dict, target_path: str) -> tuple:
    """
    从数据目录中删除指定路径的记录
    
    返回: (是否找到并删除, 删除的 dataset_id, 删除的数据名称)
    """
    target_normalized = normalize_path(target_path)
    deleted_ids = []
    deleted_names = []
    
    # 搜索所有数据类别
    categories = [
        ('vector_data', 'datasets'),
        ('vector_data', 'points'),
        ('vector_data', 'lines'),
        ('vector_data', 'polygons'),
        ('raster_data', 'datasets'),
        ('raster_data', 'imagery'),
    ]
    
    for category, subcategory in categories:
        if category not in catalog:
            continue
        cat_data = catalog[category]
        if subcategory not in cat_data:
            continue
        
        items = cat_data[subcategory]
        items_to_remove = []
        
        for i, item in enumerate(items):
            item_path = item.get('absolute_path') or item.get('file_path', '')
            if normalize_path(item_path) == target_normalized:
                items_to_remove.append(i)
                deleted_ids.append(item.get('dataset_id'))
                deleted_names.append(item.get('name', '未知'))
        
        # 从后往前删除，避免索引问题
        for i in reversed(items_to_remove):
            del items[i]
            print(f"  📋 从 {category}.{subcategory} 中删除记录")
    
    # 更新元数据
    if deleted_ids and 'metadata' in catalog:
        catalog['metadata']['updated_at'] = datetime.now().isoformat()
        # 重新计算总数
        total = 0
        for category, subcategory in categories:
            if category in catalog and subcategory in catalog[category]:
                total += len(catalog[category][subcategory])
        catalog['metadata']['total_datasets'] = total
        catalog['metadata']['total_files'] = total
    
    return len(deleted_ids) > 0, deleted_ids, deleted_names


def delete_from_vector_db(vector_db: dict, dataset_ids: list) -> int:
    """
    从向量数据库中删除指定 dataset_id 的记录
    
    返回: 删除的记录数
    """
    if not dataset_ids or 'vectors' not in vector_db:
        return 0
    
    original_count = len(vector_db['vectors'])
    
    # 过滤掉要删除的记录
    vector_db['vectors'] = [
        v for v in vector_db['vectors'] 
        if v.get('dataset_id') not in dataset_ids
    ]
    
    deleted_count = original_count - len(vector_db['vectors'])
    
    # 更新元数据
    if deleted_count > 0 and 'metadata' in vector_db:
        vector_db['metadata']['updated_at'] = datetime.now().isoformat()
        vector_db['metadata']['total_vectors'] = len(vector_db['vectors'])
    
    return deleted_count


def delete_data(file_path: str, dry_run: bool = False):
    """
    删除数据文件及其相关记录
    
    Args:
        file_path: 要删除的文件路径
        dry_run: 如果为 True，只显示将要执行的操作，不实际删除
    """
    print("\n" + "=" * 60)
    print("🗑️  AutoGIS 数据删除工具")
    print("=" * 60)
    
    file_path = os.path.abspath(file_path)
    print(f"\n📁 目标文件: {file_path}")
    
    if dry_run:
        print("⚠️  [预览模式] 不会实际删除文件")
    
    # 检查文件是否存在
    file_exists = os.path.exists(file_path)
    if file_exists:
        file_size = os.path.getsize(file_path)
        print(f"   状态: 存在 ({file_size / 1024:.2f} KB)")
    else:
        print("   状态: 文件不存在（将只删除目录中的记录）")
    
    # 加载数据目录
    print(f"\n📂 加载数据目录...")
    catalog = load_json(DATA_CATALOG_PATH)
    if not catalog:
        return False
    
    # 加载向量数据库
    print(f"📂 加载向量数据库...")
    vector_db = load_json(VECTOR_DB_PATH)
    if not vector_db:
        return False
    
    # 从数据目录中删除
    print(f"\n🔍 搜索并删除目录记录...")
    found, deleted_ids, deleted_names = delete_from_catalog(catalog, file_path)
    
    if found:
        print(f"   ✅ 找到 {len(deleted_ids)} 条记录:")
        for name in deleted_names:
            print(f"      - {name}")
    else:
        print("   ⚠️  未在数据目录中找到匹配记录")
    
    # 从向量数据库中删除
    print(f"\n🔍 删除向量数据库记录...")
    vector_deleted = delete_from_vector_db(vector_db, deleted_ids)
    if vector_deleted > 0:
        print(f"   ✅ 删除了 {vector_deleted} 条向量记录")
    else:
        print("   ⚠️  未找到对应的向量记录")
    
    # 删除物理文件
    if file_exists:
        print(f"\n🗑️  删除物理文件...")
        if not dry_run:
            try:
                os.remove(file_path)
                print(f"   ✅ 文件已删除: {file_path}")
            except Exception as e:
                print(f"   ❌ 删除文件失败: {e}")
                return False
        else:
            print(f"   [预览] 将删除: {file_path}")
    
    # 保存更新后的 JSON 文件
    if not dry_run:
        print(f"\n💾 保存更新...")
        save_json(DATA_CATALOG_PATH, catalog)
        save_json(VECTOR_DB_PATH, vector_db)
    else:
        print(f"\n[预览] 将更新: {DATA_CATALOG_PATH}")
        print(f"[预览] 将更新: {VECTOR_DB_PATH}")
    
    print("\n" + "=" * 60)
    print("✅ 删除操作完成!")
    print("=" * 60 + "\n")
    
    return True


def list_all_data():
    """列出所有已注册的数据"""
    print("\n" + "=" * 60)
    print("📋 已注册的数据列表")
    print("=" * 60)
    
    catalog = load_json(DATA_CATALOG_PATH)
    if not catalog:
        return
    
    categories = [
        ('vector_data', 'datasets'),
        ('vector_data', 'points'),
        ('vector_data', 'lines'),
        ('vector_data', 'polygons'),
        ('raster_data', 'datasets'),
        ('raster_data', 'imagery'),
    ]
    
    index = 1
    for category, subcategory in categories:
        if category not in catalog:
            continue
        cat_data = catalog[category]
        if subcategory not in cat_data:
            continue
        
        items = cat_data[subcategory]
        if items:
            print(f"\n[{category}.{subcategory}]")
            for item in items:
                name = item.get('name', '未知')
                path = item.get('absolute_path') or item.get('file_path', '未知路径')
                exists = "✅" if os.path.exists(path) else "❌"
                print(f"  {index}. {exists} {name}")
                print(f"      路径: {path}")
                index += 1
    
    print("\n" + "=" * 60 + "\n")


def interactive_mode():
    """交互式删除模式"""
    print("\n" + "=" * 60)
    print("🗑️  AutoGIS 数据删除工具 - 交互模式")
    print("=" * 60)
    
    # 列出所有数据
    catalog = load_json(DATA_CATALOG_PATH)
    if not catalog:
        return
    
    categories = [
        ('vector_data', 'datasets'),
        ('vector_data', 'points'),
        ('vector_data', 'lines'),
        ('vector_data', 'polygons'),
        ('raster_data', 'datasets'),
        ('raster_data', 'imagery'),
    ]
    
    all_items = []
    print("\n已注册的数据:")
    print("-" * 40)
    
    index = 1
    for category, subcategory in categories:
        if category not in catalog:
            continue
        cat_data = catalog[category]
        if subcategory not in cat_data:
            continue
        
        for item in cat_data[subcategory]:
            name = item.get('name', '未知')
            path = item.get('absolute_path') or item.get('file_path', '')
            exists = "✅" if os.path.exists(path) else "❌"
            print(f"  [{index}] {exists} {name}")
            all_items.append(path)
            index += 1
    
    if not all_items:
        print("  (无数据)")
        return
    
    print("-" * 40)
    print("\n输入序号删除对应数据，输入 'q' 退出，输入 'all' 显示详细路径")
    
    while True:
        try:
            choice = input("\n请选择 (1-{}, q=退出): ".format(len(all_items))).strip()
            
            if choice.lower() == 'q':
                print("已退出")
                break
            
            if choice.lower() == 'all':
                for i, path in enumerate(all_items, 1):
                    print(f"  [{i}] {path}")
                continue
            
            idx = int(choice) - 1
            if 0 <= idx < len(all_items):
                path = all_items[idx]
                confirm = input(f"确定删除 '{path}'? (y/n): ").strip().lower()
                if confirm == 'y':
                    delete_data(path)
                    # 重新加载以更新列表
                    return interactive_mode()
            else:
                print("❌ 无效的序号")
        
        except ValueError:
            print("❌ 请输入有效的数字")
        except KeyboardInterrupt:
            print("\n已退出")
            break


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print(__doc__)
        print("\n可用命令:")
        print("  python scripts/maintenance/delete_data.py <文件路径>     # 删除指定文件")
        print("  python scripts/maintenance/delete_data.py --list        # 列出所有数据")
        print("  python scripts/maintenance/delete_data.py --interactive # 交互式删除")
        print("  python scripts/maintenance/delete_data.py --dry-run <文件路径>  # 预览模式（不实际删除）")
        return
    
    arg = sys.argv[1]
    
    if arg == '--list':
        list_all_data()
    elif arg == '--interactive':
        interactive_mode()
    elif arg == '--dry-run':
        if len(sys.argv) < 3:
            print("❌ 请指定文件路径")
            return
        delete_data(sys.argv[2], dry_run=True)
    else:
        delete_data(arg)


if __name__ == '__main__':
    main()

