import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The frontend tier only talks to the backend tier over HTTP: /api is proxied to FastAPI.
// Override the backend address with BACKEND_URL=http://host:port npm run dev
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
const proxy = { "/api": { target: backend, changeOrigin: true } };

export default defineConfig({ plugins: [react(), tailwindcss()], server: { port: 5173, proxy }, preview: { port: 4173, proxy } });
