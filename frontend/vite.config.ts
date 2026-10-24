import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks: {
          antd: ["antd"],
          markdown: ["react-markdown", "remark-gfm", "rehype-sanitize"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1",
      "/mcp": "http://127.0.0.1",
    },
  },
  test: {
    environment: "jsdom",
  },
});
