import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import { AppProvider } from "@/lib/app-context";
import { DashboardLayout } from "@/components/layout/DashboardLayout";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("http://localhost:3000"),
  title: {
    default: "EcoPulse AI - Energy intelligence dashboard",
    template: "%s | EcoPulse AI",
  },
  description:
    "Energy consumption monitoring, forecasting and anomaly detection dashboard built on real public data and locally trained models.",
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
    title: "EcoPulse AI - Energy intelligence dashboard",
    description:
      "Energy consumption monitoring, forecasting and anomaly detection. Local-first, built on real data.",
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
      <body className="min-h-screen font-sans antialiased">
        <AppProvider>
          <DashboardLayout>{children}</DashboardLayout>
        </AppProvider>
      </body>
    </html>
  );
}
