import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const configDirectory = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: path.join(configDirectory, "src", "renderer"),
  publicDir: path.join(configDirectory, "src", "renderer", "public"),
  base: "./",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: path.join(configDirectory, "dist", "renderer"),
    emptyOutDir: true,
  },
});
