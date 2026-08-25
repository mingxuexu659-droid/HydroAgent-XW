<script setup lang="ts">
/**
 * API Documentation Component
 * Display all API endpoints and system documentation for AutoGIS
 */
import { ref, computed, watch, onMounted } from 'vue'

// Props
const props = defineProps<{
  visible: boolean
}>()

// Emits
const emit = defineEmits<{
  (e: 'close'): void
}>()

// State
const activeCategory = ref('overview')
const searchQuery = ref('')
const copiedEndpoint = ref<string | null>(null)

// System documentation state
const systemDocContent = ref('')
const systemDocLoading = ref(false)
const systemDocError = ref('')
const docToc = ref<Array<{level: number; text: string; id: string}>>([])

// API categories
const categories = [
  { id: 'overview', name: 'Overview', icon: '📖' },
  { id: 'system-docs', name: 'System Docs', icon: '📚' },
  { id: 'analysis', name: 'Analysis Tasks', icon: '🔍' },
  { id: 'data', name: 'Data Management', icon: '📁' },
  { id: 'catalog', name: 'Data Catalog', icon: '📊' },
  { id: 'websocket', name: 'WebSocket', icon: '🔌' }
]

// Fetch system documentation
async function fetchSystemDoc() {
  if (systemDocContent.value) return // Already loaded
  
  systemDocLoading.value = true
  systemDocError.value = ''
  
  try {
    const response = await fetch('/api/data/docs/read/SYSTEM_DOCUMENTATION')
    if (!response.ok) {
      throw new Error('Failed to load documentation')
    }
    const data = await response.json()
    systemDocContent.value = data.content
    
    // Parse table of contents
    parseTableOfContents(data.content)
  } catch (e) {
    systemDocError.value = (e as Error).message
  } finally {
    systemDocLoading.value = false
  }
}

// Parse table of contents
function parseTableOfContents(content: string) {
  const headingRegex = /^(#{1,3})\s+(.+)$/gm
  const toc: Array<{level: number; text: string; id: string}> = []
  let match
  
  while ((match = headingRegex.exec(content)) !== null) {
    const level = match[1].length
    const text = match[2].replace(/[*`]/g, '')
    const id = text.toLowerCase().replace(/[^\w\u4e00-\u9fa5]+/g, '-').replace(/^-|-$/g, '')
    toc.push({ level, text, id })
  }
  
  docToc.value = toc
}

// Convert Markdown to HTML (simple implementation)
function renderMarkdown(content: string): string {
  if (!content) return ''
  
  let html = content
  
  // Escape HTML
  html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  
  // Headers
  html = html.replace(/^### (.+)$/gm, (_, text) => {
    const id = text.toLowerCase().replace(/[^\w\u4e00-\u9fa5]+/g, '-').replace(/^-|-$/g, '')
    return `<h3 id="${id}">${text}</h3>`
  })
  html = html.replace(/^## (.+)$/gm, (_, text) => {
    const id = text.toLowerCase().replace(/[^\w\u4e00-\u9fa5]+/g, '-').replace(/^-|-$/g, '')
    return `<h2 id="${id}">${text}</h2>`
  })
  html = html.replace(/^# (.+)$/gm, (_, text) => {
    const id = text.toLowerCase().replace(/[^\w\u4e00-\u9fa5]+/g, '-').replace(/^-|-$/g, '')
    return `<h1 id="${id}">${text}</h1>`
  })
  
  // Code blocks
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre class="code-block ${lang}"><code>${code.trim()}</code></pre>`
  })
  
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
  
  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  
  // Italic
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  
  // Lists
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
  
  // Ordered lists
  html = html.replace(/^\d+\. (.+)$/gm, '<li class="ordered">$1</li>')
  
  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
  
  // Horizontal rule
  html = html.replace(/^---$/gm, '<hr />')
  
  // Paragraphs
  html = html.replace(/^(?!<[huplo]|<li|<hr)(.+)$/gm, '<p>$1</p>')
  
  // Clean extra blank lines
  html = html.replace(/\n{3,}/g, '\n\n')
  
  return html
}

// Computed rendered document content
const renderedDocContent = computed(() => renderMarkdown(systemDocContent.value))

// Scroll to specified position
function scrollToHeading(id: string) {
  const element = document.getElementById(id)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

// Watch category changes, auto-load system docs
watch(() => activeCategory.value, (newVal) => {
  if (newVal === 'system-docs') {
    fetchSystemDoc()
  }
})

// When component is visible and on system docs page, load docs
watch(() => props.visible, (newVal) => {
  if (newVal && activeCategory.value === 'system-docs') {
    fetchSystemDoc()
  }
})

// HTTP method colors
const methodColors: Record<string, { bg: string; text: string }> = {
  GET: { bg: 'rgba(16, 185, 129, 0.15)', text: '#10b981' },
  POST: { bg: 'rgba(59, 130, 246, 0.15)', text: '#3b82f6' },
  PUT: { bg: 'rgba(245, 158, 11, 0.15)', text: '#f59e0b' },
  DELETE: { bg: 'rgba(239, 68, 68, 0.15)', text: '#ef4444' },
  WS: { bg: 'rgba(139, 92, 246, 0.15)', text: '#8b5cf6' }
}

// API endpoint definitions
const apiEndpoints = {
  analysis: [
    {
      method: 'POST',
      path: '/api/analysis/submit',
      name: 'Submit Analysis Task',
      description: 'Submit a new spatial analysis task. The system will automatically complete data download, code generation, and execution.',
      requestBody: {
        query: { type: 'string', required: true, description: 'User analysis requirement description' },
        skip_download: { type: 'boolean', required: false, default: false, description: 'Whether to skip data download' },
        auto_run: { type: 'boolean', required: false, default: true, description: 'Whether to auto-run script' },
        auto_optimize: { type: 'boolean', required: false, default: true, description: 'Whether to auto-optimize on failure' },
        max_optimization_rounds: { type: 'number', required: false, default: 3, description: 'Maximum optimization rounds' }
      },
      response: {
        task_id: 'string - Task unique ID',
        status: 'string - Task status',
        message: 'string - Status message',
        progress: 'number - Progress percentage'
      },
      example: `{
  "query": "Download Beijing Sentinel-2 imagery and calculate NDVI",
  "auto_run": true,
  "auto_optimize": true
}`
    },
    {
      method: 'GET',
      path: '/api/analysis/task/{task_id}',
      name: 'Get Task Status',
      description: 'Get the current status, progress, and results of a specified task.',
      params: [
        { name: 'task_id', type: 'string', location: 'path', description: 'Task ID' }
      ],
      response: {
        task_id: 'string - Task ID',
        status: 'string - pending/analyzing/downloading/generating/executing/optimizing/completed/failed',
        message: 'string - Current status message',
        progress: 'number - Progress 0-100',
        output_files: 'array - Output file list',
        logs: 'string - Execution logs'
      }
    },
    {
      method: 'GET',
      path: '/api/analysis/tasks',
      name: 'Get Task List',
      description: 'Get historical task list with pagination support.',
      params: [
        { name: 'limit', type: 'number', location: 'query', default: 20, description: 'Return count limit (1-100)' },
        { name: 'offset', type: 'number', location: 'query', default: 0, description: 'Offset' }
      ],
      response: {
        total: 'number - Total task count',
        tasks: 'array - Task list'
      }
    },
    {
      method: 'DELETE',
      path: '/api/analysis/task/{task_id}',
      name: 'Cancel Task',
      description: 'Cancel a specified task. Only pending or analyzing tasks can be cancelled.',
      params: [
        { name: 'task_id', type: 'string', location: 'path', description: 'Task ID' }
      ]
    },
    {
      method: 'GET',
      path: '/api/analysis/task/{task_id}/code',
      name: 'Get Generated Code',
      description: 'Get the Python code generated by the task.',
      params: [
        { name: 'task_id', type: 'string', location: 'path', description: 'Task ID' }
      ],
      response: {
        code: 'string - Python code',
        language: 'string - Programming language',
        script_path: 'string - Script file path'
      }
    },
    {
      method: 'POST',
      path: '/api/analysis/execute-code',
      name: 'Execute Code',
      description: 'Execute Python code directly, return execution results and output files.',
      requestBody: {
        code: { type: 'string', required: true, description: 'Python code' }
      },
      response: {
        success: 'boolean - Whether successful',
        output: 'string - Console output',
        output_files: 'array - Generated file list'
      }
    },
    {
      method: 'POST',
      path: '/api/analysis/extract-layers',
      name: 'Extract Layer Info',
      description: 'Extract layer information that can be loaded onto the map from code.',
      requestBody: {
        code: { type: 'string', required: true, description: 'Python code' }
      },
      response: {
        success: 'boolean',
        layers: 'array - Layer info list'
      }
    }
  ],
  data: [
    {
      method: 'GET',
      path: '/api/data/files',
      name: 'Get File List',
      description: 'Get data file list from specified directory.',
      params: [
        { name: 'type', type: 'string', location: 'query', description: 'File type: vector, raster, script, all' },
        { name: 'source', type: 'string', location: 'query', default: 'results', description: 'Data source: results, downloaded, scripts' }
      ],
      response: {
        total: 'number - Total file count',
        files: 'array - File info list'
      }
    },
    {
      method: 'POST',
      path: '/api/data/upload',
      name: 'Upload File',
      description: 'Upload data file to server.',
      requestBody: {
        file: { type: 'file', required: true, description: 'File to upload' }
      }
    },
    {
      method: 'POST',
      path: '/api/data/convert-existing-raster',
      name: 'Convert Raster File',
      description: 'Convert GeoTIFF file on server to web-displayable PNG format.',
      requestBody: {
        file_path: { type: 'string', required: true, description: 'GeoTIFF file path' }
      },
      response: {
        url: 'string - PNG file URL',
        bounds: 'array - Geographic bounds [west, south, east, north]',
        format: 'string - File format'
      }
    },
    {
      method: 'POST',
      path: '/api/data/download-boundary',
      name: 'Download Boundary',
      description: 'Download administrative boundary data by place name.',
      requestBody: {
        name: { type: 'string', required: true, description: 'Place name (e.g., Beijing, Shanghai Pudong)' }
      }
    }
  ],
  catalog: [
    {
      method: 'GET',
      path: '/api/catalog',
      name: 'Get Data Catalog',
      description: 'Get all dataset info from local data catalog.',
      params: [
        { name: 'limit', type: 'number', location: 'query', default: 100, description: 'Return count limit' },
        { name: 'offset', type: 'number', location: 'query', default: 0, description: 'Offset' },
        { name: 'type', type: 'string', location: 'query', description: 'Data type: vector, raster' }
      ],
      response: {
        total: 'number - Total dataset count',
        entries: 'array - Dataset list'
      }
    },
    {
      method: 'GET',
      path: '/api/catalog/search',
      name: 'Search Data Catalog',
      description: 'Search for datasets matching criteria in data catalog.',
      params: [
        { name: 'q', type: 'string', location: 'query', required: true, description: 'Search keyword' },
        { name: 'type', type: 'string', location: 'query', description: 'Data type filter' },
        { name: 'limit', type: 'number', location: 'query', default: 50, description: 'Return count limit' }
      ]
    },
    {
      method: 'GET',
      path: '/api/catalog/stats/summary',
      name: 'Get Data Statistics',
      description: 'Get statistics summary of data catalog.',
      response: {
        total: 'number - Total dataset count',
        by_type: 'object - Count by type {vector, raster, other}',
        by_geometry: 'object - Count by geometry type'
      }
    },
    {
      method: 'GET',
      path: '/api/catalog/{entry_id}',
      name: 'Get Data Details',
      description: 'Get detailed metadata of specified dataset.',
      params: [
        { name: 'entry_id', type: 'string', location: 'path', description: 'Dataset ID' }
      ],
      response: {
        id: 'string - Data ID',
        name: 'string - Data name',
        file_type: 'string - File type',
        geometry_type: 'string - Geometry type',
        crs: 'string - Coordinate system',
        feature_count: 'number - Feature count',
        attributes: 'array - Attribute field list',
        bounds: 'array - Geographic bounds'
      }
    }
  ],
  websocket: [
    {
      method: 'WS',
      path: '/ws/task/{task_id}',
      name: 'Task Progress Push',
      description: 'Receive task execution progress in real-time via WebSocket. Task status updates are automatically pushed after connection.',
      params: [
        { name: 'task_id', type: 'string', location: 'path', description: 'Task ID' }
      ],
      messages: [
        { type: 'initial', description: 'Send current task status on connection' },
        { type: 'progress', description: 'Progress update message' },
        { type: 'status', description: 'Status change message' },
        { type: 'heartbeat', description: 'Heartbeat message, requires ping response' },
        { type: 'error', description: 'Error message' }
      ],
      example: `// Connection example
const ws = new WebSocket('ws://localhost:8000/ws/task/xxx-xxx-xxx')

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data)
  console.log('Task status:', msg.status, msg.progress + '%')
}

// Respond to heartbeat
ws.send(JSON.stringify({ action: 'ping' }))`
    }
  ]
}

// Search filter
const filteredEndpoints = computed(() => {
  if (activeCategory.value === 'overview') return []
  
  const endpoints = apiEndpoints[activeCategory.value as keyof typeof apiEndpoints] || []
  
  if (!searchQuery.value.trim()) return endpoints
  
  const query = searchQuery.value.toLowerCase()
  return endpoints.filter(ep => 
    ep.name.toLowerCase().includes(query) ||
    ep.path.toLowerCase().includes(query) ||
    ep.description.toLowerCase().includes(query)
  )
})

// Copy to clipboard
async function copyToClipboard(text: string, id: string) {
  try {
    await navigator.clipboard.writeText(text)
    copiedEndpoint.value = id
    setTimeout(() => { copiedEndpoint.value = null }, 2000)
  } catch (e) {
    console.error('Copy failed:', e)
  }
}

// Open Swagger UI
function openSwagger() {
  window.open('/docs', '_blank')
}

// Open ReDoc
function openRedoc() {
  window.open('/redoc', '_blank')
}
</script>

<template>
  <div class="api-docs" v-if="visible">
    <!-- Header -->
    <div class="docs-header">
      <div class="header-title">
        <span class="icon">📚</span>
        <h2>API Docs</h2>
        <span class="version">v1.0.0</span>
      </div>
      <div class="header-actions">
        <button class="action-btn swagger" @click="openSwagger" title="Open Swagger UI">
          <span>⚡</span> Swagger
        </button>
        <button class="action-btn redoc" @click="openRedoc" title="Open ReDoc">
          <span>📘</span> ReDoc
        </button>
        <button class="close-btn" @click="emit('close')" title="Close">✕</button>
      </div>
    </div>

    <!-- Main Content -->
    <div class="docs-content">
      <!-- Sidebar -->
      <aside class="docs-sidebar">
        <div class="sidebar-section">
          <div class="section-title">API Categories</div>
          <nav class="nav-list">
            <button 
              v-for="cat in categories" 
              :key="cat.id"
              :class="['nav-item', { active: activeCategory === cat.id }]"
              @click="activeCategory = cat.id"
            >
              <span class="nav-icon">{{ cat.icon }}</span>
              <span class="nav-text">{{ cat.name }}</span>
              <span class="nav-count" v-if="cat.id !== 'overview' && cat.id !== 'system-docs'">
                {{ (apiEndpoints[cat.id as keyof typeof apiEndpoints] || []).length }}
              </span>
            </button>
          </nav>
        </div>

        <div class="sidebar-section">
          <div class="section-title">Quick Links</div>
          <div class="quick-links">
            <a href="http://localhost:8000/docs" target="_blank" class="quick-link">
              <span>⚡</span> Swagger UI
            </a>
            <a href="http://localhost:8000/redoc" target="_blank" class="quick-link">
              <span>📘</span> ReDoc Docs
            </a>
            <a href="http://localhost:8000/openapi.json" target="_blank" class="quick-link">
              <span>📄</span> OpenAPI JSON
            </a>
          </div>
        </div>

        <div class="sidebar-section">
          <div class="section-title">Base Info</div>
          <div class="base-info">
            <div class="info-item">
              <span class="label">Base URL</span>
              <code class="value">http://localhost:8000</code>
            </div>
            <div class="info-item">
              <span class="label">WebSocket</span>
              <code class="value">ws://localhost:8000</code>
            </div>
          </div>
        </div>
      </aside>

      <!-- Main Content Area -->
      <main class="docs-main">
        <!-- Search Bar -->
        <div class="search-bar" v-if="activeCategory !== 'overview'">
          <span class="search-icon">🔍</span>
          <input 
            type="text" 
            v-model="searchQuery" 
            placeholder="Search API..."
          />
        </div>

        <!-- Overview Page -->
        <div class="overview-page" v-if="activeCategory === 'overview'">
          <div class="overview-hero">
            <div class="hero-icon">🌍</div>
            <h1>AutoGIS API</h1>
            <p class="hero-desc">Automated Geospatial Analysis System API Documentation</p>
          </div>

          <div class="overview-intro">
            <h3>🚀 Introduction</h3>
            <p>
              AutoGIS is an automated geospatial analysis platform that automatically completes 
              data acquisition, QGIS code generation, and execution based on user natural language requirements.
            </p>
          </div>

          <div class="feature-cards">
            <div class="feature-card">
              <div class="feature-icon">🔍</div>
              <h4>Intelligent Analysis</h4>
              <p>LLM-based understanding of user requirements with automatic analysis workflow planning</p>
            </div>
            <div class="feature-card">
              <div class="feature-icon">📥</div>
              <h4>Data Acquisition</h4>
              <p>Automatic download from data sources like OSM, Sentinel-2</p>
            </div>
            <div class="feature-card">
              <div class="feature-icon">💻</div>
              <h4>Code Generation</h4>
              <p>Automatic QGIS Python script generation, reusable and modifiable</p>
            </div>
            <div class="feature-card">
              <div class="feature-icon">🔄</div>
              <h4>Real-time Push</h4>
              <p>Get task progress and results in real-time via WebSocket</p>
            </div>
          </div>

          <div class="overview-section">
            <h3>📡 API Endpoints Overview</h3>
            <div class="endpoint-summary">
              <div class="summary-item" @click="activeCategory = 'analysis'">
                <span class="summary-icon">🔍</span>
                <div class="summary-info">
                  <span class="summary-name">Analysis Tasks</span>
                  <span class="summary-count">{{ apiEndpoints.analysis.length }} endpoints</span>
                </div>
              </div>
              <div class="summary-item" @click="activeCategory = 'data'">
                <span class="summary-icon">📁</span>
                <div class="summary-info">
                  <span class="summary-name">Data Management</span>
                  <span class="summary-count">{{ apiEndpoints.data.length }} endpoints</span>
                </div>
              </div>
              <div class="summary-item" @click="activeCategory = 'catalog'">
                <span class="summary-icon">📊</span>
                <div class="summary-info">
                  <span class="summary-name">Data Catalog</span>
                  <span class="summary-count">{{ apiEndpoints.catalog.length }} endpoints</span>
                </div>
              </div>
              <div class="summary-item" @click="activeCategory = 'websocket'">
                <span class="summary-icon">🔌</span>
                <div class="summary-info">
                  <span class="summary-name">WebSocket</span>
                  <span class="summary-count">{{ apiEndpoints.websocket.length }} endpoints</span>
                </div>
              </div>
            </div>
          </div>

          <div class="overview-section">
            <h3>🛠️ Quick Start</h3>
            <div class="code-example">
              <div class="code-header">
                <span>Submit Analysis Task Example</span>
                <button class="copy-btn" @click="copyToClipboard(`fetch('/api/analysis/submit', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    query: 'Download Beijing Sentinel-2 imagery and calculate NDVI',
    auto_run: true
  })
})`, 'quick-start')">
                  {{ copiedEndpoint === 'quick-start' ? '✓ Copied' : '📋 Copy' }}
                </button>
              </div>
              <pre class="code-block"><code>fetch('/api/analysis/submit', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    query: 'Download Beijing Sentinel-2 imagery and calculate NDVI',
    auto_run: true
  })
})</code></pre>
            </div>
          </div>
        </div>

        <!-- System Docs Page -->
        <div class="system-docs-page" v-else-if="activeCategory === 'system-docs'">
          <!-- Doc Navigation -->
          <div class="doc-nav-sidebar">
            <div class="doc-nav-title">📑 Table of Contents</div>
            <div class="doc-nav-list">
              <button 
                v-for="item in docToc" 
                :key="item.id"
                :class="['doc-nav-item', `level-${item.level}`]"
                @click="scrollToHeading(item.id)"
              >
                {{ item.text }}
              </button>
            </div>
          </div>

          <!-- Doc Content -->
          <div class="doc-content-area">
            <!-- Loading -->
            <div class="doc-loading" v-if="systemDocLoading">
              <div class="loading-spinner"></div>
              <span>Loading system documentation...</span>
            </div>

            <!-- Error Message -->
            <div class="doc-error" v-else-if="systemDocError">
              <div class="error-icon">⚠️</div>
              <div class="error-text">{{ systemDocError }}</div>
              <button class="retry-btn" @click="fetchSystemDoc">Retry</button>
            </div>

            <!-- Doc Content -->
            <div class="markdown-content" v-else v-html="renderedDocContent"></div>
          </div>
        </div>

        <!-- API Endpoint List -->
        <div class="endpoints-list" v-else>
          <div class="category-header">
            <h3>
              <span class="cat-icon">{{ categories.find(c => c.id === activeCategory)?.icon }}</span>
              {{ categories.find(c => c.id === activeCategory)?.name }}
            </h3>
            <span class="cat-count">{{ filteredEndpoints.length }} endpoints</span>
          </div>

          <!-- Empty State -->
          <div class="empty-state" v-if="filteredEndpoints.length === 0">
            <div class="empty-icon">🔍</div>
            <div class="empty-text">No matching API found</div>
          </div>

          <!-- 端点卡片 -->
          <div 
            v-for="(endpoint, index) in filteredEndpoints" 
            :key="index"
            class="endpoint-card"
          >
            <div class="endpoint-header">
              <span 
                class="method-badge"
                :style="{ 
                  backgroundColor: methodColors[endpoint.method]?.bg,
                  color: methodColors[endpoint.method]?.text
                }"
              >
                {{ endpoint.method }}
              </span>
              <code class="endpoint-path">{{ endpoint.path }}</code>
              <button 
                class="copy-btn small" 
                @click="copyToClipboard(endpoint.path, `path-${index}`)"
              >
                {{ copiedEndpoint === `path-${index}` ? '✓' : '📋' }}
              </button>
            </div>

            <h4 class="endpoint-name">{{ endpoint.name }}</h4>
            <p class="endpoint-desc">{{ endpoint.description }}</p>

            <!-- Parameters -->
            <div class="endpoint-section" v-if="endpoint.params?.length">
              <h5>📥 Parameters</h5>
              <table class="params-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Location</th>
                    <th>Type</th>
                    <th>Description</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="param in endpoint.params" :key="param.name">
                    <td><code>{{ param.name }}</code></td>
                    <td><span class="location-badge">{{ param.location }}</span></td>
                    <td>{{ param.type }}</td>
                    <td>{{ param.description }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Request Body -->
            <div class="endpoint-section" v-if="endpoint.requestBody">
              <h5>📤 Request Body</h5>
              <table class="params-table">
                <thead>
                  <tr>
                    <th>Field</th>
                    <th>Type</th>
                    <th>Required</th>
                    <th>Description</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(field, name) in endpoint.requestBody" :key="name">
                    <td><code>{{ name }}</code></td>
                    <td>{{ field.type }}</td>
                    <td>{{ field.required ? 'Yes' : 'No' }}</td>
                    <td>{{ field.description }}<span v-if="field.default !== undefined" class="default-val">Default: {{ field.default }}</span></td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Response -->
            <div class="endpoint-section" v-if="endpoint.response">
              <h5>📩 Response</h5>
              <div class="response-fields">
                <div class="response-field" v-for="(desc, name) in endpoint.response" :key="name">
                  <code class="field-name">{{ name }}</code>
                  <span class="field-desc">{{ desc }}</span>
                </div>
              </div>
            </div>

            <!-- WebSocket Messages -->
            <div class="endpoint-section" v-if="endpoint.messages">
              <h5>📨 Message Types</h5>
              <div class="message-types">
                <div class="message-type" v-for="msg in endpoint.messages" :key="msg.type">
                  <code class="msg-type">{{ msg.type }}</code>
                  <span class="msg-desc">{{ msg.description }}</span>
                </div>
              </div>
            </div>

            <!-- Example Code -->
            <div class="endpoint-section" v-if="endpoint.example">
              <h5>💻 Example</h5>
              <div class="code-example">
                <div class="code-header">
                  <span>Code Example</span>
                  <button class="copy-btn" @click="copyToClipboard(endpoint.example, `example-${index}`)">
                    {{ copiedEndpoint === `example-${index}` ? '✓ Copied' : '📋 Copy' }}
                  </button>
                </div>
                <pre class="code-block"><code>{{ endpoint.example }}</code></pre>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.api-docs {
  position: fixed;
  top: 56px;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-primary, #0f172a);
  z-index: 100;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.docs-header {
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

.header-title .version {
  font-size: 0.65rem;
  padding: 0.2rem 0.4rem;
  background: var(--primary-color, #3b82f6);
  color: white;
  border-radius: 4px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-color, #334155);
  border-radius: 6px;
  background: var(--bg-dark, #1a1a2e);
  color: var(--text-secondary, #94a3b8);
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  border-color: var(--primary-color, #3b82f6);
  color: var(--text-primary, #e2e8f0);
}

.action-btn.swagger:hover {
  border-color: #10b981;
  color: #10b981;
}

.action-btn.redoc:hover {
  border-color: #8b5cf6;
  color: #8b5cf6;
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary, #94a3b8);
  font-size: 1.25rem;
  cursor: pointer;
  padding: 0.5rem;
  margin-left: 0.5rem;
}

.close-btn:hover {
  color: var(--error-color, #ef4444);
}

/* 主内容 */
.docs-content {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* 侧边栏 */
.docs-sidebar {
  width: 260px;
  background: var(--bg-secondary, #1e293b);
  border-right: 1px solid var(--border-color, #334155);
  overflow-y: auto;
  padding: 1rem 0;
  flex-shrink: 0;
}

.sidebar-section {
  padding: 0 1rem;
  margin-bottom: 1.5rem;
}

.section-title {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-secondary, #94a3b8);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.75rem;
}

.nav-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 0.75rem;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-secondary, #94a3b8);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.nav-item:hover {
  background: rgba(59, 130, 246, 0.1);
  color: var(--text-primary, #e2e8f0);
}

.nav-item.active {
  background: rgba(59, 130, 246, 0.15);
  color: var(--primary-color, #3b82f6);
}

.nav-icon {
  font-size: 1rem;
}

.nav-text {
  flex: 1;
}

.nav-count {
  font-size: 0.65rem;
  padding: 0.15rem 0.4rem;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}

.quick-links {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.quick-link {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 6px;
  color: var(--text-secondary, #94a3b8);
  font-size: 0.75rem;
  text-decoration: none;
  transition: all 0.2s;
}

.quick-link:hover {
  background: rgba(59, 130, 246, 0.1);
  color: var(--primary-color, #3b82f6);
}

.base-info {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.base-info .info-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.base-info .label {
  font-size: 0.65rem;
  color: var(--text-secondary, #94a3b8);
}

.base-info .value {
  font-size: 0.7rem;
  padding: 0.35rem 0.5rem;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 4px;
  color: var(--text-primary, #e2e8f0);
}

/* 主内容区 */
.docs-main {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
}

/* 搜索栏 */
.search-bar {
  display: flex;
  align-items: center;
  background: var(--bg-secondary, #1e293b);
  border: 1px solid var(--border-color, #334155);
  border-radius: 8px;
  padding: 0 1rem;
  margin-bottom: 1.5rem;
}

.search-icon {
  margin-right: 0.5rem;
}

.search-bar input {
  flex: 1;
  background: none;
  border: none;
  color: var(--text-primary, #e2e8f0);
  padding: 0.75rem 0;
  font-size: 0.875rem;
  outline: none;
}

.search-bar input::placeholder {
  color: var(--text-secondary, #94a3b8);
}

/* 概述页面 */
.overview-hero {
  text-align: center;
  padding: 3rem 2rem;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%);
  border-radius: 16px;
  margin-bottom: 2rem;
}

.hero-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
}

.overview-hero h1 {
  font-size: 2.5rem;
  font-weight: 700;
  color: var(--text-primary, #e2e8f0);
  margin: 0 0 0.5rem;
  background: linear-gradient(135deg, #60a5fa, #a78bfa);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hero-desc {
  font-size: 1rem;
  color: var(--text-secondary, #94a3b8);
  margin: 0;
}

.overview-intro {
  margin-bottom: 2rem;
}

.overview-intro h3 {
  font-size: 1.1rem;
  color: var(--text-primary, #e2e8f0);
  margin: 0 0 0.75rem;
}

.overview-intro p {
  font-size: 0.9rem;
  color: var(--text-secondary, #94a3b8);
  line-height: 1.6;
  margin: 0;
}

.feature-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.feature-card {
  background: var(--bg-secondary, #1e293b);
  border: 1px solid var(--border-color, #334155);
  border-radius: 12px;
  padding: 1.5rem;
  text-align: center;
  transition: all 0.2s;
}

.feature-card:hover {
  border-color: var(--primary-color, #3b82f6);
  transform: translateY(-2px);
}

.feature-icon {
  font-size: 2rem;
  margin-bottom: 0.75rem;
}

.feature-card h4 {
  font-size: 0.95rem;
  color: var(--text-primary, #e2e8f0);
  margin: 0 0 0.5rem;
}

.feature-card p {
  font-size: 0.8rem;
  color: var(--text-secondary, #94a3b8);
  margin: 0;
  line-height: 1.4;
}

.overview-section {
  margin-bottom: 2rem;
}

.overview-section h3 {
  font-size: 1.1rem;
  color: var(--text-primary, #e2e8f0);
  margin: 0 0 1rem;
}

.endpoint-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0.75rem;
}

.summary-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: var(--bg-secondary, #1e293b);
  border: 1px solid var(--border-color, #334155);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.summary-item:hover {
  border-color: var(--primary-color, #3b82f6);
  background: rgba(59, 130, 246, 0.05);
}

.summary-icon {
  font-size: 1.5rem;
}

.summary-info {
  display: flex;
  flex-direction: column;
}

.summary-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
}

.summary-count {
  font-size: 0.7rem;
  color: var(--text-secondary, #94a3b8);
}

/* 代码示例 */
.code-example {
  background: var(--bg-dark, #1a1a2e);
  border-radius: 10px;
  overflow: hidden;
}

.code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 1rem;
  background: rgba(0, 0, 0, 0.2);
  font-size: 0.75rem;
  color: var(--text-secondary, #94a3b8);
}

.copy-btn {
  background: rgba(59, 130, 246, 0.15);
  border: none;
  color: var(--primary-color, #3b82f6);
  padding: 0.3rem 0.6rem;
  border-radius: 4px;
  font-size: 0.7rem;
  cursor: pointer;
  transition: all 0.2s;
}

.copy-btn:hover {
  background: rgba(59, 130, 246, 0.25);
}

.copy-btn.small {
  padding: 0.2rem 0.4rem;
  font-size: 0.65rem;
}

.code-block {
  margin: 0;
  padding: 1rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  color: var(--text-primary, #e2e8f0);
  overflow-x: auto;
}

/* 端点列表 */
.category-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.category-header h3 {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.25rem;
  color: var(--text-primary, #e2e8f0);
  margin: 0;
}

.cat-icon {
  font-size: 1.5rem;
}

.cat-count {
  font-size: 0.75rem;
  color: var(--text-secondary, #94a3b8);
}

/* 端点卡片 */
.endpoint-card {
  background: var(--bg-secondary, #1e293b);
  border: 1px solid var(--border-color, #334155);
  border-radius: 12px;
  padding: 1.25rem;
  margin-bottom: 1rem;
}

.endpoint-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.method-badge {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-family: 'JetBrains Mono', monospace;
}

.endpoint-path {
  flex: 1;
  font-size: 0.85rem;
  color: var(--text-primary, #e2e8f0);
  background: var(--bg-dark, #1a1a2e);
  padding: 0.35rem 0.6rem;
  border-radius: 4px;
}

.endpoint-name {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
  margin: 0 0 0.5rem;
}

.endpoint-desc {
  font-size: 0.85rem;
  color: var(--text-secondary, #94a3b8);
  margin: 0;
  line-height: 1.5;
}

.endpoint-section {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-color, #334155);
}

.endpoint-section h5 {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
  margin: 0 0 0.75rem;
}

/* 参数表格 */
.params-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}

.params-table th,
.params-table td {
  padding: 0.5rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--border-color, #334155);
}

.params-table th {
  font-weight: 600;
  color: var(--text-secondary, #94a3b8);
  background: var(--bg-dark, #1a1a2e);
}

.params-table td {
  color: var(--text-primary, #e2e8f0);
}

.params-table code {
  background: var(--bg-dark, #1a1a2e);
  padding: 0.15rem 0.35rem;
  border-radius: 3px;
  font-size: 0.75rem;
}

.location-badge {
  font-size: 0.65rem;
  padding: 0.15rem 0.35rem;
  background: rgba(139, 92, 246, 0.15);
  color: #a78bfa;
  border-radius: 3px;
}

.default-val {
  font-size: 0.7rem;
  color: var(--text-secondary, #94a3b8);
  margin-left: 0.5rem;
}

/* 响应字段 */
.response-fields {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.response-field {
  display: flex;
  gap: 0.75rem;
  padding: 0.5rem;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 6px;
}

.field-name {
  font-size: 0.75rem;
  color: var(--primary-color, #3b82f6);
  min-width: 100px;
}

.field-desc {
  font-size: 0.75rem;
  color: var(--text-secondary, #94a3b8);
}

/* 消息类型 */
.message-types {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.message-type {
  display: flex;
  gap: 0.75rem;
  padding: 0.5rem;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 6px;
}

.msg-type {
  font-size: 0.75rem;
  color: #8b5cf6;
  min-width: 80px;
}

.msg-desc {
  font-size: 0.75rem;
  color: var(--text-secondary, #94a3b8);
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
  font-size: 1rem;
  color: var(--text-secondary, #94a3b8);
}

/* ========== 系统文档页面 ========== */
.system-docs-page {
  display: flex;
  gap: 1.5rem;
  height: 100%;
  overflow: hidden;
}

.doc-nav-sidebar {
  width: 280px;
  flex-shrink: 0;
  background: var(--bg-secondary, #1e293b);
  border: 1px solid var(--border-color, #334155);
  border-radius: 12px;
  padding: 1rem;
  overflow-y: auto;
  max-height: calc(100vh - 200px);
}

.doc-nav-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border-color, #334155);
}

.doc-nav-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.doc-nav-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 0.5rem 0.75rem;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-secondary, #94a3b8);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-nav-item:hover {
  background: rgba(59, 130, 246, 0.1);
  color: var(--text-primary, #e2e8f0);
}

.doc-nav-item.level-1 {
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
  font-size: 0.9rem;
  padding-left: 0.5rem;
  margin-top: 0.5rem;
}

.doc-nav-item.level-2 {
  padding-left: 1rem;
  font-weight: 500;
}

.doc-nav-item.level-3 {
  padding-left: 1.5rem;
  font-size: 0.75rem;
}

.doc-content-area {
  flex: 1;
  overflow-y: auto;
  padding-right: 0.5rem;
  max-height: calc(100vh - 200px);
}

.doc-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 2rem;
  gap: 1rem;
  color: var(--text-secondary, #94a3b8);
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border-color, #334155);
  border-top-color: var(--primary-color, #3b82f6);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.doc-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 2rem;
  gap: 1rem;
}

.error-icon {
  font-size: 3rem;
}

.error-text {
  font-size: 1rem;
  color: var(--error-color, #ef4444);
}

.retry-btn {
  padding: 0.5rem 1rem;
  background: var(--primary-color, #3b82f6);
  border: none;
  border-radius: 6px;
  color: white;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
}

.retry-btn:hover {
  background: #2563eb;
}

/* Markdown 内容样式 */
.markdown-content {
  line-height: 1.8;
  color: var(--text-primary, #e2e8f0);
}

.markdown-content h1 {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-primary, #e2e8f0);
  margin: 2rem 0 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 2px solid var(--primary-color, #3b82f6);
  background: linear-gradient(135deg, #60a5fa, #a78bfa);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.markdown-content h1:first-child {
  margin-top: 0;
}

.markdown-content h2 {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
  margin: 2rem 0 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--border-color, #334155);
}

.markdown-content h3 {
  font-size: 1.2rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
  margin: 1.5rem 0 0.75rem;
}

.markdown-content p {
  margin: 0.75rem 0;
  font-size: 0.95rem;
}

.markdown-content ul {
  margin: 0.75rem 0;
  padding-left: 1.5rem;
}

.markdown-content li {
  margin: 0.35rem 0;
  font-size: 0.9rem;
}

.markdown-content .code-block {
  margin: 1rem 0;
  padding: 1rem;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 8px;
  border: 1px solid var(--border-color, #334155);
  overflow-x: auto;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 0.85rem;
  line-height: 1.5;
}

.markdown-content .code-block code {
  background: none;
  padding: 0;
}

.markdown-content .inline-code {
  background: rgba(59, 130, 246, 0.15);
  color: var(--primary-color, #3b82f6);
  padding: 0.15rem 0.4rem;
  border-radius: 4px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 0.85em;
}

.markdown-content strong {
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
}

.markdown-content em {
  font-style: italic;
  color: var(--text-secondary, #94a3b8);
}

.markdown-content a {
  color: var(--primary-color, #3b82f6);
  text-decoration: none;
  transition: all 0.2s;
}

.markdown-content a:hover {
  text-decoration: underline;
}

.markdown-content hr {
  border: none;
  height: 1px;
  background: var(--border-color, #334155);
  margin: 2rem 0;
}

.markdown-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 1rem 0;
  font-size: 0.85rem;
}

.markdown-content th,
.markdown-content td {
  padding: 0.75rem;
  border: 1px solid var(--border-color, #334155);
  text-align: left;
}

.markdown-content th {
  background: var(--bg-dark, #1a1a2e);
  font-weight: 600;
}

.markdown-content blockquote {
  margin: 1rem 0;
  padding: 0.75rem 1rem;
  background: rgba(139, 92, 246, 0.1);
  border-left: 4px solid #8b5cf6;
  border-radius: 0 8px 8px 0;
}

.markdown-content blockquote p {
  margin: 0;
}
</style>

