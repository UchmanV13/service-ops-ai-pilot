import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// Two builds from one codebase:
//  - default ("live"): talks to the Flask API, React bundled.
//  - "replay": single self-contained file for the hosted page; React comes from
//    the CDN as UMD globals and the evaluation data is inlined.
export default defineConfig(({ mode }) => {
  const replay = mode === "replay";
  return {
    define: { __MODE__: JSON.stringify(replay ? "replay" : "live") },
    esbuild: { jsxFactory: "React.createElement", jsxFragment: "React.Fragment" },
    server: { proxy: { "/api": "http://localhost:5000" } },
    plugins: replay ? [viteSingleFile()] : [],
    build: replay
      ? {
          outDir: "dist-replay",
          rollupOptions: {
            external: ["react", "react-dom", "react-dom/client"],
            output: { format: "iife", globals: { react: "React", "react-dom": "ReactDOM", "react-dom/client": "ReactDOM" } },
          },
        }
      : { outDir: "dist" },
  };
});
