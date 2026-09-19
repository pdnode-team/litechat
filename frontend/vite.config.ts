import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // Dev-only: where the Vite proxy forwards /api and /ws. Production does not
  // use this proxy — a reverse proxy in front of the SPA serves those paths.
  const devApiTarget = env.DEV_API_TARGET || 'http://127.0.0.1:8000'
  const wsTarget = devApiTarget.replace(/^http/, 'ws')

  return {
    plugins: [react()],
    server: {
      port: Number(env.DEV_PORT || 3000),
      host: env.DEV_HOST || '127.0.0.1',
      watch: {
        // Editors write files through a temporary sibling directory
        // (".Name.tsx.<pid>.<uuid>.tmpdir"). Watching it races with the write and
        // can kill the dev server with EBUSY, so ignore those and build output.
        ignored: ['**/*.tmpdir/**', '**/.*.tmpdir/**', '**/dist/**'],
      },
      proxy: {
        '/api': {
          target: devApiTarget,
          changeOrigin: true,
        },
        '/ws': {
          target: wsTarget,
          ws: true,
        },
      },
    },
  }
})
