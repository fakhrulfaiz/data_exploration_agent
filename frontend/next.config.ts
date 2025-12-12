import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Turbopack configuration for fast refresh
  turbopack: {},

  // Webpack configuration for hot reload in Docker
  webpack: (config, { isServer }) => {
    // Enable polling for file watching in Docker
    if (!isServer) {
      config.watchOptions = {
        poll: 1000, // Check for changes every second
        aggregateTimeout: 300, // Delay before rebuilding
        ignored: /node_modules/,
      };
    }
    return config;
  },
};

export default nextConfig;
