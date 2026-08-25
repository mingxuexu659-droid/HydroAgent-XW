/**
 * Map State Management
 */
import { defineStore } from 'pinia'
import { ref, computed, shallowRef } from 'vue'
import type { Map as MaplibreMap, LngLatBoundsLike } from 'maplibre-gl'
import maplibregl from 'maplibre-gl'
import * as turf from '@turf/turf'
import type { Layer, LayerStyle, LayerType } from '@/types'

// Import COG protocol support
import { cogProtocol } from '@geomatico/maplibre-cog-protocol'

// Register COG protocol (only needs to be executed once globally)
let cogProtocolRegistered = false
function ensureCogProtocol() {
  if (!cogProtocolRegistered && typeof maplibregl !== 'undefined') {
    try {
      maplibregl.addProtocol('cog', cogProtocol)
      cogProtocolRegistered = true
      console.log('✅ COG protocol registered')
    } catch (e) {
      console.warn('⚠️ COG protocol registration failed:', e)
    }
  }
}

// Color palette
const COLOR_PALETTE = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16',
  '#f97316', '#14b8a6', '#a855f7', '#f43f5e'
]

let colorIndex = 0

function getNextColor(): string {
  const color = COLOR_PALETTE[colorIndex % COLOR_PALETTE.length]
  colorIndex++
  return color ?? '#3b82f6'
}

export const useMapStore = defineStore('map', () => {
  // ============ State ============
  
  /** Map instance */
  const map = shallowRef<MaplibreMap | null>(null)
  
  /** Layer list */
  const layers = ref<Layer[]>([])
  
  /** Selected layer ID */
  const selectedLayerId = ref<string | null>(null)
  
  /** Selected feature */
  const selectedFeature = ref<GeoJSON.Feature | null>(null)
  
  /** Whether map is loaded */
  const isMapLoaded = ref(false)
  
  // ============ Getters ============
  
  /** Visible layers */
  const visibleLayers = computed(() => {
    return layers.value.filter((l: Layer) => l.visible)
  })
  
  /** Selected layer */
  const selectedLayer = computed(() => {
    if (!selectedLayerId.value) return null
    return layers.value.find((l: Layer) => l.id === selectedLayerId.value) || null
  })
  
  /** Layer count */
  const layerCount = computed(() => layers.value.length)
  
  // ============ Actions ============
  
  /**
   * Set map instance
   */
  function setMap(mapInstance: MaplibreMap): void {
    map.value = mapInstance
    isMapLoaded.value = true
  }
  
  /**
   * Add GeoJSON layer
   */
  async function addGeoJSONLayer(
    name: string,
    data: GeoJSON.FeatureCollection | string,
    style?: Partial<LayerStyle>
  ): Promise<Layer | null> {
    console.log('[addGeoJSONLayer] Start adding layer:', name, typeof data === 'string' ? data : '(data object)')
    
    if (!map.value) {
      console.error('[addGeoJSONLayer] Map not initialized')
      return null
    }
    
    // If URL, fetch data first
    let geojsonData: GeoJSON.FeatureCollection
    if (typeof data === 'string') {
      try {
        console.log('[addGeoJSONLayer] Fetching GeoJSON:', data)
        const response = await fetch(data)
        if (!response.ok) {
          console.error('[addGeoJSONLayer] Fetch failed:', response.status, response.statusText)
          return null
        }
        geojsonData = await response.json()
        console.log('[addGeoJSONLayer] Fetch success, feature count:', geojsonData.features?.length)
      } catch (e) {
        console.error('[addGeoJSONLayer] Fetch GeoJSON error:', e)
        return null
      }
    } else {
      geojsonData = data
    }
    
    const layerId = `layer-${Date.now()}`
    const sourceId = `source-${layerId}`
    
    // Validate coordinates within WGS-84 range
    console.log('[addGeoJSONLayer] Validating coordinates...')
    if (!validateGeoJSONCoordinates(geojsonData)) {
      console.error('[addGeoJSONLayer] Coordinate validation failed')
      return null
    }
    console.log('[addGeoJSONLayer] Coordinate validation passed')
    
    // Determine geometry type
    const geometryType = getGeometryType(geojsonData)
    const layerType = mapGeometryToLayerType(geometryType)
    const color = style?.color || getNextColor()
    
    console.log('[addGeoJSONLayer] Geometry type:', geometryType, 'Layer type:', layerType, 'Color:', color)
    
    try {
      // Check if source already exists, if so remove associated layers first
      if (map.value.getSource(sourceId)) {
        console.warn('[addGeoJSONLayer] Source already exists, removing old:', sourceId)
        // Remove possible layers
        const possibleLayers = [layerId, `${layerId}-fill`, `${layerId}-outline`]
        for (const lid of possibleLayers) {
          if (map.value.getLayer(lid)) {
            map.value.removeLayer(lid)
          }
        }
        map.value.removeSource(sourceId)
      }
      
      // Add data source
      console.log('[addGeoJSONLayer] Adding data source:', sourceId)
      map.value.addSource(sourceId, {
        type: 'geojson',
        data: geojsonData
      })
      console.log('[addGeoJSONLayer] Data source added successfully')
      
      // Add layer based on type
      if (layerType === 'polygon') {
        // Polygon fill
        map.value.addLayer({
          id: `${layerId}-fill`,
          type: 'fill',
          source: sourceId,
          paint: {
            'fill-color': style?.fillColor || color,
            'fill-opacity': style?.fillOpacity ?? 0.5
          }
        })
        // Polygon outline
        map.value.addLayer({
          id: `${layerId}-outline`,
          type: 'line',
          source: sourceId,
          paint: {
            'line-color': style?.strokeColor || '#ffffff',
            'line-width': style?.strokeWidth ?? 2
          }
        })
      } else if (layerType === 'line') {
        map.value.addLayer({
          id: layerId,
          type: 'line',
          source: sourceId,
          paint: {
            'line-color': color,
            'line-width': style?.width ?? 3
          }
        })
      } else if (layerType === 'point') {
        map.value.addLayer({
          id: layerId,
          type: 'circle',
          source: sourceId,
          paint: {
            'circle-radius': style?.radius ?? 6,
            'circle-color': color,
            'circle-stroke-width': 2,
            'circle-stroke-color': '#ffffff'
          }
        })
      }
      
      // Calculate bounds
      const bounds = turf.bbox(geojsonData) as [number, number, number, number]
      const featureCount = geojsonData.features?.length || 1
      
      console.log('[addGeoJSONLayer] Bounds:', bounds, 'Feature count:', featureCount)
      
      // Create layer object
      const layer: Layer = {
        id: layerId,
        name,
        type: layerType,
        visible: true,
        featureCount,
        bounds,
        style: {
          color,
          ...style
        },
        sourceData: geojsonData
      }
      
      layers.value.push(layer)
      console.log('[addGeoJSONLayer] Layer added to list, total:', layers.value.length)
      
      // Zoom to layer
      zoomToLayer(layerId)
      console.log('[addGeoJSONLayer] Layer added successfully:', layerId)
      
      return layer
    } catch (e) {
      console.error('[addGeoJSONLayer] Add layer error:', e)
      return null
    }
  }
  
  /**
   * Add raster layer (supports GeoTIFF and PNG)
   * 
   * @param name Layer name
   * @param url File URL (supports .tif/.tiff and .png)
   * @param bounds Geographic extent [west, south, east, north]
   * @param format Optional, specify format 'geotiff' | 'png'
   */
  async function addRasterLayer(
    name: string,
    url: string,
    bounds: [number, number, number, number],
    format?: string
  ): Promise<Layer | null> {
    console.log('[addRasterLayer] Adding raster layer:', name, url, bounds, format)
    
    if (!map.value) {
      console.error('[addRasterLayer] Map not initialized')
      return null
    }
    
    // Ensure COG protocol is registered
    ensureCogProtocol()
    
    try {
      const layerId = `raster-${Date.now()}`
      const sourceId = `source-${layerId}`
      
      // Determine if COG/GeoTIFF or PNG
      const isCogOrTiff = format === 'cog' || 
                          format === 'geotiff' ||
                          url.toLowerCase().endsWith('.tif') || 
                          url.toLowerCase().endsWith('.tiff')
      
      if (isCogOrTiff) {
        // Use COG protocol to load COG/GeoTIFF
        console.log('[addRasterLayer] Using COG protocol to load raster:', url)
        
        // Build full URL (needs to be absolute path)
        let fullUrl = url
        if (url.startsWith('/')) {
          fullUrl = `${window.location.origin}${url}`
        }
        
        console.log('[addRasterLayer] Full URL:', fullUrl)
        console.log('[addRasterLayer] COG URL:', `cog://${fullUrl}`)
        
        // Add COG data source
        // Use cog:// protocol prefix
        map.value.addSource(sourceId, {
          type: 'raster',
          tiles: [`cog://${fullUrl}`],
          tileSize: 256
        })
        
        // Add raster layer
        map.value.addLayer({
          id: layerId,
          type: 'raster',
          source: sourceId,
          paint: {
            'raster-opacity': 0.85,
            'raster-resampling': 'nearest'
          }
        })
        
        console.log('[addRasterLayer] COG layer added')
      } else {
        // PNG image: use image source
        console.log('[addRasterLayer] Using image source to load PNG')
        
        map.value.addSource(sourceId, {
          type: 'image',
          url: url,
          coordinates: [
            [bounds[0], bounds[3]],  // Top-left [west, north]
            [bounds[2], bounds[3]],  // Top-right [east, north]
            [bounds[2], bounds[1]],  // Bottom-right [east, south]
            [bounds[0], bounds[1]]   // Bottom-left [west, south]
          ]
        })
        
        map.value.addLayer({
          id: layerId,
          type: 'raster',
          source: sourceId,
          paint: {
            'raster-opacity': 0.85
          }
        })
        
        console.log('[addRasterLayer] PNG layer added (image source)')
      }
      
      // Create layer object
      const layer: Layer = {
        id: layerId,
        name,
        type: 'raster' as any,
        visible: true,
        featureCount: 1,
        bounds,
        style: {
          opacity: 0.85
        },
        // Save raster layer source info for restoration after basemap switch
        rasterSource: {
          url,
          format: isCogOrTiff ? 'cog' : 'png'
        }
      }
      
      layers.value.push(layer)
      console.log('[addRasterLayer] Raster layer added, total:', layers.value.length)
      
      // Zoom to layer
      map.value.fitBounds(bounds as LngLatBoundsLike, {
        padding: 50,
        maxZoom: 15
      })
      
      return layer
    } catch (e) {
      console.error('[addRasterLayer] Failed to add raster layer:', e)
      return null
    }
  }
  
  /**
   * Toggle layer visibility
   */
  function toggleLayer(layerId: string): void {
    const layer = layers.value.find((l: Layer) => l.id === layerId)
    if (!layer || !map.value) return
    
    layer.visible = !layer.visible
    const visibility = layer.visible ? 'visible' : 'none'
    
    if (layer.type === 'polygon') {
      if (map.value.getLayer(`${layerId}-fill`)) {
        map.value.setLayoutProperty(`${layerId}-fill`, 'visibility', visibility)
      }
      if (map.value.getLayer(`${layerId}-outline`)) {
        map.value.setLayoutProperty(`${layerId}-outline`, 'visibility', visibility)
      }
    } else if (layer.type === 'raster') {
      // Raster layer uses layerId directly
      if (map.value.getLayer(layerId)) {
        map.value.setLayoutProperty(layerId, 'visibility', visibility)
      }
    } else {
      if (map.value.getLayer(layerId)) {
        map.value.setLayoutProperty(layerId, 'visibility', visibility)
      }
    }
  }
  
  /**
   * Remove layer
   */
  function removeLayer(layerId: string): void {
    const layer = layers.value.find((l: Layer) => l.id === layerId)
    if (!layer || !map.value) return
    
    // Remove map layer
    if (layer.type === 'polygon') {
      if (map.value.getLayer(`${layerId}-fill`)) {
        map.value.removeLayer(`${layerId}-fill`)
      }
      if (map.value.getLayer(`${layerId}-outline`)) {
        map.value.removeLayer(`${layerId}-outline`)
      }
    } else if (layer.type === 'raster') {
      // Raster layer uses layerId directly
      if (map.value.getLayer(layerId)) {
        map.value.removeLayer(layerId)
      }
    } else {
      if (map.value.getLayer(layerId)) {
        map.value.removeLayer(layerId)
      }
    }
    
    // Remove data source
    const sourceId = `source-${layerId}`
    if (map.value.getSource(sourceId)) {
      map.value.removeSource(sourceId)
    }
    
    // Remove from list
    const index = layers.value.findIndex((l: Layer) => l.id === layerId)
    if (index !== -1) {
      layers.value.splice(index, 1)
    }
    
    // Clear selection
    if (selectedLayerId.value === layerId) {
      selectedLayerId.value = null
    }
  }
  
  /**
   * Zoom to layer
   */
  function zoomToLayer(layerId: string): void {
    const layer = layers.value.find((l: Layer) => l.id === layerId)
    if (!layer || !map.value || !layer.bounds) return
    
    map.value.fitBounds(layer.bounds as LngLatBoundsLike, {
      padding: 50,
      maxZoom: 15
    })
  }
  
  /**
   * Update layer style
   */
  function updateLayerStyle(layerId: string, style: Partial<LayerStyle>): void {
    const layer = layers.value.find((l: Layer) => l.id === layerId)
    if (!layer || !map.value) return
    
    if (layer.type === 'polygon') {
      if (style.fillColor) {
        map.value.setPaintProperty(`${layerId}-fill`, 'fill-color', style.fillColor)
      }
      if (style.fillOpacity !== undefined) {
        map.value.setPaintProperty(`${layerId}-fill`, 'fill-opacity', style.fillOpacity)
      }
      if (style.strokeColor) {
        map.value.setPaintProperty(`${layerId}-outline`, 'line-color', style.strokeColor)
      }
      if (style.strokeWidth !== undefined) {
        map.value.setPaintProperty(`${layerId}-outline`, 'line-width', style.strokeWidth)
      }
    } else if (layer.type === 'line') {
      if (style.color) {
        map.value.setPaintProperty(layerId, 'line-color', style.color)
      }
      if (style.width !== undefined) {
        map.value.setPaintProperty(layerId, 'line-width', style.width)
      }
    } else if (layer.type === 'point') {
      if (style.color) {
        map.value.setPaintProperty(layerId, 'circle-color', style.color)
      }
      if (style.radius !== undefined) {
        map.value.setPaintProperty(layerId, 'circle-radius', style.radius)
      }
    }
    
    layer.style = { ...layer.style, ...style }
  }
  
  /**
   * Select layer
   */
  function selectLayer(layerId: string | null): void {
    selectedLayerId.value = layerId
  }
  
  /**
   * Set selected feature
   */
  function setSelectedFeature(feature: GeoJSON.Feature | null): void {
    selectedFeature.value = feature
  }
  
  /**
   * Clear all layers
   */
  function clearAllLayers(): void {
    const layerIds = layers.value.map((l: Layer) => l.id)
    layerIds.forEach((id: string) => removeLayer(id))
  }
  
  /**
   * Fly to specified location
   */
  function flyTo(lng: number, lat: number, zoom?: number): void {
    if (!map.value) return
    
    map.value.flyTo({
      center: [lng, lat],
      zoom: zoom ?? map.value.getZoom() ?? 10
    })
  }
  
  // ============ Helper Functions ============
  
  function validateGeoJSONCoordinates(geojson: GeoJSON.FeatureCollection): boolean {
    if (!geojson.features || geojson.features.length === 0) {
      return true // Empty data treated as valid
    }
    
    // Find the first feature with geometry data
    let feature = null
    for (const f of geojson.features) {
      if (f && f.geometry) {
        feature = f
        break
      }
    }
    
    // If all features have no geometry data (attribute-only file, e.g. statistics), treat as invalid
    if (!feature || !feature.geometry) {
      console.warn('[validateGeoJSONCoordinates] All features have no geometry data (possibly statistics file)')
      return false
    }
    
    // Get the first coordinate point
    let coords: number[] | null = null
    const geom = feature.geometry as any
    
    if (geom.type === 'Point') {
      coords = geom.coordinates
    } else if (geom.type === 'LineString' || geom.type === 'MultiPoint') {
      coords = geom.coordinates[0]
    } else if (geom.type === 'Polygon' || geom.type === 'MultiLineString') {
      coords = geom.coordinates[0]?.[0]
    } else if (geom.type === 'MultiPolygon') {
      coords = geom.coordinates[0]?.[0]?.[0]
    }
    
    if (!coords || coords.length < 2) return false
    
    const lng = coords[0]
    const lat = coords[1]
    
    if (lng === undefined || lat === undefined) return false
    
    // Check if coordinates are within valid WGS-84 range
    // Longitude: -180 to 180, Latitude: -90 to 90
    const isValid = lng >= -180 && lng <= 180 && lat >= -90 && lat <= 90
    
    if (!isValid) {
      console.warn(`Invalid coordinates: [${lng}, ${lat}] - possibly wrong CRS (not WGS-84)`)
    }
    
    return isValid
  }
  
  function getGeometryType(geojson: GeoJSON.FeatureCollection): string {
    if (geojson.features && geojson.features.length > 0) {
      const firstFeature = geojson.features[0]
      return firstFeature?.geometry?.type || 'Unknown'
    }
    return 'Unknown'
  }
  
  function mapGeometryToLayerType(geometryType: string): LayerType {
    const mapping: Record<string, LayerType> = {
      'Point': 'point',
      'MultiPoint': 'point',
      'LineString': 'line',
      'MultiLineString': 'line',
      'Polygon': 'polygon',
      'MultiPolygon': 'polygon'
    }
    return mapping[geometryType] || 'polygon'
  }
  
  return {
    // State
    map,
    layers,
    selectedLayerId,
    selectedFeature,
    isMapLoaded,
    
    // Getters
    visibleLayers,
    selectedLayer,
    layerCount,
    
    // Actions
    setMap,
    addGeoJSONLayer,
    addRasterLayer,
    toggleLayer,
    removeLayer,
    zoomToLayer,
    updateLayerStyle,
    selectLayer,
    setSelectedFeature,
    clearAllLayers,
    flyTo
  }
})

