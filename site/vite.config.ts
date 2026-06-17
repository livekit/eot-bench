import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Absolute base matching the production mount path. The site is served at
// livekit.com/benchmarks/eot-bench (a Next.js rewrite in apps/www →
// livekit.github.io/eot-bench) WITHOUT a trailing slash, so a relative base
// ('./') resolves assets against the parent dir (/benchmarks/assets/…) and
// 404s. An absolute base pins asset URLs regardless of trailing slash.
// The screenshot render server (scripts/screenshot-assets.mjs) strips this
// prefix so `pnpm gen-assets` still serves dist from root.
export default defineConfig({
  base: '/benchmarks/eot-bench/',
  plugins: [react(), tailwindcss()],
});
