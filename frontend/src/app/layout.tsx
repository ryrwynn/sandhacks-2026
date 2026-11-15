import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Suspense } from "react";
import SiteNav from "@/components/SiteNav";
import { MockBanner } from "@/components/ui";
import { SavedProvider } from "@/lib/saved";
import { SidebarProvider, ToolsSidebar } from "@/components/ToolsSidebar";

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
        <SidebarProvider>
          <Suspense fallback={<div className="h-14 bg-surface" />}><SiteNav /></Suspense>
          <MockBanner />
          <div className="mx-auto flex w-full max-w-7xl flex-1">
            <Suspense fallback={<div className="hidden w-60 shrink-0 md:block" />}><ToolsSidebar /></Suspense>
            <div className="min-w-0 flex-1 overflow-x-clip px-4 pb-24 pt-5 md:pb-12">{children}</div>
          </div>
        </SidebarProvider>
        </SavedProvider>
      </body>
    </html>
  );
}
