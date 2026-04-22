import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { nodePolyfills } from "vite-plugin-node-polyfills";

export default defineConfig({
  plugins: [
    react(),
    // Privy + Solana libs (bn.js, @solana/web3.js, etc.) expect Node's
    // `Buffer`, `process`, and `global` to exist. Vite externalizes them by
    // default; this plugin injects browser-safe shims.
    nodePolyfills({
      globals: { Buffer: true, global: true, process: true },
    }),
  ],
  server: {
    host: "0.0.0.0",
    port: 5173,
    hmr: {
      host: "localhost",
      port: 5173,
    },
    // Docker + Windows (WSL2) doesn't forward host fs events into the
    // container reliably. Polling is slower but catches every edit.
    watch: {
      usePolling: true,
      interval: 500,
    },
  },
});
