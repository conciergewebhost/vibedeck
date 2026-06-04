// @ts-check
import { defineConfig } from "astro/config";
import node from "@astrojs/node";

// SSR mode: pages render on each request, so newly uploaded decks appear
// without a rebuild. The node adapter runs a standalone server (see
// Caddyfile.example — Caddy reverse-proxies to it on :4321).
export default defineConfig({
  output: "server",
  adapter: node({ mode: "standalone" }),
  server: { port: 4321 },
});
