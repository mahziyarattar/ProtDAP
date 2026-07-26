import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxies API calls to the FastAPI backend during development so the app
// can use relative paths (e.g. fetch('/chat')) without hardcoding a backend
// origin, and so the session cookie is treated as same-origin by the
// browser. See app/main.py's CORSMiddleware for the non-proxied path
// (calling the backend origin directly with credentials: 'include').
const BACKEND_ORIGIN = process.env.VITE_BACKEND_ORIGIN ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/chat': BACKEND_ORIGIN,
      '/structures': BACKEND_ORIGIN,
      '/liveness': BACKEND_ORIGIN,
    },
  },
})
