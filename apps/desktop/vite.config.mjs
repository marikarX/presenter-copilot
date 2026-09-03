import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const configDirectory = path.dirname(fileURLToPath(import.meta.url));
const devCspPlugin = {
  name: "presenter-copilot-dev-csp",
  transformIndexHtml: {
    order: "post",
    handler(html, context) {
      if (!context.server) return html;
      return html.replace(
        "connect-src 'self'",
        "connect-src 'self' http://127.0.0.1:5173 ws://127.0.0.1:5173",
      );
    },
  },
};

export default defineConfig({
  root: path.join(configDirectory, "src"),
  publicDir: path.join(configDirectory, "src", "renderer", "public"),
  base: "./",
  plugins: [react(), devCspPlugin],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: path.join(configDirectory, "dist", "renderer"),
    emptyOutDir: true,
    rollupOptions: {
      input: [
        path.join(configDirectory, "src", "index.html"),
        path.join(configDirectory, "src", "hud", "index.html"),
      ],
    },
  },
});
