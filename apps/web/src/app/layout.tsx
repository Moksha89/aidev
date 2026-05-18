import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Developer",
  description: "Self-hosted AI developer platform with frontend-first approvals.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background text-foreground">
        {children}
      </body>
    </html>
  );
}
