# -*- coding: utf-8 -*-
"""
Batch-fix the incorrect "[XXX完整的边界数据 (boundary)]" prefix
in data_catalog.json and vector_db.json for all Sentinel-2 files.

Root cause: dict iteration order in data_retrieval_engine.py caused
'boundary' to match before 'sentinel' in filenames like
  Beijing_sentinel_2_202511_202602_boundary.tif
"""

import json
import re
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CATALOG_PATH = DATA_DIR / "data_catalog.json"
VECTOR_DB_PATH = DATA_DIR / "vector_db.json"


def fix_description(desc: str) -> str | None:
    """If desc has wrong boundary prefix for a sentinel file, fix it. Return None if no fix needed."""
    m = re.match(r'\[(\w+)完整的边界数据 \(boundary\)\]', desc)
    if m and 'sentinel' in desc.lower():
        region = m.group(1)
        old = f'[{region}完整的边界数据 (boundary)]'
        new = f'[{region}完整的遥感卫星影像 (Sentinel)]'
        return desc.replace(old, new)
    return None


def fix_catalog():
    with open(CATALOG_PATH, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    fixed = 0

    def walk_datasets(datasets):
        nonlocal fixed
        for ds in datasets:
            if not isinstance(ds, dict):
                continue
            fn = ds.get('file_name', '') or ds.get('name', '')
            desc = ds.get('description', '')
            if 'sentinel' in fn.lower() and '完整的边界数据 (boundary)' in desc:
                new_desc = fix_description(desc)
                if new_desc:
                    ds['description'] = new_desc
                    if ds.get('category') == 'unknown':
                        ds['category'] = 'remote_sensing_imagery'
                    fixed += 1
                    print(f"  ✓ catalog: {fn}")

    # Walk all sections
    for section_key in catalog:
        section = catalog[section_key]
        if isinstance(section, dict):
            for sub_key, sub_val in section.items():
                if isinstance(sub_val, list):
                    walk_datasets(sub_val)
        elif isinstance(section, list):
            walk_datasets(section)

    with open(CATALOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    print(f"\nCatalog: fixed {fixed} entries")
    return fixed


def fix_vector_db():
    with open(VECTOR_DB_PATH, 'r', encoding='utf-8') as f:
        vdb = json.load(f)

    fixed = 0
    for vec in vdb.get('vectors', []):
        desc = vec.get('description', '')
        if 'sentinel' in desc.lower() and '完整的边界数据 (boundary)' in desc:
            new_desc = fix_description(desc)
            if new_desc:
                vec['description'] = new_desc
                fixed += 1
                did = vec.get('dataset_id', '')[:16]
                print(f"  ✓ vector_db: {did}...")

    with open(VECTOR_DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(vdb, f, ensure_ascii=False, indent=2)

    print(f"Vector DB: fixed {fixed} entries")
    return fixed


if __name__ == "__main__":
    print("=== Fixing Sentinel-2 descriptions ===\n")
    c = fix_catalog()
    print()
    v = fix_vector_db()
    print(f"\n=== Done: {c + v} total fixes ===")
