import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import type { ProxyOptions } from 'vite'

// Proxies API calls to the FastAPI backend during development so the app
// can use relative paths (e.g. fetch('/chat')) without hardcoding a backend
// origin, and so the session cookie is treated as same-origin by the
// browser. See app/main.py's CORSMiddleware for the non-proxied path
// (calling the backend origin directly with credentials: 'include').
const BACKEND_ORIGIN = process.env.VITE_BACKEND_ORIGIN ?? 'http://127.0.0.1:8000'

// Shared proxy options: keep SSE (/chat/stream) unbuffered so status/token
// events reach the browser as they are produced.
const apiProxy: ProxyOptions = {
  target: BACKEND_ORIGIN,
  changeOrigin: true,
  configure: (proxy) => {
    proxy.on('proxyRes', (proxyRes) => {
      const contentType = proxyRes.headers['content-type']
      if (typeof contentType === 'string' && contentType.includes('text/event-stream')) {
        proxyRes.headers['cache-control'] = 'no-cache'
        proxyRes.headers['x-accel-buffering'] = 'no'
      }
    })
  },
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Matches /chat and /chat/stream
      '/chat': apiProxy,
      '/fold': apiProxy,
      '/structures': apiProxy,
      '/liveness': apiProxy,
    },
  },
})
