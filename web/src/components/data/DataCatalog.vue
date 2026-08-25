<script setup lang="ts">
/**
 * Data Catalog Component - Display local data assets
 */
import { ref, computed, onMounted, watch } from 'vue'
import * as catalogApi from '@/api/catalog'
import DataGraph from './DataGraph.vue'
import type { CatalogEntry, CatalogStats } from '@/types'

// Props
const props = defineProps<{
  visible: boolean
}>()

// Emits
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'load-data', entry: CatalogEntry): void
}>()

// State
const loading = ref(false)
const entries = ref<CatalogEntry[]>([])
const stats = ref<CatalogStats | null>(null)
const searchQuery = ref('')
const typeFilter = ref<'all' | 'vector' | 'raster'>('all')
const selectedEntry = ref<CatalogEntry | null>(null)
const total = ref(0)
const viewMode = ref<'list' | 'graph'>('list')  // View mode

// Geometry type icons
const geometryIcons: Record<string, string> = {
  'Point': '📍',
  'MultiPoint': '📍',
  'LineString': '〰️',
  'MultiLineString': '〰️',
  'Polygon': '⬡',
  'MultiPolygon': '⬡',
  'Mixed': '🔷',
  'Unknown': '🔷',
  'Raster': '🖼️'
}

// Get entry icon (based on type and geometry type)
function getEntryIcon(entry: CatalogEntry): string {
  // Raster data shows raster icon first
  const fileType = entry.file_type?.toLowerCase() || ''
  if (['geotiff', 'tif', 'tiff', 'cog'].some(t => fileType.includes(t))) {
    return '🖼️'
  }
  if (entry.data_category === 'raster') {
    return '🖼️'
  }
  // Vector data shows icon based on geometry type
  return geometryIcons[entry.geometry_type || 'Unknown'] || '📄'
}

// Geometry type colors
const geometryColors: Record<string, string> = {
  'Point': '#3b82f6',
  'MultiPoint': '#3b82f6',
  'LineString': '#f59e0b',
  'MultiLineString': '#f59e0b',
  'Polygon': '#10b981',
  'MultiPolygon': '#10b981',
  'Unknown': '#6b7280',
  'Geometry': '#6b7280',
  'Raster': '#8b5cf6'  // 紫色，适合表示影像/栅格数据
}

// Calculate geometry type distribution
const geometryDistribution = computed(() => {
  if (!stats.value?.by_geometry) return []
  const total = Object.values(stats.value.by_geometry).reduce((a, b) => a + b, 0)
  return Object.entries(stats.value.by_geometry).map(([type, count]) => ({
    type,
    count,
    percentage: total > 0 ? (count / total * 100).toFixed(1) : '0',
    color: geometryColors[type] || '#6b7280',
    icon: geometryIcons[type] || '📄'
  }))
})

// Calculate total storage size
const totalSize = computed(() => {
  const size = entries.value.reduce((sum, e) => sum + (e.file_size_mb || 0), 0)
  if (size < 1) return `${(size * 1024).toFixed(0)} KB`
  if (size > 1000) return `${(size / 1024).toFixed(2)} GB`
  return `${size.toFixed(2)} MB`
})

// File type colors
const typeColors: Record<string, string> = {
  'GeoJSON': '#10b981',
  'Shapefile': '#f59e0b',
  'GeoPackage': '#8b5cf6',
  'GeoTIFF': '#ef4444',
  'TIFF': '#ef4444',
  'unknown': '#6b7280'
}

// Filtered entries
const filteredEntries = computed(() => {
  let result = entries.value
  
  // Type filter
  if (typeFilter.value !== 'all') {
    const vectorFormats = ['GeoJSON', 'Shapefile', 'GeoPackage', 'geojson', 'shp', 'gpkg']
    const rasterFormats = ['GeoTIFF', 'TIFF', 'tif', 'tiff']
    
    if (typeFilter.value === 'vector') {
      result = result.filter(e => vectorFormats.some(f => 
        e.file_type?.toLowerCase().includes(f.toLowerCase())
      ))
    } else {
      result = result.filter(e => rasterFormats.some(f => 
        e.file_type?.toLowerCase().includes(f.toLowerCase())
      ))
    }
  }
  
  // Search filter
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(e => 
      e.name?.toLowerCase().includes(query) ||
      e.description?.toLowerCase().includes(query) ||
      e.geometry_type?.toLowerCase().includes(query)
    )
  }
  
  return result
})

// Load data
async function loadData() {
  loading.value = true
  try {
    const [catalogRes, statsRes] = await Promise.all([
      catalogApi.getCatalog(500, 0),
      catalogApi.getCatalogStats()
    ])
    entries.value = catalogRes.entries
    total.value = catalogRes.total
    stats.value = statsRes
  } catch (e) {
    console.error('Failed to load data catalog:', e)
  } finally {
    loading.value = false
  }
}

// Search
async function handleSearch() {
  if (!searchQuery.value.trim()) {
    await loadData()
    return
  }
  
  loading.value = true
  try {
    const result = await catalogApi.searchCatalog({
      query: searchQuery.value,
      type: typeFilter.value === 'all' ? undefined : typeFilter.value,
      limit: 100
    })
    entries.value = result.entries
    total.value = result.total
  } catch (e) {
    console.error('Search failed:', e)
  } finally {
    loading.value = false
  }
}

// Format file size
function formatSize(sizeMb?: number): string {
  if (!sizeMb) return '-'
  if (sizeMb < 1) return `${(sizeMb * 1024).toFixed(0)} KB`
  return `${sizeMb.toFixed(2)} MB`
}

// Format count
function formatCount(count?: number): string {
  if (!count) return '-'
  if (count >= 1000000) return `${(count / 1000000).toFixed(1)}M`
  if (count >= 1000) return `${(count / 1000).toFixed(1)}K`
  return count.toString()
}

// Get file name
function getFileName(path?: string): string {
  if (!path) return ''
  return path.split(/[/\\]/).pop() || path
}

// Load to map
function loadToMap(entry: CatalogEntry) {
  emit('load-data', entry)
}

// View details
function viewDetails(entry: CatalogEntry) {
  selectedEntry.value = entry
}

// Close details
function closeDetails() {
  selectedEntry.value = null
}

// Watch visibility changes
watch(() => props.visible, (visible) => {
  if (visible && entries.value.length === 0) {
    loadData()
  }
})

onMounted(() => {
  if (props.visible) {
    loadData()
  }
})
</script>

<template>
  <div class="data-catalog" v-if="visible">
    <!-- Header -->
    <div class="catalog-header">
      <div class="header-title">
        <span class="icon">📊</span>
        <h2>Data Catalog</h2>
        <span class="count" v-if="total > 0">{{ total }} datasets</span>
      </div>
      <div class="header-actions">
        <div class="view-toggle">
          <button 
            :class="['toggle-btn', { active: viewMode === 'list' }]" 
            @click="viewMode = 'list'" 
            title="List View"
          >📋</button>
          <button 
            :class="['toggle-btn', { active: viewMode === 'graph' }]" 
            @click="viewMode = 'graph'" 
            title="Knowledge Graph"
          >🕸️</button>
        </div>
        <button class="refresh-btn" @click="loadData" :disabled="loading" title="Refresh">
          <span :class="{ spinning: loading }">🔄</span>
        </button>
        <button class="close-btn" @click="emit('close')" title="Close">✕</button>
      </div>
    </div>

    <!-- Statistics Overview (shown in list view) -->
    <div class="stats-overview" v-if="stats && viewMode === 'list'">
      <!-- Statistics Cards -->
      <div class="stats-cards">
        <div class="stat-card total" :class="{ active: typeFilter === 'all' }" @click="typeFilter = 'all'">
          <div class="stat-icon">📁</div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.total }}</div>
            <div class="stat-label">Total Datasets</div>
          </div>
        </div>
        <div class="stat-card vector" :class="{ active: typeFilter === 'vector' }" @click="typeFilter = 'vector'">
          <div class="stat-icon">🗺️</div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.by_type.vector }}</div>
            <div class="stat-label">Vector Data</div>
          </div>
        </div>
        <div class="stat-card raster" :class="{ active: typeFilter === 'raster' }" @click="typeFilter = 'raster'">
          <div class="stat-icon">🖼️</div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.by_type.raster }}</div>
            <div class="stat-label">Raster Data</div>
          </div>
        </div>
        <div class="stat-card storage">
          <div class="stat-icon">💾</div>
          <div class="stat-info">
            <div class="stat-value">{{ totalSize }}</div>
            <div class="stat-label">Storage Size</div>
          </div>
        </div>
      </div>
      
      <!-- Geometry Type Distribution -->
      <div class="geometry-distribution" v-if="geometryDistribution.length > 0">
        <div class="distribution-title">Geometry Type Distribution</div>
        <div class="distribution-bars">
          <div 
            class="distribution-item" 
            v-for="item in geometryDistribution" 
            :key="item.type"
          >
            <div class="item-header">
              <span class="item-icon">{{ item.icon }}</span>
              <span class="item-type">{{ item.type }}</span>
              <span class="item-count">{{ item.count }}</span>
            </div>
            <div class="item-bar">
              <div 
                class="item-fill" 
                :style="{ width: item.percentage + '%', backgroundColor: item.color }"
              ></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Search and Filter (shown in list view) -->
    <div class="search-bar" v-if="viewMode === 'list'">
      <div class="search-input-wrapper">
        <span class="search-icon">🔍</span>
        <input 
          type="text" 
          v-model="searchQuery" 
          placeholder="Search datasets..." 
          @keyup.enter="handleSearch"
        />
        <button class="search-btn" @click="handleSearch">Search</button>
      </div>
      <div class="filter-tabs">
        <button 
          :class="['filter-tab', { active: typeFilter === 'all' }]"
          @click="typeFilter = 'all'"
        >
          All
        </button>
        <button 
          :class="['filter-tab', { active: typeFilter === 'vector' }]"
          @click="typeFilter = 'vector'"
        >
          🗺️ Vector
        </button>
        <button 
          :class="['filter-tab', { active: typeFilter === 'raster' }]"
          @click="typeFilter = 'raster'"
        >
          🖼️ Raster
        </button>
      </div>
    </div>

    <!-- Knowledge Graph View -->
    <div class="graph-view" v-if="viewMode === 'graph' && !loading">
      <DataGraph 
        :entries="filteredEntries" 
        :visible="viewMode === 'graph'"
        @select="viewDetails"
        @load="loadToMap"
      />
    </div>

    <!-- 数据列表 -->
    <div class="data-list" v-if="viewMode === 'list' && !loading">
      <div class="data-item" v-for="entry in filteredEntries" :key="entry.id">
        <div class="item-icon">
          {{ getEntryIcon(entry) }}
        </div>
        <div class="item-content">
          <div class="item-header">
            <span class="item-name" :title="entry.name">{{ entry.name }}</span>
            <span 
              class="item-type" 
              :style="{ backgroundColor: typeColors[entry.file_type || 'unknown'] + '20', color: typeColors[entry.file_type || 'unknown'] }"
            >
              {{ entry.file_type || 'Unknown' }}
            </span>
          </div>
          <div class="item-meta">
            <span v-if="entry.geometry_type" class="meta-item" :style="{ color: geometryColors[entry.geometry_type] }">
              <span class="meta-icon">{{ geometryIcons[entry.geometry_type] || '📐' }}</span>{{ entry.geometry_type }}
            </span>
            <span v-if="entry.feature_count" class="meta-item">
              <span class="meta-icon">📊</span>{{ formatCount(entry.feature_count) }} features
            </span>
            <span v-if="entry.crs" class="meta-item">
              <span class="meta-icon">🌐</span>{{ entry.crs }}
            </span>
            <span v-if="entry.file_size_mb" class="meta-item">
              <span class="meta-icon">💾</span>{{ formatSize(entry.file_size_mb) }}
            </span>
          </div>
          <div class="item-desc" v-if="entry.description">
            {{ entry.description.slice(0, 100) }}{{ entry.description.length > 100 ? '...' : '' }}
          </div>
        </div>
        <div class="item-actions">
          <button class="action-btn view" @click="viewDetails(entry)" title="View Details">
            👁️
          </button>
          <button class="action-btn load" @click="loadToMap(entry)" title="Load to Map">
            📍
          </button>
        </div>
      </div>
      
      <!-- Empty State -->
      <div class="empty-state" v-if="filteredEntries.length === 0">
        <div class="empty-icon">📭</div>
        <div class="empty-text">No Data</div>
        <div class="empty-hint" v-if="searchQuery">
          No data matching "{{ searchQuery }}" found
        </div>
        <div class="empty-hint" v-else>
          Downloaded data will appear here after analysis tasks
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div class="loading-state" v-if="loading">
      <div class="spinner"></div>
      <div class="loading-text">Loading...</div>
    </div>

    <!-- Detail Panel -->
    <div class="detail-panel" v-if="selectedEntry" @click.self="closeDetails">
      <div class="detail-content">
        <div class="detail-header">
          <h3>{{ selectedEntry.name }}</h3>
          <button class="close-btn" @click="closeDetails">✕</button>
        </div>
        
        <div class="detail-body">
          <!-- Basic Info -->
          <div class="detail-section">
            <h4>📋 Basic Info</h4>
            <div class="detail-grid">
              <div class="detail-item">
                <span class="label">File Type</span>
                <span class="value">{{ selectedEntry.file_type || '-' }}</span>
              </div>
              <div class="detail-item">
                <span class="label">Geometry Type</span>
                <span class="value">{{ selectedEntry.geometry_type || '-' }}</span>
              </div>
              <div class="detail-item">
                <span class="label">CRS</span>
                <span class="value">{{ selectedEntry.crs || '-' }}</span>
              </div>
              <div class="detail-item">
                <span class="label">Feature Count</span>
                <span class="value">{{ formatCount(selectedEntry.feature_count) }}</span>
              </div>
            </div>
          </div>

          <!-- File Path -->
          <div class="detail-section">
            <h4>📁 File Path</h4>
            <div class="file-path">{{ selectedEntry.file_path }}</div>
          </div>

          <!-- Description -->
          <div class="detail-section" v-if="selectedEntry.description">
            <h4>📝 Description</h4>
            <div class="description">{{ selectedEntry.description }}</div>
          </div>

          <!-- Attributes -->
          <div class="detail-section" v-if="selectedEntry.attributes && selectedEntry.attributes.length > 0">
            <h4>🏷️ Attributes ({{ selectedEntry.attributes.length }})</h4>
            <div class="attributes-list">
              <span 
                class="attribute-tag" 
                v-for="attr in selectedEntry.attributes.slice(0, 20)" 
                :key="typeof attr === 'string' ? attr : attr.name"
              >
                {{ typeof attr === 'string' ? attr : attr.name }}
              </span>
              <span class="more-tag" v-if="selectedEntry.attributes.length > 20">
                +{{ selectedEntry.attributes.length - 20 }} more
              </span>
            </div>
          </div>

          <!-- Bounds -->
          <div class="detail-section" v-if="selectedEntry.bounds">
            <h4>🗺️ Geographic Bounds</h4>
            <div class="bounds-info">
              <div class="bounds-item">
                <span class="label">West</span>
                <span class="value">{{ selectedEntry.bounds[0]?.toFixed(4) }}</span>
              </div>
              <div class="bounds-item">
                <span class="label">South</span>
                <span class="value">{{ selectedEntry.bounds[1]?.toFixed(4) }}</span>
              </div>
              <div class="bounds-item">
                <span class="label">East</span>
                <span class="value">{{ selectedEntry.bounds[2]?.toFixed(4) }}</span>
              </div>
              <div class="bounds-item">
                <span class="label">North</span>
                <span class="value">{{ selectedEntry.bounds[3]?.toFixed(4) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="detail-footer">
          <button class="action-btn primary" @click="loadToMap(selectedEntry); closeDetails()">
            📍 Load to Map
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.data-catalog {
  position: fixed;
  top: 48px;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-primary, #0f172a);
  z-index: 100;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.catalog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border-color, #334155);
  background: var(--bg-secondary, #1e293b);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.header-title .icon {
  font-size: 1.5rem;
}

.header-title h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
}

.header-title .count {
  font-size: 0.75rem;
  color: var(--text-secondary, #94a3b8);
  background: var(--bg-dark, #1a1a2e);
  padding: 0.25rem 0.5rem;
  border-radius: 12px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.view-toggle {
  display: flex;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 8px;
  padding: 0.2rem;
  border: 1px solid var(--border-color, #334155);
}

.toggle-btn {
  background: none;
  border: none;
  color: var(--text-secondary, #94a3b8);
  font-size: 0.9rem;
  padding: 0.4rem 0.6rem;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.toggle-btn:hover {
  color: var(--text-primary, #e2e8f0);
}

.toggle-btn.active {
  background: rgba(59, 130, 246, 0.2);
  color: var(--primary-color, #3b82f6);
}

.refresh-btn {
  background: none;
  border: none;
  color: var(--text-secondary, #94a3b8);
  font-size: 1rem;
  cursor: pointer;
  padding: 0.5rem;
  border-radius: 6px;
  transition: all 0.2s;
}

.refresh-btn:hover {
  background: rgba(59, 130, 246, 0.1);
  color: var(--primary-color, #3b82f6);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.refresh-btn .spinning {
  display: inline-block;
  animation: spin 1s linear infinite;
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary, #94a3b8);
  font-size: 1.25rem;
  cursor: pointer;
  padding: 0.5rem;
  border-radius: 6px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: rgba(239, 68, 68, 0.1);
  color: var(--error-color, #ef4444);
}

/* 统计概览 */
.stats-overview {
  display: flex;
  gap: 1rem;
  padding: 1rem 1.5rem;
  background: var(--bg-secondary, #1e293b);
  border-bottom: 1px solid var(--border-color, #334155);
}

/* 统计卡片 */
.stats-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
  flex: 1;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 10px;
  border: 1px solid var(--border-color, #334155);
  cursor: pointer;
  transition: all 0.2s;
}

.stat-card:hover {
  border-color: var(--primary-color, #3b82f6);
  transform: translateY(-1px);
}

.stat-card.total { border-left: 3px solid #3b82f6; }
.stat-card.vector { border-left: 3px solid #10b981; }
.stat-card.raster { border-left: 3px solid #f59e0b; }
.stat-card.storage { border-left: 3px solid #8b5cf6; cursor: default; }
.stat-card.storage:hover { transform: none; }

.stat-card.active {
  background: rgba(59, 130, 246, 0.1);
  border-color: var(--primary-color, #3b82f6);
}

.stat-card.total.active { background: rgba(59, 130, 246, 0.1); }
.stat-card.vector.active { background: rgba(16, 185, 129, 0.1); border-color: #10b981; }
.stat-card.raster.active { background: rgba(245, 158, 11, 0.1); border-color: #f59e0b; }

.stat-icon {
  font-size: 1.25rem;
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-primary, #e2e8f0);
}

.stat-label {
  font-size: 0.7rem;
  color: var(--text-secondary, #94a3b8);
}

/* 几何类型分布 */
.geometry-distribution {
  flex: 1;
  max-width: 300px;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 10px;
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-color, #334155);
}

.distribution-title {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary, #94a3b8);
  margin-bottom: 0.5rem;
}

.distribution-bars {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.distribution-item .item-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}

.distribution-item .item-icon {
  font-size: 0.75rem;
}

.distribution-item .item-type {
  font-size: 0.7rem;
  color: var(--text-secondary, #94a3b8);
  flex: 1;
}

.distribution-item .item-count {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
}

.distribution-item .item-bar {
  height: 6px;
  background: var(--bg-secondary, #1e293b);
  border-radius: 3px;
  overflow: hidden;
}

.distribution-item .item-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
}

/* 搜索栏 */
.search-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  padding: 1rem 1.5rem;
  background: var(--bg-secondary, #1e293b);
  border-bottom: 1px solid var(--border-color, #334155);
}

.search-input-wrapper {
  flex: 1;
  min-width: 200px;
  display: flex;
  align-items: center;
  background: var(--bg-dark, #1a1a2e);
  border: 1px solid var(--border-color, #334155);
  border-radius: 8px;
  padding: 0 0.5rem;
}

.search-icon {
  font-size: 1rem;
  margin-right: 0.5rem;
}

.search-input-wrapper input {
  flex: 1;
  background: none;
  border: none;
  color: var(--text-primary, #e2e8f0);
  padding: 0.75rem 0.5rem;
  font-size: 0.875rem;
  outline: none;
}

.search-input-wrapper input::placeholder {
  color: var(--text-secondary, #94a3b8);
}

.search-btn {
  background: var(--primary-color, #3b82f6);
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.search-btn:hover {
  background: #2563eb;
}

.filter-tabs {
  display: flex;
  gap: 0.5rem;
}

.filter-tab {
  background: var(--bg-dark, #1a1a2e);
  border: 1px solid var(--border-color, #334155);
  color: var(--text-secondary, #94a3b8);
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-tab:hover {
  border-color: var(--primary-color, #3b82f6);
  color: var(--text-primary, #e2e8f0);
}

.filter-tab.active {
  background: rgba(59, 130, 246, 0.1);
  border-color: var(--primary-color, #3b82f6);
  color: var(--primary-color, #3b82f6);
}

/* 图谱视图 */
.graph-view {
  flex: 1;
  overflow-y: auto;
  padding: 1rem 1.5rem;
  display: flex;
  justify-content: center;
  align-items: flex-start;
}

/* 数据列表 */
.data-list {
  flex: 1;
  overflow-y: auto;
  padding: 1rem 1.5rem;
}

.data-item {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 1rem;
  background: var(--bg-secondary, #1e293b);
  border: 1px solid var(--border-color, #334155);
  border-radius: 10px;
  margin-bottom: 0.75rem;
  transition: all 0.2s;
}

.data-item:hover {
  border-color: var(--primary-color, #3b82f6);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.item-icon {
  font-size: 1.5rem;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 8px;
  flex-shrink: 0;
}

.item-content {
  flex: 1;
  min-width: 0;
}

.item-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.item-name {
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-type {
  font-size: 0.65rem;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-weight: 500;
  flex-shrink: 0;
}

.item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.7rem;
  color: var(--text-secondary, #94a3b8);
}

.meta-icon {
  font-size: 0.75rem;
}

.item-desc {
  font-size: 0.75rem;
  color: var(--text-secondary, #94a3b8);
  line-height: 1.4;
}

.item-actions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.action-btn {
  background: var(--bg-dark, #1a1a2e);
  border: 1px solid var(--border-color, #334155);
  color: var(--text-secondary, #94a3b8);
  width: 32px;
  height: 32px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.9rem;
}

.action-btn:hover {
  background: rgba(59, 130, 246, 0.1);
  border-color: var(--primary-color, #3b82f6);
}

.action-btn.view:hover {
  background: rgba(139, 92, 246, 0.1);
  border-color: #8b5cf6;
}

.action-btn.load:hover {
  background: rgba(16, 185, 129, 0.1);
  border-color: #10b981;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 2rem;
  text-align: center;
}

.empty-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
  opacity: 0.5;
}

.empty-text {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
  margin-bottom: 0.5rem;
}

.empty-hint {
  font-size: 0.875rem;
  color: var(--text-secondary, #94a3b8);
}

/* 加载状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 2rem;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border-color, #334155);
  border-top-color: var(--primary-color, #3b82f6);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 1rem;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-text {
  color: var(--text-secondary, #94a3b8);
  font-size: 0.875rem;
}

/* 详情面板 */
.detail-panel {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
  padding: 2rem;
}

.detail-content {
  background: var(--bg-secondary, #1e293b);
  border-radius: 12px;
  width: 100%;
  max-width: 600px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border-color, #334155);
}

.detail-header h3 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
}

.detail-body {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
}

.detail-section {
  margin-bottom: 1.5rem;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.detail-section h4 {
  margin: 0 0 0.75rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.detail-item .label {
  font-size: 0.7rem;
  color: var(--text-secondary, #94a3b8);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.detail-item .value {
  font-size: 0.875rem;
  color: var(--text-primary, #e2e8f0);
  font-weight: 500;
}

.file-path {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: var(--text-secondary, #94a3b8);
  background: var(--bg-dark, #1a1a2e);
  padding: 0.75rem;
  border-radius: 6px;
  word-break: break-all;
}

.description {
  font-size: 0.875rem;
  color: var(--text-secondary, #94a3b8);
  line-height: 1.6;
}

.attributes-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.attribute-tag {
  font-size: 0.7rem;
  padding: 0.25rem 0.5rem;
  background: var(--bg-dark, #1a1a2e);
  color: var(--text-secondary, #94a3b8);
  border-radius: 4px;
  border: 1px solid var(--border-color, #334155);
}

.more-tag {
  font-size: 0.7rem;
  padding: 0.25rem 0.5rem;
  background: rgba(59, 130, 246, 0.1);
  color: var(--primary-color, #3b82f6);
  border-radius: 4px;
}

.bounds-info {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.5rem;
}

.bounds-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.5rem;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 6px;
}

.bounds-item .label {
  font-size: 0.65rem;
  color: var(--text-secondary, #94a3b8);
  margin-bottom: 0.25rem;
}

.bounds-item .value {
  font-size: 0.75rem;
  color: var(--text-primary, #e2e8f0);
  font-family: 'JetBrains Mono', monospace;
}

.detail-footer {
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border-color, #334155);
  display: flex;
  justify-content: flex-end;
}

.action-btn.primary {
  background: var(--primary-color, #3b82f6);
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  width: auto;
  height: auto;
  font-size: 0.875rem;
  font-weight: 500;
}

.action-btn.primary:hover {
  background: #2563eb;
}
</style>

