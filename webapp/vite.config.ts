import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local loop: tunnel → Vite :5173 → proxy /api to the test bot's oauth port.
// BotFather Main Mini App URL = the tunnel HTTPS origin.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    // Cloudflare quick tunnels present a *.trycloudflare.com Host header;
    // the slug changes every run, so allow all hosts in local Mini App dev.
    allowedHosts: true,
    proxy: {
      // Same tunnel as the Mini App: Microsoft redirects here after Xbox login.
      "/auth": {
        target: "http://127.0.0.1:8081",
        changeOrigin: true,
      },
      "/api": {
        target: "http://127.0.0.1:8081",
        changeOrigin: true,
        // Keep Mini App auth headers intact through the Vite proxy.
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq, req) => {
            const initData = req.headers["x-telegram-init-data"];
            if (typeof initData === "string") {
              proxyReq.setHeader("X-Telegram-Init-Data", initData);
            }
          });
        },
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // Vite 8 defaults to lightningcss minify, which drops unprefixed
    // backdrop-filter when -webkit-backdrop-filter is also present, and
    // collapses blur(0)/saturate(1) to invalid blur()/saturate().
    // Chromium (Telegram Android WebView) then loses glass/blur effects.
    // https://github.com/vitejs/vite/issues/22649
    cssMinify: "esbuild",
  },
});
