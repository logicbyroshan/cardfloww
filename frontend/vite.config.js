import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite dev server proxies all Django API, auth, and static requests to the backend
// so sessions and CSRF cookies work seamlessly without any CORS config.
const DJANGO_PORT = 8000;
const DJANGO_ORIGIN = `http://127.0.0.1:${DJANGO_PORT}`;

const djangoRoutes = [
  '/api',
  '/panel',
  '/login',
  '/logout',
  '/reprint',
  '/static',
  '/media',
  '/card_media',
  '/mediafiles',
  '/admin',
  '/operators',
  '/assistants',
  '/client',
  '/staff',
  '/work',
  '/auth',
  '/exports',
];

export default defineConfig({
  base: '/static/',
  plugins: [react()],
  server: {
    port: 5173,
    open: true,               // Auto-open browser on start
    proxy: Object.fromEntries(
      djangoRoutes.map((route) => [
        route,
        {
          target: DJANGO_ORIGIN,
          changeOrigin: true,
          secure: false,
          cookieDomainRewrite: { '*': '' },   // ← strip domain so cookies work on localhost
          configure: (proxy) => {
            proxy.on('error', (err) => {
              console.warn(`[Vite proxy] ${err.message} — is Django running on port ${DJANGO_PORT}?`);
            });
          },
        },
      ])
    ),
  },
})
