import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("http://localhost:3000"),
  title: {
    default: "EcoPulse AI - Local energy intelligence",
    template: "%s | EcoPulse AI",
  },
  description:
    "A local-first platform for energy consumption monitoring, forecasting, and anomaly detection, built on real public datasets.",
  applicationName: "EcoPulse AI",
  keywords: [
    "energy analytics",
    "time series forecasting",
    "anomaly detection",
    "data engineering",
    "FastAPI",
    "Next.js",
  ],
  openGraph: {
    title: "EcoPulse AI - Local energy intelligence",
    description:
      "Energy consumption monitoring, forecasting, and anomaly detection. Local-first, built on real data.",
    type: "website",
    locale: "en_GB",
  },
};

export const viewport: Viewport = {
  themeColor: "#101713",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable}`}
    >
      <body className="min-h-screen font-sans antialiased">{children}</body>
    </html>
  );
}
