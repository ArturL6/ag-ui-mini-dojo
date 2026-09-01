import type { NextConfig } from "next";

const backend = process.env.AGENT_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      { source: "/api/agent", destination: `${backend}/agent` },
      { source: "/api/health", destination: `${backend}/health` },
    ];
  },
};

export default nextConfig;
