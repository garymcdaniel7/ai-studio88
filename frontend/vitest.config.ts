import path from "node:path";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "node",
    globals: true,
    include: ["src/**/*.test.ts", "src/**/*.test.tsx", "tests/**/*.test.ts", "tests/**/*.test.tsx"],
    exclude: ["node_modules", ".next", "e2e", "test-results", "playwright-report"],
  },
});
