import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

function trimTrailingSlash(value) {
  return value.replace(/\/$/, "");
}

function toWebSocketTarget(apiTarget) {
  if (apiTarget.startsWith("https://")) {
    return `wss://${apiTarget.slice("https://".length)}`;
  }
  if (apiTarget.startsWith("http://")) {
    return `ws://${apiTarget.slice("http://".length)}`;
  }
  return apiTarget;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = trimTrailingSlash(env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000");
  const wsTarget = trimTrailingSlash(env.VITE_WS_PROXY_TARGET ?? toWebSocketTarget(apiTarget));

  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, "")
        },
        "/ws": {
          target: wsTarget,
          ws: true,
          changeOrigin: true
        }
      }
    }
  };
});
