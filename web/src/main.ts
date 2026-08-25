/**
 * 应用入口
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import './styles/main.css'

// 创建应用
const app = createApp(App)

// 使用 Pinia
app.use(createPinia())

// 挂载应用
app.mount('#app')
