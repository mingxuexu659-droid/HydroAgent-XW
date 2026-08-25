<script setup lang="ts">
/**
 * Code Viewer Component
 */
import { ref, computed, watch } from 'vue'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import 'highlight.js/styles/github-dark.css'

// Register Python syntax highlighting
hljs.registerLanguage('python', python)

// Props
const props = defineProps<{
  code: string | null
  collapsed?: boolean
}>()

// Emits
const emit = defineEmits<{
  (e: 'toggle'): void
  (e: 'copy'): void
  (e: 'load-code', code: string): void
  (e: 'execute-code', code: string): void
}>()

// State
const isCollapsed = ref(props.collapsed ?? true)
const copied = ref(false)
const isExecuting = ref(false)
const fileInput = ref<HTMLInputElement>()
const textareaRef = ref<HTMLTextAreaElement>()
const editableCode = ref(props.code || '')  // Editable code
const isEdited = ref(false)  // Whether code has been edited
const isNewScript = ref(false)  // Whether it's a new script

// Sync scroll
function syncScroll(event: Event) {
  const textarea = event.target as HTMLTextAreaElement
  const highlightLayer = textarea.parentElement?.querySelector('.highlight-layer') as HTMLElement
  const lineNumbers = textarea.parentElement?.parentElement?.querySelector('.line-numbers') as HTMLElement
  
  if (highlightLayer) {
    highlightLayer.scrollTop = textarea.scrollTop
    highlightLayer.scrollLeft = textarea.scrollLeft
  }
  if (lineNumbers) {
    lineNumbers.scrollTop = textarea.scrollTop
  }
}

// Watch props.code changes, sync to editableCode
watch(() => props.code, (newCode) => {
  if (newCode && !isEdited.value) {
    editableCode.value = newCode
  }
})

// Highlighted code (for read-only display, kept for future use)
const highlightedCode = computed(() => {
  if (!editableCode.value) return ''
  try {
    return hljs.highlight(editableCode.value, { language: 'python' }).value
  } catch {
    return editableCode.value
  }
})

// Line count
const lineCount = computed(() => {
  if (!editableCode.value) return 0
  return editableCode.value.split('\n').length
})

// Handle code editing
function onCodeChange(event: Event) {
  const target = event.target as HTMLTextAreaElement
  editableCode.value = target.value
  isEdited.value = true
}

// Reset to original code
function resetCode() {
  if (isNewScript.value) {
    // If it's a new script, clear and prompt to create new
    createNewScript()
    return
  }
  editableCode.value = props.code || ''
  isEdited.value = false
}

// Create new script
function createNewScript() {
  // If code exists and has been edited, confirm first
  if (editableCode.value && isEdited.value) {
    const confirmed = window.confirm('Current code has been edited. Creating a new script will overwrite it. Continue?')
    if (!confirmed) return
  }
  
  // Update timestamp in template
  const template = `# -*- coding: utf-8 -*-
"""
AutoGIS Spatial Analysis Script
Created: ${new Date().toLocaleString('en-US')}
"""

# Import necessary libraries
from qgis.core import *
from qgis.analysis import *
import geopandas as gpd
import numpy as np
import os

# ============ Configuration ============
# Output directory
OUTPUT_DIR = "./output/results"

# ============ Main Code ============
# Write your analysis code here

def main():
    """Main function"""
    # 1. Load data
    # gdf = gpd.read_file("path/to/your/data.geojson")
    
    # 2. Process data
    # ...
    
    # 3. Save results
    # output_path = os.path.join(OUTPUT_DIR, "result.geojson")
    # gdf.to_file(output_path, driver="GeoJSON")
    # print(f"Results saved to: {output_path}")
    
    pass

if __name__ == "__main__":
    main()
`
  
  editableCode.value = template
  isNewScript.value = true
  isEdited.value = false
  isCollapsed.value = false  // Auto expand
  
  // Focus on editor
  setTimeout(() => {
    textareaRef.value?.focus()
  }, 100)
}

// Watch collapsed property
watch(() => props.collapsed, (val) => {
  if (val !== undefined) {
    isCollapsed.value = val
  }
})

// Toggle collapse
function toggle() {
  isCollapsed.value = !isCollapsed.value
  emit('toggle')
}

// Copy code
async function copyCode() {
  if (!editableCode.value) return
  
  try {
    await navigator.clipboard.writeText(editableCode.value)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
    emit('copy')
  } catch (e) {
    console.error('Failed to copy:', e)
  }
}

// Download code
function downloadCode() {
  if (!editableCode.value) return
  
  const blob = new Blob([editableCode.value], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `analysis_${Date.now()}.py`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// Load code file
function triggerLoadFile() {
  fileInput.value?.click()
}

function handleFileLoad(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  
  const reader = new FileReader()
  reader.onload = (e) => {
    const code = e.target?.result as string
    emit('load-code', code)
  }
  reader.readAsText(file)
  target.value = '' // Reset to allow selecting same file again
}

// Execute code
async function executeCode() {
  if (!editableCode.value || isExecuting.value) return
  
  isExecuting.value = true
  emit('execute-code', editableCode.value)  // Use editable code
  
  // Reset state after simulated execution
  setTimeout(() => {
    isExecuting.value = false
  }, 2000)
}
</script>

<template>
  <div class="code-viewer" :class="{ collapsed: isCollapsed }">
    <!-- Hidden file input -->
    <input 
      ref="fileInput"
      type="file"
      accept=".py,.txt"
      style="display: none;"
      @change="handleFileLoad"
    />
    
    <!-- Header -->
    <div class="viewer-header" @click="toggle">
      <div class="header-left">
        <span class="icon">📝</span>
        <span class="title">Code</span>
        <span class="line-count" v-if="lineCount > 0">{{ lineCount }} lines</span>
      </div>
      <div class="header-right">
        <!-- New script button -->
        <button 
          v-if="!isCollapsed"
          class="action-btn new-script"
          @click.stop="createNewScript"
          title="Create new blank script"
        >
          ✨ New
        </button>
        <!-- Load code button -->
        <button 
          v-if="!isCollapsed"
          class="action-btn primary"
          @click.stop="triggerLoadFile"
          title="Load local code file"
        >
          📂 Load
        </button>
        <!-- Execute button -->
        <button 
          v-if="!isCollapsed && editableCode"
          class="action-btn execute"
          @click.stop="executeCode"
          :disabled="isExecuting"
          title="Execute code"
        >
          <span v-if="isExecuting" class="spinner-small"></span>
          {{ isExecuting ? 'Running...' : '▶️ Run' }}
        </button>
        <button 
          v-if="!isCollapsed && editableCode"
          class="action-btn"
          @click.stop="copyCode"
          :title="copied ? 'Copied' : 'Copy code'"
        >
          {{ copied ? '✓' : '📋' }}
        </button>
        <button 
          v-if="!isCollapsed && editableCode"
          class="action-btn"
          @click.stop="downloadCode"
          title="Download code"
        >
          💾
        </button>
        <button class="toggle-btn" :title="isCollapsed ? 'Expand' : 'Collapse'">
          {{ isCollapsed ? '▼' : '▲' }}
        </button>
      </div>
    </div>

    <!-- Code content -->
    <div class="viewer-content" v-show="!isCollapsed">
      <div v-if="editableCode || code" class="code-container">
        <div class="code-editor-wrapper">
          <!-- Line numbers -->
          <div class="line-numbers" aria-hidden="true">
            <span v-for="n in lineCount" :key="n">{{ n }}</span>
          </div>
          <!-- Code edit area -->
          <div class="code-area">
            <!-- Syntax highlight layer (background) -->
            <pre class="highlight-layer" aria-hidden="true"><code v-html="highlightedCode"></code></pre>
            <!-- Editable layer (foreground, transparent) -->
            <textarea 
              class="code-editor"
              :value="editableCode"
              @input="onCodeChange"
              @scroll="syncScroll"
              ref="textareaRef"
              spellcheck="false"
              placeholder="Enter or edit code here..."
            ></textarea>
          </div>
          <!-- Edit status indicator -->
          <div class="edit-indicator" v-if="isNewScript || isEdited">
            <span v-if="isNewScript" class="new-badge">New Script</span>
            <span v-else-if="isEdited" class="edit-badge">Edited</span>
            <button v-if="isEdited && !isNewScript" class="reset-btn" @click="resetCode" title="Reset to original code">↺ Reset</button>
          </div>
        </div>
      </div>
      <div v-else class="empty-state">
        <div class="empty-icon">📝</div>
        <p>No code yet</p>
        <p class="hint">Click <strong>✨ New</strong> to create a script, or <strong>📂 Load</strong> a local code file</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.code-viewer {
  background: var(--bg-panel, #16213e);
  border-top: 1px solid var(--border-color, #334155);
  display: flex;
  flex-direction: column;
  max-height: 50%;
  transition: max-height 0.3s ease;
}

.code-viewer.collapsed {
  max-height: 44px;
}

.viewer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  cursor: pointer;
  user-select: none;
  border-bottom: 1px solid var(--border-color, #334155);
}

.viewer-header:hover {
  background: rgba(59, 130, 246, 0.05);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.icon {
  font-size: 1rem;
}

.title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
}

.line-count {
  font-size: 0.75rem;
  color: var(--text-secondary, #94a3b8);
  padding: 0.125rem 0.375rem;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 4px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.action-btn {
  padding: 0.2rem 0.4rem;
  border: 1px solid var(--border-color, #334155);
  border-radius: 4px;
  background: transparent;
  color: var(--text-secondary, #94a3b8);
  font-size: 0.7rem;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 0.2rem;
}

.action-btn:hover:not(:disabled) {
  border-color: var(--primary-color, #3b82f6);
  color: var(--primary-color, #3b82f6);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.new-script {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
  border-color: #f59e0b;
  color: white;
}

.action-btn.new-script:hover {
  background: linear-gradient(135deg, #d97706 0%, #b45309 100%);
  border-color: #d97706;
  color: white;
}

.action-btn.primary {
  background: var(--primary-color, #3b82f6);
  border-color: var(--primary-color, #3b82f6);
  color: white;
}

.action-btn.primary:hover {
  background: #2563eb;
  border-color: #2563eb;
  color: white;
}

.action-btn.execute {
  background: var(--success-color, #10b981);
  border-color: var(--success-color, #10b981);
  color: white;
}

.action-btn.execute:hover:not(:disabled) {
  background: #059669;
  border-color: #059669;
  color: white;
}

.spinner-small {
  width: 10px;
  height: 10px;
  border: 2px solid transparent;
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.toggle-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--text-secondary, #94a3b8);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
}

.viewer-content {
  flex: 1;
  overflow: auto;
}

.code-container {
  padding: 0.5rem;
}

.code-editor-wrapper {
  position: relative;
  display: flex;
  background: #0d1117;
  border: 1px solid var(--border-color, #334155);
  border-radius: 8px;
  overflow: hidden;
}

/* Line numbers */
.line-numbers {
  display: flex;
  flex-direction: column;
  padding: 1rem 0.75rem;
  background: #161b22;
  border-right: 1px solid #30363d;
  color: #6e7681;
  font-family: 'Fira Code', 'Consolas', 'Monaco', monospace;
  font-size: 0.8125rem;
  line-height: 1.6;
  text-align: right;
  user-select: none;
  overflow: auto;
  min-width: 3rem;
  max-height: 450px;
  -ms-overflow-style: none;
  scrollbar-width: none;
}

.line-numbers::-webkit-scrollbar {
  display: none;
}

.line-numbers span {
  display: block;
}

/* Code edit area */
.code-area {
  position: relative;
  flex: 1;
  min-height: 300px;
  max-height: 450px;
  overflow: hidden;
}

/* Syntax highlight layer - hide scrollbar but scrollable */
.highlight-layer {
  position: absolute;
  top: 0;
  left: 0;
  right: -20px;  /* 隐藏滚动条 */
  bottom: 0;
  margin: 0;
  padding: 1rem;
  padding-right: calc(1rem + 20px);  /* 补偿隐藏的滚动条 */
  background: transparent;
  overflow: auto;
  pointer-events: none;
  white-space: pre;
  word-wrap: normal;
}

.highlight-layer code {
  display: block;
  font-family: 'Fira Code', 'Consolas', 'Monaco', monospace;
  font-size: 0.8125rem;
  line-height: 1.6;
  color: #c9d1d9;
}

/* Editable layer */
.code-editor {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  padding: 1rem;
  background: transparent;
  border: none;
  color: transparent;
  caret-color: #58a6ff;
  font-family: 'Fira Code', 'Consolas', 'Monaco', monospace;
  font-size: 0.8125rem;
  line-height: 1.6;
  resize: none;
  outline: none;
  tab-size: 4;
  white-space: pre;
  word-wrap: normal;
  overflow: auto;
}

/* Hide highlight layer scrollbar */
.highlight-layer::-webkit-scrollbar {
  display: none;
}

.highlight-layer {
  -ms-overflow-style: none;
  scrollbar-width: none;
}

.code-editor::placeholder {
  color: #6e7681;
}

.code-editor:focus {
  outline: none;
}

.code-editor-wrapper:focus-within {
  border-color: var(--primary-color, #3b82f6);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}

/* Edit status indicator */
.edit-indicator {
  position: absolute;
  top: 0.5rem;
  right: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  z-index: 10;
}

.edit-badge {
  font-size: 0.65rem;
  padding: 0.15rem 0.4rem;
  background: #f59e0b;
  color: #000;
  border-radius: 4px;
  font-weight: 600;
}

.new-badge {
  font-size: 0.65rem;
  padding: 0.15rem 0.4rem;
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  color: white;
  border-radius: 4px;
  font-weight: 600;
}

.reset-btn {
  font-size: 0.65rem;
  padding: 0.15rem 0.4rem;
  background: rgba(0, 0, 0, 0.5);
  border: 1px solid #30363d;
  color: #8b949e;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.reset-btn:hover {
  border-color: #58a6ff;
  color: #58a6ff;
}

.empty-state {
  padding: 2.5rem;
  text-align: center;
  color: var(--text-secondary, #94a3b8);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.empty-icon {
  font-size: 3rem;
  opacity: 0.5;
}

.empty-state p {
  margin: 0;
}

.empty-state .hint {
  font-size: 0.8rem;
  margin-top: 0.25rem;
  line-height: 1.5;
}

.empty-state .hint strong {
  color: var(--text-primary, #e2e8f0);
}
</style>

