import legacy from '@vitejs/plugin-legacy';
import { defineConfig } from 'vite';

export default defineConfig({
    root: 'src',
    build: {
        outDir: '../dist',
        emptyOutDir: true,
        rollupOptions: {
            input: {
                main: 'src/index.html',
                developer: 'src/developer.html',
            },
        },
    },
    plugins: [
        legacy({
            targets: ['defaults', 'not IE 11'],
        }),
    ],
    server: {
        host: '0.0.0.0',
        port: 3000,
    },
});
