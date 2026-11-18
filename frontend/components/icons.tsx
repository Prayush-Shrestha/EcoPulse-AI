import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const iconAttributes = {
  "aria-hidden": true,
  focusable: false,
  fill: "none",
  viewBox: "0 0 24 24",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function BrandMark(props: IconProps) {
  return (
    <svg {...iconAttributes} {...props}>
      <path d="M3 15h4L9.5 8l5 12L17 11l2 4h2" />
    </svg>
  );
}

export function PulseIcon(props: IconProps) {
  return (
    <svg {...iconAttributes} {...props}>
      <path d="M3 12h4l2.5-7 4.5 14 3-7h4" />
    </svg>
  );
}

export function ActivityIcon(props: IconProps) {
  return (
    <svg {...iconAttributes} {...props}>
      <path d="M3 12h3.5l2.5-6 4.5 12 2.5-6H21" />
    </svg>
  );
}

export function TrendIcon(props: IconProps) {
  return (
    <svg {...iconAttributes} {...props}>
      <path d="m3 17 6-6 4 4 8-8" />
      <path d="M15 7h6v6" />
    </svg>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <svg {...iconAttributes} {...props}>
      <path d="M12 3 2.8 19.5h18.4L12 3Z" />
      <path d="M12 9v4.5" />
      <path d="M12 16.75h.01" />
    </svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <svg {...iconAttributes} {...props}>
      <path d="m20 6-11 11-5-5" />
    </svg>
  );
}

export function MinusIcon(props: IconProps) {
  return (
    <svg {...iconAttributes} {...props}>
      <path d="M5 12h14" />
    </svg>
  );
}

export function ArrowUpRight(props: IconProps) {
  return (
    <svg {...iconAttributes} {...props}>
      <path d="M7 17 17 7" />
      <path d="M8 7h9v9" />
    </svg>
  );
}

export function ArrowDown(props: IconProps) {
  return (
    <svg {...iconAttributes} {...props}>
      <path d="M12 5v14" />
      <path d="m18 13-6 6-6-6" />
    </svg>
  );
}

export function RefreshIcon(props: IconProps) {
  return (
    <svg {...iconAttributes} {...props}>
      <path d="M20 11a8 8 0 1 0-2.34 6.34" />
      <path d="M20 4v7h-7" />
    </svg>
  );
}

export function ShieldIcon(props: IconProps) {
  return (
    <svg {...iconAttributes} {...props}>
      <path d="M12 3 4.5 6v5.5c0 4.4 3.1 8.1 7.5 9.5 4.4-1.4 7.5-5.1 7.5-9.5V6L12 3Z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

export function InfoIcon(props: IconProps) {
  return (
    <svg {...iconAttributes} {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <path d="M12 7.75h.01" />
    </svg>
  );
}
