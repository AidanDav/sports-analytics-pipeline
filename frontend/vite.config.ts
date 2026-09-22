import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Listen on all interfaces so Docker can forward the port
    host: "0.0.0.0",
    port: 5173,
    // Docker on Windows doesn't forward file change events into the
    // container, so poll instead or HMR silently stops working
    watch: {
      usePolling: true,
    },
  },
})
