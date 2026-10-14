import { defineConfig } from 'vite';
// Direct browser requests preserve the server's Origin and CSRF checks.
export default defineConfig({ server: { host: '127.0.0.1', port: 5173, strictPort: true } });
