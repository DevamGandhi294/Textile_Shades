import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Magic Outline",
  description: "Clean, closed outline borders from a sketch, photo or prompt.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
