import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ObTrac - RAG Observability",
  description: "Open Source RAG Observability & Evaluation Framework",
  // Favicon is auto-detected from src/app/icon.png (Next.js file convention)
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
