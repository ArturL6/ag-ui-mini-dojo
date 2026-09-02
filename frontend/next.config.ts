import type { NextConfig } from "next";

const backend = process.env.AGENT_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      { source: "/api/agent", destination: `${backend}/agent` },
      { source: "/api/langgraph", destination: `${backend}/agent/langgraph` },
      { source: "/api/langgraph-functional", destination: `${backend}/agent/langgraph-functional` },
      { source: "/api/health", destination: `${backend}/health` },
    ];
  },
};

export default nextConfig;
