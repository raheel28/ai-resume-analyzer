import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Forward /api calls to FastAPI so the browser sees one origin in dev.
    proxy: { "/api": "http://localhost:8000" },
  },
});
