import type { NextConfig } from "next";

/** The simulator app (see lib/simulator.ts); its routes are served from this domain. */
const SIMULATOR_URL = process.env.SIMULATOR_URL ?? "https://bless-sim.vercel.app";

/** Paths that belong to the simulator: its pages, its API, its assets and the Cerchio images. */
const SIMULATOR_PATHS = ["/gioco/bot", "/gioco/stanza/:code", "/gioco/analisi", "/gioco/tutorial", "/api/game", "/sim-static/:path*", "/cerchio/:path*"];

const nextConfig: NextConfig = {
  images: {
    formats: ["image/avif", "image/webp"],
  },
  rewrites: async () => SIMULATOR_PATHS.map((path) => ({ source: path, destination: `${SIMULATOR_URL}${path}` })),
};

export default nextConfig;
