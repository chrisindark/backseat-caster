import { MediaPlaybackCoordinator } from "@/components/MediaPlaybackCoordinator";
import { Theme } from "@radix-ui/themes";
import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "BackseatCaster - AI Gaming Clip Engine",
  description: "Browse YouTube gameplay VODs, download highlights, and generate AI-narrated short-form clips.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`dark ${inter.variable}`}>
      <body className="bg-[#090a0f] text-slate-100 antialiased overflow-x-clip selection:bg-rose-500 selection:text-white">
        <Theme appearance="dark" accentColor="crimson" grayColor="slate" radius="large">
          <MediaPlaybackCoordinator />
          {children}
        </Theme>
      </body>
    </html>
  );
}