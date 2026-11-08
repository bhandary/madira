import type { NextConfig } from "next";

const backend = process.env.MADIRA_BACKEND_URL || "http://127.0.0.1:8123";

const nextConfig: NextConfig = {
  // Playwright and the doctor use 127.0.0.1. Dev assets are otherwise limited to localhost.
  allowedDevOrigins: ["127.0.0.1"],
  // The account menu sits at the bottom of the sidebar. Keep the dev badge off it.
  devIndicators: { position: "bottom-right" },
  images: {
    // Profile photos are loaded by the browser (unoptimized). No query-string pin:
    // Google appends a size parameter.
    remotePatterns: [
      { protocol: "https", hostname: "**.googleusercontent.com" },
      { protocol: "https", hostname: "**.ggpht.com" },
    ],
  },
  async rewrites() {
    return [{ source: "/madira-api/:path*", destination: `${backend}/:path*` }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
