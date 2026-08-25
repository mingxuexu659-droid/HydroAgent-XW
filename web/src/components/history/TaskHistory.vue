<script setup lang="ts">
/**
 * Task History Component
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useTaskStore } from '@/stores/task'
import * as analysisApi from '@/api/analysis'
import type { Task, TaskStatus } from '@/types'

// Props
const props = defineProps<{
  visible: boolean
}>()

// Emits
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'load-task', task: Task): void
  (e: 'view-code', taskId: string): void
}>()

// Store
const taskStore = useTaskStore()

// State
const loading = ref(false)
const tasks = ref<Task[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)
const selectedTask = ref<Task | null>(null)
const searchQuery = ref('')
const statusFilter = ref<TaskStatus | 'all'>('all')
const taskCode = ref<string | null>(null)
const loadingCode = ref(false)

// Status configuration
const statusConfig: Record<TaskStatus, { label: string; color: string; icon: string }> = {
  'pending': { label: 'Pending', color: '#94a3b8', icon: '⏳' },
  'analyzing': { label: 'Analyzing', color: '#3b82f6', icon: '🔍' },
  'downloading': { label: 'Downloading', color: '#8b5cf6', icon: '📥' },
  'generating': { label: 'Generating', color: '#f59e0b', icon: '⚙️' },
  'executing': { label: 'Executing', color: '#06b6d4', icon: '▶️' },
  'optimizing': { label: 'Optimizing', color: '#ec4899', icon: '🔧' },
  'completed': { label: 'Completed', color: '#10b981', icon: '✅' },
  'failed': { label: 'Failed', color: '#ef4444', icon: '❌' }
}

// Filtered tasks
const filteredTasks = computed(() => {
  let result = tasks.value
  
  // Status filter
  if (statusFilter.value !== 'all') {
    result = result.filter(t => t.status === statusFilter.value)
  }
  
  // Search filter (in logs or message)
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(t => 
      t.message?.toLowerCase().includes(query) ||
      t.logs?.toLowerCase().includes(query) ||
      t.task_id.toLowerCase().includes(query)
    )
  }
  
  return result
})

// Paginated tasks
const paginatedTasks = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredTasks.value.slice(start, start + pageSize.value)
})

// Total pages
const totalPages = computed(() => Math.ceil(filteredTasks.value.length / pageSize.value))

// Load task list
async function loadTasks() {
  loading.value = true
  try {
    const response = await analysisApi.listTasks(100, 0)
    tasks.value = response.tasks
    total.value = response.total
  } catch (e) {
    console.error('Failed to load history:', e)
  } finally {
    loading.value = false
  }
}

// Format time
function formatTime(dateStr?: string): string {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  
  // Less than 1 minute
  if (diff < 60000) return 'Just now'
  // Less than 1 hour
  if (diff < 3600000) return `${Math.floor(diff / 60000)} min ago`
  // Less than 24 hours
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} hours ago`
  // Less than 7 days
  if (diff < 604800000) return `${Math.floor(diff / 86400000)} days ago`
  
  // Format date
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// Format duration
function formatDuration(task: Task): string {
  if (!task.created_at) return '-'
  const start = new Date(task.created_at)
  const end = task.updated_at ? new Date(task.updated_at) : new Date()
  const diff = end.getTime() - start.getTime()
  
  if (diff < 1000) return '<1s'
  if (diff < 60000) return `${Math.floor(diff / 1000)}s`
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ${Math.floor((diff % 60000) / 1000)}s`
  return `${Math.floor(diff / 3600000)}h ${Math.floor((diff % 3600000) / 60000)}m`
}

// Extract query content
function extractQuery(task: Task): string {
  // Extract user query from logs
  if (task.logs) {
    const match = task.logs.match(/User query[：:]\s*(.+?)(?:\n|$)/i)
    if (match) return match[1].trim()
    
    // Try other patterns
    const queryMatch = task.logs.match(/Start processing task[：:]?\s*(.+?)(?:\n|$)/i)
    if (queryMatch) return queryMatch[1].trim()
  }
  return task.message || 'Unknown task'
}

// View task details
async function viewTask(task: Task) {
  selectedTask.value = task
  taskCode.value = null
  
  // Load code
  if (task.status === 'completed') {
    loadingCode.value = true
    try {
      const response = await analysisApi.getTaskCode(task.task_id)
      taskCode.value = response.code
    } catch (e) {
      console.error('Failed to load code:', e)
    } finally {
      loadingCode.value = false
    }
  }
}

// Close details
function closeDetail() {
  selectedTask.value = null
  taskCode.value = null
}

// Rerun task
function rerunTask(task: Task) {
  const query = extractQuery(task)
  if (query && query !== 'Unknown task') {
    taskStore.queryText = query
    emit('close')
  }
}

// Load task results to map
function loadToMap(task: Task) {
  emit('load-task', task)
}

// View code in code viewer
function viewCode(task: Task) {
  emit('view-code', task.task_id)
}

// Delete task
async function deleteTask(task: Task) {
  if (!confirm(`Are you sure you want to delete task ${task.task_id.slice(0, 8)}...?`)) return
  
  try {
    await analysisApi.cancelTask(task.task_id)
    tasks.value = tasks.value.filter(t => t.task_id !== task.task_id)
    if (selectedTask.value?.task_id === task.task_id) {
      selectedTask.value = null
    }
  } catch (e) {
    console.error('Failed to delete task:', e)
  }
}

// Refresh
function refresh() {
  loadTasks()
}

// Watch visibility
watch(() => props.visible, (visible) => {
  if (visible && tasks.value.length === 0) {
    loadTasks()
  }
})

onMounted(() => {
  if (props.visible) {
    loadTasks()
  }
})
</script>

<template>
  <div class="task-history" v-if="visible">
    <!-- Header -->
    <div class="history-header">
      <div class="header-title">
        <span class="icon">📜</span>
        <h2>History</h2>
        <span class="count" v-if="total > 0">{{ total }} records</span>
      </div>
      <div class="header-actions">
        <button class="refresh-btn" @click="refresh" :disabled="loading" title="Refresh">
          <span :class="{ spinning: loading }">🔄</span>
        </button>
        <button class="close-btn" @click="emit('close')" title="Close">✕</button>
      </div>
    </div>

    <!-- Search and Filter -->
    <div class="filter-bar">
      <div class="search-input">
        <span class="search-icon">🔍</span>
        <input 
          type="text" 
          v-model="searchQuery" 
          placeholder="Search tasks..."
        />
      </div>
      <div class="status-filters">
        <button 
          :class="['filter-btn', { active: statusFilter === 'all' }]"
          @click="statusFilter = 'all'"
        >
          All
        </button>
        <button 
          :class="['filter-btn', { active: statusFilter === 'completed' }]"
          @click="statusFilter = 'completed'"
        >
          ✅ Completed
        </button>
        <button 
          :class="['filter-btn', { active: statusFilter === 'failed' }]"
          @click="statusFilter = 'failed'"
        >
          ❌ Failed
        </button>
        <button 
          :class="['filter-btn running', { active: ['pending', 'analyzing', 'downloading', 'generating', 'executing', 'optimizing'].includes(statusFilter as string) }]"
          @click="statusFilter = 'executing'"
        >
          ⏳ Running
        </button>
      </div>
    </div>

    <!-- Main Content Area -->
    <div class="history-content">
      <!-- Task List -->
      <div class="task-list" :class="{ 'with-detail': selectedTask }">
        <!-- Loading State -->
        <div class="loading-state" v-if="loading">
          <div class="spinner"></div>
          <span>Loading...</span>
        </div>

        <!-- Empty State -->
        <div class="empty-state" v-else-if="filteredTasks.length === 0">
          <div class="empty-icon">📭</div>
          <div class="empty-text">No History</div>
          <div class="empty-hint" v-if="searchQuery || statusFilter !== 'all'">
            No tasks match the criteria
          </div>
        </div>

        <!-- 任务卡片 -->
        <div 
          v-else
          v-for="task in paginatedTasks" 
          :key="task.task_id"
          class="task-card"
          :class="{ selected: selectedTask?.task_id === task.task_id }"
          @click="viewTask(task)"
        >
          <div class="task-status">
            <span 
              class="status-dot" 
              :style="{ backgroundColor: statusConfig[task.status]?.color }"
            ></span>
            <span class="status-icon">{{ statusConfig[task.status]?.icon }}</span>
          </div>
          
          <div class="task-info">
            <div class="task-query">{{ extractQuery(task).slice(0, 60) }}{{ extractQuery(task).length > 60 ? '...' : '' }}</div>
            <div class="task-meta">
              <span class="meta-item">
                <span class="meta-icon">🕐</span>
                {{ formatTime(task.created_at) }}
              </span>
              <span class="meta-item" v-if="task.status === 'completed' || task.status === 'failed'">
                <span class="meta-icon">⏱️</span>
                {{ formatDuration(task) }}
              </span>
              <span class="meta-item" v-if="task.output_files?.length">
                <span class="meta-icon">📁</span>
                {{ task.output_files.length }} files
              </span>
            </div>
          </div>
          
          <div class="task-progress" v-if="task.progress > 0 && task.progress < 100">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: task.progress + '%' }"></div>
            </div>
            <span class="progress-text">{{ task.progress }}%</span>
          </div>
          
          <div class="task-actions" @click.stop>
            <button 
              class="action-btn" 
              @click="rerunTask(task)"
              title="Rerun"
            >
              🔁
            </button>
            <button 
              class="action-btn" 
              @click="deleteTask(task)"
              title="Delete"
            >
              🗑️
            </button>
          </div>
        </div>

        <!-- Pagination -->
        <div class="pagination" v-if="totalPages > 1">
          <button 
            class="page-btn" 
            :disabled="currentPage === 1"
            @click="currentPage--"
          >
            ‹ Previous
          </button>
          <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
          <button 
            class="page-btn" 
            :disabled="currentPage === totalPages"
            @click="currentPage++"
          >
            Next ›
          </button>
        </div>
      </div>

      <!-- Task Detail Panel -->
      <div class="task-detail" v-if="selectedTask">
        <div class="detail-header">
          <h3>Task Details</h3>
          <button class="close-detail" @click="closeDetail">✕</button>
        </div>

        <div class="detail-body">
          <!-- Basic Info -->
          <div class="detail-section">
            <h4>📋 Basic Info</h4>
            <div class="info-grid">
              <div class="info-item">
                <span class="label">Task ID</span>
                <span class="value mono">{{ selectedTask.task_id.slice(0, 12) }}...</span>
              </div>
              <div class="info-item">
                <span class="label">Status</span>
                <span class="value">
                  <span 
                    class="status-badge"
                    :style="{ backgroundColor: statusConfig[selectedTask.status]?.color + '20', color: statusConfig[selectedTask.status]?.color }"
                  >
                    {{ statusConfig[selectedTask.status]?.icon }} {{ statusConfig[selectedTask.status]?.label }}
                  </span>
                </span>
              </div>
              <div class="info-item">
                <span class="label">Created</span>
                <span class="value">{{ formatTime(selectedTask.created_at) }}</span>
              </div>
              <div class="info-item">
                <span class="label">Duration</span>
                <span class="value">{{ formatDuration(selectedTask) }}</span>
              </div>
              <div class="info-item full">
                <span class="label">Progress</span>
                <div class="progress-display">
                  <div class="progress-bar large">
                    <div 
                      class="progress-fill" 
                      :style="{ 
                        width: selectedTask.progress + '%',
                        backgroundColor: statusConfig[selectedTask.status]?.color
                      }"
                    ></div>
                  </div>
                  <span class="progress-text">{{ selectedTask.progress }}%</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Query Content -->
          <div class="detail-section">
            <h4>🔍 Query Content</h4>
            <div class="query-box">
              {{ extractQuery(selectedTask) }}
            </div>
          </div>

          <!-- Output Files -->
          <div class="detail-section" v-if="selectedTask.output_files?.length">
            <h4>📁 Output Files ({{ selectedTask.output_files.length }})</h4>
            <div class="files-list">
              <div 
                class="file-item" 
                v-for="file in selectedTask.output_files" 
                :key="file.path"
              >
                <span class="file-icon">
                  {{ file.type === 'vector' ? '🗺️' : file.type === 'raster' ? '🖼️' : '📄' }}
                </span>
                <span class="file-name">{{ file.name }}</span>
                <span class="file-type">{{ file.type }}</span>
              </div>
            </div>
          </div>

          <!-- Generated Code -->
          <div class="detail-section" v-if="selectedTask.status === 'completed'">
            <h4>💻 Generated Code</h4>
            <div class="code-preview" v-if="loadingCode">
              <div class="spinner small"></div>
              <span>Loading...</span>
            </div>
            <div class="code-preview" v-else-if="taskCode">
              <pre>{{ taskCode.slice(0, 500) }}{{ taskCode.length > 500 ? '\n...' : '' }}</pre>
            </div>
            <div class="code-preview empty" v-else>
              <span>No code</span>
            </div>
          </div>

          <!-- Execution Logs -->
          <div class="detail-section" v-if="selectedTask.logs">
            <h4>📝 Execution Logs</h4>
            <div class="logs-preview">
              <pre>{{ selectedTask.logs.slice(-1000) }}</pre>
            </div>
          </div>
        </div>

        <!-- Action Buttons -->
        <div class="detail-footer">
          <button class="action-btn primary" @click="rerunTask(selectedTask)">
            🔁 Rerun
          </button>
          <button 
            class="action-btn secondary" 
            @click="loadToMap(selectedTask)"
            v-if="selectedTask.status === 'completed' && selectedTask.output_files?.length"
          >
            📍 Load Results
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.task-history {
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

.history-header {
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
  gap: 0.5rem;
}

.refresh-btn,
.close-btn {
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

.close-btn:hover {
  background: rgba(239, 68, 68, 0.1);
  color: var(--error-color, #ef4444);
}

.refresh-btn .spinning {
  display: inline-block;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 筛选栏 */
.filter-bar {
  display: flex;
  gap: 1rem;
  padding: 1rem 1.5rem;
  background: var(--bg-secondary, #1e293b);
  border-bottom: 1px solid var(--border-color, #334155);
  flex-wrap: wrap;
}

.search-input {
  flex: 1;
  min-width: 200px;
  display: flex;
  align-items: center;
  background: var(--bg-dark, #1a1a2e);
  border: 1px solid var(--border-color, #334155);
  border-radius: 8px;
  padding: 0 0.75rem;
}

.search-icon {
  margin-right: 0.5rem;
}

.search-input input {
  flex: 1;
  background: none;
  border: none;
  color: var(--text-primary, #e2e8f0);
  padding: 0.6rem 0;
  font-size: 0.875rem;
  outline: none;
}

.search-input input::placeholder {
  color: var(--text-secondary, #94a3b8);
}

.status-filters {
  display: flex;
  gap: 0.5rem;
}

.filter-btn {
  background: var(--bg-dark, #1a1a2e);
  border: 1px solid var(--border-color, #334155);
  color: var(--text-secondary, #94a3b8);
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-btn:hover {
  border-color: var(--primary-color, #3b82f6);
  color: var(--text-primary, #e2e8f0);
}

.filter-btn.active {
  background: rgba(59, 130, 246, 0.1);
  border-color: var(--primary-color, #3b82f6);
  color: var(--primary-color, #3b82f6);
}

/* 主内容区 */
.history-content {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* 任务列表 */
.task-list {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  transition: all 0.3s;
}

.task-list.with-detail {
  flex: 0 0 50%;
  max-width: 50%;
  border-right: 1px solid var(--border-color, #334155);
}

/* 任务卡片 */
.task-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: var(--bg-secondary, #1e293b);
  border: 1px solid var(--border-color, #334155);
  border-radius: 10px;
  margin-bottom: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.task-card:hover {
  border-color: var(--primary-color, #3b82f6);
  transform: translateX(4px);
}

.task-card.selected {
  border-color: var(--primary-color, #3b82f6);
  background: rgba(59, 130, 246, 0.05);
}

.task-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-icon {
  font-size: 1.25rem;
}

.task-info {
  flex: 1;
  min-width: 0;
}

.task-query {
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text-primary, #e2e8f0);
  margin-bottom: 0.35rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.task-meta {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
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

.task-progress {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 80px;
}

.progress-bar {
  flex: 1;
  height: 4px;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 2px;
  overflow: hidden;
}

.progress-bar.large {
  height: 8px;
  border-radius: 4px;
}

.progress-fill {
  height: 100%;
  background: var(--primary-color, #3b82f6);
  border-radius: inherit;
  transition: width 0.3s;
}

.progress-text {
  font-size: 0.65rem;
  color: var(--text-secondary, #94a3b8);
  min-width: 32px;
}

.task-actions {
  display: flex;
  gap: 0.25rem;
}

.task-actions .action-btn {
  background: transparent;
  border: none;
  font-size: 0.9rem;
  cursor: pointer;
  padding: 0.35rem;
  border-radius: 4px;
  opacity: 0.6;
  transition: all 0.2s;
}

.task-actions .action-btn:hover {
  opacity: 1;
  background: rgba(255, 255, 255, 0.1);
}

/* 分页 */
.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  margin-top: 0.5rem;
}

.page-btn {
  background: var(--bg-secondary, #1e293b);
  border: 1px solid var(--border-color, #334155);
  color: var(--text-secondary, #94a3b8);
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.page-btn:hover:not(:disabled) {
  border-color: var(--primary-color, #3b82f6);
  color: var(--primary-color, #3b82f6);
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-size: 0.75rem;
  color: var(--text-secondary, #94a3b8);
}

/* 任务详情 */
.task-detail {
  flex: 0 0 50%;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary, #0f172a);
  overflow: hidden;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border-color, #334155);
  background: var(--bg-secondary, #1e293b);
}

.detail-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
}

.close-detail {
  background: none;
  border: none;
  color: var(--text-secondary, #94a3b8);
  font-size: 1.25rem;
  cursor: pointer;
  padding: 0.25rem;
}

.close-detail:hover {
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

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.info-item.full {
  grid-column: 1 / -1;
}

.info-item .label {
  font-size: 0.7rem;
  color: var(--text-secondary, #94a3b8);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.info-item .value {
  font-size: 0.875rem;
  color: var(--text-primary, #e2e8f0);
}

.info-item .value.mono {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
}

.progress-display {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.progress-display .progress-bar {
  flex: 1;
}

.query-box {
  background: var(--bg-secondary, #1e293b);
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.875rem;
  color: var(--text-primary, #e2e8f0);
  line-height: 1.5;
  border: 1px solid var(--border-color, #334155);
}

.files-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: var(--bg-secondary, #1e293b);
  border-radius: 6px;
}

.file-icon {
  font-size: 1rem;
}

.file-name {
  flex: 1;
  font-size: 0.8rem;
  color: var(--text-primary, #e2e8f0);
}

.file-type {
  font-size: 0.65rem;
  color: var(--text-secondary, #94a3b8);
  padding: 0.15rem 0.4rem;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 4px;
}

.code-preview,
.logs-preview {
  background: var(--bg-dark, #1a1a2e);
  border-radius: 8px;
  padding: 1rem;
  max-height: 200px;
  overflow: auto;
}

.code-preview pre,
.logs-preview pre {
  margin: 0;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: var(--text-secondary, #94a3b8);
  white-space: pre-wrap;
  word-break: break-all;
}

.code-preview.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary, #94a3b8);
  font-size: 0.8rem;
}

.detail-footer {
  display: flex;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border-color, #334155);
  background: var(--bg-secondary, #1e293b);
}

.detail-footer .action-btn {
  flex: 1;
  padding: 0.6rem 1rem;
  border: none;
  border-radius: 8px;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.detail-footer .action-btn.primary {
  background: var(--primary-color, #3b82f6);
  color: white;
}

.detail-footer .action-btn.primary:hover {
  background: #2563eb;
}

.detail-footer .action-btn.secondary {
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
}

.detail-footer .action-btn.secondary:hover {
  background: rgba(16, 185, 129, 0.25);
}

/* 加载和空状态 */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 2rem;
  text-align: center;
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

.spinner.small {
  width: 20px;
  height: 20px;
  border-width: 2px;
  margin-bottom: 0.5rem;
}

.loading-state span {
  color: var(--text-secondary, #94a3b8);
  font-size: 0.875rem;
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
</style>

