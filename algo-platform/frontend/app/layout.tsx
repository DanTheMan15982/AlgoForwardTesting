import type { Metadata } from "next";
import Link from "next/link";
import { Space_Grotesk, Space_Mono } from "next/font/google";
import { ThemeProvider } from "@/components/ThemeProvider";
import { SessionIndicator } from "@/components/SessionIndicator";
import "./globals.css";

const spaceGrotesk = Space_Grotesk({ subsets: ["latin"], variable: "--font-space" });
const spaceMono = Space_Mono({ subsets: ["latin"], weight: ["400", "700"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "Algo Forward Testing",
  description: "Local forward testing dashboard"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${spaceGrotesk.variable} ${spaceMono.variable} font-sans grid-ambient min-h-screen`}>
        <ThemeProvider>
          <div className="px-4 py-5 sm:px-6 lg:px-10">
            <header className="mb-8 flex flex-wrap items-center justify-between gap-6">
              <div>
                <p className="text-xs uppercase tracking-[0.35em] text-neonSoft">
                  Forward Test
                </p>
                <h1 className="text-2xl md:text-3xl font-semibold text-white">
                  Algo Forward Testing Platform
                </h1>
                <p className="mt-2 text-xs text-slate-500">
                  Live sim • Local-only • No auth
                </p>
                <nav className="mt-4 flex flex-wrap gap-2 text-xs uppercase tracking-[0.25em] text-slate-400">
                  <Link
                    href="/"
                    className="rounded-full border border-border/70 bg-panel/50 px-3 py-1 transition-colors hover:border-neon/60 hover:text-white"
                  >
                    Dashboard
                  </Link>
                  <Link
                    href="/market-data"
                    className="rounded-full border border-border/70 bg-panel/50 px-3 py-1 transition-colors hover:border-neon/60 hover:text-white"
                  >
                    Market Data
                  </Link>
                </nav>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
                <SessionIndicator />
                <div className="rounded-full border border-border/70 bg-panel/60 px-3 py-1 uppercase tracking-[0.25em] text-neon">
                  Terminal
                </div>
              </div>
            </header>
            {children}
          </div>
        </ThemeProvider>
      </body>
    </html>
  );
}
