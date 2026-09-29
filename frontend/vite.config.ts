import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In development the API is proxied to the FastAPI backend, so the browser talks to one origin.
const backend = process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8020';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5195,
    host: '127.0.0.1',
    proxy: { '/api': { target: backend, changeOrigin: true } },
  },
  preview: {
    port: 4173,
    host: '127.0.0.1',
    proxy: { '/api': { target: backend, changeOrigin: true } },
  },
});
