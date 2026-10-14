import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The build goes inside the Python package, which serves it from 127.0.0.1.
// In development (npm run dev) API calls go to the backend started with: python -m dupfinder --no-browser
const BACKEND = 'http://127.0.0.1:8765';

export default defineConfig({
  plugins: [react()],
  build: { outDir: '../dupfinder/web', emptyOutDir: true },
  server: {
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      // the backend page holds the API token: in development it is read from here
      '/__backend__': { target: BACKEND, changeOrigin: true, rewrite: () => '/' },
    },
  },
});
