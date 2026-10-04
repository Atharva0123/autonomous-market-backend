import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  outputFileTracingRoot: process.cwd(),
  agentRules: false,
  async headers() {
    return [{
      source: "/:path*",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
      ],
    }];
  },
  async rewrites() {
    // Server-side proxy keeps session cookies same-origin and API credentials
    // private. Set API_BACKEND_URL in the deployment host's server environment.
    const configuredBackend = process.env.API_BACKEND_URL;
    if (!configuredBackend) {
      // In a unified Vercel deployment, vercel.json handles the /api route.
      return [];
    }
    let backendUrl: URL;
    try {
      backendUrl = new URL(configuredBackend);
    } catch {
      throw new Error("API_BACKEND_URL must be an absolute backend URL.");
    }
    if (process.env.VERCEL && backendUrl.protocol !== "https:") {
      throw new Error("API_BACKEND_URL must use HTTPS on Vercel so session cookies stay protected in transit.");
    }
    const backend = configuredBackend.replace(/\/$/, "");
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
