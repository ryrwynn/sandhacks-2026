import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Suspense } from "react";
import SiteNav from "@/components/SiteNav";
import { MockBanner } from "@/components/ui";
import { SavedProvider } from "@/lib/saved";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "RentOrKnot",
  description: "Save apartments you like and watch their asking rent over time in San Diego.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col bg-bg font-sans text-ink">
        <SavedProvider>
          <Suspense fallback={<div className="h-14 bg-surface" />}><SiteNav /></Suspense>
          <MockBanner />
          <div className="mx-auto w-full max-w-6xl flex-1 overflow-x-clip px-4 pb-24 pt-5 md:pb-12">{children}</div>
        </SavedProvider>
      </body>
    </html>
  );
}
