import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The browser only ever talks to this server. `/api/*` is forwarded to the backend,
// so the backend needs no CORS setup and one HTTPS tunnel covers app and API.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxy = {
    // Garment cutout service (pwa/cutout/server.py), runs next to this server.
    '/cutout': { target: env.CUTOUT_URL || 'http://localhost:8010', changeOrigin: true },
    '/api': {
      target: env.BACKEND_URL || 'http://localhost:8000',
      changeOrigin: true,
      // The agent endpoint (/outfits/today) needs a bearer token. It is added here, on the server,
      // so it never reaches the phone.
      headers: env.TODAY_API_TOKEN ? { Authorization: `Bearer ${env.TODAY_API_TOKEN}` } : undefined,
      rewrite: (p: string) => p.replace(/^\/api/, ''),
    },
  }
  return {
    plugins: [react()],
    server: { host: true, port: 5173, allowedHosts: true, proxy },
    preview: { host: true, port: 4173, allowedHosts: true, proxy },
  }
})
