import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// Dev server on :3000, proxying the FastAPI backend on :8000 (or VITE_BACKEND_URL in Docker).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backendTarget = env.VITE_BACKEND_URL || 'http://localhost:8000';

  return {
    base: './',
    plugins: [react()],
    server: {
      port: 3000,
      proxy: {
        '/api': { target: backendTarget, changeOrigin: true },
        '/health': { target: backendTarget, changeOrigin: true },
      },
    },
  };
});
