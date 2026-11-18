import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produces .next/standalone: a small self-contained server (server.js) that
  // includes only the node_modules it needs. Required by frontend/Dockerfile.
  output: "standalone",
};

export default nextConfig;
