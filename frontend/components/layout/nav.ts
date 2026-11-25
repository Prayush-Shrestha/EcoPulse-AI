import {
  BarChart3,
  LayoutDashboard,
  Lightbulb,
  Settings,
  TrendingUp,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  subtitle: string;
  icon: LucideIcon;
  /** Exact-match only (the overview route). */
  exact?: boolean;
}

export const navItems: NavItem[] = [
  {
    href: "/",
    label: "Overview",
    subtitle: "Energy intelligence at a glance",
    icon: LayoutDashboard,
    exact: true,
  },
  {
    href: "/analytics",
    label: "Energy Analytics",
    subtitle: "Consumption trends, patterns and history",
    icon: BarChart3,
  },
  {
    href: "/forecasting",
    label: "Forecasting",
    subtitle: "Model-generated demand forecasts",
    icon: TrendingUp,
  },
  {
    href: "/anomalies",
    label: "Anomaly Monitoring",
    subtitle: "Detected deviations in consumption",
    icon: TriangleAlert,
  },
  {
    href: "/insights",
    label: "Smart Insights",
    subtitle: "Rule-based observations from your data",
    icon: Lightbulb,
  },
  {
    href: "/settings",
    label: "Settings",
    subtitle: "Connection, models and dataset status",
    icon: Settings,
  },
];

export function findNavItem(pathname: string): NavItem {
  const match = navItems.find((item) =>
    item.exact ? pathname === item.href : pathname.startsWith(item.href),
  );
  return match ?? navItems[0];
}
