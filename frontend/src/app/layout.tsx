import type { Metadata, Viewport } from "next";
import { Geist, Nunito, DM_Sans, Atkinson_Hyperlegible } from "next/font/google";
import { THEME_INIT_SCRIPT } from "@/lib/theme";
import "./globals.css";
import { Suspense } from "react";
import SiteNav from "@/components/SiteNav";
import { MockBanner } from "@/components/ui";
import SiteFooter from "@/components/SiteFooter";
import { SavedProvider } from "@/lib/saved";
import { SidebarProvider, ToolsSidebar } from "@/components/ToolsSidebar";

// One family per theme (THEMES in lib/theme.ts); the active theme picks its variable in globals.css.
const geist = Geist({ variable: "--font-geist", subsets: ["latin"], display: "swap" });
const nunito = Nunito({ variable: "--font-nunito", subsets: ["latin"], display: "swap" });
const dmSans = DM_Sans({ variable: "--font-dm-sans", subsets: ["latin"], display: "swap" });
const atkinson = Atkinson_Hyperlegible({ variable: "--font-atkinson", weight: ["400", "700"], subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: "RentOrKnot",
  description: "Save apartments you like and watch their asking rent over time in San Diego.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning className={`${geist.variable} ${nunito.variable} ${dmSans.variable} ${atkinson.variable} h-full antialiased`}>
      <head><script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} /></head>
      <body className="flex min-h-full flex-col bg-bg font-sans text-ink">
        <SavedProvider>
        <SidebarProvider>
          <Suspense fallback={<div className="h-14 bg-surface" />}><SiteNav /></Suspense>
          <MockBanner />
          <div className="flex w-full flex-1">
            <Suspense fallback={<div className="hidden w-60 shrink-0 md:block" />}><ToolsSidebar /></Suspense>
            <div className="min-w-0 flex-1 overflow-x-clip px-4 pb-6 pt-5 md:pb-8"><div className="mx-auto w-full max-w-6xl">{children}</div></div>
          </div>
          <SiteFooter />
        </SidebarProvider>
        </SavedProvider>
      </body>
    </html>
  );
}
