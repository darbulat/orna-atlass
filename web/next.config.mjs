import path from "node:path";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants.js";

/** @type {import('next').NextConfig} */
const baseConfig = {
  ...(process.env.NEXT_DIST_DIR ? { distDir: process.env.NEXT_DIST_DIR } : {}),
};

export default function nextConfig(phase) {
  if (phase !== PHASE_DEVELOPMENT_SERVER || process.env.ORNA_E2E_PROBES !== "1") {
    return baseConfig;
  }
  const continuationObserver = path.resolve(
    process.cwd(),
    "components/audio/favoriteContinuation.e2e.ts",
  );
  return {
    ...baseConfig,
    webpack(config) {
      config.resolve.alias["./favoriteContinuation"] = continuationObserver;
      config.resolve.alias["../../components/audio/favoriteContinuation"] = continuationObserver;
      return config;
    },
  };
}
