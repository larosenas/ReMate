import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// En desarrollo, las llamadas a /api se redirigen al Flask local (ADR 0004).
// En producción, Flask sirve el contenido de dist/ y la API en el mismo puerto.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Sin changeOrigin (la forma corta lo activa): Flask tiene que ver la misma dirección que
      // el navegador para aceptar los cambios (backend/app/origen.py).
      '/api': { target: 'http://127.0.0.1:5000', changeOrigin: false },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/pruebas/configuracion.js'],
    // Cobertura con `npm run test:cobertura`. Los mínimos dejan margen sobre la cobertura actual y
    // evitan que entre lógica nueva sin pruebas.
    coverage: {
      provider: 'v8',
      include: ['src/**'],
      exclude: ['src/pruebas/**', 'src/**/*.test.{js,jsx}', 'src/main.jsx'],
      reporter: ['text-summary', 'text'],
      thresholds: { statements: 80, branches: 75, functions: 80, lines: 80 },
    },
  },
})
