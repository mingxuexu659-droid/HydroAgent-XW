<script setup lang="ts">
/**
 * Task Logs Component - Display raw output
 */
import { ref, watch, nextTick } from 'vue'

// Props
const props = defineProps<{
  logs: string  // Raw output text
  collapsed?: boolean
}>()

// State
const isCollapsed = ref(props.collapsed ?? false)
const logsContainer = ref<HTMLElement>()

// Auto scroll to bottom
watch(() => props.logs, async () => {
  if (!isCollapsed.value && logsContainer.value) {
    await nextTick()
    logsContainer.value.scrollTop = logsContainer.value.scrollHeight
  }
})

// Toggle collapse
function toggle() {
  isCollapsed.value = !isCollapsed.value
}
</script>

<template>
  <div class="task-logs" :class="{ collapsed: isCollapsed }">
    <!-- Header -->
    <div class="logs-header" @click="toggle">
      <div class="header-left">
        <span class="icon">📋</span>
        <span class="title">Execution Logs</span>
      </div>
      <button class="toggle-btn" :title="isCollapsed ? 'Expand' : 'Collapse'">
        {{ isCollapsed ? '▼' : '▲' }}
      </button>
    </div>

    <!-- Log Content -->
    <div class="logs-content" v-show="!isCollapsed" ref="logsContainer">
      <pre v-if="logs" class="log-text">{{ logs }}</pre>
      <div v-else class="empty-state">
        <p>No output yet</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.task-logs {
  border-bottom: 1px solid var(--border-color, #334155);
  max-height: 300px;
  display: flex;
  flex-direction: column;
}

.task-logs.collapsed {
  max-height: 44px;
}

.logs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0.75rem;
  cursor: pointer;
  user-select: none;
  background: var(--bg-panel, #16213e);
  flex-shrink: 0;
}

.logs-header:hover {
  background: rgba(59, 130, 246, 0.05);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.icon {
  font-size: 0.9rem;
}

.title {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
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
  font-size: 0.7rem;
}

.logs-content {
  flex: 1;
  overflow-y: auto;
  background: #0d1117;
  padding: 0.5rem;
}

.log-text {
  margin: 0;
  font-family: 'Consolas', 'Fira Code', monospace;
  font-size: 0.75rem;
  line-height: 1.5;
  color: #c9d1d9;
  white-space: pre-wrap;
  word-break: break-word;
}

.empty-state {
  text-align: center;
  padding: 1rem;
  color: var(--text-secondary, #94a3b8);
  font-size: 0.8rem;
}
</style>
