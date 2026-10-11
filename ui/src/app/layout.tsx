import type { Metadata } from "next";
import { Theme } from "@radix-ui/themes";
import "./globals.css";

export const metadata: Metadata = {
  title: "BackseatCaster - AI Gaming Clip Engine",
  description: "Browse YouTube gameplay VODs, download highlights, and generate AI-narrated short-form clips.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#090a0f] text-slate-100 antialiased selection:bg-rose-500 selection:text-white">
        <Theme appearance="dark" accentColor="crimson" grayColor="slate" radius="large">
          {children}
        </Theme>
      </body>
    </html>
  );
}
