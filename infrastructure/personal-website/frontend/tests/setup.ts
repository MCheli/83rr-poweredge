import { vi } from 'vitest'

// Mock Nuxt composables
global.defineNuxtConfig = vi.fn()
global.useRuntimeConfig = vi.fn(() => ({
  public: {
    apiBase: '/api'
  }
}))

global.nextTick = vi.fn(() => Promise.resolve())
global.onMounted = vi.fn()
global.watch = vi.fn()
global.ref = vi.fn((value) => ({ value }))

// Mock window.open for action commands
Object.defineProperty(window, 'open', {
  writable: true,
  value: vi.fn()
})