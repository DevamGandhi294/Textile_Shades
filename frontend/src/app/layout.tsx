import type { Metadata, Viewport } from "next";
import { Figtree } from "next/font/google";
import "./globals.css";

const appFont = Figtree({
  variable: "--font-app",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "TextileBorder OutlineTool",
  description: "Turn a photo of a sketch into clean lines and files for embroidery, CorelDRAW and CAD.",
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${appFont.variable} h-full antialiased`}>
      <body className="min-h-full bg-white text-ink">{children}</body>
    </html>
  );
}
