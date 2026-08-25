# QGIS Algorithm Classification Report

## 1. Overview

This report presents the classification of **1,336 QGIS processing algorithms** (version 3.44.5) into **5 major categories**. The algorithms originate from 7 providers: SAGA Next Gen (589), QGIS native c++ (321), GRASS (307), GDAL (57), QGIS (44), QGIS PDAL (17), and QGIS 3D (1), and span 66 original groups.

## 2. Classification Method

### 2.1 Approach

The classification is based on **rule-based mapping** using the `Group` field in the original algorithm metadata. Each of the 66 original groups is mapped to one of 5 major categories according to its functional semantics. The mapping is deterministic and reproducible.

### 2.2 Classification Criteria

The 5 categories are designed to satisfy:

- **Mutual exclusivity**: each algorithm belongs to exactly one category.
- **Collective exhaustiveness**: all 1,336 algorithms are covered with no omissions.
- **Functional coherence**: algorithms within the same category share a common analytical paradigm or data type focus.

### 2.3 Mapping Table

The complete Group-to-Category mapping is as follows:

| Category | Mapped Groups |
|:---|:---|
| Raster & Remote Sensing | Raster (r.\*), Raster, Raster analysis, Raster miscellaneous, Raster conversion, Raster extraction, Raster projections, Raster creation, Raster tools, Raster terrain analysis, Terrain Analysis, terrain_analysis, Imagery, Imagery (i.\*), imagery |
| Vector Analysis | Vector (v.\*), Vector geometry, Vector general, Vector creation, Vector analysis, Vector table, Vector selection, Vector overlay, Vector geoprocessing, Vector miscellaneous, Vector conversion, Vector coverage, Vector tiles, Check geometry, Fix geometry, Features, polygon_tools |
| Data Management | Import/Export, Projection, Database, GPS, Metadata tools, Layer tools, File tools, General (g.\*), group_files, Network analysis, Miscellaneous (m.\*), Tool Chains |
| Spatial Statistics | Spatial and Geostatistics, Interpolation, Climate and Weather, sim_hydrology, sim_qm_of_esp, sim_rivflow, sim_ecosystems_hugget, sim_cellular_automata, sim_fire_spreading, sim_air_flow, sim_geomorphology, sim_erosion, sim_landscape_evolution |
| Cartography & 3D | Cartography, Plots, Visualization(NVIZ), Modeler tools, Mesh, 3D Tiles, Point cloud data management, Point cloud conversion, Point cloud extraction |

## 3. Category Definitions

### 3.1 Raster & Remote Sensing (595 algorithms, 44.5%)

Processing and analysis of **grid/cell-based data**, including raster imagery, digital elevation models, and remote sensing products.

**Scope includes:**
- Raster algebra, reclassification, resampling, mosaic, and format conversion
- Terrain analysis: slope, aspect, hillshade, watershed extraction, topographic wetness index (TWI), topographic position index (TPI)
- Remote sensing: band math, vegetation indices (NDVI), supervised/unsupervised classification, PCA, image filtering, radiometric correction, image segmentation

**Providers:** GRASS (r.\*, i.\*), SAGA (Raster, Terrain Analysis, Imagery), GDAL (Raster analysis/conversion/extraction), QGIS native

### 3.2 Vector Analysis (454 algorithms, 34.0%)

Processing and analysis of **point, line, and polygon features**, including geometric operations, spatial queries, and attribute management.

**Scope includes:**
- Geometry operations: buffer, centroid, convex hull, Voronoi, simplify, smooth, affine transform
- Overlay analysis: clip, intersect, union, difference, symmetric difference
- Spatial query and selection: select by location, select by attribute, spatial join
- Attribute table operations: field calculator, summary statistics, table join
- Geometry validation and repair: validity check, geometry fix, sliver polygon elimination
- Feature creation: regular grid, random points, contour generation

**Providers:** GRASS (v.\*), QGIS native (Vector geometry/general/overlay/table/selection/creation), GDAL, SAGA (Features, polygon_tools)

### 3.3 Data Management (117 algorithms, 8.8%)

**Data organization, conversion, and preprocessing** workflows that prepare data for analysis.

**Scope includes:**
- Format conversion and I/O: Shapefile, GeoJSON, GeoPackage, CSV, database read/write (PostGIS)
- Projection and CRS: define/reproject coordinate reference systems, coordinate transformation
- GPS data processing: GPX import, track-to-point/line conversion
- Layer and file management: merge, split, rename, metadata editing
- Database operations: SQL execution, PostGIS import/export
- Network analysis: shortest path, service area

**Providers:** SAGA (Import/Export, Projection), GDAL, QGIS native (Database, GPS, Layer tools, File tools, Metadata tools, Network analysis)

### 3.4 Spatial Statistics (104 algorithms, 7.8%)

**Quantitative modeling, geostatistics, and process simulation** for advanced spatial analysis.

**Scope includes:**
- Spatial statistics: spatial autocorrelation (Moran's I), hotspot analysis, kernel density estimation, spatial regression
- Interpolation: IDW, Kriging, spline interpolation
- Geostatistics: variogram analysis, semi-variance modeling
- Environmental simulation: meteorological data processing, precipitation analysis, hydrological simulation (runoff, flow accumulation), fire spread simulation, erosion modeling, cellular automata, landscape evolution

**Providers:** SAGA (Spatial and Geostatistics, Climate and Weather, sim_\* series), QGIS (Interpolation)

### 3.5 Cartography & 3D (66 algorithms, 4.9%)

**Visualization, cartographic production, and 3D/point cloud data** processing.

**Scope includes:**
- Cartography: thematic map styling, label placement, map decoration, grid generation
- Visualization: charts (histogram, scatter plot, box plot), 3D terrain visualization (NVIZ)
- Point cloud processing: LiDAR import, filtering, classification, format conversion (LAS/LAZ), feature extraction
- 3D data: 3D Tiles, mesh data processing, tessellation
- Modeler tools: logic control and workflow construction in the graphical modeler

**Providers:** QGIS native (Cartography, Plots, Mesh, 3D Tiles, Modeler tools), QGIS PDAL (Point cloud), GRASS (NVIZ)

## 4. Classification Results

### 4.1 Summary

| # | Category | Count | Percentage |
|:---:|:---|:---:|:---:|
| 1 | Raster & Remote Sensing | 595 | 44.5% |
| 2 | Vector Analysis | 454 | 34.0% |
| 3 | Data Management | 117 | 8.8% |
| 4 | Spatial Statistics | 104 | 7.8% |
| 5 | Cartography & 3D | 66 | 4.9% |
| | **Total** | **1,336** | **100%** |

### 4.2 Distribution by Provider

| Provider | Raster & RS | Vector | Data Mgmt | Spatial Stats | Carto & 3D | Total |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| SAGA Next Gen | 283 | 121 | 85 | 100 | 0 | 589 |
| QGIS (native c++) | 58 | 197 | 26 | 1 | 39 | 321 |
| GRASS | 210 | 92 | 4 | 0 | 1 | 307 |
| GDAL | 40 | 17 | 0 | 0 | 0 | 57 |
| QGIS | 4 | 26 | 2 | 3 | 9 | 44 |
| QGIS (PDAL) | 0 | 0 | 0 | 0 | 17 | 17 |
| QGIS (3D) | 0 | 1 | 0 | 0 | 0 | 1 |
| **Total** | **595** | **454** | **117** | **104** | **66** | **1,336** |

### 4.3 Output

The classified dataset is saved as:

```
data/qgis_alg_detail.3.44.5_classified.csv
```

The output file retains all original columns (`Algorithm ID`, `Display Name`, `Group`, `Provider`, `Provider Name`, `Help Text`) and appends a new column `Category` with one of the 5 classification labels.



## origin class
=== GDAL (57 algorithms) ===
  Raster analysis: 17
  Raster miscellaneous: 10
  Vector geoprocessing: 7
  Vector miscellaneous: 6
  Raster conversion: 6
  Raster extraction: 4
  Vector conversion: 4
  Raster projections: 3

=== GRASS (307 algorithms) ===
  Raster (r.*): 170
  Vector (v.*): 92
  Imagery (i.*): 40
  General (g.*): 3
  Miscellaneous (m.*): 1
  Visualization(NVIZ): 1

=== QGIS (44 algorithms) ===
  Plots: 8
  Vector geometry: 7
  Vector analysis: 5
  Vector creation: 5
  Vector selection: 5
  Interpolation: 3
  Vector table: 2
  Vector general: 2
  Raster terrain analysis: 2
  Database: 2
  Raster analysis: 1
  Raster tools: 1
  Cartography: 1

=== QGIS (3D) (1 algorithms) ===
  Vector geometry: 1

=== QGIS (PDAL) (17 algorithms) ===
  Point cloud data management: 10
  Point cloud conversion: 4
  Point cloud extraction: 3

=== QGIS (native c++) (321 algorithms) ===
  Vector geometry: 75
  Raster analysis: 37
  Vector general: 29
  Check geometry: 21
  Vector creation: 14
  Cartography: 13
  Modeler tools: 13
  Vector analysis: 12
  Vector table: 11
  Vector overlay: 11
  Mesh: 10
  Fix geometry: 10
  Raster creation: 9
  Vector selection: 8
  Metadata tools: 6
  Raster tools: 6
  Raster terrain analysis: 6
  Database: 5
  Network analysis: 5
  GPS: 4
  Vector coverage: 3
  Vector tiles: 3
  Layer tools: 3
  File tools: 3
  3D Tiles: 2
  Plots: 1
  Interpolation: 1

=== SAGA Next Gen (589 algorithms) ===
  Raster: 120
  Features: 119
  Terrain Analysis: 94
  Imagery: 66
  Import/Export: 57
  Spatial and Geostatistics: 42
  Climate and Weather: 28
  Projection: 25
  sim_hydrology: 9
  sim_qm_of_esp: 5
  sim_rivflow: 4
  sim_ecosystems_hugget: 3
  sim_cellular_automata: 3
  sim_fire_spreading: 2
  Tool Chains: 2
  polygon_tools: 2
  sim_air_flow: 1
  sim_geomorphology: 1
  group_files: 1
  sim_erosion: 1
  imagery: 1
  terrain_analysis: 1
  sim_landscape_evolution: 1
  Raster tools: 1

