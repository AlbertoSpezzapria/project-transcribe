import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In sviluppo l'API è servita sotto /api dalla stessa origine del frontend:
// i cookie di sessione restano first-party e non serve CORS.
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8010";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": new URL("./src", import.meta.url).pathname } },
  server: {
    port: 5173,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
});
