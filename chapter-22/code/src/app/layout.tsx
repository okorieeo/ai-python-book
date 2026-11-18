import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { ui } from "@/lib/ui";

export const metadata: Metadata = {
  title: "AI Chat Admin",
  description: "Dashboards and admin tools for the AI Chat SaaS",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className={ui.page}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
