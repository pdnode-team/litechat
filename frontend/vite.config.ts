import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    watch: {
      // Editors write files through a temporary sibling directory
      // (".Name.tsx.<pid>.<uuid>.tmpdir"). Watching it races with the write and
      // can kill the dev server with EBUSY, so ignore those and build output.
      ignored: ['**/*.tmpdir/**', '**/.*.tmpdir/**', '**/dist/**'],
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
    },
  },
})
