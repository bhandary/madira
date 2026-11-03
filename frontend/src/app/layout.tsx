import type { Metadata } from "next";
import { Fraunces, Outfit } from "next/font/google";
import { AppShell } from "@/components/AppShell";
import { Providers } from "@/app/providers";
import "./globals.css";

const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin"],
});

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Madira — Maison Madira beverage program",
  description: "Head Sommelier agent for pairings, lists, inventory, training, and supplier tastings.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${outfit.variable} ${fraunces.variable} h-full`}>
      <body className="min-h-full">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
