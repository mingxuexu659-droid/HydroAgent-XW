<script setup lang="ts">
/**
 * 要素属性面板组件
 */
import { computed } from 'vue'

// Props
const props = defineProps<{
  feature: GeoJSON.Feature | null
}>()

// Emits
const emit = defineEmits<{
  (e: 'close'): void
}>()

// Computed
const properties = computed(() => {
  if (!props.feature?.properties) return []
  return Object.entries(props.feature.properties).map(([key, value]) => ({
    key,
    value: formatValue(value)
  }))
})

const geometryType = computed(() => {
  return props.feature?.geometry?.type || 'Unknown'
})

// 格式化值
function formatValue(value: any): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
</script>

<template>
  <div class="feature-properties" v-if="feature">
    <div class="panel-header">
      <h3>Feature Properties</h3>
      <button class="close-btn" @click="emit('close')" title="Close">
        ✕
      </button>
    </div>
    
    <div class="geometry-info">
      <span class="geometry-type">{{ geometryType }}</span>
    </div>
    
    <div class="properties-list" v-if="properties.length > 0">
      <div 
        v-for="prop in properties" 
        :key="prop.key"
        class="property-item"
      >
        <span class="property-key">{{ prop.key }}</span>
        <span class="property-value">{{ prop.value }}</span>
      </div>
    </div>
    
    <div class="empty-state" v-else>
      <p>This feature has no property data</p>
    </div>
  </div>
</template>

<style scoped>
.feature-properties {
  padding: 1rem;
  background: var(--bg-panel, #16213e);
  height: 100%;
  overflow-y: auto;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.panel-header h3 {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
}

.close-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--text-secondary, #94a3b8);
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.close-btn:hover {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.geometry-info {
  margin-bottom: 1rem;
}

.geometry-type {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}

.properties-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.property-item {
  display: flex;
  flex-direction: column;
  padding: 0.5rem;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 4px;
}

.property-key {
  font-size: 0.75rem;
  color: var(--text-secondary, #94a3b8);
  margin-bottom: 0.25rem;
}

.property-value {
  font-size: 0.875rem;
  color: var(--text-primary, #e2e8f0);
  word-break: break-all;
}

.empty-state {
  text-align: center;
  padding: 2rem 1rem;
  color: var(--text-secondary, #94a3b8);
  font-size: 0.875rem;
}
</style>

