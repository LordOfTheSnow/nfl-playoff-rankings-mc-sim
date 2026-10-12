import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./frontend/tests/setup.js"],
    include: ["frontend/tests/**/*.test.js"],
    globals: true,
    // Property-based tests: minimum 100 iterations
    testTimeout: 30000,
  },
});
