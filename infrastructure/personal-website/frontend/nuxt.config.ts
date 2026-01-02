// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  devtools: { enabled: true },
  modules: [
    '@nuxtjs/tailwindcss'
  ],
  tailwindcss: {
    configPath: '~/tailwind.config.js',
    cssPath: '~/assets/css/terminal.css',
    exposeConfig: false,
    viewer: false
  },
  css: ['~/assets/css/terminal.css'],
  app: {
    head: {
      title: 'Mark Cheli - Developer Terminal',
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'description', content: 'Mark Cheli - Developer | Interactive Terminal Interface' },
        { name: 'author', content: 'Mark Cheli' },
        { property: 'og:title', content: 'Mark Cheli - Developer Terminal' },
        { property: 'og:description', content: 'Interactive terminal interface showcasing projects and services' },
        { property: 'og:type', content: 'website' }
      ],
      link: [
        { rel: 'icon', type: 'image/x-icon', href: '/favicon.ico' },
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
        { href: 'https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap', rel: 'stylesheet' }
      ]
    }
  },
  nitro: {
    devProxy: {
      '/api': {
        target: process.env.API_URL || 'http://localhost:5000',
        changeOrigin: true,
        prependPath: true
      }
    }
  },
  runtimeConfig: {
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '/api'
    }
  }
})