import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      // Only enable when feature flag academics.offline_attendance_pwa is on
      // The service worker is always generated; runtime activation is flag-gated
      workbox: {
        // Cache the attendance marking screen (cache-first — available offline)
        runtimeCaching: [
          {
            urlPattern: /\/attendance/,
            handler: "CacheFirst",
            options: {
              cacheName: "attendance-ui",
              expiration: { maxEntries: 10, maxAgeSeconds: 86400 },
            },
          },
          // API: student list for a session — network-first with offline fallback
          {
            urlPattern: /\/api\/v1\/attendance\/sessions\/.+\/students/,
            handler: "NetworkFirst",
            options: {
              cacheName: "session-students",
              networkTimeoutSeconds: 4,
              expiration: { maxEntries: 50, maxAgeSeconds: 3600 },
            },
          },
          // All other API routes — network-only (no offline for writes)
          {
            urlPattern: /\/api\//,
            handler: "NetworkOnly",
          },
        ],
      },
      manifest: {
        name: "ALIS Attendance",
        short_name: "ALIS",
        description: "ALIS offline attendance marking for faculty",
        theme_color: "#1D9E75",
        background_color: "#0f172a",
        display: "standalone",
        orientation: "portrait",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
        ],
      },
    }),
  ],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
