import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  root: "client",
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/agent": "http://localhost:8765",
      "/health": "http://localhost:8765",
    },
  },
});
