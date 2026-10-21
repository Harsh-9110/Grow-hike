import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': { target: 'http://backend:8000', changeOrigin: true }, '/health': 'http://backend:8000', '/ready': 'http://backend:8000' } },
});
