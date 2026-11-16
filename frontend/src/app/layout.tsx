import type { Metadata } from "next";
import { Inter_Tight } from "next/font/google";
import { AppShell } from "@/components/AppShell";
import { ThemeSync } from "@/components/ThemeSync";
import { Providers } from "@/app/providers";
import "./globals.css";

const interTight = Inter_Tight({
  variable: "--font-inter-tight",
  subsets: ["latin"],
  weight: ["300", "400"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Madira — Maison Madira beverage program",
  description: "Head Sommelier agent for pairings, lists, inventory, training, and supplier tastings.",
};

const themeBoot = `(function(){try{var d=window.matchMedia("(prefers-color-scheme: dark)").matches;document.documentElement.classList.toggle("dark",d);}catch(e){}})();`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${interTight.variable} h-full`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBoot }} />
      </head>
      <body className={`${interTight.className} min-h-full`}>
        <ThemeSync />
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
