import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = {
  target: "http://127.0.0.1:8000",
  changeOrigin: true,
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": backend,
      // Proxied so the relative "API Docs" link works in dev too — in
      // production FastAPI serves the SPA and these from the same origin.
      "/docs": backend,
      "/redoc": backend,
      "/openapi.json": backend,
    },
  },
});
