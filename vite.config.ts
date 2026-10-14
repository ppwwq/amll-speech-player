import wasm from "vite-plugin-wasm";
import compression from 'vite-plugin-compression';

export default {
  base: "./", // Works at a GitHub Pages repository subpath and any static host.
  build: {
    target: ["esnext"],
  },
  plugins: [
    wasm(),
    compression({
      algorithm: 'gzip',
      ext: '.gz',
      threshold: 1024,
      deleteOriginFile: false,
    })
  ],
};