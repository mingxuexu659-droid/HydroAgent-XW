<script setup lang="ts">
/**
 * Main Application Component
 */
import { ref, computed, watch } from 'vue'
import { useTaskStore } from '@/stores/task'
import { useMapStore } from '@/stores/map'
import QueryInput from '@/components/analysis/QueryInput.vue'
import TaskProgress from '@/components/analysis/TaskProgress.vue'
import TaskLogs from '@/components/analysis/TaskLogs.vue'
import CodeViewer from '@/components/analysis/CodeViewer.vue'
import MapContainer from '@/components/map/MapContainer.vue'
import LayerPanel from '@/components/map/LayerPanel.vue'
import FeatureProperties from '@/components/map/FeatureProperties.vue'
import MessageModal from '@/components/common/MessageModal.vue'
import DataCatalog from '@/components/data/DataCatalog.vue'
import TaskHistory from '@/components/history/TaskHistory.vue'
import ApiDocs from '@/components/docs/ApiDocs.vue'
import type { AnalysisRequest, CatalogEntry, Task } from '@/types'

// Stores
const taskStore = useTaskStore()
const mapStore = useMapStore()

// State
const codeCollapsed = ref(false)  // Code expanded by default
const showDataCatalog = ref(false)  // Data catalog display state
const showTaskHistory = ref(false)  // History display state
const showApiDocs = ref(false)  // API docs display state
const activeNav = ref('analysis')  // Current active nav: analysis, catalog, history, docs

// Message modal state
const showModal = ref(false)
const modalTitle = ref('')
const modalMessage = ref('')
const modalType = ref<'success' | 'error' | 'info'>('info')

// Show message modal
function showMessage(title: string, message: string, type: 'success' | 'error' | 'info' = 'info') {
  modalTitle.value = title
  modalMessage.value = message
  modalType.value = type
  showModal.value = true
}

// Close message modal
function closeModal() {
  showModal.value = false
}

// Navigation switch
function switchNav(nav: string) {
  activeNav.value = nav
  showDataCatalog.value = nav === 'catalog'
  showTaskHistory.value = nav === 'history'
  showApiDocs.value = nav === 'docs'
}

// Load data from catalog to map
async function handleLoadCatalogData(entry: CatalogEntry) {
  console.log('[App] Loading data from catalog:', entry.name, entry.file_path, entry.file_type)
  
  try {
    // Determine loading method based on file type
    const fileType = entry.file_type?.toLowerCase() || ''
    const isVector = ['geojson', 'shapefile', 'geopackage', 'shp', 'gpkg'].some(t => fileType.includes(t))
    const isRaster = ['geotiff', 'tif', 'tiff'].some(t => fileType.includes(t))
    
    if (isVector) {
      // Vector data: try to load via URL
      // Build URL - preserve subdirectory structure
      let url = ''
      const filePath = entry.file_path.replace(/\\/g, '/')
      
      if (filePath.includes('downloaded_data')) {
        // Extract relative path after downloaded_data (including subdirectories)
        const match = filePath.match(/downloaded_data[/\\](.+)$/)
        if (match) {
          const relativePath = match[1]
          url = `/downloaded/${encodeURIComponent(relativePath).replace(/%2F/g, '/')}`
        }
      } else if (filePath.includes('output/results')) {
        const match = filePath.match(/output[/\\]results[/\\](.+)$/)
        if (match) {
          const relativePath = match[1]
          url = `/results/${encodeURIComponent(relativePath).replace(/%2F/g, '/')}`
        }
      }
      
      console.log('[App] Built URL:', url)
      
      if (url && entry.file_type?.toLowerCase() === 'geojson') {
        const layer = await mapStore.addGeoJSONLayer(entry.name, url)
        if (layer) {
          showMessage('Load Success', `Added "${entry.name}" to map`, 'success')
          // Close data catalog, return to analysis view
          showDataCatalog.value = false
          activeNav.value = 'analysis'
        } else {
          showMessage('Load Failed', `Cannot load "${entry.name}", please check file format`, 'error')
        }
      } else {
        showMessage('Notice', `This file needs to be viewed in QGIS: ${entry.name}`, 'info')
      }
    } else if (isRaster) {
      // Raster data: convert to PNG via backend first
      console.log('[App] Starting raster file conversion:', entry.file_path)
      
      try {
        const formData = new FormData()
        formData.append('file_path', entry.file_path)
        
        const response = await fetch('/api/data/convert-existing-raster', {
          method: 'POST',
          body: formData
        })
        
        if (!response.ok) {
          const error = await response.json()
          throw new Error(error.detail || 'Raster conversion failed')
        }
        
        const result = await response.json()
        console.log('[App] Raster conversion result:', result)
        
        // Use returned URL and bounds to load raster layer
        const layer = await mapStore.addRasterLayer(
          entry.name,
          result.url,
          result.bounds,
          result.format || 'png'
        )
        
        if (layer) {
          showMessage('Load Success', `Added "${entry.name}" to map`, 'success')
          // Close data catalog, return to analysis view
          showDataCatalog.value = false
          activeNav.value = 'analysis'
        } else {
          showMessage('Load Failed', `Cannot load raster layer "${entry.name}"`, 'error')
        }
      } catch (err) {
        console.error('Raster conversion failed:', err)
        showMessage('Conversion Failed', `Raster file conversion failed: ${(err as Error).message}`, 'error')
      }
    } else {
      showMessage('Notice', `Unsupported file type: ${entry.file_type}`, 'info')
    }
  } catch (e) {
    console.error('Failed to load data:', e)
    showMessage('Load Failed', `Error loading "${entry.name}"`, 'error')
  }
}

// Computed
const currentTask = computed(() => taskStore.currentTask)
const isLoading = computed(() => taskStore.isLoading || taskStore.isRunning)
const generatedCode = computed(() => taskStore.generatedCode)
const layers = computed(() => mapStore.layers)
const selectedFeature = computed(() => mapStore.selectedFeature)
const taskLogs = computed(() => currentTask.value?.logs || '')

// Submit analysis task
async function handleSubmit(request: AnalysisRequest) {
  try {
    await taskStore.submitTask(request)
  } catch (error) {
    console.error('Submit task failed:', error)
  }
}

// Map ready
function onMapReady(map: any) {
  console.log('Map ready')
}

// Feature click
function onFeatureClick(feature: any) {
  console.log('Feature clicked:', feature)
}

// Close properties panel
function closePropertiesPanel() {
  mapStore.setSelectedFeature(null)
}

// Extract layers from generated code and load to map
async function loadResultsToMap() {
  // Get current generated code
  const code = generatedCode.value
  if (!code) {
    showMessage('Notice', 'No generated code to analyze', 'info')
    return
  }
  
  // If map not loaded, wait up to 5 seconds
  if (!mapStore.isMapLoaded) {
    console.log('Map not loaded, waiting...')
    let waited = 0
    while (!mapStore.isMapLoaded && waited < 5000) {
      await new Promise(resolve => setTimeout(resolve, 100))
      waited += 100
    }
    
    if (!mapStore.isMapLoaded) {
      showMessage('Error', 'Map loading timeout, please refresh the page', 'error')
      return
    }
  }
  
  try {
    // Call backend API to extract layer info
    console.log('📝 Extracting layer info from code...')
    const response = await fetch('/api/analysis/extract-layers', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ code })
    })
    
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to extract layers')
    }
    
    const result = await response.json()
    console.log('Extraction result:', result)
    
    if (!result.success) {
      showMessage('Error', result.message || 'Failed to extract layers', 'error')
      return
    }
    
    const layers = result.layers || []
    if (layers.length === 0) {
      showMessage('Notice', 'No addMapLayer calls found in code, or files not generated yet', 'info')
      return
    }
    
    // Load layers to map
    let loadedCount = 0
    const errors: string[] = []
    const qgisOnlyLayers: string[] = []
    
    for (const layer of layers) {
      console.log('Processing layer:', layer.name, layer.url, layer.web_compatible)
      
      if (!layer.web_compatible) {
        qgisOnlyLayers.push(`${layer.name}: ${layer.message || 'Cannot display in Web'}`)
        continue
      }
      
      if (layer.url && (layer.url.endsWith('.geojson') || layer.url.endsWith('.json'))) {
        // Vector layer (GeoJSON)
        try {
          const loadedLayer = await mapStore.addGeoJSONLayer(layer.name, layer.url)
          if (loadedLayer) {
            loadedCount++
            console.log(`✓ Vector layer loaded: ${layer.name}`)
          } else {
            errors.push(`${layer.name}: Load failed`)
          }
        } catch (err) {
          console.error(`Failed to load layer: ${layer.name}`, err)
          errors.push(`${layer.name}: ${(err as Error).message}`)
        }
      } else if (layer.url && layer.bounds && (
        layer.url.endsWith('.png') || 
        layer.url.endsWith('.tif') || 
        layer.url.endsWith('.tiff') ||
        layer.type === 'raster'
      )) {
        // Raster layer (GeoTIFF or PNG)
        try {
          // Prefer backend returned format field, otherwise determine by URL suffix
          const format = layer.format || 
            ((layer.url.endsWith('.tif') || layer.url.endsWith('.tiff')) ? 'geotiff' : 'png')
          console.log(`🎨 Loading raster layer: ${layer.name}, format: ${format}, bounds:`, layer.bounds)
          const loadedLayer = await mapStore.addRasterLayer(layer.name, layer.url, layer.bounds, format)
          if (loadedLayer) {
            loadedCount++
            console.log(`✓ Raster layer loaded: ${layer.name}`)
          } else {
            errors.push(`${layer.name}: Load failed`)
          }
        } catch (err) {
          console.error(`Failed to load raster layer: ${layer.name}`, err)
          errors.push(`${layer.name}: ${(err as Error).message}`)
        }
      }
    }
    
    // Build result message
    let message = ''
    if (loadedCount > 0) {
      message += `✅ Successfully loaded ${loadedCount} layers to map\n`
    }
    if (qgisOnlyLayers.length > 0) {
      message += `\n⚠️ View in QGIS:\n${qgisOnlyLayers.join('\n')}\n`
    }
    if (errors.length > 0) {
      message += `\n❌ Load failed:\n${errors.join('\n')}`
    }
    
    if (loadedCount > 0) {
      showMessage('Load Complete', message, 'success')
    } else if (qgisOnlyLayers.length > 0 || errors.length > 0) {
      showMessage('Load Result', message || 'No loadable layers', 'info')
    } else {
      showMessage('Notice', 'No loadable layer files (files may not be generated yet, please execute the code first)', 'info')
    }
    
  } catch (err) {
    console.error('Error extracting layers:', err)
    showMessage('Error', 'Failed to extract layers: ' + (err as Error).message, 'error')
  }
}

// Handle loading local code file
function handleLoadCode(code: string) {
  taskStore.setCode(code)
  console.log('Loaded code from file, length:', code.length)
}

// Handle code execution
async function handleExecuteCode(code: string) {
  if (!code) {
    showMessage('Notice', 'No code to execute', 'info')
    return
  }
  
  try {
    // Call backend API to execute code
    const response = await fetch('/api/analysis/execute-code', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ code })
    })
    
    // Get response text first for debugging
    const responseText = await response.text()
    console.log('[Debug] execute-code response:', responseText.substring(0, 500))
    
    if (!response.ok) {
      // Try to parse error response
      try {
        const error = JSON.parse(responseText)
        throw new Error(error.detail || 'Execution failed')
      } catch {
        throw new Error(`Execution failed (HTTP ${response.status}): ${responseText.substring(0, 200)}`)
      }
    }
    
    // Parse JSON response
    let result
    try {
      result = JSON.parse(responseText)
    } catch (e) {
      console.error('[Debug] JSON parse failed:', e, 'Response:', responseText)
      throw new Error(`Response parse failed: ${responseText.substring(0, 200)}`)
    }
    
    // Display different info based on execution result
    if (result.success) {
      let message = 'Code executed successfully!'
      if (result.message) {
        message = result.message
      }
      
      // Categorize files
      const vectorFiles: any[] = []       // Vector files displayable in Web
      const qgisOnlyFiles: any[] = []     // Files only viewable in QGIS
      const rasterFiles: any[] = []
      const otherFiles: any[] = []
      
      if (result.output_files && result.output_files.length > 0) {
        for (const file of result.output_files) {
          if (file.qgis_only) {
            // CRS incompatible, only viewable in QGIS
            qgisOnlyFiles.push(file)
          } else if (file.type === 'vector') {
            vectorFiles.push(file)
          } else if (file.type === 'raster') {
            rasterFiles.push(file)
          } else {
            otherFiles.push(file)
          }
        }
        
        message += `\n\nGenerated ${result.output_files.length} files:`
        
        if (vectorFiles.length > 0) {
          message += `\n\n📍 Vector files (${vectorFiles.length}, loaded to map):`
          for (const file of vectorFiles) {
            message += `\n  - ${file.name}`
          }
        }
        
        if (qgisOnlyFiles.length > 0) {
          message += `\n\n⚠️ View in QGIS (${qgisOnlyFiles.length}):`
          for (const file of qgisOnlyFiles) {
            message += `\n  - ${file.name}`
            if (file.path) {
              message += `\n    📁 Path: ${file.path}`
            }
            if (file.message) {
              message += `\n    💡 ${file.message}`
            }
          }
        }
        
        if (rasterFiles.length > 0) {
          // Check if there are raster files displayable in Web
          const webRasterFiles = rasterFiles.filter(f => f.web_compatible && f.url && f.bounds)
          const qgisRasterFiles = rasterFiles.filter(f => !f.web_compatible || !f.url || !f.bounds)
          
          if (webRasterFiles.length > 0) {
            message += `\n\n🗺️ Raster files (${webRasterFiles.length}, loaded to map):`
            for (const file of webRasterFiles) {
              message += `\n  - ${file.name}`
            }
          }
          
          if (qgisRasterFiles.length > 0) {
            message += `\n\n🖼️ QGIS-only raster (${qgisRasterFiles.length}):`
            for (const file of qgisRasterFiles) {
              message += `\n  - ${file.name}`
              if (file.path) {
                message += `\n    📁 Path: ${file.path}`
              }
            }
            message += `\n\n💡 Tip: View these raster files in QGIS for full effect`
          }
        }
        
        if (otherFiles.length > 0) {
          message += `\n\n📄 Other files (${otherFiles.length}):`
          for (const file of otherFiles) {
            message += `\n  - ${file.name}`
          }
        }
      }
      
      if (result.output) {
        // Only show last few lines of output to avoid being too long
        const outputLines = result.output.split('\n')
        const displayLines = outputLines.slice(-20).join('\n')
        if (outputLines.length > 20) {
          message += `\n\nOutput (last 20 lines):\n${displayLines}`
        } else {
          message += `\n\nOutput:\n${displayLines}`
        }
      }
      
      showMessage('Execution Success', message, 'success')
      
      // Load vector files to map
      console.log('[Debug] vectorFiles:', vectorFiles.length, 'isMapLoaded:', mapStore.isMapLoaded)
      
      if (vectorFiles.length > 0) {
        if (!mapStore.isMapLoaded) {
          console.warn('[Debug] Map not loaded, cannot add layers')
          alert('⚠️ Map not fully loaded, cannot add layers. Please refresh the page.')
        } else {
          // Record successfully loaded layer count
          let loadedCount = 0
          
          for (const file of vectorFiles) {
            console.log('[Debug] Processing file:', file)
            
            // Support GeoJSON format (backend auto-converts SHP to GeoJSON)
            const fileUrl = file.url || ''
            console.log('[Debug] fileUrl:', fileUrl)
            
            if (fileUrl.endsWith('.geojson') || fileUrl.endsWith('.json')) {
              // Use relative URL, forwarded via Vite proxy
              const url = fileUrl
              // Use backend returned layer name instead of filename
              const layerName = file.name || fileUrl.split('/').pop()?.replace(/\.(geojson|json)$/, '') || 'Unnamed Layer'
              
              console.log('[Debug] Loading layer:', layerName, 'URL:', url)
              
              try {
                console.log(`[App] Calling addGeoJSONLayer: ${layerName}, ${url}`)
                const layer = await mapStore.addGeoJSONLayer(layerName, url)
                if (layer) {
                  console.log(`✓ Layer loaded: ${layerName}`, layer)
                  loadedCount++
                } else {
                  console.error(`✗ Layer load returned null: ${layerName}`)
                  console.warn(`Layer "${layerName}" load failed, check browser console`)
                }
              } catch (e) {
                console.error(`Layer load exception: ${layerName}`, e)
              }
            } else {
              console.warn('[Debug] File URL is not geojson:', fileUrl)
            }
          }
          
          // Show tip if layers loaded successfully
          if (loadedCount > 0) {
            console.log(`[Debug] Successfully loaded ${loadedCount} vector layers`)
          }
        }
      }
      
      // Load displayable raster files to map
      const webRasterFiles = rasterFiles.filter(f => f.web_compatible && f.url && f.bounds)
      console.log('[Debug] webRasterFiles:', webRasterFiles.length)
      
      if (webRasterFiles.length > 0 && mapStore.isMapLoaded) {
        let rasterLoadedCount = 0
        
        for (const file of webRasterFiles) {
          console.log('[Debug] Loading raster file:', file)
          
          try {
            const layerName = file.name || 'Raster Layer'
            const url = file.url
            const bounds = file.bounds  // [west, south, east, north]
            // Detect file format
            const format = file.format || (url.endsWith('.tif') || url.endsWith('.tiff') ? 'geotiff' : 'png')
            
            console.log(`[App] Calling addRasterLayer: ${layerName}, ${url}, format: ${format}, bounds:`, bounds)
            const layer = await mapStore.addRasterLayer(layerName, url, bounds, format)
            if (layer) {
              console.log(`✓ Raster layer loaded: ${layerName}`)
              rasterLoadedCount++
            } else {
              console.error(`✗ Raster layer load returned null: ${layerName}`)
            }
          } catch (e) {
            console.error(`Raster layer load exception: ${file.name}`, e)
          }
        }
        
        if (rasterLoadedCount > 0) {
          console.log(`[Debug] Successfully loaded ${rasterLoadedCount} raster layers`)
        }
      }
    } else {
      // Execution failed, show detailed error info
      let errorMessage = ''
      if (result.message) {
        errorMessage += result.message
      }
      if (result.error) {
        errorMessage += `\n\nError details:\n${result.error}`
      }
      if (result.output) {
        errorMessage += `\n\nOutput:\n${result.output}`
      }
      showMessage('Code Execution Failed', errorMessage || 'Unknown error', 'error')
    }
  } catch (err) {
    console.error('Execute code error:', err)
    showMessage('Execution Error', (err as Error).message, 'error')
  }
}

// Handle load layers
async function handleLoadLayers() {
  // Call loadResultsToMap directly, using the same mature logic
  // This ensures both buttons behave identically
  console.log('🗺️ Header button: Calling loadResultsToMap...')
  await loadResultsToMap()
}

// Load task results from history to map
async function handleLoadHistoryTask(task: Task) {
  console.log('[App] Loading task from history:', task.task_id)
  
  // Set current task
  taskStore.setCurrentTask(task)
  
  // Get code
  if (task.status === 'completed') {
    try {
      const code = await taskStore.fetchCode(task.task_id)
      if (code) {
        // Close history, return to analysis view
        showTaskHistory.value = false
        activeNav.value = 'analysis'
        
        // Auto-load results to map
        await loadResultsToMap()
        
        showMessage('Load Success', 'Task results loaded from history', 'success')
      }
    } catch (e) {
      console.error('Failed to load history task:', e)
      showMessage('Load Failed', 'Cannot load history task results', 'error')
    }
  } else {
    showMessage('Notice', 'Task not completed, cannot load results', 'info')
  }
}

// Show history task code in code viewer
async function handleViewHistoryCode(taskId: string) {
  try {
    const code = await taskStore.fetchCode(taskId)
    if (code) {
      showTaskHistory.value = false
      activeNav.value = 'analysis'
      showMessage('Code Loaded', 'History code displayed in code viewer', 'success')
    }
  } catch (e) {
    console.error('Failed to load code:', e)
    showMessage('Load Failed', 'Cannot load history code', 'error')
  }
}

// Whether task is completed
const isTaskCompleted = computed(() => {
  return currentTask.value?.status === 'completed'
})

// Watch for task completion, get code and show execution results
watch(() => currentTask.value?.status, async (status, oldStatus) => {
  console.log('[Watch] Task status changed:', oldStatus, '->', status)
  
  if (status === 'completed' && oldStatus !== 'completed' && currentTask.value) {
    console.log('✅ Task completed, getting code and execution results...')
    console.log('[Watch] Task ID:', currentTask.value.task_id)
    console.log('[Watch] Task Type:', currentTask.value.task_type)
    
    // Determine task type
    const taskType = currentTask.value.task_type || ''
    
    // If data download only type, load downloaded data to map directly
    if (taskType === 'data_download_only') {
      console.log('📥 Data download task, auto-loading downloaded files to map...')
      const downloadedFiles = currentTask.value.downloaded_files || []
      
      if (downloadedFiles.length === 0) {
        showMessage('Complete', 'Data download complete, but no downloaded files found', 'info')
        return
      }
      
      let loadedCount = 0
      let errorCount = 0
      
      for (const file of downloadedFiles) {
        try {
          console.log('[App] Processing downloaded file:', file)
          
          // Build URL
          let url = ''
          let fileName = file.name || 'unknown'
          const filePath = (file.path || '').replace(/\\/g, '/')
          const fileType = file.type || 'unknown'
          
          // For GeoJSON files
          if (fileType === 'geojson' || filePath.endsWith('.geojson')) {
            // Handle downloaded_data directory
            if (filePath.includes('downloaded_data')) {
              const match = filePath.match(/downloaded_data[/\\](.+)$/)
              if (match) {
                const relativePath = match[1]
                url = `/downloaded/${encodeURIComponent(relativePath).replace(/%2F/g, '/')}`
              }
            }
            // Handle output/routes or output/results directory
            else if (filePath.includes('output/routes')) {
              const match = filePath.match(/output[/\\]routes[/\\](.+)$/)
              if (match) {
                const relativePath = match[1]
                url = `/output/routes/${encodeURIComponent(relativePath).replace(/%2F/g, '/')}`
              }
            }
            else if (filePath.includes('output/results')) {
              const match = filePath.match(/output[/\\]results[/\\](.+)$/)
              if (match) {
                const relativePath = match[1]
                url = `/results/${encodeURIComponent(relativePath).replace(/%2F/g, '/')}`
              }
            }
            // Generic output directory handling
            else if (filePath.includes('output')) {
              const match = filePath.match(/output[/\\](.+)$/)
              if (match) {
                const relativePath = match[1]
                url = `/output/${encodeURIComponent(relativePath).replace(/%2F/g, '/')}`
              }
            }
            
            if (url) {
              console.log('[App] Loading GeoJSON:', fileName, url)
              const layer = await mapStore.addGeoJSONLayer(fileName, url)
              if (layer) {
                loadedCount++
                console.log('[App] Load success:', fileName)
              } else {
                errorCount++
                console.error('[App] Load failed:', fileName)
              }
            } else {
              console.warn('[App] Cannot build file URL:', filePath)
            }
          } 
          // For raster files
          else if (fileType === 'raster' || filePath.endsWith('.tif') || filePath.endsWith('.tiff')) {
            console.log('[App] Skipping raster file (needs separate handling):', fileName)
            // Raster files need to be loaded via catalog, not handled here
          }
        } catch (e) {
          console.error(`[App] Failed to load file: ${file.name}`, e)
          errorCount++
        }
      }
      
      const message = `Downloaded ${downloadedFiles.length} data files\nLoaded to map: ${loadedCount}${errorCount > 0 ? `\nLoad failed: ${errorCount}` : ''}`
      showMessage('Download Complete', message, loadedCount > 0 ? 'success' : 'info')
      return
    }
    
    // For other types (data_and_code, code_only), get code and auto-load layers
    try {
      // Get generated code and script path
      const code = await taskStore.fetchCode(currentTask.value.task_id)
      console.log('Code retrieved')
      console.log('   Code length:', code?.length || 0)
      console.log('   Script path:', taskStore.scriptPath)
      
      if (code && code.length > 0) {
        // Auto-load layers to map
        console.log('Auto-loading layers to map...')
        
        // Wait a moment to ensure UI update completes
        await new Promise(resolve => setTimeout(resolve, 500))
        
        try {
          // Call backend to get execution results
          const response = await fetch('/api/analysis/extract-layers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
          })
          
          if (response.ok) {
            const result = await response.json()
            const layers = result.layers || []
            
            // Categorize files
            const vectorLayers: string[] = []
            const rasterLayers: string[] = []
            const qgisOnlyLayers: string[] = []
            const errors: string[] = []
            let loadedCount = 0
            
            // Load layers
            for (const layer of layers) {
              if (!layer.web_compatible) {
                qgisOnlyLayers.push(layer.name)
                continue
              }
              
              if (layer.url && (layer.url.endsWith('.geojson') || layer.url.endsWith('.json'))) {
                try {
                  const loadedLayer = await mapStore.addGeoJSONLayer(layer.name, layer.url)
                  if (loadedLayer) {
                    vectorLayers.push(layer.name)
                    loadedCount++
                  }
                } catch (e) {
                  errors.push(`${layer.name}: ${(e as Error).message}`)
                }
              } else if (layer.url && layer.bounds) {
                try {
                  const format = layer.format || 'png'
                  const loadedLayer = await mapStore.addRasterLayer(layer.name, layer.url, layer.bounds, format)
                  if (loadedLayer) {
                    rasterLayers.push(layer.name)
                    loadedCount++
                  }
                } catch (e) {
                  errors.push(`${layer.name}: ${(e as Error).message}`)
                }
              }
            }
            
            // Get task execution log output
            const taskLogs = currentTask.value?.logs || ''
            
            // Extract code execution output from logs (between special markers)
            let outputInfo = ''
            const logLines = taskLogs.split('\n')
            const outputLines: string[] = []
            let inOutputSection = false
            
            for (const line of logLines) {
              // Check if entering/exiting code execution output section
              if (line.includes('====== Code Execution Output ======') || line.includes('====== 代码执行输出 ======')) {
                inOutputSection = true
                continue
              }
              if (line.includes('======================') && inOutputSection) {
                inOutputSection = false
                continue
              }
              
              // Inside output section, collect all non-empty lines
              if (inOutputSection && line.trim()) {
                outputLines.push(line.trim())
              }
            }
            
            if (outputLines.length > 0) {
              outputInfo = outputLines.slice(-20).join('\n') // Last 20 lines
            }
            
            // Build result message
            let message = `Code executed successfully!`
            
            if (layers.length > 0) {
              message += `\n\nGenerated ${layers.length} files:`
            }
            
            if (vectorLayers.length > 0) {
              message += `\n\nVector files (${vectorLayers.length}, loaded to map):`
              for (const name of vectorLayers) {
                message += `\n  - ${name}`
              }
            }
            
            if (rasterLayers.length > 0) {
              message += `\n\nRaster files (${rasterLayers.length}):`
              for (const name of rasterLayers) {
                message += `\n  - ${name}`
              }
            }
            
            if (qgisOnlyLayers.length > 0) {
              message += `\n\nView in QGIS (${qgisOnlyLayers.length}):`
              for (const name of qgisOnlyLayers) {
                message += `\n  - ${name}`
              }
            }
            
            if (outputInfo) {
              message += `\n\nOutput:\n${outputInfo}`
            }
            
            if (errors.length > 0) {
              message += `\n\nLoad failed:\n${errors.join('\n')}`
            }
            
            // Show execution result dialog
            showMessage('Execution Success', message, 'success')
            console.log('Layer auto-load complete!')
          }
        } catch (err) {
          console.error('Auto-load layers failed:', err)
          showMessage('Notice', 'Layer load failed, please click "📍 Extract Layers to Map" button to load manually', 'info')
        }
      } else {
        console.warn('Code is empty, cannot auto-load layers')
      }
    } catch (err) {
      console.error('Failed to get code:', err)
    }
  }
}, { immediate: false })
</script>

<template>
  <div class="app-container">
    <!-- Top Navigation -->
    <header class="app-header">
      <div class="logo">
        <span class="logo-icon">🌍</span>
        <span class="logo-text">AutoGIS</span>
        <span class="version">v1.1.0</span>
      </div>
      <nav class="nav-links">
        <a href="#" 
           :class="['nav-link', { active: activeNav === 'analysis' }]"
           @click.prevent="switchNav('analysis')"
        >Analysis</a>
        <a href="#" 
           :class="['nav-link', { active: activeNav === 'catalog' }]"
           @click.prevent="switchNav('catalog')"
        >Data Catalog</a>
        <a href="#" 
           :class="['nav-link', { active: activeNav === 'history' }]"
           @click.prevent="switchNav('history')"
        >History</a>
        <a href="#" 
           :class="['nav-link', { active: activeNav === 'docs' }]"
           @click.prevent="switchNav('docs')"
        >API Docs</a>
      </nav>
    </header>

    <!-- Main Content Area -->
    <main class="app-main">
      <!-- Left Sidebar -->
      <aside class="sidebar">
        <!-- Query Input -->
        <QueryInput 
          @submit="handleSubmit" 
          :loading="isLoading"
        />
        
        <!-- Task Section (scrollable) -->
        <div class="task-section" v-if="currentTask">
          <!-- Task Progress -->
          <TaskProgress :task="currentTask" />
          
          <!-- Execution Logs -->
          <TaskLogs 
            v-if="taskLogs"
            :logs="taskLogs"
            :collapsed="false"
          />
          
          <!-- Load Results Button - Extract layers from generated code (fallback) -->
          <div class="load-results" v-if="generatedCode">
            <button 
              class="load-btn" 
              @click="loadResultsToMap"
              title="Manually load layers to map (usually auto-loaded)"
            >
              📍 Extract Layers to Map
            </button>
          </div>
        </div>
        
        <!-- Layer Control - Fixed Area -->
        <div class="layer-section">
          <LayerPanel />
        </div>
      </aside>

      <!-- Map Area -->
      <div class="map-area">
        <MapContainer 
          @map-ready="onMapReady"
          @feature-click="onFeatureClick"
        />
        
        <!-- Code Viewer -->
        <CodeViewer 
          :code="generatedCode"
          :collapsed="codeCollapsed"
          @toggle="codeCollapsed = !codeCollapsed"
          @load-code="handleLoadCode"
          @execute-code="handleExecuteCode"
        />
      </div>

      <!-- Right Properties Panel -->
      <aside class="properties-panel" v-if="selectedFeature">
        <FeatureProperties 
          :feature="selectedFeature"
          @close="closePropertiesPanel"
        />
      </aside>
    </main>

    <!-- Error Toast -->
    <Transition name="slide">
      <div class="error-toast" v-if="taskStore.error">
        <span class="error-icon">⚠️</span>
        <span class="error-message">{{ taskStore.error }}</span>
        <button class="error-close" @click="taskStore.error = null">✕</button>
      </div>
    </Transition>

    <!-- Message Modal -->
    <MessageModal
      :show="showModal"
      :title="modalTitle"
      :message="modalMessage"
      :type="modalType"
      @close="closeModal"
    />

    <!-- Data Catalog -->
    <DataCatalog
      :visible="showDataCatalog"
      @close="showDataCatalog = false; activeNav = 'analysis'"
      @load-data="handleLoadCatalogData"
    />

    <!-- History -->
    <TaskHistory
      :visible="showTaskHistory"
      @close="showTaskHistory = false; activeNav = 'analysis'"
      @load-task="handleLoadHistoryTask"
      @view-code="handleViewHistoryCode"
    />

    <!-- API Docs -->
    <ApiDocs
      :visible="showApiDocs"
      @close="showApiDocs = false; activeNav = 'analysis'"
    />
  </div>
</template>

<style scoped>
.app-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg-dark);
  color: var(--text-primary);
}

.app-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0 1.5rem;
  height: 56px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.logo {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.logo-icon {
  font-size: 1.5rem;
}

.logo-text {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-primary);
}

.version {
  font-size: 0.625rem;
  padding: 0.125rem 0.375rem;
  background: var(--primary-color);
  color: white;
  border-radius: 4px;
  font-weight: 600;
}

.nav-links {
  display: flex;
  gap: 0.5rem;
}

.nav-link {
  color: var(--text-secondary);
  text-decoration: none;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 500;
  transition: all 0.2s;
}

.nav-link:hover {
  color: var(--text-primary);
  background: rgba(59, 130, 246, 0.1);
  text-decoration: none;
}

.nav-link.active {
  color: var(--primary-color);
  background: rgba(59, 130, 246, 0.1);
}

.app-main {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.sidebar {
  width: 360px;
  background: var(--bg-panel);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

/* Task Section - scrollable, max 50% height */
.task-section {
  max-height: 45%;
  overflow-y: auto;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

/* Layer Section - takes remaining space */
.layer-section {
  flex: 1;
  min-height: 200px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.load-results {
  padding: 0.75rem;
  border-bottom: 1px solid var(--border-color);
}

.load-btn {
  width: 100%;
  padding: 0.5rem;
  border: none;
  border-radius: 6px;
  background: var(--success-color, #10b981);
  color: white;
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  transition: all 0.2s;
}

.load-btn:hover {
  background: #059669;
}

.map-area {
  flex: 1;
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.properties-panel {
  width: 320px;
  background: var(--bg-panel);
  border-left: 1px solid var(--border-color);
  overflow-y: auto;
  flex-shrink: 0;
}

/* Error Toast */
.error-toast {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background: var(--error-color);
  color: white;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  z-index: 1000;
}

.error-icon {
  font-size: 1.25rem;
}

.error-message {
  font-size: 0.875rem;
  max-width: 400px;
}

.error-close {
  background: transparent;
  border: none;
  color: white;
  opacity: 0.8;
  cursor: pointer;
  font-size: 1rem;
  padding: 0.25rem;
}

.error-close:hover {
  opacity: 1;
}

/* Transition Animation */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translate(-50%, 20px);
  opacity: 0;
}
</style>

