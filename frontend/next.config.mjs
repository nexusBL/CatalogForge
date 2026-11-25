/** @type {import('next').NextConfig} */
const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/catalogue-assets/:path*",
        destination: `${API_URL}/catalogue-assets/:path*`,
      },
    ];
  },
  webpack: (config, { dev }) => {
    if (dev) {
      // Console Ninja injects webpack buildHook; PackFileCacheStrategy then
      // spins on a Windows path-case mismatch and `next dev` never becomes Ready.
      config.cache = { type: "memory" };
    }
    return config;
  },
};

export default nextConfig;
