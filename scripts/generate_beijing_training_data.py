# -*- coding: utf-8 -*-
"""
Generate land-use training samples for Beijing area based on known geographic locations.

Each anchor point is a well-known location in Beijing where the land cover type
is highly predictable. Small random jitter is added around each anchor to create
multiple samples per location.

Output: GeoJSON point file with 'class' (int) and 'class_name' (str) attributes.
CRS: EPSG:4326 (WGS-84)

Classes:
  1 = Water
  2 = Vegetation (forest / park)
  3 = Built-up (urban)
  4 = Bare Soil
  5 = Cropland
"""

import json
import random
import os
from pathlib import Path

random.seed(42)
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ──────────────────────────────────────────────
# Anchor points: (lon, lat, jitter_radius_deg)
#   jitter_radius controls how far samples scatter
#   around the anchor (in degrees, ~0.01° ≈ 1 km)
# ──────────────────────────────────────────────

ANCHORS = {
    1: {  # Water
        "name": "Water",
        "points": [
            # Miyun Reservoir (very large, safe to jitter)
            (116.970, 40.480, 0.015),
            (116.950, 40.500, 0.015),
            (116.990, 40.460, 0.015),
            # Guanting Reservoir
            (115.600, 40.230, 0.012),
            (115.620, 40.220, 0.012),
            # Kunming Lake (Summer Palace) – small, tight jitter
            (116.272, 39.995, 0.003),
            # Huairou Reservoir
            (116.630, 40.330, 0.008),
            # Shahe Reservoir
            (116.300, 40.130, 0.005),
            # Baihe River segments
            (116.800, 40.550, 0.006),
            (116.850, 40.520, 0.006),
            # Chaobai River
            (116.780, 40.200, 0.005),
            (116.770, 40.180, 0.005),
            # Yongding River
            (116.120, 39.920, 0.004),
        ],
    },
    2: {  # Vegetation
        "name": "Vegetation",
        "points": [
            # Olympic Forest Park
            (116.390, 40.025, 0.005),
            # Fragrant Hills (Xiangshan)
            (116.190, 40.000, 0.008),
            (116.180, 39.990, 0.008),
            # Badaling / Great Wall forest
            (116.020, 40.350, 0.010),
            (116.000, 40.370, 0.010),
            # Yanqing forest
            (115.970, 40.450, 0.010),
            # Mentougou mountains
            (115.950, 39.950, 0.012),
            (115.920, 39.970, 0.012),
            # Changping mountains
            (116.100, 40.300, 0.010),
            # Fangshan mountains
            (115.800, 39.780, 0.010),
            # Temple of Heaven park
            (116.410, 39.880, 0.003),
            # Beihai Park
            (116.390, 39.925, 0.002),
            # Yuanmingyuan (Old Summer Palace)
            (116.300, 40.008, 0.004),
        ],
    },
    3: {  # Built-up
        "name": "Built-up",
        "points": [
            # CBD / Guomao
            (116.460, 39.910, 0.005),
            (116.470, 39.905, 0.005),
            # Wangfujing
            (116.410, 39.915, 0.004),
            # Zhongguancun / Haidian
            (116.320, 39.980, 0.006),
            (116.310, 39.975, 0.006),
            # Fengtai
            (116.290, 39.860, 0.006),
            # Tongzhou urban center
            (116.660, 39.910, 0.006),
            (116.670, 39.900, 0.006),
            # Shunyi urban center
            (116.650, 40.130, 0.005),
            # Changping urban
            (116.230, 40.215, 0.005),
            # Yizhuang economic zone
            (116.510, 39.790, 0.005),
            # Lize financial area
            (116.420, 39.870, 0.004),
            # Wangjing
            (116.480, 39.990, 0.004),
        ],
    },
    4: {  # Bare Soil
        "name": "Bare Soil",
        "points": [
            # Yanqing north plain (dry land)
            (115.980, 40.530, 0.010),
            (116.020, 40.540, 0.010),
            # Huairou north dry hills
            (116.600, 40.450, 0.008),
            # Fangshan quarry / mining area
            (115.980, 39.720, 0.008),
            (116.000, 39.710, 0.008),
            # Daxing new airport construction fringe
            (116.420, 39.520, 0.008),
            (116.440, 39.530, 0.008),
            # Pinggu east exposed land
            (117.100, 40.180, 0.008),
            # Changping north exposed land
            (116.300, 40.300, 0.008),
            # Miyun east dry riverbed
            (117.050, 40.400, 0.008),
            # Mentougou exposed slopes
            (115.880, 39.870, 0.008),
            # Fangshan south dry area
            (116.050, 39.650, 0.008),
            # Yanqing east dry area
            (116.100, 40.480, 0.008),
        ],
    },
    5: {  # Cropland
        "name": "Cropland",
        "points": [
            # Shunyi farmland
            (116.720, 40.150, 0.010),
            (116.740, 40.160, 0.010),
            # Daxing farmland
            (116.400, 39.680, 0.010),
            (116.380, 39.660, 0.010),
            # Tongzhou farmland
            (116.800, 39.850, 0.010),
            (116.820, 39.830, 0.010),
            # Changping farmland
            (116.350, 40.180, 0.008),
            # Pinggu farmland
            (117.050, 40.130, 0.010),
            (117.030, 40.110, 0.010),
            # Miyun south farmland
            (116.850, 40.350, 0.008),
            # Fangshan south farmland
            (116.100, 39.650, 0.008),
            # Huairou south farmland
            (116.650, 40.280, 0.008),
            # Yanqing farmland
            (115.980, 40.470, 0.008),
        ],
    },
}

# How many jittered samples to generate per anchor point
SAMPLES_PER_ANCHOR = 5


def jitter(lon, lat, radius):
    """Add random offset within a circle of given radius (degrees)."""
    dx = random.uniform(-radius, radius)
    dy = random.uniform(-radius, radius)
    return round(lon + dx, 6), round(lat + dy, 6)


def generate_features():
    features = []
    fid = 0
    for class_id, info in ANCHORS.items():
        class_name = info["name"]
        for lon, lat, radius in info["points"]:
            for _ in range(SAMPLES_PER_ANCHOR):
                jlon, jlat = jitter(lon, lat, radius)
                features.append({
                    "type": "Feature",
                    "id": fid,
                    "properties": {
                        "class": class_id,
                        "class_name": class_name,
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [jlon, jlat],
                    },
                })
                fid += 1
    return features


def main():
    features = generate_features()

    geojson = {
        "type": "FeatureCollection",
        "name": "Beijing_LandUse_Training_Samples",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }

    # ── Summary ──
    from collections import Counter
    counts = Counter(f["properties"]["class"] for f in features)
    print("=== Beijing Land-Use Training Data ===")
    for cid in sorted(counts):
        cname = ANCHORS[cid]["name"]
        print(f"  Class {cid} ({cname:12s}): {counts[cid]:4d} samples")
    print(f"  {'Total':20s}: {len(features):4d} samples")

    # ── Write ──
    out_dir = PROJECT_ROOT / "data" / "training"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "beijing_landuse_training.geojson")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Saved to: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
