const apiUrl = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export const siteConfig = {
  name: "EcoPulse AI",
  version: "0.1.0",
  apiUrl,
  apiDocsUrl: `${apiUrl}/docs`,
  apiHealthUrl: `${apiUrl}/api/v1/health`,
  nav: [
    { label: "Capabilities", href: "#capabilities" },
    { label: "Architecture", href: "#architecture" },
    { label: "Data", href: "#data" },
    { label: "Roadmap", href: "#roadmap" },
  ],
} as const;
