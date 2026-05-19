/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    // ASR pipeline 對 4-5 分鐘音檔可耗 60-120s（resample + VAD + ASR + diarization）。
    // Next.js dev rewrite proxy 預設 30s 超時直接 ECONNRESET，frontend 收到 plain
    // "Internal Server Error" 500 而非 backend JSON envelope。提升至 10 分鐘以對齊
    // backend ASR_REQUEST_TIMEOUT_SEC=1200 與 client.ts DEFAULT_TIMEOUT_MS=1_200_000。
    proxyTimeout: 600_000,
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.BACKEND_BASE_URL || 'http://localhost:8000'}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
