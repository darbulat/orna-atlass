import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";

export default defineConfig([
  ...nextVitals,
  {
    // React Compiler is not enabled in this application. Keep the runtime
    // hooks rules while avoiding compiler-only rewrites during the security
    // upgrade from Next 14.
    rules: {
      "react-hooks/error-boundaries": "off",
      "react-hooks/immutability": "off",
      "react-hooks/preserve-manual-memoization": "off",
      "react-hooks/set-state-in-effect": "off",
    },
  },
  globalIgnores([
    ".next*/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "node_modules*/**",
    "playwright-report/**",
    "public/cesium/**",
    "test-results/**",
  ]),
]);
