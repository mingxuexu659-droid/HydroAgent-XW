<script setup lang="ts">
/**
 * Layer Panel Component
 */
import { ref, computed } from 'vue'
import { useMapStore } from '@/stores/map'

// Store
const mapStore = useMapStore()

// State
const fileInput = ref<HTMLInputElement | null>(null)
const isLoading = ref(false)
const errorMessage = ref<string | null>(null)

// Computed
const layers = computed(() => mapStore.layers)

// Get type label
function getTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    point: 'Point',
    line: 'Line',
    polygon: 'Polygon',
    raster: 'Raster'
  }
  return labels[type] || type
}

// Trigger file selection (supports multi-select, auto-combine Shapefile)
function triggerFileSelect() {
  fileInput.value?.click()
}

// Select folder and load all Shapefiles in it (backup function)
async function selectShapefileFolder() {
  try {
    // @ts-ignore - showDirectoryPicker is experimental API
    const dirHandle = await window.showDirectoryPicker({
      mode: 'read'
    })
    
    errorMessage.value = null
    isLoading.value = true
    
    // Collect all Shapefiles in folder
    const shapefiles = new Map<string, File[]>()
    const otherFiles: File[] = []
    
    for await (const entry of dirHandle.values()) {
      if (entry.kind === 'file') {
        const file = await entry.getFile()
        const name = file.name.toLowerCase()
        
        // Check if it's a Shapefile related file
        const shpMatch = name.match(/^(.+)\.(shp|dbf|shx|prj|cpg|sbn|sbx)$/i)
        
        if (shpMatch) {
          const baseName = shpMatch[1]
          if (!shapefiles.has(baseName)) {
            shapefiles.set(baseName, [])
          }
          shapefiles.get(baseName)!.push(file)
        } else if (name.endsWith('.geojson') || name.endsWith('.json') || 
                   name.endsWith('.tif') || name.endsWith('.tiff') ||
                   name.endsWith('.zip')) {
          otherFiles.push(file)
        }
      }
    }
    
    // Load found Shapefiles
    let loadedCount = 0
    for (const [baseName, files] of shapefiles) {
      const hasShp = files.some(f => f.name.toLowerCase().endsWith('.shp'))
      const hasDbf = files.some(f => f.name.toLowerCase().endsWith('.dbf'))
      const hasShx = files.some(f => f.name.toLowerCase().endsWith('.shx'))
      
      if (hasShp && hasDbf && hasShx) {
        console.log(`📦 Loading Shapefile: ${baseName} (${files.length} files)`)
        await uploadShapefileFiles(baseName, files)
        loadedCount++
      } else if (hasShp) {
        console.warn(`⚠️ Incomplete Shapefile: ${baseName}`)
      }
    }
    
    // Load other files
    for (const file of otherFiles) {
      await loadFile(file)
      loadedCount++
    }
    
    if (loadedCount === 0) {
      errorMessage.value = 'No loadable geospatial data files found in folder'
    } else {
      console.log(`✅ Loaded ${loadedCount} layers total`)
    }
    
  } catch (e: any) {
    if (e.name !== 'AbortError') {
      errorMessage.value = (e as Error).message
    }
  } finally {
    isLoading.value = false
  }
}

// Handle file selection (supports multi-select, auto-combine Shapefile)
async function handleFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files
  
  if (!files || files.length === 0) return
  
  errorMessage.value = null
  isLoading.value = true
  
  try {
    const fileArray = Array.from(files)
    
    // Group: Shapefile components and other files
    const shapefileGroups = new Map<string, File[]>()
    const otherFiles: File[] = []
    
    for (const file of fileArray) {
      const name = file.name.toLowerCase()
      const shpMatch = name.match(/^(.+)\.(shp|dbf|shx|prj|cpg|sbn|sbx)$/i)
      
      if (shpMatch && shpMatch[1]) {
        const baseName = shpMatch[1]
        if (!shapefileGroups.has(baseName)) {
          shapefileGroups.set(baseName, [])
        }
        shapefileGroups.get(baseName)?.push(file)
      } else {
        otherFiles.push(file)
      }
    }
    
    // Load Shapefile groups
    for (const [baseName, shpFiles] of shapefileGroups) {
      const hasShp = shpFiles.some(f => f.name.toLowerCase().endsWith('.shp'))
      const hasDbf = shpFiles.some(f => f.name.toLowerCase().endsWith('.dbf'))
      const hasShx = shpFiles.some(f => f.name.toLowerCase().endsWith('.shx'))
      
      if (hasShp && hasDbf && hasShx) {
        console.log(`📦 Loading Shapefile: ${baseName} (${shpFiles.length} files)`)
        await uploadShapefileFiles(baseName, shpFiles)
      } else if (hasShp) {
        // Only .shp, prompt user to select dependency files
        const shpFile = shpFiles.find(f => f.name.toLowerCase().endsWith('.shp'))!
        await loadShapefileWithDependencies(shpFile)
      }
    }
    
    // Load other files
    for (const file of otherFiles) {
      await loadFile(file)
    }
  } catch (err) {
    errorMessage.value = (err as Error).message
  } finally {
    isLoading.value = false
    // Clear input to allow re-selecting same file
    input.value = ''
  }
}

// Load single file
async function loadFile(file: File) {
  const fileName = file.name.toLowerCase()
  
  if (fileName.endsWith('.geojson') || fileName.endsWith('.json')) {
    await loadGeoJSON(file)
  } else if (fileName.endsWith('.zip')) {
    // Shapefile packed in zip file
    await loadShapefileZip(file)
  } else if (fileName.endsWith('.tif') || fileName.endsWith('.tiff')) {
    // GeoTIFF raster file
    await loadRasterFile(file)
  } else if (fileName.endsWith('.gpkg')) {
    // GeoPackage file
    await loadGeoPackage(file)
  } else if (fileName.endsWith('.shp')) {
    // Shapefile - auto read dependency files from same directory
    await loadShapefileWithDependencies(file)
  } else if (fileName.endsWith('.dbf') || fileName.endsWith('.shx') || 
             fileName.endsWith('.prj') || fileName.endsWith('.cpg') || 
             fileName.endsWith('.sbn') || fileName.endsWith('.sbx')) {
    // Shapefile dependency files - ignore (will be loaded with .shp)
    console.log(`Skipping Shapefile dependency file: ${file.name}`)
  } else {
    throw new Error(`Unsupported file format: ${file.name}\nSupported: .geojson, .json, .gpkg, .tif, .tiff, .shp, .zip`)
  }
}

// Load GeoJSON file
async function loadGeoJSON(file: File) {
  const text = await file.text()
  
  let parsed: any
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new Error(`Failed to parse JSON: ${file.name}`)
  }
  
  // Validate GeoJSON structure
  if (!parsed.type) {
    throw new Error(`Invalid GeoJSON: missing type property`)
  }
  
  // Convert to FeatureCollection
  let geojson: GeoJSON.FeatureCollection
  
  if (parsed.type === 'FeatureCollection') {
    geojson = parsed
  } else if (parsed.type === 'Feature') {
    // Single Feature, convert to FeatureCollection
    geojson = {
      type: 'FeatureCollection',
      features: [parsed]
    }
  } else {
    // If it's Geometry, wrap as Feature
    geojson = {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        properties: {},
        geometry: parsed
      }]
    }
  }
  
  // Check if map is loaded
  if (!mapStore.isMapLoaded) {
    throw new Error('Map not fully loaded yet, please try again later')
  }
  
  // Use filename (without extension) as layer name
  const layerName = file.name.replace(/\.(geojson|json)$/i, '')
  
  const layer = await mapStore.addGeoJSONLayer(layerName, geojson)
  
  if (!layer) {
    throw new Error(`Failed to load layer: ${file.name}\nCRS may be incorrect (requires WGS-84)`)
  }
}

// Load GeoPackage file
async function loadGeoPackage(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  
  try {
    const response = await fetch('/api/data/convert-geopackage', {
      method: 'POST',
      body: formData
    })
    
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'GeoPackage conversion failed')
    }
    
    const geojson = await response.json()
    
    // Check if map is loaded
    if (!mapStore.isMapLoaded) {
      throw new Error('Map not fully loaded yet, please try again later')
    }
    
    const layerName = file.name.replace(/\.gpkg$/i, '')
    const layer = await mapStore.addGeoJSONLayer(layerName, geojson)
    
    if (!layer) {
      throw new Error(`Failed to load layer: ${file.name}`)
    }
  } catch (err) {
    if ((err as Error).message.includes('fetch')) {
      throw new Error('GeoPackage conversion service unavailable')
    }
    throw err
  }
}

// Load Shapefile ZIP file
async function loadShapefileZip(file: File) {
  // Need backend API to handle Shapefile conversion
  const formData = new FormData()
  formData.append('file', file)
  
  try {
    const response = await fetch('/api/data/convert-shapefile', {
      method: 'POST',
      body: formData
    })
    
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Shapefile conversion failed')
    }
    
    const geojson = await response.json()
    
    const layerName = file.name.replace(/\.zip$/i, '')
    const layer = await mapStore.addGeoJSONLayer(layerName, geojson)
    
    if (!layer) {
      throw new Error(`Failed to load layer: ${file.name}`)
    }
  } catch (err) {
    if ((err as Error).message.includes('fetch')) {
      throw new Error('Shapefile conversion service unavailable, please use GeoJSON format')
    }
    throw err
  }
}

// Use File System Access API to auto-load Shapefile and its dependencies
async function loadShapefileWithDependencies(shpFile: File) {
  const baseName = shpFile.name.replace(/\.shp$/i, '')
  
  // Try to use File System Access API to get files from same directory
  // @ts-ignore - showOpenFilePicker is experimental API
  if (typeof window.showOpenFilePicker === 'function' && (shpFile as any).handle) {
    try {
      // If file has handle, try to get parent directory
      // @ts-ignore
      const dirHandle = await (shpFile as any).handle.getParent()
      const files: File[] = [shpFile]
      
      for await (const entry of dirHandle.values()) {
        if (entry.kind === 'file') {
          const name = entry.name.toLowerCase()
          const fileBaseName = name.replace(/\.(dbf|shx|prj|cpg|sbn|sbx|shp\.xml)$/i, '')
          
          if (fileBaseName === baseName.toLowerCase()) {
            const file = await entry.getFile()
            files.push(file)
          }
        }
      }
      
      await uploadShapefileFiles(baseName, files)
      return
    } catch (e) {
      console.log('File System Access API unavailable, using fallback')
    }
  }
  
  // Fallback: prompt user to select missing files
  const missingFiles = await promptForShapefileDependencies(baseName)
  
  if (missingFiles) {
    const allFiles = [shpFile, ...missingFiles]
    await uploadShapefileFiles(baseName, allFiles)
  }
}

// Prompt user to select Shapefile dependency files
async function promptForShapefileDependencies(baseName: string): Promise<File[] | null> {
  // Create temporary file picker
  return new Promise((resolve) => {
    const tempInput = document.createElement('input')
    tempInput.type = 'file'
    tempInput.multiple = true
    tempInput.accept = '.dbf,.shx,.prj,.cpg'
    
    // Show prompt
    const message = `Please select dependency files for "${baseName}":\n• ${baseName}.dbf (required)\n• ${baseName}.shx (required)\n• ${baseName}.prj (optional)\n• ${baseName}.cpg (optional)`
    
    if (!confirm(message + '\n\nClick "OK" to select files, or "Cancel" to skip')) {
      resolve(null)
      return
    }
    
    tempInput.onchange = (e) => {
      const files = (e.target as HTMLInputElement).files
      if (files && files.length > 0) {
        resolve(Array.from(files))
      } else {
        resolve(null)
      }
    }
    
    tempInput.click()
  })
}

// Upload Shapefile file group
async function uploadShapefileFiles(baseName: string, files: File[]) {
  // Check required files
  const hasDbf = files.some(f => f.name.toLowerCase().endsWith('.dbf'))
  const hasShx = files.some(f => f.name.toLowerCase().endsWith('.shx'))
  
  if (!hasDbf || !hasShx) {
    const missing: string[] = []
    if (!hasDbf) missing.push('.dbf')
    if (!hasShx) missing.push('.shx')
    throw new Error(`Shapefile missing required files: ${missing.join(', ')}`)
  }
  
  const formData = new FormData()
  for (const file of files) {
    formData.append('files', file)
  }
  
  const response = await fetch('/api/data/convert-shapefile-multi', {
    method: 'POST',
    body: formData
  })
  
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Shapefile conversion failed')
  }
  
  const geojson = await response.json()
  
  const layer = await mapStore.addGeoJSONLayer(baseName, geojson)
  
  if (!layer) {
    throw new Error(`Failed to load layer: ${baseName}`)
  }
}

// Load raster file (GeoTIFF)
async function loadRasterFile(file: File) {
  // Upload to backend for conversion
  const formData = new FormData()
  formData.append('file', file)
  
  try {
    const response = await fetch('/api/data/convert-raster', {
      method: 'POST',
      body: formData
    })
    
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Raster conversion failed')
    }
    
    const result = await response.json()
    
    // Result contains: { url, bounds, format, name }
    const layerName = result.name || file.name.replace(/\.(tif|tiff)$/i, '')
    const layer = await mapStore.addRasterLayer(
      layerName, 
      result.url, 
      result.bounds, 
      result.format || 'png'
    )
    
    if (!layer) {
      throw new Error(`Failed to load raster layer: ${file.name}`)
    }
  } catch (err) {
    if ((err as Error).message.includes('fetch')) {
      throw new Error('Raster conversion service unavailable')
    }
    throw err
  }
}

// Handle drag and drop
function handleDragOver(event: DragEvent) {
  event.preventDefault()
  event.stopPropagation()
}

async function handleDrop(event: DragEvent) {
  event.preventDefault()
  event.stopPropagation()
  
  const files = event.dataTransfer?.files
  if (!files || files.length === 0) return
  
  errorMessage.value = null
  isLoading.value = true
  
  try {
    for (const file of Array.from(files)) {
      await loadFile(file)
    }
  } catch (err) {
    errorMessage.value = (err as Error).message
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div 
    class="layer-panel"
    @dragover="handleDragOver"
    @drop="handleDrop"
  >
    <div class="panel-header">
      <h3 class="section-title">
        <span class="icon">📚</span>
        Layer Manager
        <span class="layer-count">({{ layers.length }})</span>
      </h3>
      
      <!-- Add data button -->
      <button 
        class="add-btn"
        @click="triggerFileSelect"
        :disabled="isLoading"
        title="Add data (supports GeoJSON, GPKG, TIF, Shapefile)"
      >
        <span v-if="isLoading" class="spinner"></span>
        <span v-else>📂 Add</span>
      </button>
      
      <!-- Hidden file input -->
      <input
        ref="fileInput"
        type="file"
        accept=".geojson,.json,.zip,.tif,.tiff,.shp,.dbf,.shx,.prj,.cpg,.gpkg"
        multiple
        style="display: none"
        @change="handleFileSelect"
      />
    </div>
    
    <!-- Error alert -->
    <div v-if="errorMessage" class="error-alert">
      <span>⚠️</span>
      <span>{{ errorMessage }}</span>
      <button class="close-btn" @click="errorMessage = null">✕</button>
    </div>

    <div class="layers-list" v-if="layers.length > 0">
      <div 
        v-for="layer in layers" 
        :key="layer.id"
        class="layer-item"
        :class="{ inactive: !layer.visible }"
      >
        <!-- Visibility toggle -->
        <button 
          class="visibility-toggle"
          @click="mapStore.toggleLayer(layer.id)"
          :title="layer.visible ? 'Hide layer' : 'Show layer'"
        >
          <span v-if="layer.visible">👁</span>
          <span v-else>👁‍🗨</span>
        </button>

        <!-- Layer info -->
        <div class="layer-info">
          <div class="layer-name">{{ layer.name }}</div>
          <div class="layer-meta">
            <span class="layer-type" :class="layer.type">
              {{ getTypeLabel(layer.type) }}
            </span>
            <span class="feature-count" v-if="layer.featureCount">
              {{ layer.featureCount }} features
            </span>
          </div>
        </div>

        <!-- Action buttons -->
        <div class="layer-actions">
          <button 
            class="action-btn"
            @click="mapStore.zoomToLayer(layer.id)"
            title="Zoom to layer"
          >
            🔍
          </button>
          <button 
            class="action-btn danger"
            @click="mapStore.removeLayer(layer.id)"
            title="Remove layer"
          >
            🗑
          </button>
        </div>
      </div>
    </div>

    <div 
      class="empty-state drop-zone"
      :class="{ 'drag-active': false }"
      v-else
    >
      <span class="empty-icon">📂</span>
      <p>No layers yet</p>
      <p class="empty-hint">
        Click "Add" to load data<br/>
        Supports: GeoJSON, GPKG, TIF, ZIP<br/>
        Shapefile: select shp+dbf+shx
      </p>
    </div>
  </div>
</template>

<style scoped>
.layer-panel {
  padding: 0.75rem;
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
  margin: 0;
}

.icon {
  font-size: 0.875rem;
}

.layer-count {
  color: var(--text-secondary, #94a3b8);
  font-weight: normal;
  font-size: 0.75rem;
}

.add-btn {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.375rem 0.625rem;
  border: none;
  border-radius: 6px;
  background: var(--primary-color, #3b82f6);
  color: white;
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.add-btn:hover:not(:disabled) {
  background: #2563eb;
}

.add-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-alert {
  display: flex;
  align-items: flex-start;
  gap: 0.375rem;
  padding: 0.5rem;
  margin-bottom: 0.5rem;
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 6px;
  font-size: 0.6875rem;
  color: #fca5a5;
}

.error-alert .close-btn {
  margin-left: auto;
  padding: 0;
  border: none;
  background: none;
  color: #fca5a5;
  cursor: pointer;
  font-size: 0.75rem;
  line-height: 1;
}

.error-alert .close-btn:hover {
  color: white;
}

.layers-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  flex: 1;
  overflow-y: auto;
}

.layer-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 8px;
  transition: all 0.2s;
}

.layer-item:hover {
  background: rgba(59, 130, 246, 0.1);
}

.layer-item.inactive {
  opacity: 0.5;
}

.visibility-toggle {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 1rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background 0.2s;
}

.visibility-toggle:hover {
  background: var(--bg-panel, #16213e);
}

.layer-info {
  flex: 1;
  min-width: 0;
}

.layer-name {
  font-size: 0.875rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary, #e2e8f0);
}

.layer-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.layer-type {
  font-size: 0.625rem;
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  text-transform: uppercase;
  font-weight: 600;
}

.layer-type.point {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.layer-type.line {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
}

.layer-type.polygon {
  background: rgba(16, 185, 129, 0.2);
  color: #10b981;
}

.layer-type.raster {
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.feature-count {
  font-size: 0.75rem;
  color: var(--text-secondary, #94a3b8);
}

.layer-actions {
  display: flex;
  gap: 0.25rem;
  opacity: 0;
  transition: opacity 0.2s;
}

.layer-item:hover .layer-actions {
  opacity: 1;
}

.action-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 0.75rem;
  border-radius: 4px;
  transition: background 0.2s;
}

.action-btn:hover {
  background: var(--bg-panel, #16213e);
}

.action-btn.danger:hover {
  background: rgba(239, 68, 68, 0.2);
}

.empty-state {
  text-align: center;
  padding: 1.5rem 1rem;
  color: var(--text-secondary, #94a3b8);
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.empty-state.drop-zone {
  border: 2px dashed var(--border-color, #334155);
  border-radius: 8px;
  margin-top: 0.5rem;
  transition: all 0.2s;
}

.empty-state.drop-zone:hover,
.empty-state.drag-active {
  border-color: var(--primary-color, #3b82f6);
  background: rgba(59, 130, 246, 0.05);
}

.empty-icon {
  font-size: 1.75rem;
  display: block;
  margin-bottom: 0.375rem;
}

.empty-hint {
  font-size: 0.6875rem;
  margin-top: 0.25rem;
  line-height: 1.5;
}
</style>

