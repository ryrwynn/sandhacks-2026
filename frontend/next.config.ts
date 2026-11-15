import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  // Mastra (the /advisor/chat agent) runs on the Node server, unbundled (docs/reference/mastra.md).
  serverExternalPackages: ["@mastra/*"],
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // Local runs without Caddy: send /api/* to FastAPI with the prefix stripped.
  // In production Caddy routes /api/* before it reaches Next.js, so this never fires there.
  async rewrites() {
    const api = process.env.API_INTERNAL_URL || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
};

export default nextConfig;
