<script setup lang="ts">
/**
 * Task Progress Component
 */
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import type { Task, TaskStatus } from '@/types'

// Props
const props = defineProps<{
  task: Task
}>()

// Step definitions
const steps = [
  { id: 'analyzing', name: 'Intent Analysis' },
  { id: 'downloading', name: 'Data Retrieval' },
  { id: 'generating', name: 'Code Generation' },
  { id: 'executing', name: 'Code Execution' },
  { id: 'completed', name: 'Completed' }
]

// Status order
const statusOrder: TaskStatus[] = [
  'pending', 'analyzing', 'downloading', 'generating', 'executing', 'optimizing', 'completed', 'failed'
]

// Current step index
const currentStepIndex = computed(() => {
  return statusOrder.indexOf(props.task.status)
})

// Check if step is completed
function isStepCompleted(stepId: string, index: number): boolean {
  const stepIdx = statusOrder.indexOf(stepId as TaskStatus)
  // Fix: when task status is completed, completed step should also show as completed
  if (props.task.status === 'completed' && stepId === 'completed') {
    return true
  }
  return currentStepIndex.value > stepIdx
}

// Check if step is active
function isStepActive(stepId: string, index: number): boolean {
  const stepIdx = statusOrder.indexOf(stepId as TaskStatus)
  // Fix: completed step should not show as active (spinning)
  return currentStepIndex.value === stepIdx && props.task.status !== 'failed' && props.task.status !== 'completed'
}

// Get step class
function getStepClass(stepId: string, index: number): string {
  if (props.task.status === 'failed') {
    return isStepCompleted(stepId, index) ? 'completed' : 'pending'
  }
  if (isStepCompleted(stepId, index)) return 'completed'
  if (isStepActive(stepId, index)) return 'active'
  return 'pending'
}

// Status class
const statusClass = computed(() => {
  switch (props.task.status) {
    case 'completed': return 'success'
    case 'failed': return 'error'
    case 'optimizing': return 'warning'
    default: return 'running'
  }
})

// Status icon
const statusIcon = computed(() => {
  switch (props.task.status) {
    case 'completed': return '✅'
    case 'failed': return '❌'
    case 'optimizing': return '🔄'
    default: return '⏳'
  }
})

// Elapsed time calculation
const elapsedTime = ref('')
let timer: number | null = null

function updateElapsedTime() {
  if (!props.task.created_at) return
  
  // If task is completed or failed, use updated_at to calculate elapsed time and stop timer
  const isFinished = props.task.status === 'completed' || props.task.status === 'failed'
  
  const start = new Date(props.task.created_at).getTime()
  const end = isFinished && props.task.updated_at 
    ? new Date(props.task.updated_at).getTime() 
    : Date.now()
  const diff = Math.floor((end - start) / 1000)
  
  const minutes = Math.floor(diff / 60)
  const seconds = diff % 60
  elapsedTime.value = `${minutes}:${seconds.toString().padStart(2, '0')}`
  
  // Stop timer after task completes
  if (isFinished && timer) {
    clearInterval(timer)
    timer = null
  }
}

onMounted(() => {
  updateElapsedTime()
  timer = window.setInterval(updateElapsedTime, 1000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

// Watch task status changes, update immediately and stop timer when completed
watch(() => props.task.status, (newStatus) => {
  if (newStatus === 'completed' || newStatus === 'failed') {
    updateElapsedTime()
  }
})

// Watch task changes (restart timer when new task starts)
watch(() => props.task.task_id, () => {
  // New task starts, reset timer
  if (timer) {
    clearInterval(timer)
  }
  elapsedTime.value = '0:00'
  updateElapsedTime()
  timer = window.setInterval(updateElapsedTime, 1000)
})

// Watch created_at changes (same task restarts)
watch(() => props.task.created_at, () => {
  // Task creation time changed, reset timer
  if (timer) {
    clearInterval(timer)
  }
  elapsedTime.value = '0:00'
  updateElapsedTime()
  timer = window.setInterval(updateElapsedTime, 1000)
})
</script>

<template>
  <div class="task-progress">
    <div class="section-header">
      <h3 class="section-title">
        <span class="icon">⚡</span>
        Task Progress
      </h3>
      <!-- Elapsed Time -->
      <div class="elapsed-time" v-if="elapsedTime">
        Elapsed: {{ elapsedTime }}
      </div>
    </div>

    <!-- 进度条 -->
    <div class="progress-container">
      <div class="progress-bar">
        <div 
          class="progress-fill" 
          :style="{ width: `${task.progress}%` }"
          :class="statusClass"
        ></div>
      </div>
      <div class="progress-text">{{ task.progress }}%</div>
    </div>

    <!-- 步骤列表 -->
    <div class="steps">
      <div 
        v-for="(step, index) in steps" 
        :key="step.id"
        class="step"
        :class="getStepClass(step.id, index)"
      >
        <div class="step-icon">
          <span v-if="isStepCompleted(step.id, index)">✓</span>
          <span v-else-if="isStepActive(step.id, index)" class="spinner-small"></span>
          <span v-else>{{ index + 1 }}</span>
        </div>
        <div class="step-content">
          <div class="step-name">{{ step.name }}</div>
          <div class="step-desc" v-if="isStepActive(step.id, index)">
            {{ task.message }}
          </div>
        </div>
      </div>
    </div>

    <!-- 状态消息 -->
    <div class="status-message" :class="statusClass">
      <span class="status-icon">{{ statusIcon }}</span>
      {{ task.message }}
    </div>
  </div>
</template>

<style scoped>
.task-progress {
  padding: 0.75rem;
  border-bottom: 1px solid var(--border-color, #334155);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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

.progress-container {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: var(--bg-dark, #1a1a2e);
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-fill.running {
  background: var(--primary-color, #3b82f6);
}

.progress-fill.success {
  background: var(--success-color, #10b981);
}

.progress-fill.error {
  background: var(--error-color, #ef4444);
}

.progress-fill.warning {
  background: var(--warning-color, #f59e0b);
}

.progress-text {
  font-size: 0.75rem;
  color: var(--text-secondary, #94a3b8);
  min-width: 3rem;
  text-align: right;
}

.steps {
  margin-top: 0.375rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.15rem 0.3rem;
}

.step {
  display: flex;
  align-items: center;
  gap: 0.2rem;
  padding: 0.1rem 0;
}

/* Remove connector lines, use horizontal compact layout */
.step:not(:last-child)::after {
  display: none;
}

.step-icon {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.55rem;
  font-weight: 600;
  flex-shrink: 0;
  background: var(--bg-dark, #1a1a2e);
  border: 1.5px solid var(--border-color, #334155);
  color: var(--text-secondary, #94a3b8);
  z-index: 1;
}

.step.completed .step-icon {
  background: var(--success-color, #10b981);
  border-color: var(--success-color, #10b981);
  color: white;
}

.step.active .step-icon {
  background: var(--primary-color, #3b82f6);
  border-color: var(--primary-color, #3b82f6);
  color: white;
}

.step-name {
  font-size: 0.65rem;
  font-weight: 500;
  color: var(--text-primary, #e2e8f0);
}

.step.pending .step-name {
  color: var(--text-secondary, #94a3b8);
}

/* Hide step description to save space */
.step-desc {
  display: none;
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

.status-message {
  margin-top: 0.375rem;
  padding: 0.375rem 0.5rem;
  border-radius: 4px;
  font-size: 0.6875rem;
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.status-message.running {
  background: rgba(59, 130, 246, 0.1);
  color: var(--primary-color, #3b82f6);
}

.status-message.success {
  background: rgba(16, 185, 129, 0.1);
  color: var(--success-color, #10b981);
}

.status-message.error {
  background: rgba(239, 68, 68, 0.1);
  color: var(--error-color, #ef4444);
}

.status-message.warning {
  background: rgba(245, 158, 11, 0.1);
  color: var(--warning-color, #f59e0b);
}

.elapsed-time {
  font-size: 0.6875rem;
  color: var(--text-secondary, #94a3b8);
  white-space: nowrap;
}
</style>

