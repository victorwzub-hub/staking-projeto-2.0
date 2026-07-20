import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  transpilePackages: ["@pharma/contracts"],
  experimental: {
    cpus: 2,
  },
};

export default nextConfig;
