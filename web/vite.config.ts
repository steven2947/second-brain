/** 仅暴露web目录，API走同源代理；不把项目提示词和私有运行数据提供给浏览器。 */
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1', port: 5173, strictPort: true,
    fs: { strict: true, allow: [fileURLToPath(new URL('.', import.meta.url))] },
    proxy: {
      '/api': { target: 'http://127.0.0.1:8019', changeOrigin: false },
      '/health': { target: 'http://127.0.0.1:8019', changeOrigin: false },
    },
  },
  build: { sourcemap: false },
  test: { environment: 'node', include: ['src/**/*.test.ts', 'src/**/*.test.tsx'] },
});
