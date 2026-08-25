<script setup lang="ts">
/**
 * Query Input Component
 */
import { computed } from 'vue'
import { useTaskStore } from '@/stores/task'

// Props
const props = defineProps<{
  loading?: boolean
}>()

// Emits
const emit = defineEmits<{
  (e: 'submit', data: {
    query: string
    skip_download: boolean
    auto_run: boolean
    auto_optimize: boolean
    max_optimization_rounds: number
  }): void
}>()

// Use store to persist state (won't be lost when switching views)
const taskStore = useTaskStore()

// Query text (two-way binding to store)
const query = computed({
  get: () => taskStore.queryText,
  set: (val: string) => { taskStore.queryText = val }
})

// Options (directly use reactive object from store)
const options = taskStore.queryOptions

// Quick Templates
const templates = [
  { label: 'Buffer Analysis', query: 'Set buffer of 600 meters for Tsinghua University and Peking University vector boundaries, display boundaries, buffers and intersection areas' },
  { label: 'NDVI Calculation', query: 'Calculate NDVI from Sentinel-2 imagery over Beijing and analyze the data distribution.' },
  { label: 'Road Network', query: 'Analyze road network density of Shanghai Pudong' },
  { label: 'Land Use', query: 'Download Shenzhen land use data, group by landuse field, calculate total area for each land type, output statistics table, visualize different land use types' }
]

// Apply template
function applyTemplate(templateQuery: string) {
  query.value = templateQuery
}

// Submit
function submit() {
  if (!query.value.trim() || props.loading) return
  
  emit('submit', {
    query: query.value.trim(),
    skip_download: options.skip_download,
    auto_run: options.auto_run,
    auto_optimize: options.auto_optimize,
    max_optimization_rounds: options.max_optimization_rounds
  })
}

// Handle keyboard events
function handleKeydown(e: KeyboardEvent) {
  if (e.ctrlKey && e.key === 'Enter') {
    submit()
  }
}
</script>

<template>
  <div class="query-input">
    <h3 class="section-title">
      <span class="icon">🔍</span>
      Spatial Analysis
    </h3>
    
    <div class="input-wrapper">
      <textarea
        v-model="query"
        placeholder="Enter your spatial analysis requirements...&#10;Example: Download Beijing Sentinel-2 imagery and calculate NDVI"
        rows="4"
        :disabled="loading"
        @keydown="handleKeydown"
      ></textarea>
    </div>

    <!-- Quick Templates -->
    <div class="templates">
      <span class="templates-label">Templates:</span>
      <button 
        v-for="template in templates" 
        :key="template.label"
        @click="applyTemplate(template.query)"
        class="template-tag"
        :disabled="loading"
      >
        {{ template.label }}
      </button>
    </div>

    <!-- Options -->
    <div class="options">
      <label class="option">
        <input type="checkbox" v-model="options.skip_download" :disabled="loading">
        <span>Skip Data Download</span>
      </label>
      <label class="option">
        <input type="checkbox" v-model="options.auto_run" :disabled="loading">
        <span>Auto Execute Script</span>
      </label>
      <label class="option">
        <input type="checkbox" v-model="options.auto_optimize" :disabled="loading">
        <span>Auto Optimize Code</span>
      </label>
    </div>

    <!-- Submit Button -->
    <button 
      class="submit-btn"
      :disabled="!query.trim() || loading"
      @click="submit"
    >
      <span v-if="loading" class="spinner"></span>
      <span v-else>🚀</span>
      {{ loading ? 'Analyzing...' : 'Start Analysis' }}
    </button>
  </div>
</template>

<style scoped>
.query-input {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-color, #334155);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: var(--text-primary, #e2e8f0);
}

.icon {
  font-size: 1rem;
}

.input-wrapper textarea {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-color, #334155);
  border-radius: 8px;
  background: var(--bg-dark, #1a1a2e);
  color: var(--text-primary, #e2e8f0);
  font-size: 0.875rem;
  line-height: 1.4;
  resize: none;
  transition: border-color 0.2s;
  font-family: inherit;
}

.input-wrapper textarea:focus {
  outline: none;
  border-color: var(--primary-color, #3b82f6);
}

.input-wrapper textarea::placeholder {
  color: var(--text-secondary, #94a3b8);
}

.input-wrapper textarea:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.templates {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 0.25rem;
  margin-top: 0.25rem;
  margin-bottom: 0.2rem;
}

.templates-label {
  font-size: 0.65rem;
  color: var(--text-secondary, #94a3b8);
  white-space: nowrap;
}

.template-tag {
  padding: 0.1rem 0.25rem;
  border: 1px solid var(--border-color, #334155);
  border-radius: 3px;
  background: transparent;
  color: var(--text-secondary, #94a3b8);
  font-size: 0.6rem;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.template-tag:hover:not(:disabled) {
  border-color: var(--primary-color, #3b82f6);
  color: var(--primary-color, #3b82f6);
}

.template-tag:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.options {
  display: flex;
  flex-wrap: nowrap;
  gap: 0.4rem;
  margin-top: 0.15rem;
  margin-bottom: 0.2rem;
}

.option {
  display: flex;
  align-items: center;
  gap: 0.15rem;
  font-size: 0.65rem;
  color: var(--text-secondary, #94a3b8);
  cursor: pointer;
  white-space: nowrap;
}

.option input[type="checkbox"] {
  accent-color: var(--primary-color, #3b82f6);
  width: 11px;
  height: 11px;
  margin: 0;
}

.submit-btn {
  width: 100%;
  margin-top: 0.4rem;
  padding: 0.5rem;
  border: none;
  border-radius: 8px;
  background: var(--primary-color, #3b82f6);
  color: white;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  transition: all 0.2s;
}

.submit-btn:hover:not(:disabled) {
  background: #2563eb;
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid transparent;
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>

