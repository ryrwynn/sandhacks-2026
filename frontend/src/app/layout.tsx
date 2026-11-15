import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Suspense } from "react";
import ModeNav from "@/components/ModeNav";
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
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-slate-50 text-slate-900">
        <SavedProvider>
          <Suspense fallback={<div className="h-14 border-b border-slate-200 bg-white" />}><ModeNav /></Suspense>
          <MockBanner />
          <div className="mx-auto w-full max-w-5xl flex-1 px-4 py-4">{children}</div>
        </SavedProvider>
      </body>
    </html>
  );
}
