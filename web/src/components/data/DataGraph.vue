<script setup lang="ts">
/**
 * 数据知识图谱可视化组件
 * 以真正的图结构展示数据集之间的关联
 */
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import type { CatalogEntry } from '@/types'

const props = defineProps<{
  entries: CatalogEntry[]
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'select', entry: CatalogEntry): void
  (e: 'load', entry: CatalogEntry): void
}>()

// 状态
const hoveredNode = ref<string | null>(null)
const selectedNode = ref<string | null>(null)
const containerRef = ref<HTMLElement | null>(null)
const graphWidth = ref(1200)
const graphHeight = ref(700)

// 节点类型配置
const nodeConfig: Record<string, { color: string; icon: string; gradient: string }> = {
  'Point': { color: '#3b82f6', icon: '📍', gradient: 'linear-gradient(135deg, #3b82f6, #1d4ed8)' },
  'MultiPoint': { color: '#3b82f6', icon: '📍', gradient: 'linear-gradient(135deg, #3b82f6, #1d4ed8)' },
  'LineString': { color: '#f59e0b', icon: '〰️', gradient: 'linear-gradient(135deg, #f59e0b, #d97706)' },
  'MultiLineString': { color: '#f59e0b', icon: '〰️', gradient: 'linear-gradient(135deg, #f59e0b, #d97706)' },
  'Polygon': { color: '#10b981', icon: '⬡', gradient: 'linear-gradient(135deg, #10b981, #059669)' },
  'MultiPolygon': { color: '#10b981', icon: '⬡', gradient: 'linear-gradient(135deg, #10b981, #059669)' },
  'Raster': { color: '#8b5cf6', icon: '🖼️', gradient: 'linear-gradient(135deg, #8b5cf6, #7c3aed)' },
  'Mixed': { color: '#8b5cf6', icon: '🔷', gradient: 'linear-gradient(135deg, #8b5cf6, #7c3aed)' },
  'Unknown': { color: '#8b5cf6', icon: '🔷', gradient: 'linear-gradient(135deg, #8b5cf6, #7c3aed)' },
  'default': { color: '#6b7280', icon: '📄', gradient: 'linear-gradient(135deg, #6b7280, #4b5563)' }
}

// 计算节点数据（带位置）
const graphNodes = computed(() => {
  const count = props.entries.length
  if (count === 0) return []
  
  // 确保居中，考虑容器padding
  const centerX = graphWidth.value / 2
  const centerY = graphHeight.value / 2
  // 根据节点数量和容器大小动态调整半径
  const baseRadius = Math.min(graphWidth.value, graphHeight.value) * 0.32
  const radius = Math.min(baseRadius, 280) // 限制最大半径
  
  return props.entries.map((entry, index) => {
    // 确定节点类型
    let nodeType = entry.geometry_type || 'default'
    const fileType = entry.file_type?.toLowerCase() || ''
    if (['geotiff', 'tif', 'tiff', 'cog'].some(t => fileType.includes(t))) {
      nodeType = 'Raster'
    } else if (nodeType === 'Unknown (any)') {
      nodeType = 'Mixed'
    }
    
    const config = nodeConfig[nodeType] || nodeConfig['default']
    
    // 计算位置（围绕中心分布，从顶部开始，顺时针）
    const startAngle = -Math.PI / 2 // 从顶部开始
    const angle = startAngle + (index / count) * 2 * Math.PI
    // 轻微的椭圆效果，让水平方向稍宽
    const rx = radius * 1.15
    const ry = radius * 0.95
    const x = centerX + rx * Math.cos(angle)
    const y = centerY + ry * Math.sin(angle)
    
    // 提取区域和关键信息
    const region = extractRegion(entry.name)
    const keyAttributes = extractKeyAttributes(entry.attributes || [])
    
    return {
      id: entry.id,
      name: entry.name,
      shortName: truncateName(entry.name, 16),
      type: nodeType,
      fileType: entry.file_type,
      region,
      featureCount: entry.feature_count,
      crs: entry.crs,
      bounds: entry.bounds,
      fileSize: entry.file_size_mb,
      description: entry.description,
      attributes: keyAttributes,
      allAttributesCount: entry.attributes?.length || 0,
      config,
      entry,
      x,
      y,
      angle
    }
  })
})

// 中心节点
const centerNode = computed(() => ({
  x: graphWidth.value / 2,
  y: graphHeight.value / 2
}))

// 计算连接线（从中心到每个节点 + 节点间的关联）
const connections = computed(() => {
  const conns: Array<{
    id: string
    x1: number
    y1: number
    x2: number
    y2: number
    type: 'center' | 'relation'
    label?: string
    fromId?: string
    toId?: string
  }> = []
  
  const nodes = graphNodes.value
  const cx = centerNode.value.x
  const cy = centerNode.value.y
  
  // 中心连接
  nodes.forEach(node => {
    conns.push({
      id: `center-${node.id}`,
      x1: cx,
      y1: cy,
      x2: node.x,
      y2: node.y,
      type: 'center',
      toId: node.id
    })
  })
  
  // 节点间关联（相同区域或相同类型）
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i]
      const b = nodes[j]
      
      // 相同区域
      if (a.region && b.region && a.region === b.region) {
        conns.push({
          id: `rel-${a.id}-${b.id}-region`,
          x1: a.x,
          y1: a.y,
          x2: b.x,
          y2: b.y,
          type: 'relation',
          label: a.region,
          fromId: a.id,
          toId: b.id
        })
      }
      // 相同几何类型（可选）
      // if (a.type === b.type && a.type !== 'default' && a.type !== 'Unknown') {
      //   conns.push({...})
      // }
    }
  }
  
  return conns
})

// 提取区域名称
function extractRegion(name: string): string {
  const regions = ['北京', '上海', '深圳', '广州', '杭州', '南京', '成都', '武汉', '清华', '浦东', '西安', '重庆', '天津']
  for (const region of regions) {
    if (name.includes(region)) return region
  }
  return ''
}

// 截断名称
function truncateName(name: string, maxLen: number): string {
  if (name.length <= maxLen) return name
  return name.slice(0, maxLen - 2) + '...'
}

// 提取关键属性
function extractKeyAttributes(attributes: any[]): string[] {
  const result: string[] = []
  for (const attr of attributes) {
    if (result.length >= 5) break
    const attrName = typeof attr === 'string' ? attr : attr?.name
    if (attrName) result.push(attrName)
  }
  return result
}

// 格式化数量
function formatCount(count?: number): string {
  if (!count) return '-'
  if (count >= 10000) return `${(count / 10000).toFixed(1)}W`
  if (count >= 1000) return `${(count / 1000).toFixed(1)}K`
  return count.toString()
}

// 格式化文件大小
function formatSize(sizeMb?: number): string {
  if (!sizeMb) return '-'
  if (sizeMb < 0.01) return '<10KB'
  if (sizeMb < 1) return `${(sizeMb * 1024).toFixed(0)}KB`
  return `${sizeMb.toFixed(1)}MB`
}

// 判断连接是否高亮
function isConnectionHighlighted(conn: any): boolean {
  if (!hoveredNode.value) return false
  return conn.toId === hoveredNode.value || conn.fromId === hoveredNode.value
}

// 判断节点是否高亮
function isNodeHighlighted(nodeId: string): boolean {
  if (!hoveredNode.value) return true
  if (nodeId === hoveredNode.value) return true
  // 检查是否有关联
  return connections.value.some(c => 
    c.type === 'relation' && 
    ((c.fromId === hoveredNode.value && c.toId === nodeId) ||
     (c.toId === hoveredNode.value && c.fromId === nodeId))
  )
}

// 选择节点
function selectNode(node: any) {
  selectedNode.value = selectedNode.value === node.id ? null : node.id
}

// 关闭详情
function closeDetail(event: MouseEvent) {
  // 点击背景时关闭详情
  if ((event.target as HTMLElement).classList.contains('knowledge-graph')) {
    selectedNode.value = null
  }
}

// 加载到地图
function loadToMap(node: any) {
  emit('load', node.entry)
}

// 查看详情
function viewDetails(node: any) {
  emit('select', node.entry)
}

// 更新尺寸
function updateSize() {
  if (containerRef.value) {
    graphWidth.value = containerRef.value.clientWidth
    graphHeight.value = containerRef.value.clientHeight || 550
  }
}

onMounted(() => {
  updateSize()
  window.addEventListener('resize', updateSize)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateSize)
})

watch(() => props.visible, (visible) => {
  if (visible) {
    nextTick(updateSize)
  }
})
</script>

<template>
  <div class="knowledge-graph" ref="containerRef" v-if="visible && entries.length > 0" @click="closeDetail">
    <!-- SVG 连接层 -->
    <svg class="connections-layer" :width="graphWidth" :height="graphHeight">
      <defs>
        <!-- 渐变定义 -->
        <linearGradient id="centerGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.6" />
          <stop offset="100%" stop-color="#8b5cf6" stop-opacity="0.2" />
        </linearGradient>
        <linearGradient id="relationGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#f59e0b" stop-opacity="0.8" />
          <stop offset="100%" stop-color="#ef4444" stop-opacity="0.8" />
        </linearGradient>
        <!-- 发光效果 -->
        <filter id="glow">
          <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
          <feMerge>
            <feMergeNode in="coloredBlur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
        <!-- 箭头 -->
        <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill="#3b82f6" opacity="0.6" />
        </marker>
      </defs>
      
      <!-- 背景网格 -->
      <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
        <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(59, 130, 246, 0.05)" stroke-width="1"/>
      </pattern>
      <rect width="100%" height="100%" fill="url(#grid)" />
      
      <!-- 中心连接线 -->
      <g class="center-connections">
        <line
          v-for="conn in connections.filter(c => c.type === 'center')"
          :key="conn.id"
          :x1="conn.x1"
          :y1="conn.y1"
          :x2="conn.x2"
          :y2="conn.y2"
          class="connection-line center"
          :class="{ highlighted: isConnectionHighlighted(conn), dimmed: hoveredNode && !isConnectionHighlighted(conn) }"
        />
      </g>
      
      <!-- 关联连接线（曲线） -->
      <g class="relation-connections">
        <g v-for="conn in connections.filter(c => c.type === 'relation')" :key="conn.id">
          <path
            :d="`M ${conn.x1} ${conn.y1} Q ${centerNode.x} ${centerNode.y} ${conn.x2} ${conn.y2}`"
            class="connection-line relation"
            :class="{ highlighted: isConnectionHighlighted(conn), dimmed: hoveredNode && !isConnectionHighlighted(conn) }"
          />
          <!-- 关联标签 -->
          <text
            v-if="conn.label && isConnectionHighlighted(conn)"
            :x="(conn.x1 + conn.x2) / 2"
            :y="(conn.y1 + conn.y2) / 2 - 10"
            class="relation-label"
          >
            {{ conn.label }}
          </text>
        </g>
      </g>
      
      <!-- 动态粒子效果 -->
      <g class="particles">
        <circle
          v-for="(conn, idx) in connections.filter(c => c.type === 'center')"
          :key="`particle-${idx}`"
          r="3"
          class="particle"
          :style="{ animationDelay: `${idx * 0.3}s` }"
        >
          <animateMotion
            :dur="`${2 + idx * 0.2}s`"
            repeatCount="indefinite"
            :path="`M ${conn.x1} ${conn.y1} L ${conn.x2} ${conn.y2}`"
          />
        </circle>
      </g>
    </svg>
    
    <!-- 中心节点 -->
    <div 
      class="center-hub"
      :style="{ left: centerNode.x + 'px', top: centerNode.y + 'px' }"
    >
      <div class="hub-ring ring-1"></div>
      <div class="hub-ring ring-2"></div>
      <div class="hub-ring ring-3"></div>
      <div class="hub-core">
        <span class="hub-icon">🌐</span>
        <span class="hub-text">AutoGIS</span>
        <span class="hub-count">{{ entries.length }} Datasets</span>
      </div>
    </div>
    
    <!-- 数据节点 -->
    <div
      v-for="node in graphNodes"
      :key="node.id"
      class="graph-node"
      :class="{ 
        selected: selectedNode === node.id,
        highlighted: isNodeHighlighted(node.id),
        dimmed: hoveredNode && !isNodeHighlighted(node.id)
      }"
      :style="{ 
        left: node.x + 'px', 
        top: node.y + 'px',
        '--node-color': node.config.color,
        '--node-gradient': node.config.gradient
      }"
      @mouseenter="hoveredNode = node.id"
      @mouseleave="hoveredNode = null"
      @click="selectNode(node)"
    >
      <!-- 节点主体 -->
      <div class="node-body">
        <div class="node-icon">{{ node.config.icon }}</div>
        <div class="node-info">
          <div class="node-name">{{ node.shortName }}</div>
          <div class="node-type">{{ node.fileType }}</div>
        </div>
        <div class="node-badge" v-if="node.featureCount">
          {{ formatCount(node.featureCount) }}
        </div>
      </div>
      
      <!-- 展开的详情卡片 -->
      <div class="node-detail-card" v-if="selectedNode === node.id" @click.stop>
        <div class="detail-header">
          <span class="detail-title">{{ node.name }}</span>
          <button class="detail-close" @click="selectedNode = null">✕</button>
        </div>
        
        <div class="detail-stats">
          <div class="stat-item" v-if="node.featureCount">
            <span class="stat-icon">📊</span>
            <span class="stat-value">{{ formatCount(node.featureCount) }}</span>
            <span class="stat-label">Features</span>
          </div>
          <div class="stat-item" v-if="node.fileSize">
            <span class="stat-icon">💾</span>
            <span class="stat-value">{{ formatSize(node.fileSize) }}</span>
            <span class="stat-label">Size</span>
          </div>
          <div class="stat-item" v-if="node.crs">
            <span class="stat-icon">🌐</span>
            <span class="stat-value">{{ node.crs.replace('EPSG:', '') }}</span>
            <span class="stat-label">CRS</span>
          </div>
          <div class="stat-item" v-if="node.type !== 'default'">
            <span class="stat-icon">{{ node.config.icon }}</span>
            <span class="stat-value">{{ node.type }}</span>
            <span class="stat-label">Type</span>
          </div>
        </div>
        
        <div class="detail-attributes" v-if="node.attributes.length > 0">
          <div class="attr-title">Attributes ({{ node.allAttributesCount }})</div>
          <div class="attr-tags">
            <span class="attr-tag" v-for="attr in node.attributes" :key="attr">{{ attr }}</span>
            <span class="attr-more" v-if="node.allAttributesCount > 5">+{{ node.allAttributesCount - 5 }}</span>
          </div>
        </div>
        
        <div class="detail-desc" v-if="node.description">
          {{ node.description.slice(0, 80) }}{{ node.description.length > 80 ? '...' : '' }}
        </div>
        
        <div class="detail-actions">
          <button class="action-btn view" @click.stop="viewDetails(node)">
            👁️ Details
          </button>
          <button class="action-btn load" @click.stop="loadToMap(node)">
            📍 Load
          </button>
        </div>
      </div>
    </div>
    
    <!-- 图例 -->
    <div class="graph-legend">
      <div class="legend-title">🕸️ Data Knowledge Graph</div>
      <div class="legend-items">
        <div class="legend-item">
          <span class="legend-color" style="background: #3b82f6;"></span>
          <span>Point</span>
        </div>
        <div class="legend-item">
          <span class="legend-color" style="background: #f59e0b;"></span>
          <span>Line</span>
        </div>
        <div class="legend-item">
          <span class="legend-color" style="background: #10b981;"></span>
          <span>Polygon</span>
        </div>
        <div class="legend-item">
          <span class="legend-color" style="background: #ef4444;"></span>
          <span>Raster</span>
        </div>
        <div class="legend-item">
          <span class="legend-color" style="background: #8b5cf6;"></span>
          <span>Mixed</span>
        </div>
      </div>
      <div class="legend-tip">
        💡 Click node for details | Hover to highlight relations
      </div>
    </div>
    
    <!-- 统计信息 -->
    <div class="graph-stats">
      <div class="stat-box">
        <span class="stat-num">{{ entries.length }}</span>
        <span class="stat-txt">Datasets</span>
      </div>
      <div class="stat-box">
        <span class="stat-num">{{ connections.filter(c => c.type === 'relation').length }}</span>
        <span class="stat-txt">Relations</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.knowledge-graph {
  position: relative;
  width: 100%;
  height: calc(100vh - 180px);
  min-height: 550px;
  background: radial-gradient(ellipse at center, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 0.98) 100%);
  border-radius: 16px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* SVG 连接层 */
.connections-layer {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
}

.connection-line {
  stroke-linecap: round;
  transition: all 0.3s ease;
}

.connection-line.center {
  stroke: url(#centerGradient);
  stroke-width: 2;
  stroke-dasharray: 8 4;
  animation: dash 20s linear infinite;
}

.connection-line.center.highlighted {
  stroke: #3b82f6;
  stroke-width: 3;
  filter: url(#glow);
}

.connection-line.center.dimmed {
  opacity: 0.15;
}

.connection-line.relation {
  stroke: url(#relationGradient);
  stroke-width: 2.5;
  fill: none;
  stroke-dasharray: 6 3;
  animation: dash 15s linear infinite reverse;
}

.connection-line.relation.highlighted {
  stroke: #f59e0b;
  stroke-width: 4;
  filter: url(#glow);
}

.connection-line.relation.dimmed {
  opacity: 0.1;
}

.relation-label {
  fill: #f59e0b;
  font-size: 12px;
  font-weight: 600;
  text-anchor: middle;
  filter: url(#glow);
}

@keyframes dash {
  to {
    stroke-dashoffset: -100;
  }
}

/* 粒子效果 */
.particle {
  fill: #60a5fa;
  opacity: 0.8;
  filter: url(#glow);
}

/* 中心节点 */
.center-hub {
  position: absolute;
  width: 240px;
  height: 240px;
  transform: translate(-50%, -50%);
  z-index: 10;
}

.hub-ring {
  position: absolute;
  border-radius: 50%;
  border: 2px solid;
  animation: pulse 3s ease-in-out infinite;
}

.hub-ring.ring-1 {
  width: 150px;
  height: 150px;
  top: 50%;
  left: 50%;
  margin-top: -75px;
  margin-left: -75px;
  border-color: rgba(59, 130, 246, 0.4);
  animation-delay: 0s;
}

.hub-ring.ring-2 {
  width: 190px;
  height: 190px;
  top: 50%;
  left: 50%;
  margin-top: -95px;
  margin-left: -95px;
  border-color: rgba(139, 92, 246, 0.25);
  animation-delay: 1s;
}

.hub-ring.ring-3 {
  width: 230px;
  height: 230px;
  top: 50%;
  left: 50%;
  margin-top: -115px;
  margin-left: -115px;
  border-color: rgba(59, 130, 246, 0.15);
  animation-delay: 2s;
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.1);
    opacity: 0.5;
  }
}

.hub-core {
  width: 110px;
  height: 110px;
  border-radius: 50%;
  background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
  border: 3px solid #3b82f6;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  box-shadow: 
    0 0 40px rgba(59, 130, 246, 0.5),
    0 0 80px rgba(59, 130, 246, 0.25),
    inset 0 0 30px rgba(59, 130, 246, 0.15);
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 1;
}

.hub-icon {
  font-size: 2rem;
  margin-bottom: 0.25rem;
}

.hub-text {
  font-size: 0.9rem;
  font-weight: 700;
  color: #e2e8f0;
  background: linear-gradient(135deg, #60a5fa, #a78bfa);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hub-count {
  font-size: 0.65rem;
  color: #94a3b8;
  margin-top: 0.15rem;
}

/* 数据节点 */
.graph-node {
  position: absolute;
  transform: translate(-50%, -50%);
  z-index: 5;
  cursor: pointer;
  transition: all 0.3s ease;
}

.graph-node:hover {
  z-index: 20;
}

.graph-node.dimmed {
  opacity: 0.3;
}

.graph-node.highlighted {
  opacity: 1;
}

.node-body {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 0.8rem;
  background: linear-gradient(135deg, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 0.95) 100%);
  border: 2px solid var(--node-color);
  border-radius: 12px;
  box-shadow: 
    0 4px 20px rgba(0, 0, 0, 0.4),
    0 0 15px color-mix(in srgb, var(--node-color) 30%, transparent);
  transition: all 0.3s ease;
  min-width: 140px;
}

.graph-node:hover .node-body {
  transform: scale(1.05);
  box-shadow: 
    0 8px 30px rgba(0, 0, 0, 0.5),
    0 0 25px color-mix(in srgb, var(--node-color) 50%, transparent);
}

.graph-node.selected .node-body {
  border-color: #f59e0b;
  box-shadow: 
    0 8px 30px rgba(0, 0, 0, 0.5),
    0 0 30px rgba(245, 158, 11, 0.4);
}

.node-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--node-gradient);
  border-radius: 8px;
  font-size: 1.1rem;
  flex-shrink: 0;
}

.node-info {
  flex: 1;
  min-width: 0;
}

.node-name {
  font-size: 0.8rem;
  font-weight: 600;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-type {
  font-size: 0.6rem;
  color: var(--node-color);
  margin-top: 0.15rem;
}

.node-badge {
  font-size: 0.6rem;
  padding: 0.2rem 0.4rem;
  background: rgba(0, 0, 0, 0.4);
  color: #94a3b8;
  border-radius: 4px;
  font-weight: 600;
}

/* 展开的详情卡片 */
.node-detail-card {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 320px;
  background: linear-gradient(180deg, rgba(30, 41, 59, 0.98) 0%, rgba(15, 23, 42, 0.98) 100%);
  border: 2px solid var(--node-color);
  border-radius: 14px;
  padding: 1.25rem;
  box-shadow: 
    0 20px 60px rgba(0, 0, 0, 0.6),
    0 0 30px color-mix(in srgb, var(--node-color) 30%, transparent);
  animation: fadeInScale 0.25s ease;
  z-index: 1000;
  backdrop-filter: blur(10px);
}

@keyframes fadeInScale {
  from {
    opacity: 0;
    transform: translateX(-50%) scale(0.9);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) scale(1);
  }
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.detail-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: #e2e8f0;
  word-break: break-word;
  flex: 1;
  padding-right: 0.5rem;
}

.detail-close {
  background: rgba(239, 68, 68, 0.15);
  border: none;
  color: #f87171;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}

.detail-close:hover {
  background: rgba(239, 68, 68, 0.3);
}

.detail-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.detail-stats .stat-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.4rem 0.5rem;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 6px;
}

.detail-stats .stat-icon {
  font-size: 0.75rem;
}

.detail-stats .stat-value {
  font-size: 0.75rem;
  font-weight: 600;
  color: #e2e8f0;
}

.detail-stats .stat-label {
  font-size: 0.55rem;
  color: #94a3b8;
}

.detail-attributes {
  margin-bottom: 0.75rem;
}

.attr-title {
  font-size: 0.65rem;
  color: #94a3b8;
  margin-bottom: 0.35rem;
}

.attr-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}

.attr-tag {
  font-size: 0.6rem;
  padding: 0.15rem 0.4rem;
  background: rgba(59, 130, 246, 0.15);
  color: #94a3b8;
  border-radius: 3px;
}

.attr-more {
  font-size: 0.6rem;
  padding: 0.15rem 0.4rem;
  background: rgba(139, 92, 246, 0.2);
  color: #a78bfa;
  border-radius: 3px;
}

.detail-desc {
  font-size: 0.7rem;
  color: #94a3b8;
  line-height: 1.4;
  margin-bottom: 0.75rem;
  padding: 0.5rem;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 6px;
}

.detail-actions {
  display: flex;
  gap: 0.5rem;
}

.detail-actions .action-btn {
  flex: 1;
  padding: 0.5rem;
  border: none;
  border-radius: 6px;
  font-size: 0.7rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.detail-actions .action-btn.view {
  background: rgba(139, 92, 246, 0.2);
  color: #a78bfa;
}

.detail-actions .action-btn.view:hover {
  background: rgba(139, 92, 246, 0.35);
}

.detail-actions .action-btn.load {
  background: rgba(16, 185, 129, 0.2);
  color: #34d399;
}

.detail-actions .action-btn.load:hover {
  background: rgba(16, 185, 129, 0.35);
}

/* 图例 */
.graph-legend {
  position: absolute;
  bottom: 1rem;
  left: 1rem;
  background: rgba(15, 23, 42, 0.9);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 10px;
  padding: 0.75rem 1rem;
  backdrop-filter: blur(10px);
}

.legend-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: #e2e8f0;
  margin-bottom: 0.5rem;
}

.legend-items {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-bottom: 0.5rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.65rem;
  color: #94a3b8;
}

.legend-color {
  width: 10px;
  height: 10px;
  border-radius: 3px;
}

.legend-tip {
  font-size: 0.6rem;
  color: #64748b;
}

/* 统计信息 */
.graph-stats {
  position: absolute;
  top: 1rem;
  right: 1rem;
  display: flex;
  gap: 0.75rem;
}

.graph-stats .stat-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.5rem 0.75rem;
  background: rgba(15, 23, 42, 0.9);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 8px;
  backdrop-filter: blur(10px);
}

.graph-stats .stat-num {
  font-size: 1.1rem;
  font-weight: 700;
  color: #60a5fa;
}

.graph-stats .stat-txt {
  font-size: 0.6rem;
  color: #94a3b8;
}
</style>
