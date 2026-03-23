import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-space)", "ui-sans-serif", "system-ui"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"]
      },
      colors: {
        base: "#0f172a",
        panel: "#131b2a",
        panelSoft: "#182238",
        border: "#263245",
        neon: "#00f0ff",
        neonSoft: "#6ef3ff",
        neonMagenta: "#ff3d81",
        accent: "#a855f7",
        success: "#00ff85",
        danger: "#ff3b3b",
        warn: "#facc15"
      },
      boxShadow: {
        glow: "0 0 18px rgba(0, 240, 255, 0.25)",
        glowSoft: "0 0 12px rgba(110, 243, 255, 0.18)",
        glowMagenta: "0 0 16px rgba(255, 61, 129, 0.22)"
      }
    }
  },
  plugins: []
};

export default config;
