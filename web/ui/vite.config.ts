import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The controller serves the built assets from STATIC_DIR at the web root.
// Relative base keeps asset URLs working regardless of the mount path.
// In dev, `npm run dev` proxies /api to a locally-running app.py on :8080.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    proxy: {
      "/api": "http://localhost:8080",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
