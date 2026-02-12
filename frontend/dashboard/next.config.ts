import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    // In dev mode, proxy /api → FastAPI backend so CORS isn't needed.
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${apiUrl}/:path*` },
    ];
  },
  // Allow self-signed certs for the local backend proxy
  serverExternalPackages: [],
};

export default nextConfig;
