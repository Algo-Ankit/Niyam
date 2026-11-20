import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development `/api` is proxied to the local API (`uvicorn niyam.api:create_app --factory`).
// In production the API origin comes from VITE_API_URL at build time.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
