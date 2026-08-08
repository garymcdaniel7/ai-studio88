import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  typescript: {
    // Prevents TypeScript differences between local and Vercel from blocking deploys.
    // TypeScript is validated in CI via `tsc --noEmit`.
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
