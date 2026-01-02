/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./components/**/*.{js,vue,ts}",
    "./layouts/**/*.vue",
    "./pages/**/*.vue",
    "./plugins/**/*.{js,ts}",
    "./app.vue",
  ],
  theme: {
    extend: {
      fontFamily: {
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        terminal: {
          bg: '#0a0e14',
          text: '#b3b1ad',
          green: '#aad94c',
          blue: '#59c2ff',
          yellow: '#ffb454',
          red: '#ff3333',
        }
      }
    },
  },
  plugins: [],
}
