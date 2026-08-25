import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true
      },
      '/results': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/scripts': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/downloaded': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/ext-output': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/output': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/raster-cache': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/cog': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/png': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: true
  },
  define: {
    __VUE_OPTIONS_API__: true,
    __VUE_PROD_DEVTOOLS__: false,
    __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: false
  }
})
