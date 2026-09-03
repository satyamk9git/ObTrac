/** @type {import('next').NextConfig} */
// The /api/v1/* proxy to the backend lives in
// src/app/api/[...path]/route.ts (a real route handler, not a rewrite) —
// Next's rewrites() proxy for external destinations has an internal ~30s
// timeout that isn't configurable and killed slow AI-calling endpoints, so
// it's not used here. BACKEND_INTERNAL_URL (read by that route handler)
// still lets the proxy target differ from what the browser sees: in local
// dev the Next.js server and the backend share "localhost", but inside
// Docker "localhost" would mean the frontend container itself —
// docker-compose sets this to http://backend:8000 for the frontend service.
const nextConfig = {};

module.exports = nextConfig;
