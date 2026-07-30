import path from "node:path";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants.js";

/** @type {import('next').NextConfig} */
const baseConfig = {
  ...(process.env.NEXT_DIST_DIR ? { distDir: process.env.NEXT_DIST_DIR } : {}),
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "live.staticflickr.com" },
      { protocol: "https", hostname: "upload.wikimedia.org" },
    ],
  },
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
    images: {
      dangerouslyAllowLocalIP: true,
      remotePatterns: [
        ...baseConfig.images.remotePatterns,
        { protocol: "http", hostname: "127.0.0.1", port: "4010" },
      ],
    },
    webpack(config) {
      config.resolve.alias["./favoriteContinuation"] = continuationObserver;
      config.resolve.alias["../../components/audio/favoriteContinuation"] = continuationObserver;
      return config;
    },
  };
}
