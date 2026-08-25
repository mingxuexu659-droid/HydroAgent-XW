/**
 * 组件单元测试
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import QueryInput from '@/components/analysis/QueryInput.vue'
import TaskProgress from '@/components/analysis/TaskProgress.vue'
import LayerPanel from '@/components/map/LayerPanel.vue'
import FeatureProperties from '@/components/map/FeatureProperties.vue'

// Mock maplibre-gl
vi.mock('maplibre-gl', () => ({
  default: {
    Map: vi.fn(() => ({
      on: vi.fn(),
      remove: vi.fn(),
      addControl: vi.fn(),
      setCenter: vi.fn()
    })),
    NavigationControl: vi.fn(),
    ScaleControl: vi.fn()
  }
}))

describe('QueryInput', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should render correctly', () => {
    const wrapper = mount(QueryInput, {
      props: {
        loading: false
      }
    })
    
    expect(wrapper.find('.section-title').text()).toContain('空间分析')
    expect(wrapper.find('textarea').exists()).toBe(true)
    expect(wrapper.find('.submit-btn').exists()).toBe(true)
  })

  it('should disable submit button when query is empty', () => {
    const wrapper = mount(QueryInput, {
      props: {
        loading: false
      }
    })
    
    const submitBtn = wrapper.find('.submit-btn')
    expect(submitBtn.attributes('disabled')).toBeDefined()
  })

  it('should emit submit event with correct data', async () => {
    const wrapper = mount(QueryInput, {
      props: {
        loading: false
      }
    })
    
    const textarea = wrapper.find('textarea')
    await textarea.setValue('测试查询')
    
    const submitBtn = wrapper.find('.submit-btn')
    await submitBtn.trigger('click')
    
    const emitted = wrapper.emitted('submit')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toMatchObject({
      query: '测试查询'
    })
  })

  it('should show loading state', () => {
    const wrapper = mount(QueryInput, {
      props: {
        loading: true
      }
    })
    
    expect(wrapper.find('.spinner').exists()).toBe(true)
    expect(wrapper.find('.submit-btn').text()).toContain('分析中')
  })

  it('should apply template when clicked', async () => {
    const wrapper = mount(QueryInput, {
      props: {
        loading: false
      }
    })
    
    const templateBtn = wrapper.find('.template-tag')
    await templateBtn.trigger('click')
    
    const textarea = wrapper.find('textarea')
    expect((textarea.element as HTMLTextAreaElement).value).not.toBe('')
  })
})

describe('TaskProgress', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should render correctly', () => {
    const wrapper = mount(TaskProgress, {
      props: {
        task: {
          task_id: 'test-1',
          status: 'executing',
          message: '正在执行...',
          created_at: new Date().toISOString(),
          progress: 50,
          current_step: '代码执行',
          output_files: [],
          logs: []
        }
      }
    })
    
    expect(wrapper.find('.section-title').text()).toContain('任务进度')
    expect(wrapper.find('.progress-fill').exists()).toBe(true)
    expect(wrapper.find('.steps').exists()).toBe(true)
  })

  it('should show correct progress', () => {
    const wrapper = mount(TaskProgress, {
      props: {
        task: {
          task_id: 'test-1',
          status: 'executing',
          message: '正在执行...',
          created_at: new Date().toISOString(),
          progress: 75,
          current_step: '代码执行',
          output_files: [],
          logs: []
        }
      }
    })
    
    expect(wrapper.find('.progress-text').text()).toBe('75%')
  })

  it('should show success status when completed', () => {
    const wrapper = mount(TaskProgress, {
      props: {
        task: {
          task_id: 'test-1',
          status: 'completed',
          message: '分析完成！',
          created_at: new Date().toISOString(),
          progress: 100,
          current_step: '完成',
          output_files: [],
          logs: []
        }
      }
    })
    
    expect(wrapper.find('.status-message.success').exists()).toBe(true)
  })

  it('should show error status when failed', () => {
    const wrapper = mount(TaskProgress, {
      props: {
        task: {
          task_id: 'test-1',
          status: 'failed',
          message: '任务失败',
          created_at: new Date().toISOString(),
          progress: 0,
          current_step: '错误',
          output_files: [],
          logs: []
        }
      }
    })
    
    expect(wrapper.find('.status-message.error').exists()).toBe(true)
  })
})

describe('LayerPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should render empty state when no layers', () => {
    const wrapper = mount(LayerPanel)
    
    expect(wrapper.find('.empty-state').exists()).toBe(true)
    expect(wrapper.find('.empty-icon').text()).toBe('📂')
  })

  it('should render layers list', async () => {
    const wrapper = mount(LayerPanel)
    const { useMapStore } = await import('@/stores/map')
    const mapStore = useMapStore()
    
    mapStore.layers = [
      { id: '1', name: 'Test Layer', type: 'polygon', visible: true, featureCount: 10 }
    ] as any[]
    
    await wrapper.vm.$nextTick()
    
    expect(wrapper.find('.layers-list').exists()).toBe(true)
    expect(wrapper.find('.layer-item').exists()).toBe(true)
    expect(wrapper.find('.layer-name').text()).toBe('Test Layer')
  })
})

describe('FeatureProperties', () => {
  it('should render when feature is provided', () => {
    const wrapper = mount(FeatureProperties, {
      props: {
        feature: {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [0, 0] },
          properties: { name: 'Test', value: 123 }
        }
      }
    })
    
    expect(wrapper.find('.feature-properties').exists()).toBe(true)
    expect(wrapper.find('.geometry-type').text()).toBe('Point')
    expect(wrapper.findAll('.property-item').length).toBe(2)
  })

  it('should not render when feature is null', () => {
    const wrapper = mount(FeatureProperties, {
      props: {
        feature: null
      }
    })
    
    expect(wrapper.find('.feature-properties').exists()).toBe(false)
  })

  it('should emit close event when close button is clicked', async () => {
    const wrapper = mount(FeatureProperties, {
      props: {
        feature: {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [0, 0] },
          properties: { name: 'Test' }
        }
      }
    })
    
    await wrapper.find('.close-btn').trigger('click')
    
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('should show empty state when no properties', () => {
    const wrapper = mount(FeatureProperties, {
      props: {
        feature: {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [0, 0] },
          properties: {}
        }
      }
    })
    
    expect(wrapper.find('.empty-state').exists()).toBe(true)
  })
})

