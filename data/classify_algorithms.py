"""
对 QGIS 算法文档进行分类，在原 CSV 基础上新增一列 Category。

分类规则基于 Group 和 Provider Name 字段，将 1336 条算法归入 5 大类：
  1. Raster & Remote Sensing
  2. Vector Analysis
  3. Data Management
  4. Spatial Statistics
  5. Cartography & 3D
"""

import csv
import os

INPUT_FILE = os.path.join(os.path.dirname(__file__), "qgis_alg_detail.3.44.5.csv")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "qgis_alg_detail.3.44.5_classified.csv")

# ============================================================
# 分类映射表：Group -> Category
# ============================================================
GROUP_TO_CATEGORY = {
    # ---- 1. Raster & Remote Sensing ----
    "Raster (r.*)": "Raster & Remote Sensing",
    "Raster": "Raster & Remote Sensing",
    "Raster analysis": "Raster & Remote Sensing",
    "Raster miscellaneous": "Raster & Remote Sensing",
    "Raster conversion": "Raster & Remote Sensing",
    "Raster extraction": "Raster & Remote Sensing",
    "Raster projections": "Raster & Remote Sensing",
    "Raster creation": "Raster & Remote Sensing",
    "Raster tools": "Raster & Remote Sensing",
    "Raster terrain analysis": "Raster & Remote Sensing",
    "Terrain Analysis": "Raster & Remote Sensing",
    "terrain_analysis": "Raster & Remote Sensing",
    "Imagery": "Raster & Remote Sensing",
    "Imagery (i.*)": "Raster & Remote Sensing",
    "imagery": "Raster & Remote Sensing",

    # ---- 2. Vector Analysis ----
    "Vector (v.*)": "Vector Analysis",
    "Vector geometry": "Vector Analysis",
    "Vector general": "Vector Analysis",
    "Vector creation": "Vector Analysis",
    "Vector analysis": "Vector Analysis",
    "Vector table": "Vector Analysis",
    "Vector selection": "Vector Analysis",
    "Vector overlay": "Vector Analysis",
    "Vector geoprocessing": "Vector Analysis",
    "Vector miscellaneous": "Vector Analysis",
    "Vector conversion": "Vector Analysis",
    "Vector coverage": "Vector Analysis",
    "Vector tiles": "Vector Analysis",
    "Check geometry": "Vector Analysis",
    "Fix geometry": "Vector Analysis",
    "Features": "Vector Analysis",
    "polygon_tools": "Vector Analysis",

    # ---- 3. Data Management ----
    "Import/Export": "Data Management",
    "Projection": "Data Management",
    "Database": "Data Management",
    "GPS": "Data Management",
    "Metadata tools": "Data Management",
    "Layer tools": "Data Management",
    "File tools": "Data Management",
    "General (g.*)": "Data Management",
    "group_files": "Data Management",
    "Network analysis": "Data Management",
    "Miscellaneous (m.*)": "Data Management",
    "Tool Chains": "Data Management",

    # ---- 4. Spatial Statistics ----
    "Spatial and Geostatistics": "Spatial Statistics",
    "Interpolation": "Spatial Statistics",
    "Climate and Weather": "Spatial Statistics",
    "sim_hydrology": "Spatial Statistics",
    "sim_qm_of_esp": "Spatial Statistics",
    "sim_rivflow": "Spatial Statistics",
    "sim_ecosystems_hugget": "Spatial Statistics",
    "sim_cellular_automata": "Spatial Statistics",
    "sim_fire_spreading": "Spatial Statistics",
    "sim_air_flow": "Spatial Statistics",
    "sim_geomorphology": "Spatial Statistics",
    "sim_erosion": "Spatial Statistics",
    "sim_landscape_evolution": "Spatial Statistics",

    # ---- 5. Cartography & 3D ----
    "Cartography": "Cartography & 3D",
    "Plots": "Cartography & 3D",
    "Visualization(NVIZ)": "Cartography & 3D",
    "Modeler tools": "Cartography & 3D",
    "Mesh": "Cartography & 3D",
    "3D Tiles": "Cartography & 3D",
    "Point cloud data management": "Cartography & 3D",
    "Point cloud conversion": "Cartography & 3D",
    "Point cloud extraction": "Cartography & 3D",
}


def classify(group: str) -> str:
    """根据 Group 字段返回分类名称"""
    return GROUP_TO_CATEGORY.get(group.strip(), "Uncategorized")


def main():
    rows = []
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            row["Category"] = classify(row.get("Group", ""))
            rows.append(row)

    # 新增 Category 列
    out_fieldnames = fieldnames + ["Category"]

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # 统计
    from collections import Counter
    cats = Counter(r["Category"] for r in rows)
    print(f"总算法数: {len(rows)}")
    print(f"输出文件: {OUTPUT_FILE}")
    print("\n分类统计:")
    for cat, cnt in cats.most_common():
        print(f"  {cat}: {cnt}")


if __name__ == "__main__":
    main()
