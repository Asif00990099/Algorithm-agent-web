/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // standalone output is for the Docker image; Vercel uses its own build output
  output: process.env.VERCEL ? undefined : 'standalone',
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'assets.coingecko.com' },
      { protocol: 'https', hostname: 'coin-images.coingecko.com' },
    ],
  },
  async rewrites() {
    const api = process.env.API_INTERNAL_URL || 'http://localhost:8000';
    return [{ source: '/api/backend/:path*', destination: `${api}/api/:path*` }];
  },
};
export default nextConfig;
