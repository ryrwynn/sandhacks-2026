import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import NavBar from "@/src/components/NavBar";
import { SavedProvider } from "@/src/lib/saved";

const inter = Inter({ subsets: ["latin"], variable: "--font" });

export const metadata: Metadata = { title: "SandHacks · San Diego rent tracker", description: "Track asking rents across San Diego." };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <SavedProvider>
          <NavBar />
          <main>{children}</main>
        </SavedProvider>
      </body>
    </html>
  );
}
