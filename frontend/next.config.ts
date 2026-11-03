import type { NextConfig } from "next";

const backend = process.env.MADIRA_BACKEND_URL || "http://127.0.0.1:8123";

const nextConfig: NextConfig = {
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
