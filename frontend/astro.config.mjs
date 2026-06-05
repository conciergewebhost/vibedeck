// @ts-check
import { defineConfig } from "astro/config";
import node from "@astrojs/node";
import { loadEnv } from "vite";

// API base the SSR pages fetch (server-side) and the dev proxy forwards to.
const { API_BASE_URL } = loadEnv(
  process.env.NODE_ENV ?? "development",
  process.cwd(),
  "",
);
const apiTarget = API_BASE_URL || "http://localhost:8000";

// SSR mode: pages render on each request, so newly uploaded decks appear
// without a rebuild. The node adapter runs a standalone server (see
// Caddyfile.example — Caddy reverse-proxies to it on :4321).
export default defineConfig({
  output: "server",
  adapter: node({ mode: "standalone" }),
  server: { port: 4321 },
  vite: {
    server: {
      // Dev only: forward browser-side /api/* calls (e.g. the /admin upload
      // surface) to the backend, so `astro dev` mirrors production. In
      // production Caddy handles this — the proxy below is never used there.
      proxy: {
        "/api": { target: apiTarget, changeOrigin: true },
      },
    },
  },
});
