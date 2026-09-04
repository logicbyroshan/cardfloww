import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// ─────────────────────────────────────────────────────────────────────────────
// Architecture: Vite dev server on :5173 (React SPA)
//               Django API server on :8000 (REST API only)
//
// ONLY /api/* and /media/* are proxied to Django.
// Everything else is served by Vite as the React SPA.
// ─────────────────────────────────────────────────────────────────────────────

const DJANGO_PORT = process.env.VITE_DJANGO_PORT || 8008;
const DJANGO_ORIGIN = `http://127.0.0.1:${DJANGO_PORT}`;

// Routes that MUST be proxied to Django (JSON API + media files + session CSRF)
const djangoRoutes = [
  '/api',            // All REST API endpoints
  '/media',          // User-uploaded media files (photos, exports)
  '/app',            // Mobile app landing page (HTML served by Django)
  '/operators/api',  // Operator management endpoints
  '/assistants/api', // Assistant management endpoints
];

export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    port: 5173,
    open: '/',                // Auto-open SPA root
    proxy: Object.fromEntries(
      djangoRoutes.map((route) => [
        route,
        {
          target: DJANGO_ORIGIN,
          changeOrigin: true,
          secure: false,
          cookieDomainRewrite: { '*': '' },   // Strip domain so session cookies work on localhost
          bypass: (req) => {
            if (req.headers.accept && req.headers.accept.includes('text/html')) {
              // Only let Django serve HTML for /app mobile landing page
              if (req.url && req.url.startsWith('/app')) {
                return null;
              }
              return '/index.html';
            }
            return null;
          },
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
