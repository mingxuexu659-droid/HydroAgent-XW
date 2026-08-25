<script setup lang="ts">
/**
 * 消息模态框组件 - 用于显示完整的执行结果或错误信息
 */
import { watch } from 'vue'

const props = defineProps<{
  show: boolean
  title: string
  message: string
  type: 'success' | 'error' | 'info'
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

// 关闭模态框
function close() {
  emit('close')
}

// 按 ESC 键关闭
function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    close()
  }
}

// 监听显示状态，添加/移除键盘事件监听
watch(() => props.show, (show) => {
  if (show) {
    document.addEventListener('keydown', handleKeydown)
  } else {
    document.removeEventListener('keydown', handleKeydown)
  }
})
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="modal-overlay" @click.self="close">
      <div class="modal-container" :class="type">
        <!-- 标题栏 -->
        <div class="modal-header">
          <span class="modal-icon">
            {{ type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️' }}
          </span>
          <h3 class="modal-title">{{ title }}</h3>
          <button class="close-btn" @click="close" title="关闭 (ESC)">×</button>
        </div>
        
        <!-- 内容区域 -->
        <div class="modal-body">
          <pre class="message-content">{{ message }}</pre>
        </div>
        
        <!-- 底部按钮 -->
        <div class="modal-footer">
          <button class="btn-primary" @click="close">确定</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  padding: 2rem;
}

.modal-container {
  background: #1a1a2e;
  border-radius: 12px;
  width: 100%;
  max-width: 700px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  border: 1px solid #334155;
}

.modal-container.success {
  border-color: #10b981;
}

.modal-container.error {
  border-color: #ef4444;
}

.modal-container.info {
  border-color: #3b82f6;
}

.modal-header {
  display: flex;
  align-items: center;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid #334155;
  gap: 0.75rem;
}

.modal-icon {
  font-size: 1.5rem;
}

.modal-title {
  flex: 1;
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: #e2e8f0;
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 1.5rem;
  cursor: pointer;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.close-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #e2e8f0;
}

.modal-body {
  flex: 1;
  overflow: auto;
  padding: 1.5rem;
}

.message-content {
  margin: 0;
  padding: 1rem;
  background: #0d1117;
  border-radius: 8px;
  color: #c9d1d9;
  font-family: 'Fira Code', 'Consolas', 'Monaco', monospace;
  font-size: 0.8125rem;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
  overflow-x: auto;
}

.modal-footer {
  padding: 1rem 1.5rem;
  border-top: 1px solid #334155;
  display: flex;
  justify-content: flex-end;
}

.btn-primary {
  padding: 0.5rem 1.5rem;
  background: #3b82f6;
  border: none;
  border-radius: 6px;
  color: white;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover {
  background: #2563eb;
}

/* 滚动条样式 */
.modal-body::-webkit-scrollbar {
  width: 8px;
}

.modal-body::-webkit-scrollbar-track {
  background: #1a1a2e;
}

.modal-body::-webkit-scrollbar-thumb {
  background: #334155;
  border-radius: 4px;
}

.modal-body::-webkit-scrollbar-thumb:hover {
  background: #475569;
}

.message-content::-webkit-scrollbar {
  height: 8px;
}

.message-content::-webkit-scrollbar-track {
  background: #0d1117;
}

.message-content::-webkit-scrollbar-thumb {
  background: #30363d;
  border-radius: 4px;
}
</style>

