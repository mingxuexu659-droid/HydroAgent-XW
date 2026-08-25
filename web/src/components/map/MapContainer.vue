<script setup lang="ts">
/**
 * 地图容器组件
 */
import { ref, onMounted, onUnmounted, watch } from 'vue'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useMapStore } from '@/stores/map'

// Props
const props = defineProps<{
  center?: [number, number]
  zoom?: number
}>()

// Emits
const emit = defineEmits<{
  (e: 'map-ready', map: maplibregl.Map): void
  (e: 'feature-click', feature: GeoJSON.Feature): void
}>()

// Store
const mapStore = useMapStore()

// Refs
const mapContainer = ref<HTMLElement>()
const map = ref<maplibregl.Map>()
const is3D = ref(false)
const coordinates = ref('---, ---')
const showBasemapSelector = ref(false)
const currentBasemap = ref('osm')  // 默认使用 OSM

// 底图配置
interface BasemapConfig {
  id: string
  name: string
  icon: string
  tiles: string[]
  tileSize: number
  maxzoom: number
  attribution: string
}

const basemaps: BasemapConfig[] = [
  {
    id: 'osm',
    name: 'OSM',
    icon: '🗺️',
    // CartoDB Voyager via backend proxy (with cache, English labels)
    tiles: ['/api/data/tiles/voyager/{z}/{x}/{y}.png'],
    tileSize: 256,
    maxzoom: 19,
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> © <a href="https://carto.com/">CARTO</a>'
  },
  {
    id: 'gaode',
    name: 'Gaode',
    icon: '🌏',
    // Gaode Map with English labels (direct access, works in China)
    tiles: [
      'https://webrd01.is.autonavi.com/appmaptile?lang=en&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
      'https://webrd02.is.autonavi.com/appmaptile?lang=en&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
      'https://webrd03.is.autonavi.com/appmaptile?lang=en&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
      'https://webrd04.is.autonavi.com/appmaptile?lang=en&size=1&scale=1&style=8&x={x}&y={y}&z={z}'
    ],
    tileSize: 256,
    maxzoom: 18,
    attribution: '© Gaode Map'
  },
  {
    id: 'esri',
    name: 'ESRI',
    icon: '🛰️',
    // ESRI World Imagery - Satellite basemap
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
    tileSize: 256,
    maxzoom: 18,
    attribution: '© ESRI'
  }
]

// 生成底图样式
function createBasemapStyle(basemap: BasemapConfig): maplibregl.StyleSpecification {
  return {
    version: 8,
    name: basemap.name,
    sources: {
      'basemap-tiles': {
        type: 'raster',
        tiles: basemap.tiles,
        tileSize: basemap.tileSize,
        attribution: basemap.attribution
      }
    },
    layers: [
      {
        id: 'basemap-tiles',
        type: 'raster',
        source: 'basemap-tiles',
        minzoom: 0,
        maxzoom: basemap.maxzoom
      }
    ],
    glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf'
  }
}

// 切换底图
function switchBasemap(basemapId: string) {
  const basemap = basemaps.find(b => b.id === basemapId)
  if (!basemap || !map.value) return
  
  // 保存当前视图状态
  const center = map.value.getCenter()
  const zoom = map.value.getZoom()
  const pitch = map.value.getPitch()
  const bearing = map.value.getBearing()
  
  // 深拷贝 store 中的图层数据（避免响应式引用问题）
  const storeLayers = JSON.parse(JSON.stringify(mapStore.layers))
  
  console.log(`Switching to ${basemapId}, saving ${storeLayers.length} layers`)
  
  // 设置新样式
  map.value.setStyle(createBasemapStyle(basemap))
  
  // 等待新样式加载完成后恢复用户图层
  const restoreLayers = () => {
    if (!map.value) return
    
    console.log(`Style loaded, restoring ${storeLayers.length} layers...`)
    
    // 恢复视图
    map.value.jumpTo({ center, zoom, pitch, bearing })
    
    // 从 store 中重新添加所有图层
    storeLayers.forEach((layer: any) => {
      const sourceId = `source-${layer.id}`
      const layerId = layer.id
      
      try {
        // 🔧 处理栅格图层
        if (layer.type === 'raster' && layer.rasterSource) {
          console.log(`Restoring raster layer: ${layer.name}`, layer.rasterSource)
          
          const rasterUrl = layer.rasterSource.url
          const isCog = layer.rasterSource.format === 'cog'
          
          if (isCog) {
            // COG/GeoTIFF 格式
            let fullUrl = rasterUrl
            if (rasterUrl.startsWith('/')) {
              fullUrl = `${window.location.origin}${rasterUrl}`
            }
            
            if (!map.value?.getSource(sourceId)) {
              map.value?.addSource(sourceId, {
                type: 'raster',
                tiles: [`cog://${fullUrl}`],
                tileSize: 256
              })
            }
            
            if (!map.value?.getLayer(layerId)) {
              map.value?.addLayer({
                id: layerId,
                type: 'raster',
                source: sourceId,
                paint: {
                  'raster-opacity': layer.style?.opacity ?? 0.85,
                  'raster-resampling': 'nearest'
                },
                layout: {
                  'visibility': layer.visible ? 'visible' : 'none'
                }
              })
            }
          } else {
            // PNG 图像格式
            if (layer.bounds && !map.value?.getSource(sourceId)) {
              map.value?.addSource(sourceId, {
                type: 'image',
                url: rasterUrl,
                coordinates: [
                  [layer.bounds[0], layer.bounds[3]],
                  [layer.bounds[2], layer.bounds[3]],
                  [layer.bounds[2], layer.bounds[1]],
                  [layer.bounds[0], layer.bounds[1]]
                ]
              })
            }
            
            if (!map.value?.getLayer(layerId)) {
              map.value?.addLayer({
                id: layerId,
                type: 'raster',
                source: sourceId,
                paint: {
                  'raster-opacity': layer.style?.opacity ?? 0.85
                },
                layout: {
                  'visibility': layer.visible ? 'visible' : 'none'
                }
              })
            }
          }
          
          console.log(`Restored raster layer: ${layer.name}`)
          return
        }
        
        // 🔧 处理 GeoJSON 图层
        if (!layer.sourceData) return
        
        // 添加数据源
        if (!map.value?.getSource(sourceId)) {
          map.value?.addSource(sourceId, {
            type: 'geojson',
            data: layer.sourceData
          })
        }
        
        // 根据类型添加图层
        if (layer.type === 'polygon') {
          // 面填充
          if (!map.value?.getLayer(`${layerId}-fill`)) {
            map.value?.addLayer({
              id: `${layerId}-fill`,
              type: 'fill',
              source: sourceId,
              paint: {
                'fill-color': layer.style?.fillColor || layer.style?.color || '#3b82f6',
                'fill-opacity': layer.style?.fillOpacity ?? 0.5
              },
              layout: {
                'visibility': layer.visible ? 'visible' : 'none'
              }
            })
          }
          // 面边框
          if (!map.value?.getLayer(`${layerId}-outline`)) {
            map.value?.addLayer({
              id: `${layerId}-outline`,
              type: 'line',
              source: sourceId,
              paint: {
                'line-color': layer.style?.strokeColor || '#ffffff',
                'line-width': layer.style?.strokeWidth ?? 2
              },
              layout: {
                'visibility': layer.visible ? 'visible' : 'none'
              }
            })
          }
        } else if (layer.type === 'line') {
          if (!map.value?.getLayer(layerId)) {
            map.value?.addLayer({
              id: layerId,
              type: 'line',
              source: sourceId,
              paint: {
                'line-color': layer.style?.color || '#3b82f6',
                'line-width': layer.style?.width ?? 3
              },
              layout: {
                'visibility': layer.visible ? 'visible' : 'none'
              }
            })
          }
        } else if (layer.type === 'point') {
          if (!map.value?.getLayer(layerId)) {
            map.value?.addLayer({
              id: layerId,
              type: 'circle',
              source: sourceId,
              paint: {
                'circle-radius': layer.style?.radius ?? 6,
                'circle-color': layer.style?.color || '#3b82f6',
                'circle-stroke-width': 2,
                'circle-stroke-color': '#ffffff'
              },
              layout: {
                'visibility': layer.visible ? 'visible' : 'none'
              }
            })
          }
        }
        
        console.log(`Restored layer: ${layer.name}`)
      } catch (e) {
        console.error(`Failed to restore layer ${layer.name}:`, e)
      }
    })
    
    console.log(`Restored ${storeLayers.length} layers from store`)
  }
  
  // 监听 style.load 事件
  map.value.once('style.load', restoreLayers)
  
  // 备用：如果 style.load 已经触发，使用 idle 事件
  map.value.once('idle', () => {
    // 检查图层是否已恢复，如果没有则再次尝试
    if (storeLayers.length > 0 && !map.value?.getSource(`source-${storeLayers[0].id}`)) {
      console.log('Retrying layer restoration on idle...')
      restoreLayers()
    }
  })
  
  currentBasemap.value = basemapId
  showBasemapSelector.value = false
}

// 初始化地图
onMounted(() => {
  if (!mapContainer.value) return
  
  const defaultBasemap = basemaps.find(b => b.id === 'osm')!  // 默认使用 OSM
  
  map.value = new maplibregl.Map({
    container: mapContainer.value,
    style: createBasemapStyle(defaultBasemap),
    center: props.center || [116.4, 39.9],
    zoom: props.zoom || 10,
    pitch: 0,
    bearing: 0
  })
  
  // 添加控件
  map.value.addControl(new maplibregl.NavigationControl(), 'top-right')
  map.value.addControl(new maplibregl.ScaleControl({ maxWidth: 100 }), 'bottom-left')
  
  // 鼠标移动显示坐标
  map.value.on('mousemove', (e) => {
    const { lng, lat } = e.lngLat
    coordinates.value = `${lng.toFixed(5)}, ${lat.toFixed(5)}`
  })
  
  // 点击事件
  map.value.on('click', (e) => {
    const features = map.value?.queryRenderedFeatures(e.point)
    if (features && features.length > 0) {
      const feature = features[0] as unknown as GeoJSON.Feature
      mapStore.setSelectedFeature(feature)
      emit('feature-click', feature)
    }
  })
  
  // 地图加载完成
  map.value.on('load', () => {
    console.log('Map load event fired')
    if (map.value) {
      mapStore.setMap(map.value)
      emit('map-ready', map.value)
    }
  })
  
  // 如果地图已经加载完成（load 事件可能在监听器注册前触发）
  if (map.value.loaded()) {
    console.log('Map already loaded')
    mapStore.setMap(map.value)
    emit('map-ready', map.value)
  }
})

// 清理
onUnmounted(() => {
  map.value?.remove()
})

// 监听 center 变化
watch(() => props.center, (newCenter) => {
  if (newCenter && map.value) {
    map.value.setCenter(newCenter)
  }
})

// 方法
function zoomIn() {
  map.value?.zoomIn()
}

function zoomOut() {
  map.value?.zoomOut()
}

function resetView() {
  map.value?.flyTo({
    center: props.center || [116.4, 39.9],
    zoom: props.zoom || 10,
    pitch: 0,
    bearing: 0
  })
}

function toggle3D() {
  is3D.value = !is3D.value
  map.value?.easeTo({
    pitch: is3D.value ? 60 : 0,
    bearing: is3D.value ? -17.6 : 0
  })
}

// 暴露方法
defineExpose({
  getMap: () => map.value,
  flyTo: (options: maplibregl.FlyToOptions) => map.value?.flyTo(options),
  zoomIn,
  zoomOut,
  resetView,
  toggle3D
})
</script>

<template>
  <div class="map-container">
    <div ref="mapContainer" class="map"></div>
    
    <!-- 地图工具栏 -->
    <div class="map-toolbar">
      <button @click="zoomIn" title="放大" class="toolbar-btn">
        <span>+</span>
      </button>
      <button @click="zoomOut" title="缩小" class="toolbar-btn">
        <span>−</span>
      </button>
      <button @click="resetView" title="重置视图" class="toolbar-btn">
        <span>⌂</span>
      </button>
      <button 
        @click="toggle3D" 
        :class="['toolbar-btn', { active: is3D }]" 
        title="3D视图"
      >
        <span>3D</span>
      </button>
    </div>
    
    <!-- Basemap Switcher -->
    <div class="basemap-switcher">
      <button 
        class="basemap-trigger"
        @click="showBasemapSelector = !showBasemapSelector"
        :title="'Switch Basemap: ' + basemaps.find(b => b.id === currentBasemap)?.name"
      >
        <span class="basemap-icon">{{ basemaps.find(b => b.id === currentBasemap)?.icon }}</span>
        <span class="basemap-label">Basemap</span>
      </button>
      
      <Transition name="fade">
        <div v-if="showBasemapSelector" class="basemap-panel">
          <div class="basemap-title">Select Basemap</div>
          <div class="basemap-list">
            <button
              v-for="basemap in basemaps"
              :key="basemap.id"
              :class="['basemap-item', { active: currentBasemap === basemap.id }]"
              @click="switchBasemap(basemap.id)"
            >
              <span class="item-icon">{{ basemap.icon }}</span>
              <span class="item-name">{{ basemap.name }}</span>
              <span v-if="currentBasemap === basemap.id" class="item-check">✓</span>
            </button>
          </div>
        </div>
      </Transition>
    </div>
    
    <!-- 坐标显示 -->
    <div class="map-coordinates">
      {{ coordinates }}
    </div>
  </div>
</template>

<style scoped>
.map-container {
  position: relative;
  width: 100%;
  height: 100%;
  flex: 1;
}

.map {
  width: 100%;
  height: 100%;
}

.map-toolbar {
  position: absolute;
  top: 10px;
  left: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  z-index: 10;
}

.toolbar-btn {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 4px;
  background: var(--bg-panel, #16213e);
  color: var(--text-primary, #e2e8f0);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  transition: all 0.2s;
}

.toolbar-btn:hover {
  background: var(--primary-color, #3b82f6);
}

.toolbar-btn.active {
  background: var(--primary-color, #3b82f6);
}

.map-coordinates {
  position: absolute;
  bottom: 30px;
  left: 110px;
  padding: 4px 8px;
  background: rgba(22, 33, 62, 0.9);
  border-radius: 4px;
  font-size: 12px;
  font-family: monospace;
  color: var(--text-secondary, #94a3b8);
  z-index: 10;
}

/* 底图切换器 */
.basemap-switcher {
  position: absolute;
  bottom: 24px;
  right: 10px;
  z-index: 10;
}

.basemap-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: none;
  border-radius: 8px;
  background: rgba(22, 33, 62, 0.95);
  color: var(--text-primary, #e2e8f0);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.basemap-trigger:hover {
  background: rgba(59, 130, 246, 0.9);
}

.basemap-icon {
  font-size: 16px;
}

.basemap-label {
  font-size: 12px;
}

.basemap-panel {
  position: absolute;
  bottom: 48px;
  right: 0;
  width: 200px;
  background: rgba(22, 33, 62, 0.98);
  border-radius: 10px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
  overflow: hidden;
  backdrop-filter: blur(10px);
}

.basemap-title {
  padding: 10px 14px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, #94a3b8);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.basemap-list {
  padding: 6px;
}

.basemap-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-primary, #e2e8f0);
  cursor: pointer;
  font-size: 13px;
  text-align: left;
  transition: all 0.15s;
}

.basemap-item:hover {
  background: rgba(59, 130, 246, 0.2);
}

.basemap-item.active {
  background: rgba(59, 130, 246, 0.3);
}

.item-icon {
  font-size: 18px;
  width: 24px;
  text-align: center;
}

.item-name {
  flex: 1;
}

.item-check {
  color: var(--primary-color, #3b82f6);
  font-weight: bold;
}

/* 过渡动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>

