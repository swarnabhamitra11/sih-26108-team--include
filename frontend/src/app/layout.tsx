import "./globals.css";
import React from "react";

export const metadata = {
  title: "Standards Navigator - Indian Standards (BIS) Intelligence",
  description: "Search, verify citations, and explore Indian Standards (BIS)",
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
