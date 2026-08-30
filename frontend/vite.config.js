import { defineConfig } from 'vite'

// Deliberately dependency-light: Vite's built-in esbuild compiles the JSX, so
// there is no babel/plugin chain that can break the GitHub Actions build.
export default defineConfig({
  esbuild: {
    jsx: 'automatic'
  },
  build: {
    outDir: 'build',
    sourcemap: false,
    chunkSizeWarningLimit: 1500
  },
  server: {
    port: 3000,
    // `npm run dev` locally; point VITE_API_TARGET at the NAS for real data.
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8001',
        changeOrigin: true
      }
    }
  }
})
